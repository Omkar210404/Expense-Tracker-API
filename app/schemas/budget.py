from pydantic import BaseModel, Field

from app.models import Budget
from app.money import from_minor
from app.months import format_month
from app.schemas.common import AmountIn, AmountOut, MonthStr, ResourceId


class BudgetCreate(BaseModel):
    category_id: ResourceId
    month: MonthStr
    amount: AmountIn


class BudgetUpdate(BaseModel):
    amount: AmountIn


class BudgetOut(BaseModel):
    id: int
    category_id: int
    category_name: str = Field(examples=["Food"])
    month: str = Field(examples=["2026-06"])
    amount: AmountOut

    @classmethod
    def from_model(cls, budget: Budget) -> "BudgetOut":
        return cls(
            id=budget.id,
            category_id=budget.category_id,
            category_name=budget.category.name,
            month=format_month(budget.month),
            amount=from_minor(budget.amount_minor),
        )


class BudgetStatusItem(BaseModel):
    """One budgeted category: what was planned and what was spent."""

    budget_id: int
    category_id: int
    category_name: str
    budget: AmountOut
    spent: AmountOut
    remaining: AmountOut = Field(description="budget minus spent; negative when over budget")
    percent_used: float = Field(description="spent as a percentage of budget, one decimal", examples=[62.5])
    over_budget: bool


class UnbudgetedItem(BaseModel):
    """Spending in a category that has no budget for the month."""

    category_id: int
    category_name: str
    spent: AmountOut


class BudgetTotals(BaseModel):
    budget: AmountOut = Field(description="Sum of the month's budgets")
    spent: AmountOut = Field(description="Spending in the budgeted categories only")
    remaining: AmountOut
    percent_used: float | None = Field(description="null when the month has no budgets")


class BudgetStatus(BaseModel):
    month: str = Field(examples=["2026-06"])
    items: list[BudgetStatusItem]
    totals: BudgetTotals
    unbudgeted: list[UnbudgetedItem]
    unbudgeted_spent: AmountOut = Field(description="Spending in categories without a budget")
    total_spent: AmountOut = Field(description="All spending in the month, budgeted or not")
