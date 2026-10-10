"""Types and models shared by the other schema modules."""

import re
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, PlainSerializer, StringConstraints

MAX_AMOUNT = Decimal("9999999.99")

# Amounts come in as a number or a string with at most two decimal places.
AmountIn = Annotated[Decimal, Field(gt=0, le=MAX_AMOUNT, decimal_places=2, examples=["249.50"])]

# Amounts go out as strings with exactly two decimal places ("249.50"), so no
# client has to round a float.
AmountOut = Annotated[
    Decimal,
    PlainSerializer(lambda value: f"{value:.2f}", return_type=str),
    Field(examples=["249.50"]),
]

_MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
MIN_YEAR = 2000
MAX_YEAR = 2100


def parse_month(value: str) -> date:
    """`"2026-06"` -> `date(2026, 6, 1)`."""
    match = _MONTH_PATTERN.match(value)
    if not match:
        raise ValueError("Month must look like YYYY-MM, for example 2026-06")
    year = int(match.group(1))
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError(f"Year must be between {MIN_YEAR} and {MAX_YEAR}")
    return date(year, int(match.group(2)), 1)


def format_month(month: date) -> str:
    return f"{month.year:04d}-{month.month:02d}"


def _check_month(value: str) -> str:
    parse_month(value)
    return value


# A calendar month written as YYYY-MM.
MonthStr = Annotated[str, AfterValidator(_check_month), Field(examples=["2026-06"])]

TrimmedStr = Annotated[str, StringConstraints(strip_whitespace=True)]


class ErrorDetail(BaseModel):
    field: str = Field(examples=["body.amount"])
    message: str = Field(examples=["Input should be greater than 0"])


class ErrorBody(BaseModel):
    code: str = Field(examples=["validation_error"])
    message: str = Field(examples=["Request validation failed"])
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    """The body of every error response."""

    error: ErrorBody


def error_responses(*status_codes: int) -> dict:
    """The `responses=` entry that documents these error codes in OpenAPI."""
    descriptions = {
        401: "Missing, invalid or expired token",
        404: "Not found, or it belongs to another user",
        409: "Conflict with existing data",
        422: "Validation error",
    }
    return {code: {"model": ErrorResponse, "description": descriptions[code]} for code in status_codes}
