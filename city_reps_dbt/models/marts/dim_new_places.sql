-- Cafés and bakeries that recently passed their city license inspection,
-- near the City Reps spots: the app's "New near you" list.
--
-- Why license inspections: Chicago inspects every new food business before
-- it can open (inspection_type LICENSE). A pass in the last 90 days is the
-- earliest public sign that a place is about to open or just did. A new
-- owner at an existing place also gets one, so the app says "newly
-- licensed", not "new".
--
-- Which places: the city files most cafés as RESTAURANT, so besides BAKERY
-- and COFFEE SHOP, a restaurant counts when its name says it's a café or
-- bakery. Places already in the app's spots, places an inspector marked out
-- of business, and places outside the spots' area are left out.

{% set days_back = 90 %}
{% set cafe_words = "COFFEE|CAFE|CAFÉ|CAFFE|CAFFÈ|ESPRESSO|TEA|ROASTERS?|ROASTERY|BAKERY|BAKESHOP|PASTRY|PASTRIES|PATISSERIE|BOULANGERIE|PANADERIA|DONUTS?|BAGELS?" %}
{% set bakery_words = "BAKERY|BAKESHOP|PASTRY|PASTRIES|PATISSERIE|BOULANGERIE|PANADERIA|DONUTS?|BAGELS?" %}

with license_passes as (
    select
        license_no,
        max(inspection_date) as license_passed_on
    from {{ ref('stg_inspections') }}
    where license_no is not null
      and inspection_type in ('LICENSE', 'LICENSE RE-INSPECTION')
      and result in ('PASS', 'PASS W/ CONDITIONS')
    group by license_no
),

facilities as (
    select
        *,
        coalesce(nullif(aka_name, ''), business_name) as public_name
    from {{ ref('dim_facilities') }}
),

-- The spots' area, with about 0.7 miles of room around it
area as (
    select
        min(lat) - 0.01 as lat_min, max(lat) + 0.01 as lat_max,
        min(lon) - 0.01 as lon_min, max(lon) + 0.01 as lon_max
    from {{ ref('int_spot_coordinates') }}
),

already_spots as (
    select license_no
    from {{ ref('int_spot_license_match') }}
    where license_no is not null
)

select
    facilities.license_no,
    initcap(facilities.public_name)               as name,
    initcap(facilities.address)                   as address,
    case
        when facilities.facility_type_clean = 'BAKERY'
          or facilities.public_name ~ '\m({{ bakery_words }})\M' then 'bakery'
        else 'cafe'
    end                                           as kind,
    facilities.latitude                           as lat,
    facilities.longitude                          as lon,
    license_passes.license_passed_on,
    facilities.facility_type_clean                as facility_type
from license_passes
join facilities using (license_no)
cross join area
where license_passes.license_passed_on >= current_date - {{ days_back }}
  and not facilities.is_closed
  and facilities.latitude  between area.lat_min and area.lat_max
  and facilities.longitude between area.lon_min and area.lon_max
  and (
        facilities.facility_type_clean in ('BAKERY', 'COFFEE SHOP')
     or (facilities.facility_type_clean = 'RESTAURANT'
         and facilities.public_name ~ '\m({{ cafe_words }})\M')
  )
  and facilities.license_no not in (select license_no from already_spots)
