from decimal import Decimal

import pytest

from app.money import divide_minor, from_minor, percent, to_minor


@pytest.mark.parametrize(
    ("amount", "minor"),
    [("0.01", 1), ("1", 100), ("12.5", 1250), ("12.50", 1250), ("9999999.99", 999999999)],
)
def test_to_minor(amount, minor):
    assert to_minor(Decimal(amount)) == minor


def test_to_minor_refuses_a_third_decimal_place():
    with pytest.raises(ValueError):
        to_minor(Decimal("1.005"))


@pytest.mark.parametrize(
    ("minor", "text"),
    [(1, "0.01"), (100, "1.00"), (1250, "12.50"), (0, "0.00"), (-5000, "-50.00")],
)
def test_from_minor_always_has_two_decimals(minor, text):
    assert str(from_minor(minor)) == text


def test_round_trip_is_exact():
    # 0.1 + 0.2 is the classic float failure; in minor units it is exact.
    assert from_minor(to_minor(Decimal("0.10")) + to_minor(Decimal("0.20"))) == Decimal("0.30")


def test_percent():
    assert percent(2500, 10000) == 25.0
    assert percent(1, 3) == 33.3
    assert percent(2, 3) == 66.7
    assert percent(15000, 10000) == 150.0
    assert percent(-2500, 10000) == -25.0


def test_percent_of_zero_is_none():
    assert percent(500, 0) is None


def test_divide_minor_rounds_half_up():
    assert divide_minor(100, 3) == 33
    assert divide_minor(200, 3) == 67
    assert divide_minor(5, 2) == 3
