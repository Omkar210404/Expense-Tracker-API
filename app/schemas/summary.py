import datetime as dt

from pydantic import BaseModel, Field

from app.schemas.common import AmountOut


class MonthlyTotal(BaseModel):
    month: str = Field(examples=["2026-06"])
    total: AmountOut
    count: int = Field(description="Number of expenses in the month")


class MonthlySummary(BaseModel):
    months: list[MonthlyTotal] = Field(description="Oldest first. Months without expenses have a zero total")
    total: AmountOut
    count: int


class CategoryTotalOut(BaseModel):
    category_id: int
    category_name: str = Field(examples=["Food"])
    total: AmountOut
    count: int
    share: float = Field(description="Percentage of the overall total, one decimal", examples=[37.5])


class CategorySummary(BaseModel):
    date_from: dt.date | None
    date_to: dt.date | None
    categories: list[CategoryTotalOut] = Field(description="Largest total first. Only categories with expenses")
    total: AmountOut
    count: int


class TrendMonth(BaseModel):
    month: str = Field(examples=["2026-06"])
    total: AmountOut
    count: int
    change: AmountOut = Field(description="This month's total minus the previous month's")
    change_percent: float | None = Field(
        description="change as a percentage of the previous month's total; null when that total is zero"
    )


class Trends(BaseModel):
    months: list[TrendMonth] = Field(description="Oldest first, ending with the current month")
    total: AmountOut
    average_monthly_total: AmountOut = Field(description="total divided by the number of months in the window")
