"""Summary endpoints, checked against values worked out by hand.

"Today" is 2026-06-15 in the tests. The data set:

    2026-01-10  Food        100.00
    2026-03-05  Food        300.00
    2026-03-20  Transport   100.00
    2026-05-01  Housing    1000.00
    2026-05-31  Food        200.00
    2026-06-01  Food        450.00
    2026-06-15  Transport   150.50

    Per month:    Jan 100.00 (1)  Feb 0  Mar 400.00 (2)  Apr 0  May 1200.00 (2)  Jun 600.50 (2)
    Per category: Food 1050.00 (4)  Housing 1000.00 (1)  Transport 250.50 (2)
    Overall:      2300.50 in 7 expenses
"""

import pytest

from tests.conftest import add_expense, category_id

DATA = [
    ("2026-01-10", "Food", "100.00"),
    ("2026-03-05", "Food", "300.00"),
    ("2026-03-20", "Transport", "100.00"),
    ("2026-05-01", "Housing", "1000.00"),
    ("2026-05-31", "Food", "200.00"),
    ("2026-06-01", "Food", "450.00"),
    ("2026-06-15", "Transport", "150.50"),
]


@pytest.fixture
def data(client, alice):
    for date, category, amount in DATA:
        add_expense(client, alice, date=date, category=category, amount=amount)


def get(client, headers, path, **params):
    response = client.get(path, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def month_rows(summary):
    return [(row["month"], row["total"], row["count"]) for row in summary["months"]]


# --- /summary/monthly -------------------------------------------------------


def test_monthly_covers_first_to_last_expense_and_fills_empty_months(client, alice, data):
    summary = get(client, alice, "/summary/monthly")

    assert month_rows(summary) == [
        ("2026-01", "100.00", 1),
        ("2026-02", "0.00", 0),
        ("2026-03", "400.00", 2),
        ("2026-04", "0.00", 0),
        ("2026-05", "1200.00", 2),
        ("2026-06", "600.50", 2),
    ]
    assert (summary["total"], summary["count"]) == ("2300.50", 7)


def test_monthly_with_a_range(client, alice, data):
    summary = get(client, alice, "/summary/monthly", **{"from": "2026-03", "to": "2026-05"})

    assert month_rows(summary) == [("2026-03", "400.00", 2), ("2026-04", "0.00", 0), ("2026-05", "1200.00", 2)]
    assert (summary["total"], summary["count"]) == ("1600.00", 4)


def test_monthly_with_only_a_start(client, alice, data):
    summary = get(client, alice, "/summary/monthly", **{"from": "2026-05"})

    assert month_rows(summary) == [("2026-05", "1200.00", 2), ("2026-06", "600.50", 2)]


def test_monthly_with_only_an_end(client, alice, data):
    summary = get(client, alice, "/summary/monthly", to="2026-02")

    assert month_rows(summary) == [("2026-01", "100.00", 1), ("2026-02", "0.00", 0)]


def test_monthly_single_month(client, alice, data):
    summary = get(client, alice, "/summary/monthly", **{"from": "2026-03", "to": "2026-03"})

    assert month_rows(summary) == [("2026-03", "400.00", 2)]


def test_monthly_range_outside_the_data_is_zero(client, alice, data):
    assert month_rows(get(client, alice, "/summary/monthly", **{"from": "2026-08"})) == [("2026-08", "0.00", 0)]
    assert month_rows(get(client, alice, "/summary/monthly", to="2025-11")) == [("2025-11", "0.00", 0)]
    summary = get(client, alice, "/summary/monthly", **{"from": "2024-01", "to": "2024-03"})
    assert month_rows(summary) == [("2024-01", "0.00", 0), ("2024-02", "0.00", 0), ("2024-03", "0.00", 0)]
    assert (summary["total"], summary["count"]) == ("0.00", 0)


def test_monthly_range_crossing_a_year(client, alice):
    add_expense(client, alice, date="2025-12-31", amount="10")
    add_expense(client, alice, date="2026-01-01", amount="20")

    summary = get(client, alice, "/summary/monthly")

    assert month_rows(summary) == [("2025-12", "10.00", 1), ("2026-01", "20.00", 1)]


def test_monthly_with_no_expenses(client, alice):
    assert get(client, alice, "/summary/monthly") == {"months": [], "total": "0.00", "count": 0}
    assert month_rows(get(client, alice, "/summary/monthly", **{"from": "2026-06"})) == [("2026-06", "0.00", 0)]


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"from": "2026-06", "to": "2026-05"}, "query.from"),
        ({"from": "2026-13"}, "query.from"),
        ({"to": "June"}, "query.to"),
        ({"from": "2026-06-01"}, "query.from"),
    ],
)
def test_monthly_refuses_invalid_months(client, alice, params, field):
    response = client.get("/summary/monthly", params=params, headers=alice)

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == field


# --- /summary/categories ----------------------------------------------------


def test_categories_totals_counts_and_shares(client, alice, data):
    # Shares: 1050.00 / 2300.50 = 45.64 -> 45.6;  1000.00 / 2300.50 = 43.47 -> 43.5;
    #          250.50 / 2300.50 = 10.89 -> 10.9
    summary = get(client, alice, "/summary/categories")

    assert [
        (row["category_name"], row["total"], row["count"], row["share"]) for row in summary["categories"]
    ] == [
        ("Food", "1050.00", 4, 45.6),
        ("Housing", "1000.00", 1, 43.5),
        ("Transport", "250.50", 2, 10.9),
    ]
    assert (summary["total"], summary["count"]) == ("2300.50", 7)
    assert (summary["date_from"], summary["date_to"]) == (None, None)
    assert summary["categories"][0]["category_id"] == category_id(client, alice, "Food")


def test_categories_with_a_date_range(client, alice, data):
    # 2026-05-01 to 2026-06-01, both ends included:
    # Housing 1000.00, Food 200.00 + 450.00 = 650.00. Total 1650.00.
    # Shares: 1000 / 1650 = 60.61 -> 60.6;  650 / 1650 = 39.39 -> 39.4
    summary = get(client, alice, "/summary/categories", date_from="2026-05-01", date_to="2026-06-01")

    assert [
        (row["category_name"], row["total"], row["count"], row["share"]) for row in summary["categories"]
    ] == [("Housing", "1000.00", 1, 60.6), ("Food", "650.00", 2, 39.4)]
    assert (summary["total"], summary["count"]) == ("1650.00", 3)
    assert (summary["date_from"], summary["date_to"]) == ("2026-05-01", "2026-06-01")


def test_categories_with_one_bound(client, alice, data):
    after = get(client, alice, "/summary/categories", date_from="2026-06-01")
    before = get(client, alice, "/summary/categories", date_to="2026-01-31")

    assert [(row["category_name"], row["total"]) for row in after["categories"]] == [
        ("Food", "450.00"), ("Transport", "150.50"),
    ]
    assert [(row["category_name"], row["total"], row["share"]) for row in before["categories"]] == [
        ("Food", "100.00", 100.0),
    ]


def test_categories_equal_totals_are_ordered_by_name(client, alice):
    add_expense(client, alice, category="Transport", amount="50")
    add_expense(client, alice, category="Food", amount="50")

    summary = get(client, alice, "/summary/categories")

    assert [(row["category_name"], row["share"]) for row in summary["categories"]] == [
        ("Food", 50.0), ("Transport", 50.0),
    ]


def test_categories_with_no_expenses(client, alice):
    assert get(client, alice, "/summary/categories") == {
        "date_from": None, "date_to": None, "categories": [], "total": "0.00", "count": 0,
    }


def test_categories_with_nothing_in_the_range(client, alice, data):
    summary = get(client, alice, "/summary/categories", date_from="2026-02-01", date_to="2026-02-28")

    assert (summary["categories"], summary["total"], summary["count"]) == ([], "0.00", 0)


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"date_from": "2026-06-02", "date_to": "2026-06-01"}, "query.date_from"),
        ({"date_from": "2026-02-30"}, "query.date_from"),
        ({"date_to": "2026-06"}, "query.date_to"),
    ],
)
def test_categories_refuses_invalid_dates(client, alice, params, field):
    response = client.get("/summary/categories", params=params, headers=alice)

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == field


# --- /summary/trends --------------------------------------------------------


def trend_rows(summary):
    return [
        (row["month"], row["total"], row["count"], row["change"], row["change_percent"])
        for row in summary["months"]
    ]


def test_trends_default_is_six_months_ending_with_the_current_one(client, alice, data):
    # Window Jan to Jun 2026. The month before the window, Dec 2025, is 0.
    # Jun: 600.50 - 1200.00 = -599.50;  -599.50 / 1200.00 = -49.96% -> -50.0
    # Average: 2300.50 / 6 = 383.4167 -> 383.42
    summary = get(client, alice, "/summary/trends")

    assert trend_rows(summary) == [
        ("2026-01", "100.00", 1, "100.00", None),
        ("2026-02", "0.00", 0, "-100.00", -100.0),
        ("2026-03", "400.00", 2, "400.00", None),
        ("2026-04", "0.00", 0, "-400.00", -100.0),
        ("2026-05", "1200.00", 2, "1200.00", None),
        ("2026-06", "600.50", 2, "-599.50", -50.0),
    ]
    assert summary["total"] == "2300.50"
    assert summary["average_monthly_total"] == "383.42"


def test_trends_first_month_is_compared_with_the_month_before_the_window(client, alice, data):
    # Window Apr to Jun. April is compared with March (400.00), which is outside the window.
    # Average: 1800.50 / 3 = 600.1667 -> 600.17
    summary = get(client, alice, "/summary/trends", months=3)

    assert trend_rows(summary) == [
        ("2026-04", "0.00", 0, "-400.00", -100.0),
        ("2026-05", "1200.00", 2, "1200.00", None),
        ("2026-06", "600.50", 2, "-599.50", -50.0),
    ]
    assert (summary["total"], summary["average_monthly_total"]) == ("1800.50", "600.17")


def test_trends_one_month(client, alice, data):
    summary = get(client, alice, "/summary/trends", months=1)

    assert trend_rows(summary) == [("2026-06", "600.50", 2, "-599.50", -50.0)]
    assert (summary["total"], summary["average_monthly_total"]) == ("600.50", "600.50")


def test_trends_window_crosses_a_year(client, alice, data):
    summary = get(client, alice, "/summary/trends", months=8)

    assert [row["month"] for row in summary["months"]] == [
        "2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06",
    ]
    assert trend_rows(summary)[:2] == [("2025-11", "0.00", 0, "0.00", None), ("2025-12", "0.00", 0, "0.00", None)]
    # 2300.50 / 8 = 287.5625 -> 287.56
    assert summary["average_monthly_total"] == "287.56"


def test_trends_increase_as_a_percentage(client, alice):
    # May 800.00, June 1000.00: +200.00, 200 / 800 = +25.0%
    add_expense(client, alice, date="2026-05-10", amount="800")
    add_expense(client, alice, date="2026-06-10", amount="1000")

    summary = get(client, alice, "/summary/trends", months=1)

    assert trend_rows(summary) == [("2026-06", "1000.00", 1, "200.00", 25.0)]


def test_trends_ignores_expenses_outside_the_window(client, alice):
    add_expense(client, alice, date="2025-01-01", amount="9999")  # long before
    add_expense(client, alice, date="2026-06-16", amount="5")  # tomorrow, still June

    summary = get(client, alice, "/summary/trends", months=2)

    assert trend_rows(summary) == [("2026-05", "0.00", 0, "0.00", None), ("2026-06", "5.00", 1, "5.00", None)]


def test_trends_with_no_expenses(client, alice):
    summary = get(client, alice, "/summary/trends")

    assert len(summary["months"]) == 6
    assert all(row == (row[0], "0.00", 0, "0.00", None) for row in trend_rows(summary))
    assert (summary["total"], summary["average_monthly_total"]) == ("0.00", "0.00")


def test_trends_longest_window(client, alice, data):
    summary = get(client, alice, "/summary/trends", months=36)

    assert len(summary["months"]) == 36
    assert (summary["months"][0]["month"], summary["months"][-1]["month"]) == ("2023-07", "2026-06")
    assert summary["total"] == "2300.50"


@pytest.mark.parametrize("months", [0, -1, 37, "six"])
def test_trends_refuses_an_invalid_window(client, alice, months):
    response = client.get("/summary/trends", params={"months": months}, headers=alice)

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "query.months"


def test_summaries_need_a_token(client):
    for path in ("/summary/monthly", "/summary/categories", "/summary/trends"):
        assert client.get(path).status_code == 401
