-- Finds the business license, if any, behind each City Reps spot.
--
-- Rules:
--   1. Only cafés and bakeries (Retail Food) and bookstores (Limited Business)
--      hold these licenses. Libraries, parks and museums are skipped.
--   2. Same street address. The city often adds a unit ("1211 N DAMEN AVE 1",
--      "1458 W CHICAGO AVE 1ST"), so a license address may also start with the
--      spot's address followed by a space.
--   3. A name check: a distinctive word from the spot's name must appear in the
--      license's business or legal name. If no name matches, the match is only
--      accepted when it's the only license of that type at the address.

with spots as (
    select
        spot_id,
        name,
        upper(trim(address)) as address,
        case
            when kind in ('cafe', 'bakery') then 'RETAIL FOOD ESTABLISHMENT'
            when kind = 'books'             then 'LIMITED BUSINESS LICENSE'
        end as expected_license_type
    from {{ ref('spots') }}
),

licenses as (
    select * from {{ ref('int_license_locations') }}
),

-- Distinctive words in each spot's name, for the name check.
-- Generic words (CAFE, COFFEE, neighborhood names) don't count.
spot_words as (
    select spots.spot_id, word
    from spots
    cross join lateral regexp_split_to_table(upper(spots.name), '[^A-Z0-9]+') as word
    where length(word) >= 4
      and word not in (
          'CAFE', 'CAFFE', 'COFFEE', 'BAKERY', 'BOOKS', 'BOOKSTORE', 'ROASTERS',
          'COMPANY', 'EATERY', 'PASTRY', 'BREAD', 'HOME', 'NATURAL', 'MODERN',
          'WICKER', 'PARK', 'LOGAN', 'SQUARE', 'BUCKTOWN', 'TOWN', 'WEST',
          'LOOP', 'FULTON', 'MARKET'
      )
),

candidates as (
    select
        spots.spot_id,
        licenses.license_no,
        licenses.business_name,
        licenses.address,
        licenses.license_type,
        licenses.license_status,
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
      and (   licenses.address = spots.address
           or licenses.address like spots.address || ' %')
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
    expiration_date  as license_expiration_date,
    latitude         as license_lat,
    longitude        as license_lon,
    case when name_matches then 'address_and_name' else 'address_only' end as match_method
from ranked
where rn = 1
