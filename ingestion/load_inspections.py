"""Load Chicago food inspections into Supabase.

Source: City of Chicago, Food Inspections (data.cityofchicago.org, dataset 4ijn-s7e5).

What it loads: every inspection since 2024-01-01, one row per inspection.
The full API response is saved to data/raw/ on disk (gitignored); the
database keeps only the typed columns, to stay within Supabase's free 500 MB.

Run from the repo root:
    python ingestion/load_inspections.py
"""
import json
import os
import time
from datetime import date
from pathlib import Path

import psycopg
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL = "https://data.cityofchicago.org/resource/4ijn-s7e5.json"
DATABASE_URL = os.environ["DATABASE_URL"]  # from your Codespaces / Actions secret
PAGE_SIZE = 10000
INSPECTED_ON_OR_AFTER = "2024-01-01"


def make_session():
    """An HTTP session that retries dropped connections and server errors."""
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


def get_json(params, timeout=120, attempts=5):
    """Download one page of results as JSON.

    The session above retries failures before a response starts. This also
    retries when the connection breaks partway through a download
    ("IncompleteRead" / ChunkedEncodingError), which the city's API does
    now and then on large pages. Waits 2s, 4s, 8s, 16s between tries.
    """
    for attempt in range(1, attempts + 1):
        try:
            response = SESSION.get(URL, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.JSONDecodeError,
        ) as error:
            if attempt == attempts:
                raise
            wait = 2 ** attempt
            print(f"Download failed ({type(error).__name__}); retrying in {wait}s "
                  f"(attempt {attempt + 1} of {attempts})")
            time.sleep(wait)


def extract():
    """Page through the API and return every inspection since the cutoff."""
    rows, offset = [], 0
    while True:
        params = {
            "$where": f"inspection_date >= '{INSPECTED_ON_OR_AFTER}'",
            "$order": "inspection_id",
            "$limit": PAGE_SIZE,
            "$offset": offset,
        }
        batch = get_json(params)
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
    (out_dir / f"inspections_{date.today()}.json").write_text(json.dumps(rows))


def to_float(value):
    return float(value) if value else None


def transform(rows):
    """Pick out the columns the dbt models use."""
    return [
        {
            "inspection_id": r["inspection_id"],
            "license_number": r.get("license_"),  # the city's field is named "license_"
            "dba_name": r.get("dba_name"),
            "aka_name": r.get("aka_name"),
            "facility_type": r.get("facility_type"),
            "risk": r.get("risk"),
            "address": r.get("address"),
            "zip": r.get("zip"),
            "inspection_date": (r.get("inspection_date") or "")[:10] or None,
            "inspection_type": r.get("inspection_type"),
            "results": r.get("results"),
            "violations": r.get("violations"),
            "latitude": to_float(r.get("latitude")),
            "longitude": to_float(r.get("longitude")),
        }
        for r in rows
    ]


CREATE_TABLE = """
create table if not exists raw_inspections (
    inspection_id   text primary key,
    license_number  text,
    dba_name        text,
    aka_name        text,
    facility_type   text,
    risk            text,
    address         text,
    zip             text,
    inspection_date date,
    inspection_type text,
    results         text,
    violations      text,
    latitude        double precision,
    longitude       double precision,
    loaded_at       timestamptz default now()
);
"""

# Brings an older table up to date: adds the new columns, and drops the full
# JSON copy that used to live in "raw" (it roughly doubled the table's size).
# CASCADE also drops the dbt staging views built on the old column; dbt build
# recreates them right after the loaders run.
MIGRATE = """
alter table raw_inspections add column if not exists license_number text;
alter table raw_inspections add column if not exists aka_name text;
alter table raw_inspections drop column if exists raw cascade;
"""

COLUMNS = [
    "inspection_id", "license_number", "dba_name", "aka_name", "facility_type",
    "risk", "address", "zip", "inspection_date", "inspection_type", "results",
    "violations", "latitude", "longitude",
]
UPDATABLE = [c for c in COLUMNS if c != "inspection_id"]

# Inserts new inspections. For existing ones, rewrites the row only if something
# changed: an UPDATE makes Postgres write a whole new copy of the row, so
# rewriting unchanged rows every day would waste space.
UPSERT = f"""
insert into raw_inspections ({", ".join(COLUMNS)})
values ({", ".join(f"%({c})s" for c in COLUMNS)})
on conflict (inspection_id) do update set
    {", ".join(f"{c} = excluded.{c}" for c in UPDATABLE)},
    loaded_at = now()
where ({", ".join(f"raw_inspections.{c}" for c in UPDATABLE)})
      is distinct from ({", ".join(f"excluded.{c}" for c in UPDATABLE)});
"""


def load(records):
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE)
            cur.execute(MIGRATE)
            cur.executemany(UPSERT, records)
            cur.execute("select count(*) from raw_inspections")
            print(f"Rows in raw_inspections: {cur.fetchone()[0]}")


def main():
    rows = extract()
    save_raw_copy(rows)
    load(transform(rows))


if __name__ == "__main__":
    main()
