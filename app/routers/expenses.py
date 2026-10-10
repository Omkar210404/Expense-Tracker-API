import datetime as dt
import math
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.deps import CurrentUser, DbSession, Today
from app.models import PaymentMethod
from app.money import to_minor
from app.repositories.expenses import ExpenseFilters
from app.schemas.common import MAX_AMOUNT, MAX_ID, ResourceId, error_responses
from app.schemas.expense import ExpenseCreate, ExpenseOut, ExpensePage, ExpenseUpdate
from app.services import expenses as expense_service

router = APIRouter(prefix="/expenses", tags=["expenses"], responses=error_responses(401))

AmountFilter = Annotated[Decimal | None, Query(ge=0, le=MAX_AMOUNT, decimal_places=2)]


def expense_filters(
    date_from: Annotated[dt.date | None, Query(description="On or after this date")] = None,
    date_to: Annotated[dt.date | None, Query(description="On or before this date")] = None,
    category_id: Annotated[int | None, Query(ge=1, le=MAX_ID)] = None,
    min_amount: AmountFilter = None,
    max_amount: AmountFilter = None,
    payment_method: PaymentMethod | None = None,
    q: Annotated[
        str | None, Query(max_length=100, description="Text to find in the note, ignoring case")
    ] = None,
) -> ExpenseFilters:
    """The filters shared by the list and the CSV export."""
    return ExpenseFilters(
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        min_amount_minor=to_minor(min_amount) if min_amount is not None else None,
        max_amount_minor=to_minor(max_amount) if max_amount is not None else None,
        payment_method=payment_method.value if payment_method else None,
        search=q.strip() if q else None,
    )


Filters = Annotated[ExpenseFilters, Depends(expense_filters)]


@router.post(
    "",
    response_model=ExpenseOut,
    status_code=201,
    summary="Create an expense",
    responses=error_responses(422),
)
def create_expense(data: ExpenseCreate, db: DbSession, user: CurrentUser, today: Today):
    return ExpenseOut.from_model(expense_service.create_expense(db, user.id, data, today))


@router.get(
    "",
    response_model=ExpensePage,
    summary="List expenses with filters, sorting and pagination",
    responses=error_responses(422),
)
def list_expenses(
    db: DbSession,
    user: CurrentUser,
    filters: Filters,
    page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Literal["date", "amount", "created_at"] = "date",
    order: Literal["asc", "desc"] = "desc",
):
    """All filters are optional and combine with AND. Date ranges include both ends."""
    items, total = expense_service.list_expenses(
        db, user.id, filters, page=page, page_size=page_size, sort=sort, order=order
    )
    return ExpensePage(
        items=[ExpenseOut.from_model(expense) for expense in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size),
    )


@router.get(
    "/{expense_id}",
    response_model=ExpenseOut,
    summary="Get one expense",
    responses=error_responses(404, 422),
)
def get_expense(expense_id: ResourceId, db: DbSession, user: CurrentUser):
    return ExpenseOut.from_model(expense_service.get_expense(db, user.id, expense_id))


@router.patch(
    "/{expense_id}",
    response_model=ExpenseOut,
    summary="Change an expense",
    responses=error_responses(404, 422),
)
def update_expense(
    expense_id: ResourceId, data: ExpenseUpdate, db: DbSession, user: CurrentUser, today: Today
):
    """Send only the fields to change."""
    return ExpenseOut.from_model(expense_service.update_expense(db, user.id, expense_id, data, today))


@router.delete(
    "/{expense_id}",
    status_code=204,
    summary="Delete an expense",
    responses=error_responses(404, 422),
)
def delete_expense(expense_id: ResourceId, db: DbSession, user: CurrentUser):
    expense_service.delete_expense(db, user.id, expense_id)
    return Response(status_code=204)
