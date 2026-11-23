-- The best available coordinates for each spot: the city's own license
-- coordinates when the spot matched a license, otherwise the open-data
-- geocode (Census or OpenStreetMap).

with spots as (
    select spot_id from {{ ref('spots') }}
),

geocoded as (
    select * from {{ ref('spot_coordinates') }}
),

matches as (
    select * from {{ ref('int_spot_license_match') }}
)

select
    spots.spot_id,
    coalesce(matches.license_lat, geocoded.lat) as lat,
    coalesce(matches.license_lon, geocoded.lon) as lon,
    case
        when matches.license_lat is not null then 'city_license'
        else geocoded.source
    end as coord_source
from spots
left join geocoded using (spot_id)
left join matches using (spot_id)
