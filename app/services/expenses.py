from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.errors import InvalidInputError, NotFoundError
from app.models import Expense
from app.money import to_minor
from app.repositories import expenses
from app.repositories.expenses import ExpenseFilters
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.services import categories as categories_service

MIN_DATE = date(2000, 1, 1)
# "Today" is the server's UTC date. A user east of UTC can already be on the
# next day, so one day ahead is accepted.
FUTURE_MARGIN = timedelta(days=1)


def _check_date(value: date, today: date) -> None:
    if value < MIN_DATE:
        raise InvalidInputError("body.date", f"Date must not be before {MIN_DATE.isoformat()}")
    if value > today + FUTURE_MARGIN:
        raise InvalidInputError("body.date", "Date must not be in the future")


def _own_category(db: Session, user_id: int, category_id: int):
    """The category for an expense body. It must be one of the caller's own."""
    try:
        return categories_service.get_category(db, user_id, category_id)
    except NotFoundError:
        raise InvalidInputError("body.category_id", "Category not found") from None


def check_filters(filters: ExpenseFilters) -> None:
    if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
        raise InvalidInputError("query.date_from", "date_from must not be after date_to")
    if (
        filters.min_amount_minor is not None
        and filters.max_amount_minor is not None
        and filters.min_amount_minor > filters.max_amount_minor
    ):
        raise InvalidInputError("query.min_amount", "min_amount must not be greater than max_amount")


def create_expense(db: Session, user_id: int, data: ExpenseCreate, today: date) -> Expense:
    _check_date(data.date, today)
    category = _own_category(db, user_id, data.category_id)
    expense = expenses.add(
        db,
        user_id,
        category=category,
        amount_minor=to_minor(data.amount),
        date=data.date,
        note=data.note,
        payment_method=data.payment_method.value,
    )
    db.commit()
    return expense


def get_expense(db: Session, user_id: int, expense_id: int) -> Expense:
    """The user's own expense. Another user's expense is reported as not found."""
    expense = expenses.get(db, user_id, expense_id)
    if expense is None:
        raise NotFoundError("Expense not found")
    return expense


def update_expense(db: Session, user_id: int, expense_id: int, data: ExpenseUpdate, today: date) -> Expense:
    expense = get_expense(db, user_id, expense_id)
    changes = data.model_dump(exclude_unset=True)

    if "date" in changes:
        _check_date(changes["date"], today)
        expense.date = changes["date"]
    if "category_id" in changes:
        expense.category = _own_category(db, user_id, changes["category_id"])
    if "amount" in changes:
        expense.amount_minor = to_minor(changes["amount"])
    if "note" in changes:
        expense.note = changes["note"]
    if "payment_method" in changes:
        expense.payment_method = changes["payment_method"].value

    db.commit()
    return expense


def delete_expense(db: Session, user_id: int, expense_id: int) -> None:
    expenses.delete(db, get_expense(db, user_id, expense_id))
    db.commit()


def list_expenses(
    db: Session,
    user_id: int,
    filters: ExpenseFilters,
    *,
    page: int,
    page_size: int,
    sort: str,
    order: str,
) -> tuple[list[Expense], int]:
    """One page of matching expenses and the total number of matches."""
    check_filters(filters)
    total = expenses.count(db, user_id, filters)
    items = expenses.list_page(
        db,
        user_id,
        filters,
        sort=sort,
        descending=order == "desc",
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return items, total
