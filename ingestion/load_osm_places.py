"""Load places with opening hours from OpenStreetMap into Supabase.

Source: OpenStreetMap, via the Overpass API. © OpenStreetMap contributors,
available under the Open Database License (ODbL). Anything shown from this
data must credit OpenStreetMap.

What it loads: every named place (node, way or relation) that has an
opening_hours tag, inside a box around the City Reps spots. dbt matches
spots to these places (int_spot_osm_match) for the app's hours.

The hours are parsed here (ingestion/opening_hours.py) because OSM writes
them in a mini-language that SQL can't read. Both the original text and the
parsed week are stored.

Each run replaces the whole table with the latest snapshot, so places that
were deleted from OSM disappear too.

Run from the repo root:
    python ingestion/load_osm_places.py
"""
import csv
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import psycopg
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).resolve().parent))
from opening_hours import parse  # noqa: E402

DATABASE_URL = os.environ["DATABASE_URL"]
COORDS_FILE = Path(__file__).resolve().parents[1] / "city_reps_dbt" / "seeds" / "spot_coordinates.csv"

# The main Overpass server, then a public mirror if it's busy
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
HEADERS = {"User-Agent": "city-reps/1.0 (+https://github.com/npsubaric/city-reps)"}
# Extra room around the spots, in degrees (about 0.7 miles)
MARGIN = 0.01
# A normal load finds a few thousand places. Far fewer means a partial or
# broken response, and replacing the table with it would wipe good data.
MIN_PLACES = 300
# Tags that say what kind of place it is, in order of preference
CATEGORY_TAGS = ("amenity", "shop", "leisure", "tourism", "craft", "office")


def make_session():
    """Retries dropped connections and busy-server responses (429, 504)."""
    retry = Retry(
        total=4,
        backoff_factor=5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("POST",),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(HEADERS)
    return session


def bounding_box():
    """South, west, north, east around every spot, from the coordinates seed."""
    with COORDS_FILE.open() as f:
        rows = list(csv.DictReader(f))
    lats = [float(r["lat"]) for r in rows]
    lons = [float(r["lon"]) for r in rows]
    return (min(lats) - MARGIN, min(lons) - MARGIN, max(lats) + MARGIN, max(lons) + MARGIN)


def extract():
    south, west, north, east = bounding_box()
    query = (
        "[out:json][timeout:120];"
        f'nwr["name"]["opening_hours"]({south:.4f},{west:.4f},{north:.4f},{east:.4f});'
        "out center tags;"
    )
    session = make_session()
    for url in OVERPASS_URLS:
        try:
            response = session.post(url, data={"data": query}, timeout=180)
            response.raise_for_status()
            elements = response.json()["elements"]
            print(f"Fetched {len(elements)} places from {url}")
            return elements
        except (requests.exceptions.RequestException, ValueError, KeyError) as error:
            print(f"{url} failed ({type(error).__name__}: {error}); trying the next server")
            time.sleep(5)
    print("Every Overpass server failed. The table keeps yesterday's data.")
    sys.exit(1)


def save_raw_copy(elements):
    """Keep the untouched response on disk (data/ is gitignored)."""
    out_dir = Path("data/raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"osm_places_{date.today()}.json").write_text(json.dumps(elements))


def transform(elements):
    rows = []
    for e in elements:
        tags = e.get("tags", {})
        # Nodes have lat/lon; ways and relations have a center point
        point = e if "lat" in e else e.get("center", {})
        if "lat" not in point:
            continue
        hours_week = parse(tags.get("opening_hours"))
        rows.append({
            "osm_type": e["type"],
            "osm_id": e["id"],
            "name": tags.get("name"),
            "category": next((tags[t] for t in CATEGORY_TAGS if t in tags), None),
            "lat": point["lat"],
            "lon": point["lon"],
            "opening_hours": tags.get("opening_hours"),
            "hours_week": json.dumps(hours_week) if hours_week else None,
        })
    return rows


CREATE_TABLE = """
create table if not exists raw_osm_places (
    osm_type       text not null,
    osm_id         bigint not null,
    name           text,
    category       text,
    lat            double precision,
    lon            double precision,
    opening_hours  text,
    hours_week     jsonb,
    loaded_at      timestamptz default now(),
    primary key (osm_type, osm_id)
);
"""

# Raw tables live in the public schema, which Supabase's Data API exposes.
# Row level security with no policies means the public API key can't read
# or change them. The pipeline connects as the table owner, which RLS skips.
LOCK_DOWN = """
alter table raw_osm_places enable row level security;
do $$ begin
    if exists (select from pg_roles where rolname = 'anon') then
        revoke all on raw_osm_places from anon, authenticated;
    end if;
end $$;
"""

COLUMNS = ["osm_type", "osm_id", "name", "category", "lat", "lon", "opening_hours", "hours_week"]
UPDATABLE = [c for c in COLUMNS if c not in ("osm_type", "osm_id")]

# Same changed-only upsert as the other loaders: unchanged rows aren't rewritten
UPSERT = f"""
insert into raw_osm_places ({", ".join(COLUMNS)})
values ({", ".join(f"%({c})s" for c in COLUMNS)})
on conflict (osm_type, osm_id) do update set
    {", ".join(f"{c} = excluded.{c}" for c in UPDATABLE)},
    loaded_at = now()
where ({", ".join(f"raw_osm_places.{c}" for c in UPDATABLE)})
      is distinct from ({", ".join(f"excluded.{c}" for c in UPDATABLE)});
"""


def load(rows):
    """Upsert the snapshot and delete places that are no longer in it, in one transaction."""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE)
            cur.execute(LOCK_DOWN)
            cur.executemany(UPSERT, rows)
            cur.execute(
                "delete from raw_osm_places where (osm_type, osm_id) not in "
                "(select * from unnest(%s::text[], %s::bigint[]))",
                ([r["osm_type"] for r in rows], [r["osm_id"] for r in rows]),
            )
            print(f"Removed {cur.rowcount} places no longer in OSM")
            cur.execute("select count(*), count(hours_week) from raw_osm_places")
            total, parsed = cur.fetchone()
            print(f"Rows in raw_osm_places: {total} ({parsed} with hours the app can read)")


def main():
    elements = extract()
    if len(elements) < MIN_PLACES:
        print(f"Only {len(elements)} places came back (expected at least {MIN_PLACES}). "
              "Not replacing the table.")
        sys.exit(1)
    save_raw_copy(elements)
    load(transform(elements))


if __name__ == "__main__":
    main()
