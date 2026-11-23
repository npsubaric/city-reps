with source as (
    select * from {{ source('raw', 'raw_inspections') }}
)

select
    inspection_id,
    -- same ID as license_no in stg_business_licenses; 0 and stray non-digits become null
    nullif(case when license_number ~ '^\d+$' then license_number::bigint end, 0) as license_no,
    upper(trim(aka_name))                            as aka_name,
    upper(trim(dba_name))         as business_name,
    upper(trim(facility_type))    as facility_type_clean,
    upper(trim(risk))             as risk,
    upper(trim(address))          as address,
    zip,
    inspection_date,
    upper(trim(inspection_type))  as inspection_type,
    upper(trim(results))          as result,
    violations,
    latitude,
    longitude,
    loaded_at
from source
