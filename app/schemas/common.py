"""Types and models shared by the other schema modules."""

from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, PlainSerializer

from app.months import parse_month

MAX_AMOUNT = Decimal("9999999.99")

# Ids are bounded, so an absurdly large number in a URL or a body is a 422
# and never reaches the database driver.
MAX_ID = 2**31 - 1
ResourceId = Annotated[int, Field(ge=1, le=MAX_ID)]

# Amounts come in as a number or a string with at most two decimal places.
AmountIn = Annotated[Decimal, Field(gt=0, le=MAX_AMOUNT, decimal_places=2, examples=["249.50"])]

# Amounts go out as strings with exactly two decimal places ("249.50"), so no
# client has to round a float.
AmountOut = Annotated[
    Decimal,
    PlainSerializer(lambda value: f"{value:.2f}", return_type=str),
    Field(examples=["249.50"]),
]

def _check_month(value: str) -> str:
    parse_month(value)
    return value


# A calendar month written as YYYY-MM.
MonthStr = Annotated[str, AfterValidator(_check_month), Field(examples=["2026-06"])]


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
    return {
        code: {
            "model": ErrorResponse,
            "description": _ERROR_DOCS[code][0],
            "content": {"application/json": {"example": {"error": _ERROR_DOCS[code][1]}}},
        }
        for code in status_codes
    }


# status code -> (description, example error body) shown on the /docs page
_ERROR_DOCS = {
    401: (
        "Missing, invalid or expired token",
        {"code": "unauthorized", "message": "Not authenticated"},
    ),
    404: (
        "Not found, or it belongs to another user",
        {"code": "not_found", "message": "Expense not found"},
    ),
    409: (
        "Conflict with existing data",
        {"code": "conflict", "message": "You already have a category named 'Food'"},
    ),
    422: (
        "Validation error",
        {
            "code": "validation_error",
            "message": "Request validation failed",
            "details": [{"field": "body.amount", "message": "Input should be greater than 0"}],
        },
    ),
}
