"""Load Chicago business licenses into Supabase.

Source: City of Chicago, Business Licenses (data.cityofchicago.org, dataset r5kz-chrr).
Updated daily by the city.

What it loads: license records for retail food places (cafés, bakeries,
restaurants) and limited business licenses (bookstores and other shops)
that expire on or after 2022-01-01. That covers current businesses plus
ones whose latest record is a few years stale (the city's renewals can lag
or have gaps; Myopic Books' last record expired in 2024 though it's open),
without pulling all 1M+ rows since 2002.

Run from the repo root:
    python ingestion/load_business_licenses.py
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

import psycopg
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL = "https://data.cityofchicago.org/resource/r5kz-chrr.json"
DATABASE_URL = os.environ["DATABASE_URL"]  # from your Codespaces secret
# Smaller pages: the city's server can drop very large filtered requests
PAGE_SIZE = 10000

# Which licenses to keep. Values are the city's license_description text.
LICENSE_TYPES = ("Retail Food Establishment", "Limited Business License")
# Reaches back a few years because license records can lag behind reality
EXPIRES_ON_OR_AFTER = "2022-01-01"

# Fields this script depends on. If the city renames one, we stop early.
REQUIRED_FIELDS = {
    "license_id", "license_number", "doing_business_as_name", "address",
    "license_description", "license_status", "expiration_date",
    "latitude", "longitude",
}


def make_session():
    """An HTTP session that retries dropped connections and server errors.

    Waits 2s, 4s, 8s, 16s, 32s between tries (backoff_factor=2), so a brief
    hiccup on the city's side doesn't kill the whole load.
    """
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


SESSION = make_session()


def check_schema():
    """Fetch one row and make sure the fields we rely on still exist."""
    response = SESSION.get(URL, params={"$limit": 1}, timeout=60)
    response.raise_for_status()
    sample = response.json()[0]
    missing = REQUIRED_FIELDS - set(sample)
    if missing:
        print(f"The API is missing fields this script expects: {sorted(missing)}")
        print(f"Fields it actually has: {sorted(sample)}")
        sys.exit(1)
    print("Schema check passed")


def extract():
    """Page through the API and return every matching license record."""
    types = ", ".join(f"'{t}'" for t in LICENSE_TYPES)
    where = f"license_description in ({types}) and expiration_date >= '{EXPIRES_ON_OR_AFTER}'"
    rows, offset = [], 0
    while True:
        params = {"$where": where, "$order": "license_id", "$limit": PAGE_SIZE, "$offset": offset}
        response = SESSION.get(URL, params=params, timeout=120)
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        offset += PAGE_SIZE
        print(f"Fetched {len(rows)} rows so far")
    return rows


def save_raw_copy(rows):
    """Keep the untouched API response on disk (data/ is gitignored)."""
    out_dir = Path("data/raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"business_licenses_{date.today()}.json").write_text(json.dumps(rows))


def to_float(value):
    return float(value) if value else None


def to_date(value):
    # "2025-03-16T00:00:00.000" -> "2025-03-16"
    return value[:10] if value else None


def transform(rows):
    """Pick out the columns the dbt models use. The full record stays on disk."""
    return [
        {
            "license_id": r["license_id"],
            "license_number": r.get("license_number"),
            "account_number": r.get("account_number"),
            "legal_name": r.get("legal_name"),
            "doing_business_as_name": r.get("doing_business_as_name"),
            "address": r.get("address"),
            "zip_code": r.get("zip_code"),
            "license_description": r.get("license_description"),
            "business_activity": r.get("business_activity"),
            "application_type": r.get("application_type"),
            "license_start_date": to_date(r.get("license_start_date")),
            "expiration_date": to_date(r.get("expiration_date")),
            "license_status": r.get("license_status"),
            "license_status_change_date": to_date(r.get("license_status_change_date")),
            "latitude": to_float(r.get("latitude")),
            "longitude": to_float(r.get("longitude")),
        }
        for r in rows
    ]


CREATE_TABLE = """
create table if not exists raw_business_licenses (
    license_id                  text primary key,
    license_number              text,
    account_number              text,
    legal_name                  text,
    doing_business_as_name      text,
    address                     text,
    zip_code                    text,
    license_description         text,
    business_activity           text,
    application_type            text,
    license_start_date          date,
    expiration_date             date,
    license_status              text,
    license_status_change_date  date,
    latitude                    double precision,
    longitude                   double precision,
    loaded_at                   timestamptz default now()
);
"""

COLUMNS = [
    "license_id", "license_number", "account_number", "legal_name",
    "doing_business_as_name", "address", "zip_code", "license_description",
    "business_activity", "application_type", "license_start_date",
    "expiration_date", "license_status", "license_status_change_date",
    "latitude", "longitude",
]
UPDATABLE = [c for c in COLUMNS if c != "license_id"]

# Drops the full JSON copy that used to live in "raw". It was most of the
# table's size and pushed Supabase past its free 500 MB. CASCADE also drops
# the dbt views built on it; dbt build recreates them after the loaders run.
MIGRATE = "alter table raw_business_licenses drop column if exists raw cascade;"

# On a re-run, refresh every column except the key, so status changes
# (like a license being cancelled) are picked up. Rows are only rewritten when
# something changed: an UPDATE makes Postgres write a whole new copy of the
# row, so rewriting unchanged rows every day would waste space.
UPSERT = f"""
insert into raw_business_licenses ({", ".join(COLUMNS)})
values ({", ".join(f"%({c})s" for c in COLUMNS)})
on conflict (license_id) do update set
    {", ".join(f"{c} = excluded.{c}" for c in UPDATABLE)},
    loaded_at = now()
where ({", ".join(f"raw_business_licenses.{c}" for c in UPDATABLE)})
      is distinct from ({", ".join(f"excluded.{c}" for c in UPDATABLE)});
"""

def load(records):
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE)
            cur.execute(MIGRATE)
            cur.executemany(UPSERT, records)
            cur.execute("select count(*) from raw_business_licenses")
            print(f"Rows in raw_business_licenses: {cur.fetchone()[0]}")


def main():
    check_schema()
    rows = extract()
    if not rows:
        print("No rows matched the filter. Check LICENSE_TYPES and EXPIRES_ON_OR_AFTER.")
        sys.exit(1)
    save_raw_copy(rows)
    load(transform(rows))


if __name__ == "__main__":
    main()
