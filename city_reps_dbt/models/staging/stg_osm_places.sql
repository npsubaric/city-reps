-- One row per OpenStreetMap place with opening hours, near the City Reps spots.
-- © OpenStreetMap contributors, ODbL.
select
    osm_type || '/' || osm_id as osm_key,
    osm_type,
    osm_id,
    name,
    upper(name)               as name_upper,
    category,
    lat,
    lon,
    opening_hours,
    hours_week,
    loaded_at
from {{ source('raw', 'raw_osm_places') }}
where name is not null
  and lat is not null
  and lon is not null
