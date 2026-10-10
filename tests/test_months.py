from datetime import date

import pytest

from app.months import add_months, format_month, month_end, month_start, months_between, parse_month


def test_parse_and_format_round_trip():
    assert parse_month("2026-06") == date(2026, 6, 1)
    assert format_month(date(2026, 6, 1)) == "2026-06"
    assert format_month(parse_month("2000-01")) == "2000-01"


@pytest.mark.parametrize("value", ["2026-13", "2026-00", "2026-6", "26-06", "2026/06", "2026-06-01", "", "June", "1999-12", "2101-01"])
def test_parse_refuses_an_invalid_month(value):
    with pytest.raises(ValueError):
        parse_month(value)


def test_month_start():
    assert month_start(date(2026, 6, 15)) == date(2026, 6, 1)


@pytest.mark.parametrize(
    ("month", "last_day"),
    [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2028, 2, 1), date(2028, 2, 29)),  # leap year
        (date(2026, 4, 1), date(2026, 4, 30)),
        (date(2026, 12, 1), date(2026, 12, 31)),
    ],
)
def test_month_end(month, last_day):
    assert month_end(month) == last_day


@pytest.mark.parametrize(
    ("month", "count", "expected"),
    [
        (date(2026, 6, 1), 0, date(2026, 6, 1)),
        (date(2026, 6, 1), 1, date(2026, 7, 1)),
        (date(2026, 12, 1), 1, date(2027, 1, 1)),
        (date(2026, 1, 1), -1, date(2025, 12, 1)),
        (date(2026, 6, 1), -6, date(2025, 12, 1)),
        (date(2026, 6, 1), 18, date(2027, 12, 1)),
        (date(2026, 6, 1), -36, date(2023, 6, 1)),
    ],
)
def test_add_months(month, count, expected):
    assert add_months(month, count) == expected


def test_months_between_includes_both_ends_and_crosses_years():
    assert months_between(date(2025, 11, 1), date(2026, 2, 1)) == [
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]
    assert months_between(date(2026, 6, 1), date(2026, 6, 1)) == [date(2026, 6, 1)]
    assert months_between(date(2026, 7, 1), date(2026, 6, 1)) == []
