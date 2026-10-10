import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession, Today
from app.schemas.common import MonthStr, error_responses
from app.schemas.summary import CategorySummary, MonthlySummary, Trends
from app.services import summaries as summary_service

router = APIRouter(prefix="/summary", tags=["summary"], responses=error_responses(401, 422))


@router.get("/monthly", response_model=MonthlySummary, summary="Total per month")
def monthly(
    db: DbSession,
    user: CurrentUser,
    from_month: Annotated[
        MonthStr | None, Query(alias="from", description="First month, as YYYY-MM. Default: your first expense")
    ] = None,
    to_month: Annotated[
        MonthStr | None, Query(alias="to", description="Last month, as YYYY-MM. Default: your last expense")
    ] = None,
):
    """Total and number of expenses per month, oldest first. Months without expenses show zero."""
    return summary_service.monthly_summary(db, user.id, from_month, to_month)


@router.get("/categories", response_model=CategorySummary, summary="Total per category")
def categories(
    db: DbSession,
    user: CurrentUser,
    date_from: Annotated[dt.date | None, Query(description="On or after this date")] = None,
    date_to: Annotated[dt.date | None, Query(description="On or before this date")] = None,
):
    """Total, count and share of the overall total per category, largest first."""
    return summary_service.category_summary(db, user.id, date_from, date_to)


@router.get("/trends", response_model=Trends, summary="Month-over-month change")
def trends(
    db: DbSession,
    user: CurrentUser,
    today: Today,
    months: Annotated[int, Query(ge=1, le=36, description="How many months to show, ending with the current one")] = 6,
):
    """Each month's total compared with the month before it. No forecasting."""
    return summary_service.trends(db, user.id, months, today)
