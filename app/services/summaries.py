"""Summaries. Each definition here is repeated in the README, so a number means one thing."""

from datetime import date

from sqlalchemy.orm import Session

from app.errors import InvalidInputError
from app.money import divide_minor, from_minor, percent
from app.months import add_months, format_month, month_end, month_start, months_between, parse_month
from app.repositories import expenses
from app.schemas.summary import (
    CategorySummary,
    CategoryTotalOut,
    MonthlySummary,
    MonthlyTotal,
    TrendMonth,
    Trends,
)


def _totals_for_months(db: Session, user_id: int, first: date, last: date) -> dict[date, tuple[int, int]]:
    """month -> (total in minor units, count) for the months that have expenses."""
    rows = expenses.totals_by_month(db, user_id, date_from=first, date_to=month_end(last))
    return {date(row.year, row.month, 1): (row.total_minor, row.count) for row in rows}


def monthly_summary(db: Session, user_id: int, from_text: str | None, to_text: str | None) -> MonthlySummary:
    """Total and count per month, oldest first.

    A bound that is not given defaults to the user's first (or last) month
    with an expense. Months inside the range without expenses are included
    with a zero total, so the series has no gaps.
    """
    start = parse_month(from_text) if from_text else None
    end = parse_month(to_text) if to_text else None
    if start and end and start > end:
        raise InvalidInputError("query.from", "from must not be after to")

    if start is None or end is None:
        bounds = expenses.date_bounds(db, user_id)
        if bounds is None and start is None and end is None:
            return MonthlySummary(months=[], total=from_minor(0), count=0)
        earliest = month_start(bounds[0]) if bounds else None
        latest = month_start(bounds[1]) if bounds else None
        if end is None:
            end = max(latest, start) if latest and start else (latest or start)
        if start is None:
            start = min(earliest, end) if earliest else end

    totals = _totals_for_months(db, user_id, start, end)
    months = []
    for month in months_between(start, end):
        total, count = totals.get(month, (0, 0))
        months.append(MonthlyTotal(month=format_month(month), total=from_minor(total), count=count))

    return MonthlySummary(
        months=months,
        total=from_minor(sum(total for total, _ in totals.values())),
        count=sum(count for _, count in totals.values()),
    )


def category_summary(
    db: Session, user_id: int, date_from: date | None, date_to: date | None
) -> CategorySummary:
    """Total, count and share per category, largest first. Categories without expenses are left out."""
    if date_from and date_to and date_from > date_to:
        raise InvalidInputError("query.date_from", "date_from must not be after date_to")

    rows = expenses.totals_by_category(db, user_id, date_from=date_from, date_to=date_to)
    rows.sort(key=lambda row: (-row.total_minor, row.category_name.casefold()))
    overall = sum(row.total_minor for row in rows)

    return CategorySummary(
        date_from=date_from,
        date_to=date_to,
        categories=[
            CategoryTotalOut(
                category_id=row.category_id,
                category_name=row.category_name,
                total=from_minor(row.total_minor),
                count=row.count,
                # overall is above zero whenever there is a row, because amounts are positive.
                share=percent(row.total_minor, overall),
            )
            for row in rows
        ],
        total=from_minor(overall),
        count=sum(row.count for row in rows),
    )


def trends(db: Session, user_id: int, months: int, today: date) -> Trends:
    """The last `months` calendar months ending with the current one.

    Each month is compared with the month before it. The month before the
    window is read too, so the first month in the window also has a change.
    """
    current = month_start(today)
    first = add_months(current, -(months - 1))
    before_first = add_months(first, -1)
    totals = _totals_for_months(db, user_id, before_first, current)

    items = []
    previous_total = totals.get(before_first, (0, 0))[0]
    window_total = 0
    for month in months_between(first, current):
        total, count = totals.get(month, (0, 0))
        change = total - previous_total
        items.append(
            TrendMonth(
                month=format_month(month),
                total=from_minor(total),
                count=count,
                change=from_minor(change),
                change_percent=percent(change, previous_total),
            )
        )
        window_total += total
        previous_total = total

    return Trends(
        months=items,
        total=from_minor(window_total),
        average_monthly_total=from_minor(divide_minor(window_total, months)),
    )
