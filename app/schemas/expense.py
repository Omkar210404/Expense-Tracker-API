import datetime as dt
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.models import Expense, PaymentMethod
from app.money import from_minor
from app.schemas.common import AmountIn, AmountOut, ResourceId

Note = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=500),
    Field(examples=["Lunch with the team"]),
]


def _blank_to_none(value: str | None) -> str | None:
    return value or None


class ExpenseCreate(BaseModel):
    amount: AmountIn
    category_id: ResourceId
    date: dt.date = Field(examples=["2026-06-10"])
    note: Note | None = None
    payment_method: PaymentMethod

    _blank_note = field_validator("note")(_blank_to_none)


class ExpenseUpdate(BaseModel):
    """Send only the fields to change. `note` may be set to null to clear it."""

    amount: AmountIn | None = None
    category_id: ResourceId | None = None
    date: dt.date | None = Field(default=None, examples=["2026-06-10"])
    note: Note | None = None
    payment_method: PaymentMethod | None = None

    _blank_note = field_validator("note")(_blank_to_none)

    @model_validator(mode="after")
    def only_note_may_be_null(self):
        for field in ("amount", "category_id", "date", "payment_method"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ExpenseOut(BaseModel):
    id: int
    amount: AmountOut
    category_id: int
    category_name: str = Field(examples=["Food"])
    date: dt.date
    note: str | None
    payment_method: PaymentMethod
    created_at: dt.datetime
    updated_at: dt.datetime

    @classmethod
    def from_model(cls, expense: Expense) -> "ExpenseOut":
        return cls(
            id=expense.id,
            amount=from_minor(expense.amount_minor),
            category_id=expense.category_id,
            category_name=expense.category.name,
            date=expense.date,
            note=expense.note,
            payment_method=PaymentMethod(expense.payment_method),
            created_at=expense.created_at,
            updated_at=expense.updated_at,
        )


class ExpensePage(BaseModel):
    items: list[ExpenseOut]
    total: int = Field(description="Number of expenses that match the filters")
    page: int
    page_size: int
    pages: int = Field(description="Number of pages at this page size")
