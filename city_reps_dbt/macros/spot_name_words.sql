{#
  Distinctive words in each spot's name, for matching spots to other
  datasets by name (business licenses, OpenStreetMap places).
  Generic words (CAFE, COFFEE, neighborhood names) don't count.
  `spots` is a CTE or relation with spot_id and name.
#}
{% macro spot_name_words(spots) %}
    select {{ spots }}.spot_id, word
    from {{ spots }}
    cross join lateral regexp_split_to_table(upper({{ spots }}.name), '[^A-Z0-9]+') as word
    where length(word) >= 4
      and word not in (
          'CAFE', 'CAFFE', 'COFFEE', 'BAKERY', 'BOOKS', 'BOOKSTORE', 'ROASTERS',
          'COMPANY', 'EATERY', 'PASTRY', 'BREAD', 'HOME', 'NATURAL', 'MODERN',
          'WICKER', 'PARK', 'LOGAN', 'SQUARE', 'BUCKTOWN', 'TOWN', 'WEST',
          'LOOP', 'FULTON', 'MARKET'
      )
{% endmacro %}
