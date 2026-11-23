{% docs __overview__ %}
# City Reps data pipeline

The data behind [City Reps](https://npsubaric.github.io/city-reps/), a Chicago
spot picker for remote workers. Code: [github.com/npsubaric/city-reps](https://github.com/npsubaric/city-reps).

Every morning GitHub Actions loads the City of Chicago's business licenses and
food inspections plus OpenStreetMap opening hours into Supabase, then
`dbt build` runs these models and their tests.

**How the layers fit**

- **staging**: cleaned copies of the raw tables, one view per source
- **intermediate**: matching each hand-picked spot to its city license,
  its best coordinates and its OpenStreetMap place
- **marts**: `dim_facilities` (latest inspection per licensed location, citywide)
  and `dim_spots` (one row per spot, everything the app needs)
- **api**: `public.spots`, the read-only table the website calls through
  Supabase's Data API

Click the button at the bottom right to see the lineage graph.

Data: City of Chicago open data; © OpenStreetMap contributors (ODbL);
US Census Geocoder.
{% enddocs %}
