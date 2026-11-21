-- One row per license record (a license term), cleaned up.
-- A business can have several records over time: the first issue, then renewals.

with source as (
    select * from {{ source('raw', 'raw_business_licenses') }}
)

select
    license_id,
    -- same ID as license_no in stg_inspections; guard against stray non-digits
    case when license_number ~ '^\d+$' then license_number::bigint end as license_no,
    account_number,
    upper(trim(legal_name))                        as legal_name,
    upper(trim(doing_business_as_name))            as business_name,
    upper(trim(address))                           as address,
    zip_code,
    upper(trim(license_description))               as license_type,
    upper(trim(business_activity))                 as business_activity,
    upper(trim(application_type))                  as application_type,
    license_start_date,
    expiration_date,
    upper(trim(license_status))                    as license_status,
    license_status_change_date,
    latitude,
    longitude,
    loaded_at
from source
