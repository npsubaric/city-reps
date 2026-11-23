-- One row per City Reps spot: its details, the best available coordinates,
-- and what the city's license data says about it.
--
-- Coordinates: the city's own license coordinates when the spot matched a
-- license, otherwise the open-data geocode (Census or OpenStreetMap).
--
-- license_state is deliberately cautious. License records lag and have gaps,
-- so an expired license means "on file", not "closed". Only an explicit
-- cancellation (AAC) or revocation (REV) by the city counts as cancelled.
--
-- The latest food inspection (from dim_facilities, joined on license_no) adds
-- a second signal: an inspection after the license expired suggests the place
-- is still operating, and an "OUT OF BUSINESS" result is a strong sign it closed.

with spots as (
    select * from {{ ref('spots') }}
),

geocoded as (
    select * from {{ ref('spot_coordinates') }}
),

matches as (
    select * from {{ ref('int_spot_license_match') }}
),

inspections as (
    select license_no, last_inspection_date, last_result
    from {{ ref('dim_facilities') }}
)

select
    spots.spot_id,
    spots.name,
    spots.neighborhood,
    spots.address,
    spots.kind,
    spots.is_free,
    spots.good_for_work,

    coalesce(matches.license_lat, geocoded.lat) as lat,
    coalesce(matches.license_lon, geocoded.lon) as lon,
    case
        when matches.license_lat is not null then 'city_license'
        else geocoded.source
    end as coord_source,

    matches.license_no,
    matches.license_business_name,
    matches.match_method,
    matches.license_expiration_date,
    case
        when matches.license_no is null
         and spots.kind in ('cafe', 'bakery', 'books')        then 'not_found'
        when matches.license_no is null                       then 'not_applicable'
        when matches.license_status in ('AAC', 'REV')         then 'cancelled'
        when matches.license_expiration_date >= current_date  then 'current'
        else 'on_file'
    end as license_state,

    inspections.last_inspection_date,
    inspections.last_result                                     as last_inspection_result,
    coalesce(inspections.last_result = 'OUT OF BUSINESS', false) as inspector_marked_closed
from spots
left join geocoded using (spot_id)
left join matches using (spot_id)
left join inspections
    on inspections.license_no = matches.license_no
