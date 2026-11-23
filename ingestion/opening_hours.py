"""Turn OpenStreetMap opening_hours text into the week format the app uses.

OSM writes hours in a small language of its own, like
    "Mo-Fr 07:00-15:00; Sa,Su 08:00-14:00"
(spec: https://wiki.openstreetmap.org/wiki/Key:opening_hours).

The app wants one list of 7 days, Sunday first. Each day is [open, close] in
decimal hours (7.5 = 7:30 AM; a close past 24 runs past midnight), or None
when the place is closed that day.

This handles the common forms: day ranges and lists, several time ranges in
a day, "off", "24/7", hours past midnight, and later rules overriding earlier
ones. Anything else (months, holidays only, sunrise, comments, "+") returns
None so the app says "Check hours" instead of guessing.

Several time ranges in one day (closed for lunch) collapse to first open,
last close. The app can only show one range per day.
"""
import re

OSM_DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]  # OSM order, Monday first
DAY = r"(?:Mo|Tu|We|Th|Fr|Sa|Su|PH|SH)"
DAY_SELECTOR = re.compile(rf"^({DAY}(?:-{DAY})?(?:\s*,\s*{DAY}(?:-{DAY})?)*)(?:\s+|$)")
TIME_RANGE = re.compile(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$")
# A comma right after a time, followed by a day, starts a new rule:
# "Mo-Fr 07:00-15:00, Sa 08:00-14:00"
RULE_COMMA = re.compile(rf"(?<=\d)\s*,\s*(?={DAY}\b)")


def expand_days(selector):
    """'Mo-We,Fr,PH' -> [0, 1, 2, 4]. Holidays (PH, SH) are skipped."""
    days = []
    for part in re.split(r"\s*,\s*", selector):
        if "-" in part:
            start, end = part.split("-")
            if start in ("PH", "SH") or end in ("PH", "SH"):
                return None
            i, j = OSM_DAYS.index(start), OSM_DAYS.index(end)
            days.extend((i + k) % 7 for k in range((j - i) % 7 + 1))  # Fr-Mo wraps
        elif part not in ("PH", "SH"):
            days.append(OSM_DAYS.index(part))
    return days


def parse_times(text):
    """'07:00-12:00,13:00-17:00' -> [7.0, 17.0]. None if it can't be read."""
    opens, closes = [], []
    for part in re.split(r"\s*,\s*", text):
        m = TIME_RANGE.match(part)
        if not m:
            return None
        start = int(m[1]) + int(m[2]) / 60
        end = int(m[3]) + int(m[4]) / 60
        if end <= start:  # "18:00-02:00" runs past midnight
            end += 24
        if start >= 24 or end > 48:
            return None
        opens.append(start)
        closes.append(end)
    return [round(min(opens), 2), round(max(closes), 2)]


def parse(value):
    """OSM opening_hours text -> 7 days, Sunday first, or None if unreadable."""
    if not value or not value.strip():
        return None
    value = value.strip()
    if value == "24/7":
        return [[0.0, 24.0] for _ in range(7)]

    week = [None] * 7  # Monday first while parsing
    any_rule = False
    for rule in re.split(r"\s*;\s*", value):
        for rule in RULE_COMMA.split(rule):
            rule = rule.strip()
            if not rule:
                continue
            m = DAY_SELECTOR.match(rule)
            if m:
                days = expand_days(m[1])
                if days is None:
                    return None
                if not days:  # a holiday-only rule like "PH off": ignore it
                    continue
                times = rule[m.end():].strip()
            else:
                days, times = list(range(7)), rule  # no days given = every day
            if times in ("off", "closed"):
                span = None
            else:
                span = parse_times(times)
                if span is None:
                    return None
            for d in days:  # later rules override earlier ones, as in OSM
                week[d] = span
            any_rule = True

    if not any_rule:
        return None
    return [week[6]] + week[:6]  # Sunday first, like JavaScript's getDay()
