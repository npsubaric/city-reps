-- Finds the OpenStreetMap place behind each City Reps spot, for its hours.
--
-- Rules:
--   1. Within 150 meters of the spot's coordinates.
--   2. A distinctive word from the spot's name appears in the OSM name
--      (same word list as the license match, macros/spot_name_words.sql).
--      Unlike the license match there's no address-only fallback: OSM
--      addresses are often missing, and a wrong match would show wrong hours.
--   3. Closest wins; on a tie, the place whose hours could be parsed.

{% set max_meters = 150 %}

with spots as (
    select spots.spot_id, spots.name, coords.lat, coords.lon
    from {{ ref('spots') }} as spots
    join {{ ref('int_spot_coordinates') }} as coords using (spot_id)
),

spot_words as (
    {{ spot_name_words('spots') }}
),

places as (
    select * from {{ ref('stg_osm_places') }}
),

candidates as (
    select
        spots.spot_id,
        places.osm_key,
        places.name as osm_name,
        places.opening_hours,
        places.hours_week,
        -- Equirectangular distance: accurate to well under a meter at this scale
        sqrt(
            power((places.lat - spots.lat) * 111320, 2)
          + power((places.lon - spots.lon) * 111320 * cos(radians(spots.lat)), 2)
        ) as distance_m
    from spots
    join places
      -- cheap box first (about 170 m each way), exact distance below
      on  places.lat between spots.lat - 0.0015 and spots.lat + 0.0015
      and places.lon between spots.lon - 0.0021 and spots.lon + 0.0021
    where exists (
        select 1
        from spot_words
        where spot_words.spot_id = spots.spot_id
          and places.name_upper ~ ('\m' || spot_words.word || '\M')
    )
),

ranked as (
    select
        *,
        row_number() over (
            partition by spot_id
            order by distance_m, (hours_week is not null) desc, osm_key
        ) as rn
    from candidates
    where distance_m <= {{ max_meters }}
)

select
    spot_id,
    osm_key,
    osm_name,
    opening_hours as osm_opening_hours,
    hours_week    as osm_hours_week,
    round(distance_m::numeric, 1) as osm_distance_m
from ranked
where rn = 1
