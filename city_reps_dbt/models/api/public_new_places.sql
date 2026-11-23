-- "New near you" for the website: cafés and bakeries that recently passed
-- their city license inspection. Read-only through Supabase's Data API at
--   GET <project>/rest/v1/new_places
-- (same protection as public.spots, see macros/public_read_only.sql).
{{ config(
    materialized='table',
    alias='new_places',
    schema=env_var('DBT_API_SCHEMA', 'public'),
    post_hook="{{ public_read_only(this) }}"
) }}

select
    license_no,
    name,
    address,
    kind,
    lat,
    lon,
    license_passed_on
from {{ ref('dim_new_places') }}
