from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.deps import CurrentUser, DbSession
from app.schemas.budget import BudgetCreate, BudgetOut, BudgetStatus, BudgetUpdate
from app.schemas.common import MonthStr, ResourceId, error_responses
from app.services import budgets as budget_service

router = APIRouter(prefix="/budgets", tags=["budgets"], responses=error_responses(401))


@router.post(
    "",
    response_model=BudgetOut,
    status_code=201,
    summary="Set a budget for one category in one month",
    responses=error_responses(409, 422),
)
def create_budget(data: BudgetCreate, db: DbSession, user: CurrentUser):
    """A budget covers one month only. It does not carry over to the next month."""
    return BudgetOut.from_model(budget_service.create_budget(db, user.id, data))


@router.get("", response_model=list[BudgetOut], summary="List budgets", responses=error_responses(422))
def list_budgets(
    db: DbSession,
    user: CurrentUser,
    month: Annotated[MonthStr | None, Query(description="Only this month, as YYYY-MM")] = None,
):
    return [BudgetOut.from_model(budget) for budget in budget_service.list_budgets(db, user.id, month)]


# Declared before /{budget_id}, so "status" is not read as an id.
@router.get(
    "/status",
    response_model=BudgetStatus,
    summary="Spent vs budget for one month",
    responses=error_responses(422),
)
def budget_status(
    db: DbSession,
    user: CurrentUser,
    month: Annotated[MonthStr, Query(description="The month to report on, as YYYY-MM")],
):
    """For each budgeted category: budget, spent, remaining and percent used.

    Spending in categories without a budget that month is listed under `unbudgeted`.
    """
    return budget_service.budget_status(db, user.id, month)


@router.get(
    "/{budget_id}",
    response_model=BudgetOut,
    summary="Get one budget",
    responses=error_responses(404, 422),
)
def get_budget(budget_id: ResourceId, db: DbSession, user: CurrentUser):
    return BudgetOut.from_model(budget_service.get_budget(db, user.id, budget_id))


@router.patch(
    "/{budget_id}",
    response_model=BudgetOut,
    summary="Change a budget's amount",
    responses=error_responses(404, 422),
)
def update_budget(budget_id: ResourceId, data: BudgetUpdate, db: DbSession, user: CurrentUser):
    return BudgetOut.from_model(budget_service.update_budget(db, user.id, budget_id, data))


@router.delete(
    "/{budget_id}",
    status_code=204,
    summary="Delete a budget",
    responses=error_responses(404, 422),
)
def delete_budget(budget_id: ResourceId, db: DbSession, user: CurrentUser):
    budget_service.delete_budget(db, user.id, budget_id)
    return Response(status_code=204)
