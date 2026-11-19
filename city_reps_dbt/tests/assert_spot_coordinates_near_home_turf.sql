-- Every City Reps spot is on the North, West or Near South Side.
-- A coordinate outside this box (like a Hyde Park match for The 606)
-- means the geocoder picked the wrong place. Returns the bad rows.
select spot_id, lat, lon, source, matched_to
from {{ ref('spot_coordinates') }}
where lat not between 41.84 and 41.95
   or lon not between -87.75 and -87.61
