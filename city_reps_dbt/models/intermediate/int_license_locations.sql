-- One row per licensed location (license_no), taken from its most recent term.
-- stg_business_licenses has one row per term: the first issue plus each renewal.
--
-- Also splits the address into parts so spots can match address ranges:
--   "1755-1759 W GRAND AVE 1"  ->  house_num_low 1755, house_num_high 1759,
--                                  street_and_unit "W GRAND AVE 1"

with latest_terms as (
    select distinct on (license_no)
        license_no,
        license_id              as latest_license_id,
        account_number,
        business_name,
        legal_name,
        address,
        license_type,
        license_status,
        license_status_change_date,
        license_start_date,
        expiration_date,
        latitude,
        longitude
    from {{ ref('stg_business_licenses') }}
    where license_no is not null
    -- DISTINCT ON keeps the first row per license_no, so sort the latest term first
    order by license_no, expiration_date desc nulls last, license_id desc
)

select
    *,
    substring(address from '^(\d+)')::int as house_num_low,
    coalesce(
        substring(address from '^\d+-(\d+)')::int,
        substring(address from '^(\d+)')::int
    ) as house_num_high,
    -- everything after the house number(s), with runs of spaces collapsed
    regexp_replace(regexp_replace(address, '^\d+(-\d+)?\s+', ''), '\s+', ' ', 'g') as street_and_unit
from latest_terms
