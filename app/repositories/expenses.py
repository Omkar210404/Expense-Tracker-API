from dataclasses import dataclass
from datetime import date

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.models import Category, Expense


@dataclass(frozen=True)
class ExpenseFilters:
    """Filters for the expense list and the CSV export. All are optional and combine with AND."""

    date_from: date | None = None
    date_to: date | None = None
    category_id: int | None = None
    min_amount_minor: int | None = None
    max_amount_minor: int | None = None
    payment_method: str | None = None
    search: str | None = None


SORT_COLUMNS = {
    "date": Expense.date,
    "amount": Expense.amount_minor,
    "created_at": Expense.created_at,
}


def _conditions(user_id: int, filters: ExpenseFilters) -> list:
    # The user filter is always first and is never optional.
    conditions = [Expense.user_id == user_id]
    if filters.date_from is not None:
        conditions.append(Expense.date >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(Expense.date <= filters.date_to)
    if filters.category_id is not None:
        conditions.append(Expense.category_id == filters.category_id)
    if filters.min_amount_minor is not None:
        conditions.append(Expense.amount_minor >= filters.min_amount_minor)
    if filters.max_amount_minor is not None:
        conditions.append(Expense.amount_minor <= filters.max_amount_minor)
    if filters.payment_method is not None:
        conditions.append(Expense.payment_method == filters.payment_method)
    if filters.search:
        # autoescape: a "%" or "_" typed by the user is matched literally.
        conditions.append(Expense.note.icontains(filters.search, autoescape=True))
    return conditions


def add(
    db: Session,
    user_id: int,
    *,
    category: Category,
    amount_minor: int,
    date: date,
    note: str | None,
    payment_method: str,
) -> Expense:
    expense = Expense(
        user_id=user_id,
        category=category,
        amount_minor=amount_minor,
        date=date,
        note=note,
        payment_method=payment_method,
    )
    db.add(expense)
    db.flush()
    return expense


def get(db: Session, user_id: int, expense_id: int) -> Expense | None:
    return db.scalar(select(Expense).where(Expense.user_id == user_id, Expense.id == expense_id))


def delete(db: Session, expense: Expense) -> None:
    db.delete(expense)
    db.flush()


def count(db: Session, user_id: int, filters: ExpenseFilters) -> int:
    query = select(func.count()).select_from(Expense).where(*_conditions(user_id, filters))
    return db.scalar(query) or 0


def list_page(
    db: Session,
    user_id: int,
    filters: ExpenseFilters,
    *,
    sort: str,
    descending: bool,
    limit: int,
    offset: int,
) -> list[Expense]:
    column = SORT_COLUMNS[sort]
    # The id breaks ties, so the order is stable from one page to the next.
    ordering = (column.desc(), Expense.id.desc()) if descending else (column.asc(), Expense.id.asc())
    query = (
        select(Expense)
        .where(*_conditions(user_id, filters))
        .order_by(*ordering)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(query))


@dataclass(frozen=True)
class CategoryTotal:
    category_id: int
    category_name: str
    total_minor: int
    count: int


@dataclass(frozen=True)
class MonthTotal:
    year: int
    month: int
    total_minor: int
    count: int


def totals_by_category(
    db: Session, user_id: int, *, date_from: date | None = None, date_to: date | None = None
) -> list[CategoryTotal]:
    """Total and count per category that has at least one expense in the range."""
    filters = ExpenseFilters(date_from=date_from, date_to=date_to)
    query = (
        select(Category.id, Category.name, func.sum(Expense.amount_minor), func.count(Expense.id))
        .select_from(Expense)
        .join(Category, Expense.category_id == Category.id)
        .where(*_conditions(user_id, filters))
        .group_by(Category.id, Category.name)
    )
    return [CategoryTotal(*row) for row in db.execute(query)]


def totals_by_month(
    db: Session, user_id: int, *, date_from: date | None = None, date_to: date | None = None
) -> list[MonthTotal]:
    """Total and count per calendar month that has at least one expense in the range."""
    filters = ExpenseFilters(date_from=date_from, date_to=date_to)
    # extract() is translated for each database, unlike SQLite's strftime().
    year = extract("year", Expense.date)
    month = extract("month", Expense.date)
    query = (
        select(year, month, func.sum(Expense.amount_minor), func.count(Expense.id))
        .where(*_conditions(user_id, filters))
        .group_by(year, month)
        .order_by(year, month)
    )
    return [MonthTotal(int(row[0]), int(row[1]), int(row[2]), int(row[3])) for row in db.execute(query)]


def date_bounds(db: Session, user_id: int) -> tuple[date, date] | None:
    """The dates of the user's earliest and latest expense, or None when there are none."""
    row = db.execute(
        select(func.min(Expense.date), func.max(Expense.date)).where(Expense.user_id == user_id)
    ).one()
    return (row[0], row[1]) if row[0] is not None else None


def list_all(db: Session, user_id: int, filters: ExpenseFilters) -> list[Expense]:
    """Every matching expense, oldest first. Used by the CSV export."""
    query = (
        select(Expense)
        .where(*_conditions(user_id, filters))
        .order_by(Expense.date.asc(), Expense.id.asc())
    )
    return list(db.scalars(query))
