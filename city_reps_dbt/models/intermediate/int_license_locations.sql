-- One row per licensed location (license_no), taken from its most recent term.
-- stg_business_licenses has one row per term: the first issue plus each renewal.

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
