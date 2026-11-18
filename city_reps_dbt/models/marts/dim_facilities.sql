with ranked as (
    select
        *,
        row_number() over (
            partition by license_no
            order by inspection_date desc, inspection_id desc
        ) as rn
    from {{ ref('stg_inspections') }}
    where license_no is not null
)

select
    license_no,
    business_name,
    aka_name,
    facility_type_clean,
    address,
    zip,
    latitude,
    longitude,
    inspection_date               as last_inspection_date,
    result                        as last_result,
    result = 'OUT OF BUSINESS'    as is_closed
from ranked
where rn = 1