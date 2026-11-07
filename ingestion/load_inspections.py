import json
import os
from datetime import date
from pathlib import Path

import psycopg
import requests
from psycopg.types.json import Jsonb

URL = "https://data.cityofchicago.org/resource/4ijn-s7e5.json"
DATABASE_URL = os.environ["DATABASE_URL"]  # from your Codespaces secret

# --- 1. Extract: pull the latest inspections from the city API ---
rows, offset, page = [], 0, 50000
while True:
    params = {
        "$where": "inspection_date >= '2024-01-01'",
        "$order": "inspection_id",
        "$limit": page,
        "$offset": offset,
    }
    response = requests.get(URL, params=params, timeout=60)
    response.raise_for_status()
    batch = response.json()
    if not batch:
        break
    rows.extend(batch)
    offset += page
    print(f"Fetched {len(rows)} rows so far")

# Keep a raw copy on disk (ignored by git)
out_dir = Path("data/raw")
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / f"inspections_{date.today()}.json").write_text(json.dumps(rows, indent=2))

# --- 2. Shape each record into table columns ---
def to_float(value):
    return float(value) if value else None

records = [
    {
        "inspection_id": r["inspection_id"],
        "dba_name": r.get("dba_name"),
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
        "raw": Jsonb(r),  # full original record, just in case
    }
    for r in rows
]

# --- 3. Load: create the table if needed, then upsert ---
CREATE_TABLE = """
create table if not exists raw_inspections (
    inspection_id   text primary key,
    dba_name        text,
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
    raw             jsonb,
    loaded_at       timestamptz default now()
);
"""

UPSERT = """
insert into raw_inspections (
    inspection_id, dba_name, facility_type, risk, address, zip,
    inspection_date, inspection_type, results, violations,
    latitude, longitude, raw
) values (
    %(inspection_id)s, %(dba_name)s, %(facility_type)s, %(risk)s, %(address)s, %(zip)s,
    %(inspection_date)s, %(inspection_type)s, %(results)s, %(violations)s,
    %(latitude)s, %(longitude)s, %(raw)s
)
on conflict (inspection_id) do update set
    results = excluded.results,
    violations = excluded.violations,
    raw = excluded.raw,
    loaded_at = now();
"""

with psycopg.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE)
        cur.executemany(UPSERT, records)
        cur.execute("select count(*) from raw_inspections")
        print(f"Rows in raw_inspections: {cur.fetchone()[0]}")
