"""Geocode the City Reps spots using open data sources.

Reads  city_reps_dbt/seeds/spots.csv
Writes city_reps_dbt/seeds/spot_coordinates.csv

Sources, tried in order:
1. US Census Geocoder: matches street addresses. Results are public domain.
2. OpenStreetMap Nominatim: fallback for places without a normal street
   address (intersections, trails, parks). Data (c) OpenStreetMap
   contributors, available under the ODbL.

Run from the repo root:
    python ingestion/geocode_spots.py
"""
import csv
import re
import time
from pathlib import Path

import requests

SEEDS = Path(__file__).resolve().parents[1] / "city_reps_dbt" / "seeds"
SPOTS_CSV = SEEDS / "spots.csv"
OUT_CSV = SEEDS / "spot_coordinates.csv"

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim asks every app to identify itself
HEADERS = {"User-Agent": "city-reps/0.1 (https://github.com/npsubaric/city-reps)"}

# A box around Chicago, used to reject matches in the wrong city
LAT_RANGE = (41.64, 42.03)
LON_RANGE = (-87.95, -87.52)

# Spots whose app address isn't a street address. Each hint is the nearest
# real address on Chicago's grid, so the Census geocoder can place it.
GEOCODE_HINTS = {
    "606-east": "1800 N Ashland Ave",       # Ashland & Bloomingdale (1800 N) trailhead
    "fulton-walk": "1000 W Fulton Market",  # middle of the Fulton Market walk
}


def in_chicago(lat, lon):
    return LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]


def census(address):
    """Return (lat, lon, matched_address) from the Census Geocoder, or None."""
    params = {
        "address": f"{address}, Chicago, IL",
        "benchmark": "Public_AR_Current",
        "format": "json",
    }
    response = requests.get(CENSUS_URL, params=params, timeout=30)
    response.raise_for_status()
    matches = response.json()["result"]["addressMatches"]
    if not matches:
        return None
    best = matches[0]
    # Census returns x = longitude, y = latitude
    return best["coordinates"]["y"], best["coordinates"]["x"], best["matchedAddress"]


def nominatim(query):
    """Return (lat, lon, display_name) from OpenStreetMap, or None."""
    params = {"q": f"{query}, Chicago, IL", "format": "jsonv2", "limit": 1, "countrycodes": "us"}
    response = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    time.sleep(1)  # Nominatim's usage policy: at most 1 request per second
    hits = response.json()
    if not hits:
        return None
    return float(hits[0]["lat"]), float(hits[0]["lon"]), hits[0]["display_name"]


def geocode(spot):
    """Try each source in order; return (lat, lon, source, matched) or None."""
    address = GEOCODE_HINTS.get(spot["spot_id"], spot["address"])
    # Drop notes in parentheses, like "(east end)", which confuse OpenStreetMap
    name = re.sub(r"\s*\(.*?\)", "", spot["name"]).strip()
    attempts = [
        ("census", census, address),
        ("openstreetmap", nominatim, name),
        ("openstreetmap", nominatim, address),
    ]
    for source, lookup, query in attempts:
        result = lookup(query)
        if result and in_chicago(result[0], result[1]):
            lat, lon, matched = result
            return round(lat, 6), round(lon, 6), source, matched
    return None


def main():
    with SPOTS_CSV.open(encoding="utf-8") as f:
        spots = list(csv.DictReader(f))

    rows, missing = [], []
    for spot in spots:
        result = geocode(spot)
        if result is None:
            missing.append(spot)
            print(f"  no match: {spot['spot_id']} ({spot['address']})")
            continue
        lat, lon, source, matched = result
        rows.append({
            "spot_id": spot["spot_id"],
            "lat": lat,
            "lon": lon,
            "source": source,
            "matched_to": matched,
        })
        print(f"  {source:<13} {spot['spot_id']}")

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["spot_id", "lat", "lon", "source", "matched_to"],
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    by_source = {}
    for row in rows:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
    print(f"\nGeocoded {len(rows)} of {len(spots)} spots: {by_source}")
    if missing:
        print(f"{len(missing)} still need coordinates. Add them to {OUT_CSV.name} by hand.")
    print(f"Wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
