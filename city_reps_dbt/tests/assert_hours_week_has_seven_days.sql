-- hours_week must be 7 days, each null (closed) or [open, close] with
-- open < close. Returns any spot that breaks that.
select spot_id, hours_week
from {{ ref('dim_spots') }}
where hours_week is not null
  and (
      jsonb_array_length(hours_week) <> 7
      or exists (
          select 1
          from jsonb_array_elements(hours_week) as day
          where jsonb_typeof(day) <> 'null'
            and (   jsonb_array_length(day) <> 2
                 or (day ->> 0)::numeric >= (day ->> 1)::numeric
                 or (day ->> 0)::numeric < 0
                 or (day ->> 1)::numeric > 48)
      )
  )
