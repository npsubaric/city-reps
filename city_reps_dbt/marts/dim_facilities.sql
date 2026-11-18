-- models/marts/dim_facilities.sql
with ranked as (
  select *,
    row_number() over (partition by license_no
                       order by inspection_date desc) as rn
  from {{ source('raw', 'raw_inspections') }}
  where license_no is not null and license_no <> 0
)
select
  license_no,
  business_name,
  aka_name,
  facility_type_clean,
  address, zip, latitude, longitude,
  inspection_date as last_inspection_date,
  result         as last_result,
  result = 'Out of Business' as is_closed,
--   business_name ~* '(coffee|cafe|café|espresso|roast|bakery|tea)'
--     or aka_name ~* '(coffee|cafe|café|espresso|roast|bakery|tea)'
--     as is_cafe_candidate
from ranked
where rn = 1

