-- Finds the business license, if any, behind each City Reps spot.
--
-- Rules:
--   1. Only cafés and bakeries (Retail Food) and bookstores (Limited Business)
--      hold these licenses. Libraries, parks and museums are skipped.
--   2. Same street address. The city often adds a unit ("1211 N DAMEN AVE 1",
--      "1458 W CHICAGO AVE 1ST") and files some places under a range of
--      numbers ("1755-1759 W GRAND AVE"). A spot matches when its house number
--      falls inside the license's range, on the same side of the street, and
--      the street is the same (the license may add a unit after it).
--      spot_match_address_overrides can point a spot at a different address
--      when the city files its license under one (Caffè Umbria: 2545 vs 2535).
--   3. A name check: a distinctive word from the spot's name must appear in the
--      license's business or legal name. If no name matches, the match is only
--      accepted when it's the only license of that type at the address.

with spots_with_overrides as (
    select
        spots.spot_id,
        spots.name,
        spots.kind,
        upper(trim(coalesce(overrides.match_address, spots.address))) as address
    from {{ ref('spots') }} as spots
    left join {{ ref('spot_match_address_overrides') }} as overrides
        using (spot_id)
),

spots as (
    select
        spot_id,
        name,
        address,
        substring(address from '^(\d+)')::int                        as house_num,
        regexp_replace(substring(address from '^\d+\s+(.*)$'), '\s+', ' ', 'g') as street,
        case
            when kind in ('cafe', 'bakery') then 'RETAIL FOOD ESTABLISHMENT'
            when kind = 'books'             then 'LIMITED BUSINESS LICENSE'
        end as expected_license_type
    from spots_with_overrides
),

licenses as (
    select * from {{ ref('int_license_locations') }}
),

-- Distinctive words in each spot's name, for the name check (macros/spot_name_words.sql)
spot_words as (
    {{ spot_name_words('spots') }}
),

candidates as (
    select
        spots.spot_id,
        licenses.license_no,
        licenses.business_name,
        licenses.address,
        licenses.license_type,
        licenses.license_status,
        licenses.license_start_date,
        licenses.expiration_date,
        licenses.latitude,
        licenses.longitude,
        exists (
            select 1
            from spot_words
            where spot_words.spot_id = spots.spot_id
              and (   licenses.business_name ~ ('\m' || spot_words.word || '\M')
                   or licenses.legal_name    ~ ('\m' || spot_words.word || '\M'))
        ) as name_matches,
        count(*) over (partition by spots.spot_id) as licenses_at_address
    from spots
    join licenses
      on  licenses.license_type = spots.expected_license_type
      -- house number inside the license's range, same side of the street
      and spots.house_num between licenses.house_num_low and licenses.house_num_high
      and spots.house_num % 2 = licenses.house_num_low % 2
      -- same street; the license may add a unit after it
      and (   licenses.street_and_unit = spots.street
           or licenses.street_and_unit like spots.street || ' %')
),

ranked as (
    select
        *,
        row_number() over (
            partition by spot_id
            order by name_matches desc, expiration_date desc nulls last, license_no desc
        ) as rn
    from candidates
    where name_matches or licenses_at_address = 1
)

select
    spot_id,
    license_no,
    business_name    as license_business_name,
    address          as license_address,
    license_type,
    license_status,
    license_start_date,
    expiration_date  as license_expiration_date,
    latitude         as license_lat,
    longitude        as license_lon,
    case when name_matches then 'address_and_name' else 'address_only' end as match_method
from ranked
where rn = 1
