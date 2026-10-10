"""Calendar months. A month is represented by the date of its first day."""

import calendar
import re
from datetime import date

_MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
MIN_YEAR = 2000
MAX_YEAR = 2100


def parse_month(value: str) -> date:
    """`"2026-06"` -> `date(2026, 6, 1)`."""
    match = _MONTH_PATTERN.match(value)
    if not match:
        raise ValueError("Month must look like YYYY-MM, for example 2026-06")
    year = int(match.group(1))
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError(f"Year must be between {MIN_YEAR} and {MAX_YEAR}")
    return date(year, int(match.group(2)), 1)


def format_month(month: date) -> str:
    return f"{month.year:04d}-{month.month:02d}"


def month_start(day: date) -> date:
    return day.replace(day=1)


def month_end(month: date) -> date:
    """The last day of the month, so a date range can include it."""
    return month.replace(day=calendar.monthrange(month.year, month.month)[1])


def add_months(month: date, count: int) -> date:
    """The first day of the month `count` months after (or before, if negative) `month`."""
    index = month.year * 12 + (month.month - 1) + count
    return date(index // 12, index % 12 + 1, 1)


def months_between(first: date, last: date) -> list[date]:
    """Every month from `first` to `last`, both included."""
    months = []
    current = month_start(first)
    while current <= last:
        months.append(current)
        current = add_months(current, 1)
    return months
