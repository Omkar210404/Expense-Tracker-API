"""Conversion between decimal amounts and the integer minor units that are stored."""

from decimal import ROUND_HALF_UP, Decimal

MINOR_PER_UNIT = 100
_CENT = Decimal("0.01")


def to_minor(amount: Decimal) -> int:
    """`Decimal("12.50")` -> `1250`. Refuses an amount with more than two decimal places."""
    minor = amount * MINOR_PER_UNIT
    if minor != minor.to_integral_value():
        raise ValueError(f"{amount} has more than two decimal places")
    return int(minor)


def from_minor(minor: int) -> Decimal:
    """`1250` -> `Decimal("12.50")`, always with two decimal places."""
    return (Decimal(minor) / MINOR_PER_UNIT).quantize(_CENT)


def percent(part: int, whole: int) -> float | None:
    """`part` as a percentage of `whole`, one decimal place. `None` when `whole` is zero."""
    if whole == 0:
        return None
    value = Decimal(part) * 100 / Decimal(whole)
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def divide_minor(total: int, count: int) -> int:
    """`total / count` rounded half up to a whole minor unit."""
    return int((Decimal(total) / Decimal(count)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
