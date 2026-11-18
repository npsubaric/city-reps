with source as (
    select * from {{ source('raw', 'raw_inspections') }}
)

select
    inspection_id,
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
