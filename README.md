# City Reps

**A data pipeline behind a Chicago "where should I work from today?" app for remote workers.**

City Reps is a small app that helps me get out of my apartment: it picks a café, library, park or bookstore near me based on my mood, the time and the weather, and tracks a "never miss twice" streak. This repo is the data engineering behind it. Every day it loads the City of Chicago's open data, matches it to the app's 74 hand-picked spots, and builds one tested table the app reads: `dim_spots`.

Built by [Nikolas Subaric](https://github.com/npsubaric), a data engineer in Chicago.

---

## Architecture

```mermaid
flowchart LR
    subgraph Sources
        A[Chicago Food Inspections API]
        B[Chicago Business Licenses API]
        C[City Reps spots<br/>seeds/spots.csv]
        D[US Census Geocoder<br/>+ OpenStreetMap]
    end

    subgraph Ingestion [Python]
        E[load_inspections.py]
        F[load_business_licenses.py]
        G[geocode_spots.py]
    end

    subgraph Supabase [Supabase Postgres]
        H[(raw_inspections)]
        I[(raw_business_licenses)]
        J[(spots +<br/>spot_coordinates)]
        subgraph dbt
            K[staging] --> L[intermediate] --> M[marts]
        end
    end

    A --> E --> H
    B --> F --> I
    C --> J
    D --> G --> J
    H & I & J --> K
    M --> N[dim_spots<br/>→ City Reps app]
```

**Stack:** Python · PostgreSQL (Supabase) · dbt Core · GitHub Actions · built entirely in GitHub Codespaces

---

## Data sources

| Source | What it provides | License |
| --- | --- | --- |
| [Chicago Business Licenses](https://data.cityofchicago.org/d/r5kz-chrr) | Every licensed business, with status and coordinates; updated daily | City of Chicago open data |
| [Chicago Food Inspections](https://data.cityofchicago.org/d/4ijn-s7e5) | Health inspections for every food establishment | City of Chicago open data |
| [US Census Geocoder](https://geocoding.geo.census.gov/) | Coordinates for street addresses | Public domain |
| [OpenStreetMap](https://www.openstreetmap.org/) via Nominatim | Coordinates for places without a street address | © OpenStreetMap contributors, [ODbL](https://opendatacommons.org/licenses/odbl/) |

---

## dbt models

| Layer | Model | Grain | What it does |
| --- | --- | --- | --- |
| Staging | `stg_inspections` | inspection | Cleans names, addresses and results; extracts license numbers |
| Staging | `stg_business_licenses` | license term | Cleans the license data (one row per issue or renewal) |
| Intermediate | `int_license_locations` | license | Latest term per license, with the address parsed into a house-number range and street |
| Intermediate | `int_spot_license_match` | spot | Matches each spot to its business license |
| Mart | `dim_facilities` | inspected location | Latest inspection per licensed food location citywide |
| Mart | **`dim_spots`** | spot | **The app's table:** best coordinates and license status for every spot |

Seeds: `spots` (the app's spots), `spot_coordinates` (open-data geocodes), `spot_match_address_overrides` (hand-checked exceptions, each with a reason).

**40 data tests** cover unique and non-null keys, relationships between tables, allowed values for every status and source column, and a custom test that fails if any spot's coordinates fall outside the app's neighborhoods.

---

## Design decisions

**1. No Google data in the repo.** The app's spots were first found with Google Places, whose terms restrict storing coordinates. Since this repo is public, the coordinates were rebuilt from open sources instead: the city's own license coordinates where a spot matches a license, and Census or OpenStreetMap geocodes otherwise. A `coord_source` column records where each value came from.

**2. Address-range matching, not fuzzy distance.** The city often files a business under a range of street numbers (`1755-1759 W GRAND AVE 1`) with a unit on the end. A spot matches a license when its house number falls inside the range, on the same side of the street (same odd/even parity), on the same street, and a distinctive word from the spot's name appears in the license name. This is exact and explainable, where a distance threshold would be a guess.

**3. Cautious closure logic.** License records lag and have gaps: Myopic Books is open, but its latest license record expired in 2024, and Quimby's records jump from 2019 to 2027. So an expired license marks a spot `on_file`, never "closed". Only an explicit city cancellation (`AAC`) or revocation (`REV`) counts as `cancelled`.

**4. Overrides with reasons.** The few cases rules can't handle go in a seed file with a required explanation. Caffè Umbria's public address is 2545 W Armitage, but the city files its license at 2535, in the same building.

**5. Built to run unattended within free tiers.** Loaders are idempotent (upserts keyed on the city's IDs), retry dropped connections and broken downloads with backoff, check the API's schema before loading, and only rewrite rows that changed. The full API responses stay on disk, not in the database, which keeps it within Supabase's free 500 MB.

---

## Automation

| Workflow | When | What it does |
| --- | --- | --- |
| [Daily pipeline](.github/workflows/daily_pipeline.yml) | Every day, 11:17 UTC (+ manual button) | Runs both loaders, then `dbt build` |
| [CI](.github/workflows/ci.yml) | Every pull request | Builds and tests every model in a separate `ci` schema, so checks never touch production tables |

Every change goes through a pull request and must pass CI before merging.

---

## Run it yourself

**1. Set four secrets** (as Codespaces secrets for development and Actions secrets for the workflows), using a Supabase **session pooler** connection:

| Secret | Value |
| --- | --- |
| `DATABASE_URL` | `postgresql://USER:PASSWORD@HOST:5432/postgres` |
| `SUPABASE_HOST` | e.g. `aws-0-us-east-1.pooler.supabase.com` |
| `SUPABASE_USER` | e.g. `postgres.abcdefgh` |
| `SUPABASE_PASSWORD` | your database password |

**2. Install and run**, from the repo root:

```bash
pip install -r requirements.txt
mkdir -p ~/.dbt && echo "manage_state: false" > ~/.dbt/user_settings.yml   # dbt 1.12: no browser sign-in

python ingestion/load_inspections.py
python ingestion/load_business_licenses.py
cd city_reps_dbt && dbt build
```

`geocode_spots.py` only needs re-running when spots are added or their addresses change.

---

## Project structure

```
city-reps/
├── .github/workflows/      daily pipeline + CI
├── ingestion/              Python loaders and the geocoder
├── city_reps_dbt/
│   ├── models/
│   │   ├── staging/        cleaned copies of the raw tables
│   │   ├── intermediate/   license locations, spot matching
│   │   └── marts/          dim_spots, dim_facilities
│   ├── seeds/              spots, coordinates, overrides
│   └── tests/              custom data tests
└── requirements.txt
```

---

## What's next

- Connect the City Reps app to `dim_spots`
- "New near you": surface newly licensed cafés from the daily license data
- Live CTA train arrivals for each pick
