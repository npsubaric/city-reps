with ranked as (
    select
        *,
        row_number() over (
            partition by license_no
            order by inspection_date desc, inspection_id desc
        ) as rn,
        -- history since the data starts (2024), for the app's detail panel
        count(*) over (partition by license_no) as inspection_count,
        count(*) filter (where result = 'FAIL') over (partition by license_no) as failed_inspection_count
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
    inspection_type               as last_inspection_type,
    result                        as last_result,
    -- Violations arrive as one text field, separated by " | "
    coalesce(array_length(string_to_array(nullif(trim(violations), ''), ' | '), 1), 0)
                                  as last_violation_count,
    inspection_count,
    failed_inspection_count,
    result = 'OUT OF BUSINESS'    as is_closed
from ranked
where rn = 1