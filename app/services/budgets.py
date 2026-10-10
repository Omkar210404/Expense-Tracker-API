from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ConflictError, InvalidInputError, NotFoundError
from app.models import Budget
from app.money import from_minor, percent, to_minor
from app.months import format_month, month_end, parse_month
from app.repositories import budgets, expenses
from app.schemas.budget import (
    BudgetCreate,
    BudgetStatus,
    BudgetStatusItem,
    BudgetTotals,
    BudgetUpdate,
    UnbudgetedItem,
)
from app.services import categories as categories_service


def _duplicate(category_name: str, month: date) -> ConflictError:
    return ConflictError(
        f"A budget for '{category_name}' in {format_month(month)} already exists. Change it instead."
    )


def create_budget(db: Session, user_id: int, data: BudgetCreate) -> Budget:
    month = parse_month(data.month)
    try:
        category = categories_service.get_category(db, user_id, data.category_id)
    except NotFoundError:
        raise InvalidInputError("body.category_id", "Category not found") from None

    if budgets.get_for_category_and_month(db, user_id, category.id, month) is not None:
        raise _duplicate(category.name, month)

    budget = budgets.add(db, user_id, category=category, month=month, amount_minor=to_minor(data.amount))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate(category.name, month) from None
    return budget


def get_budget(db: Session, user_id: int, budget_id: int) -> Budget:
    """The user's own budget. Another user's budget is reported as not found."""
    budget = budgets.get(db, user_id, budget_id)
    if budget is None:
        raise NotFoundError("Budget not found")
    return budget


def list_budgets(db: Session, user_id: int, month: str | None) -> list[Budget]:
    return budgets.list_for_user(db, user_id, month=parse_month(month) if month else None)


def update_budget(db: Session, user_id: int, budget_id: int, data: BudgetUpdate) -> Budget:
    budget = get_budget(db, user_id, budget_id)
    budget.amount_minor = to_minor(data.amount)
    db.commit()
    return budget


def delete_budget(db: Session, user_id: int, budget_id: int) -> None:
    budgets.delete(db, get_budget(db, user_id, budget_id))
    db.commit()


def budget_status(db: Session, user_id: int, month_text: str) -> BudgetStatus:
    """Spent vs budget for one month.

    Only expenses dated inside the month count. Spending in a category that
    has no budget this month is listed separately, so nothing is hidden.
    """
    month = parse_month(month_text)
    month_budgets = budgets.list_for_user(db, user_id, month=month)
    spending = expenses.totals_by_category(db, user_id, date_from=month, date_to=month_end(month))
    spent_by_category = {row.category_id: row.total_minor for row in spending}

    items = []
    for budget in month_budgets:
        spent = spent_by_category.get(budget.category_id, 0)
        items.append(
            BudgetStatusItem(
                budget_id=budget.id,
                category_id=budget.category_id,
                category_name=budget.category.name,
                budget=from_minor(budget.amount_minor),
                spent=from_minor(spent),
                remaining=from_minor(budget.amount_minor - spent),
                percent_used=percent(spent, budget.amount_minor),
                over_budget=spent > budget.amount_minor,
            )
        )

    budgeted_ids = {budget.category_id for budget in month_budgets}
    unbudgeted_rows = sorted(
        (row for row in spending if row.category_id not in budgeted_ids),
        key=lambda row: (-row.total_minor, row.category_name.casefold()),
    )

    total_budget = sum(budget.amount_minor for budget in month_budgets)
    budgeted_spent = sum(spent_by_category.get(category_id, 0) for category_id in budgeted_ids)
    unbudgeted_spent = sum(row.total_minor for row in unbudgeted_rows)

    return BudgetStatus(
        month=format_month(month),
        items=items,
        totals=BudgetTotals(
            budget=from_minor(total_budget),
            spent=from_minor(budgeted_spent),
            remaining=from_minor(total_budget - budgeted_spent),
            percent_used=percent(budgeted_spent, total_budget),
        ),
        unbudgeted=[
            UnbudgetedItem(
                category_id=row.category_id, category_name=row.category_name, spent=from_minor(row.total_minor)
            )
            for row in unbudgeted_rows
        ],
        unbudgeted_spent=from_minor(unbudgeted_spent),
        total_spent=from_minor(budgeted_spent + unbudgeted_spent),
    )
