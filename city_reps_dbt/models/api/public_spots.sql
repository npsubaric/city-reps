-- The public City Reps API: what the website reads from Supabase.
--
-- Lives in the public schema, which Supabase's Data API serves at
--   GET <project>/rest/v1/spots
-- with the project's publishable key. That key ships in the website, so this
-- table is read-only for it (macros/public_read_only.sql), and it only has
-- the columns the app shows. Everything else stays in analytics, which the
-- API can't reach.
{{ config(
    materialized='table',
    alias='spots',
    schema=env_var('DBT_API_SCHEMA', 'public'),
    post_hook="{{ public_read_only(this) }}"
) }}

select
    spot_id,
    name,
    neighborhood,
    address,
    kind,
    is_free,
    good_for_work,
    is_outdoors,
    moods,
    time_needed,
    note,
    lat,
    lon,
    coord_source,
    license_state,
    -- License and inspection details for the app's detail panel. All of it
    -- is already public in the city's open data.
    license_no,
    license_business_name,
    license_type,
    license_start_date,
    license_expiration_date,
    last_inspection_date,
    last_inspection_type,
    last_inspection_result,
    last_violation_count,
    inspection_count,
    failed_inspection_count,
    inspector_marked_closed,
    hours_week,
    hours_source,
    now() as refreshed_at
from {{ ref('dim_spots') }}
