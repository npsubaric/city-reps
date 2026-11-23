"""Tests for the OSM opening_hours parser. Run: python -m pytest ingestion"""
from opening_hours import parse

WEEKDAYS_7_TO_3 = [7.0, 15.0]


def test_every_day():
    assert parse("07:00-15:00") == [WEEKDAYS_7_TO_3] * 7


def test_24_7():
    assert parse("24/7") == [[0.0, 24.0]] * 7


def test_weekdays_and_weekend_sunday_first():
    week = parse("Mo-Fr 07:00-15:00; Sa,Su 08:00-14:00")
    assert week[0] == [8.0, 14.0]          # Sunday
    assert week[1:6] == [WEEKDAYS_7_TO_3] * 5
    assert week[6] == [8.0, 14.0]          # Saturday


def test_closed_days_and_overrides():
    week = parse("Mo-Su 07:00-15:00; Mo off")
    assert week[1] is None
    assert week[2] == WEEKDAYS_7_TO_3


def test_unlisted_days_are_closed():
    week = parse("Th-Su 08:00-14:00")
    assert week[1] is None and week[2] is None and week[3] is None  # Mo, Tu, We
    assert week[4] == [8.0, 14.0]


def test_comma_between_rules():
    week = parse("Mo-Fr 07:00-15:00, Sa 08:00-14:00")
    assert week[6] == [8.0, 14.0]
    assert week[0] is None


def test_past_midnight_and_minutes():
    assert parse("Fr 18:30-02:00")[5] == [18.5, 26.0]


def test_lunch_break_collapses():
    assert parse("Mo 07:00-12:00,13:00-17:00")[1] == [7.0, 17.0]


def test_wrapping_range():
    week = parse("Fr-Mo 09:00-17:00")
    assert [d is not None for d in week] == [True, True, False, False, False, True, True]


def test_holiday_rules_ignored():
    assert parse("Mo-Su 07:00-15:00; PH off") == [WEEKDAYS_7_TO_3] * 7
    assert parse("Mo-Sa 07:00-15:00; Su,PH 08:00-14:00")[0] == [8.0, 14.0]


def test_unreadable_returns_none():
    for value in ["", None, "sunrise-sunset", "Jan-Mar Mo 08:00-12:00",
                  "Mo-Fr 07:00+", '"by appointment"', "Mo-Fr 07:00-15:00 || 'call'"]:
        assert parse(value) is None, value
