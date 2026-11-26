# City Reps

**A data pipeline behind a Chicago "where should I work from today?" app for remote workers.**

City Reps is a small app that helps me get out of my apartment: it picks a café, library, park or bookstore near me based on my mood, the time and the weather, and tracks a "never miss twice" streak. This repo is the data engineering behind it. Every day it loads the City of Chicago's open data and OpenStreetMap, matches them to the app's 74 hand-picked spots, and builds tested tables in Supabase. The website reads them live.

**Live app:** [npsubaric.github.io/city-reps](https://npsubaric.github.io/city-reps/) · **dbt docs:** [npsubaric.github.io/city-reps/docs](https://npsubaric.github.io/city-reps/docs/) (models, tests, lineage graph)

<p align="center"><img src="assets/demo.gif" alt="City Reps demo: picking a spot, the map, New near you and the directory" width="360"></p>

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
        O[OpenStreetMap<br/>Overpass API]
    end

    subgraph Ingestion [Python]
        E[load_inspections.py]
        F[load_business_licenses.py]
        G[geocode_spots.py]
        P[load_osm_places.py]
    end

    subgraph Supabase [Supabase Postgres]
        H[(raw_inspections)]
        I[(raw_business_licenses)]
        J[(spots +<br/>spot_coordinates)]
        Q[(raw_osm_places)]
        subgraph dbt
            K[staging] --> L[intermediate] --> M[marts] --> R[public.spots<br/>read-only API]
        end
    end

    A --> E --> H
    B --> F --> I
    C --> J
    D --> G --> J
    O --> P --> Q
    H & I & J & Q --> K
    R --> N[City Reps website<br/>GitHub Pages]
```

**Stack:** Python · PostgreSQL (Supabase) · dbt Core · GitHub Actions · GitHub Pages · built entirely in GitHub Codespaces

---

## Data sources

| Source | What it provides | License |
| --- | --- | --- |
| [Chicago Business Licenses](https://data.cityofchicago.org/d/r5kz-chrr) | Every licensed business, with status and coordinates; updated daily | City of Chicago open data |
| [Chicago Food Inspections](https://data.cityofchicago.org/d/4ijn-s7e5) | Health inspections for every food establishment | City of Chicago open data |
| [US Census Geocoder](https://geocoding.geo.census.gov/) | Coordinates for street addresses | Public domain |
| [OpenStreetMap](https://www.openstreetmap.org/) via Nominatim | Coordinates for places without a street address | © OpenStreetMap contributors, [ODbL](https://opendatacommons.org/licenses/odbl/) |
| [OpenStreetMap](https://www.openstreetmap.org/) via Overpass | Opening hours | © OpenStreetMap contributors, [ODbL](https://opendatacommons.org/licenses/odbl/) |
| Chicago Park District and City of Chicago | Posted hours for parks, the 606, Millennium Park and the Riverwalk (6 AM to 11 PM) | Public information |

---

## dbt models

| Layer | Model | Grain | What it does |
| --- | --- | --- | --- |
| Staging | `stg_inspections` | inspection | Cleans names, addresses and results; extracts license numbers |
| Staging | `stg_business_licenses` | license term | Cleans the license data (one row per issue or renewal) |
| Staging | `stg_osm_places` | OSM place | OpenStreetMap places that have opening hours |
| Intermediate | `int_license_locations` | license | Latest term per license, with the address parsed into a house-number range and street |
| Intermediate | `int_spot_license_match` | spot | Matches each spot to its business license |
| Intermediate | `int_spot_coordinates` | spot | Best coordinates: the city's license location, else the open-data geocode |
| Intermediate | `int_spot_osm_match` | spot | Matches each spot to its OpenStreetMap place (within 150 m, sharing a name word) |
| Mart | `dim_facilities` | inspected location | Latest inspection per licensed food location citywide |
| Mart | **`dim_spots`** | spot | Coordinates, license status, latest inspection and hours for every spot |
| Mart | `dim_new_places` | licensed location | Cafés and bakeries near the spots that passed their city license inspection in the last 90 days |
| API | **`public.spots`** | spot | **What the website reads:** the app's columns from `dim_spots`, read-only through Supabase's Data API |
| API | `public.new_places` | licensed location | The app's "New near you" list, read-only |

Seeds: `spots` (the app's spots and notes), `spot_coordinates` (open-data geocodes), `spot_hours_rules` (posted park hours), `spot_match_address_overrides` (hand-checked exceptions, each with a reason).

**63 data tests** cover unique and non-null keys, relationships between tables, allowed values for every status and source column, and custom tests that fail if any spot's coordinates fall outside the app's neighborhoods, if any hours are malformed, or if any table the public API can reach is missing row level security. The opening-hours parser has its own Python unit tests.

---

## Design decisions

**1. No Google data in the repo.** The app's spots were first found with Google Places, whose terms restrict storing coordinates. Since this repo is public, the coordinates were rebuilt from open sources instead: the city's own license coordinates where a spot matches a license, and Census or OpenStreetMap geocodes otherwise. A `coord_source` column records where each value came from.

**2. Address-range matching, not fuzzy distance.** The city often files a business under a range of street numbers (`1755-1759 W GRAND AVE 1`) with a unit on the end. A spot matches a license when its house number falls inside the range, on the same side of the street (same odd/even parity), on the same street, and a distinctive word from the spot's name appears in the license name. This is exact and explainable, where a distance threshold would be a guess.

**3. Cautious closure logic.** License records lag and have gaps: Myopic Books is open, but its latest license record expired in 2024, and Quimby's records jump from 2019 to 2027. So an expired license marks a spot `on_file`, never "closed". Only an explicit city cancellation (`AAC`) or revocation (`REV`) counts as `cancelled`.

**4. Overrides with reasons.** The few cases rules can't handle go in a seed file with a required explanation. Caffè Umbria's public address is 2545 W Armitage, but the city files its license at 2535, in the same building.

**5. Hours from open data, honestly.** Opening hours come from OpenStreetMap, whose hours are written in a small language of their own (`Mo-Fr 07:00-15:00; Sa,Su 08:00-14:00`). The loader parses the common forms into a simple week; anything it can't read confidently (holidays, seasons, "sunrise") stays unparsed, and the app says "Check hours" rather than guessing. Parks use their posted hours instead.

**6. A public API that's read-only by construction.** The website calls Supabase directly with a publishable key, which anyone can see. So the API table has row level security with a read-only policy, the raw tables are locked down, and a dbt test fails the build if any table the API can reach lacks row level security. If Supabase is unreachable, the site falls back to the daily JSON export.

**7. "New near you" from inspections, not reviews.** Chicago inspects every new food business before it opens. A passed `LICENSE` inspection in the last 90 days is the earliest public sign a café is opening, often before it shows up anywhere else. The city files most cafés as `RESTAURANT`, so restaurants count only when their name says café, coffee, bakery and the like.

**8. Built to run unattended within free tiers.** Loaders are idempotent (upserts keyed on the city's IDs), retry dropped connections and broken downloads with backoff, check the API's schema before loading, and only rewrite rows that changed. The full API responses stay on disk, not in the database, which keeps it within Supabase's free 500 MB.

---

## Automation

| Workflow | When | What it does |
| --- | --- | --- |
| [Daily pipeline](.github/workflows/daily_pipeline.yml) | Every day, 5:17 AM Chicago time (+ manual button) | Runs the loaders, then `dbt build`, then commits the JSON export if the data changed |
| [Deploy website](.github/workflows/pages.yml) | After each pipeline run, and on changes to the app or models | Publishes `app/`, the backup JSON and the dbt docs site to GitHub Pages |
| [Record demo GIF](.github/workflows/record_demo.yml) | By hand, after visible app changes | Drives the live site with Playwright and commits `assets/demo.gif` |
| [CI](.github/workflows/ci.yml) | Every pull request | Runs the Python tests, then builds and tests every model in separate `ci` and `ci_public` schemas, so checks never touch production tables |

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

For the website, also add two Actions **variables** (Settings > Secrets and variables > Actions > Variables), from Supabase's Project Settings > API: `SUPABASE_URL` (the project URL) and `SUPABASE_PUBLISHABLE_KEY` (the publishable or anon key, which is safe in a browser). Then turn on Pages with Source: GitHub Actions.

**2. Install and run**, from the repo root:

```bash
pip install -r requirements.txt
mkdir -p ~/.dbt && echo "manage_state: false" > ~/.dbt/user_settings.yml   # dbt 1.12: no browser sign-in

python ingestion/load_inspections.py
python ingestion/load_business_licenses.py
python ingestion/load_osm_places.py
cd city_reps_dbt && dbt build
```

`geocode_spots.py` only needs re-running when spots are added or their addresses change.

---

## Project structure

```
city-reps/
├── .github/workflows/      daily pipeline, website deploy, CI
├── app/                    the City Reps website (one HTML file)
├── export/                 daily JSON export (the website's backup copy)
├── ingestion/              Python loaders, geocoder, opening-hours parser
├── city_reps_dbt/
│   ├── models/
│   │   ├── staging/        cleaned copies of the raw tables
│   │   ├── intermediate/   license locations, spot matching
│   │   ├── marts/          dim_spots, dim_facilities
│   │   └── api/            public.spots, the website's read-only table
│   ├── seeds/              spots, coordinates, park hours, overrides
│   └── tests/              custom data tests
└── requirements.txt
```

---

## What's next

- Live CTA train arrivals for each pick
