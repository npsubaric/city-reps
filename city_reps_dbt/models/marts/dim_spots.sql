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
--
-- Hours: posted hours for parks and public spaces (spot_hours_rules seed)
-- first, then OpenStreetMap (int_spot_osm_match). hours_week is 7 days,
-- Sunday first, each [open, close] in decimal hours or null for closed.
-- No hours means the app shows "Check hours".

with spots as (
    select * from {{ ref('spots') }}
),

coords as (
    select * from {{ ref('int_spot_coordinates') }}
),

matches as (
    select * from {{ ref('int_spot_license_match') }}
),

inspections as (
    select license_no, last_inspection_date, last_inspection_type, last_result,
           last_violation_count, last_violations, inspection_count, failed_inspection_count
    from {{ ref('dim_facilities') }}
),

osm as (
    select * from {{ ref('int_spot_osm_match') }}
),

-- The same hours every day of the week
hours_rules as (
    select
        rules.spot_id,
        rules.source,
        jsonb_build_array(day, day, day, day, day, day, day) as hours_week
    from {{ ref('spot_hours_rules') }} as rules
    cross join lateral jsonb_build_array(rules.open_hour, rules.close_hour) as day
)

select
    spots.spot_id,
    spots.name,
    spots.neighborhood,
    spots.address,
    spots.kind,
    spots.is_free,
    spots.good_for_work,
    spots.is_outdoors,
    string_to_array(spots.moods, ' ') as moods,
    spots.time_needed,
    spots.note,

    coords.lat,
    coords.lon,
    coords.coord_source,

    matches.license_no,
    matches.license_business_name,
    matches.license_type,
    matches.match_method,
    matches.license_start_date,
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
    inspections.last_inspection_type,
    inspections.last_violation_count,
    inspections.last_violations,
    inspections.inspection_count,
    inspections.failed_inspection_count,
    coalesce(inspections.last_result = 'OUT OF BUSINESS', false) as inspector_marked_closed,

    coalesce(hours_rules.hours_week, osm.osm_hours_week) as hours_week,
    case
        when hours_rules.spot_id is not null  then hours_rules.source
        when osm.osm_hours_week is not null   then 'openstreetmap'
    end as hours_source,
    osm.osm_key,
    osm.osm_name,
    osm.osm_opening_hours
from spots
left join coords using (spot_id)
left join matches using (spot_id)
left join osm using (spot_id)
left join hours_rules using (spot_id)
left join inspections
    on inspections.license_no = matches.license_no
