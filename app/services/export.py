import csv
import io

from sqlalchemy.orm import Session

from app.money import from_minor
from app.repositories import expenses
from app.repositories.expenses import ExpenseFilters
from app.services.expenses import check_filters

CSV_COLUMNS = ("id", "date", "amount", "category", "payment_method", "note")

# A spreadsheet runs a cell that starts with one of these as a formula.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def neutralise(text: str | None) -> str:
    """Make a text cell safe to open in a spreadsheet.

    A note such as `=HYPERLINK(...)` would be run as a formula. A leading
    apostrophe makes the spreadsheet treat it as text.
    """
    if not text:
        return ""
    return f"'{text}" if text.startswith(_FORMULA_STARTS) else text


def expenses_csv(db: Session, user_id: int, filters: ExpenseFilters) -> str:
    """The user's matching expenses as CSV text, oldest first, with a header row."""
    check_filters(filters)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for expense in expenses.list_all(db, user_id, filters):
        writer.writerow(
            (
                expense.id,
                expense.date.isoformat(),
                f"{from_minor(expense.amount_minor):.2f}",
                neutralise(expense.category.name),
                expense.payment_method,
                neutralise(expense.note),
            )
        )
    return buffer.getvalue()
