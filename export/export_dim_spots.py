"""Export analytics.dim_spots to export/dim_spots.json for the City Reps app.

The app can't query Supabase directly, so the daily pipeline writes this file
and commits it to the repo whenever the data changes.

The output is deterministic (sorted by spot_id, no timestamps), so the file
only changes, and only gets a new commit, when the underlying data does. The
commit date shows when the data last changed.

Run from the repo root, after dbt build:
    python export/export_dim_spots.py
"""
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]
SCHEMA = os.environ.get("DBT_SCHEMA", "analytics")
OUT_FILE = Path(__file__).resolve().parent / "dim_spots.json"

COLUMNS = [
    "spot_id", "name", "neighborhood", "address", "kind", "is_free", "good_for_work",
    "lat", "lon", "coord_source",
    "license_no", "license_business_name", "match_method",
    "license_expiration_date", "license_state",
    "last_inspection_date", "last_inspection_result", "inspector_marked_closed",
]

ATTRIBUTION = [
    "City of Chicago open data: Business Licenses (r5kz-chrr), Food Inspections (4ijn-s7e5)",
    "US Census Geocoder (public domain)",
    "© OpenStreetMap contributors, ODbL (spots with coord_source = openstreetmap)",
]


def to_json_value(value):
    """Make database values JSON-friendly."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float):
        return round(value, 6)
    return value


def fetch_spots():
    query = f"select {', '.join(COLUMNS)} from {SCHEMA}.dim_spots order by spot_id"
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        rows = conn.execute(query).fetchall()
    return [{col: to_json_value(row[col]) for col in COLUMNS} for row in rows]


def main():
    spots = fetch_spots()
    if not spots:
        raise SystemExit("dim_spots is empty; refusing to overwrite the export.")
    payload = {"attribution": ATTRIBUTION, "count": len(spots), "spots": spots}
    OUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(spots)} spots to {OUT_FILE}")


if __name__ == "__main__":
    main()
