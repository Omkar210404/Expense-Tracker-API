"""Filters, sorting and pagination on GET /expenses.

Every test uses the same eight expenses, so the expected results can be read
straight from the table below.
"""

import pytest

from tests.conftest import add_expense, category_id

# (label, amount, date, category, payment method, note)
EXPENSES = [
    ("rent", "12000.00", "2026-05-01", "Housing", "bank_transfer", "May rent"),
    ("bus", "45.00", "2026-05-03", "Transport", "upi", "Bus pass top-up"),
    ("lunch", "250.00", "2026-05-15", "Food", "upi", "Lunch with Priya"),
    ("power", "1830.75", "2026-05-31", "Utilities", "card", "Electricity bill"),
    ("taxi", "320.00", "2026-06-01", "Transport", "cash", "Taxi to the airport"),
    ("dinner", "899.50", "2026-06-05", "Food", "card", "Team DINNER, 100% worth it"),
    ("chai", "20.00", "2026-06-05", "Food", "cash", None),
    ("books", "640.00", "2026-06-12", "Education", "card", "Python_book and notes"),
]


@pytest.fixture
def ids(client, alice):
    """Create the eight expenses. Returns label -> id."""
    created = {}
    for label, amount, date, category, method, note in EXPENSES:
        expense = add_expense(
            client, alice, amount=amount, date=date, category=category, payment_method=method, note=note
        )
        created[label] = expense["id"]
    return created


def listed(client, headers, ids, **params):
    """The labels of the expenses returned for these query parameters, in order."""
    params.setdefault("page_size", 100)
    response = client.get("/expenses", params=params, headers=headers)
    assert response.status_code == 200, response.text
    labels = {expense_id: label for label, expense_id in ids.items()}
    return [labels[item["id"]] for item in response.json()["items"]]


def test_default_order_is_newest_first(client, alice, ids):
    # chai and dinner share a date; the later one created comes first.
    assert listed(client, alice, ids) == ["books", "chai", "dinner", "taxi", "power", "lunch", "bus", "rent"]


def test_empty_list_for_a_new_user(client, alice):
    response = client.get("/expenses", headers=alice)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20, "pages": 0}


# --- filters --------------------------------------------------------------


def test_date_from_is_inclusive(client, alice, ids):
    assert listed(client, alice, ids, date_from="2026-06-05") == ["books", "chai", "dinner"]


def test_date_to_is_inclusive(client, alice, ids):
    assert listed(client, alice, ids, date_to="2026-05-03") == ["bus", "rent"]


def test_date_range_includes_both_ends(client, alice, ids):
    assert listed(client, alice, ids, date_from="2026-05-31", date_to="2026-06-01") == ["taxi", "power"]


def test_date_range_of_one_day(client, alice, ids):
    assert listed(client, alice, ids, date_from="2026-06-05", date_to="2026-06-05") == ["chai", "dinner"]


def test_date_range_with_nothing_in_it(client, alice, ids):
    assert listed(client, alice, ids, date_from="2026-04-01", date_to="2026-04-30") == []


def test_filter_by_category(client, alice, ids):
    food = category_id(client, alice, "Food")
    assert listed(client, alice, ids, category_id=food) == ["chai", "dinner", "lunch"]


def test_filter_by_a_category_with_no_expenses(client, alice, ids):
    health = category_id(client, alice, "Health")
    assert listed(client, alice, ids, category_id=health) == []


def test_filter_by_an_unknown_category_is_empty_not_an_error(client, alice, ids):
    assert listed(client, alice, ids, category_id=999999) == []


def test_min_amount_is_inclusive(client, alice, ids):
    assert listed(client, alice, ids, min_amount="899.50") == ["dinner", "power", "rent"]


def test_max_amount_is_inclusive(client, alice, ids):
    assert listed(client, alice, ids, max_amount="45") == ["chai", "bus"]


def test_amount_range(client, alice, ids):
    assert listed(client, alice, ids, min_amount="250", max_amount="640") == ["books", "taxi", "lunch"]


def test_filter_by_payment_method(client, alice, ids):
    assert listed(client, alice, ids, payment_method="card") == ["books", "dinner", "power"]


def test_search_ignores_case(client, alice, ids):
    assert listed(client, alice, ids, q="dinner") == ["dinner"]
    assert listed(client, alice, ids, q="LUNCH") == ["lunch"]


def test_search_matches_part_of_the_note(client, alice, ids):
    assert listed(client, alice, ids, q="bil") == ["power"]
    assert listed(client, alice, ids, q="t") == ["books", "dinner", "taxi", "power", "lunch", "bus", "rent"]


def test_search_does_not_match_expenses_without_a_note(client, alice, ids):
    assert "chai" not in listed(client, alice, ids, q="a")


def test_search_treats_percent_and_underscore_as_plain_text(client, alice, ids):
    # In SQL LIKE these are wildcards; here they must match only themselves.
    assert listed(client, alice, ids, q="100%") == ["dinner"]
    assert listed(client, alice, ids, q="%") == ["dinner"]
    assert listed(client, alice, ids, q="_") == ["books"]
    assert listed(client, alice, ids, q="python_book") == ["books"]


def test_search_with_no_match(client, alice, ids):
    assert listed(client, alice, ids, q="zzz") == []


def test_blank_search_is_ignored(client, alice, ids):
    assert len(listed(client, alice, ids, q="   ")) == 8


def test_filters_combine_with_and(client, alice, ids):
    food = category_id(client, alice, "Food")

    assert listed(client, alice, ids, category_id=food, date_from="2026-06-01") == ["chai", "dinner"]
    assert listed(client, alice, ids, category_id=food, date_from="2026-06-01", min_amount="100") == ["dinner"]
    assert listed(
        client, alice, ids,
        category_id=food, date_from="2026-06-01", min_amount="100", payment_method="card", q="team",
    ) == ["dinner"]
    assert listed(
        client, alice, ids,
        category_id=food, date_from="2026-06-01", min_amount="100", payment_method="cash",
    ) == []


# --- sorting --------------------------------------------------------------


def test_sort_by_date_ascending(client, alice, ids):
    assert listed(client, alice, ids, sort="date", order="asc") == [
        "rent", "bus", "lunch", "power", "taxi", "dinner", "chai", "books",
    ]


def test_sort_by_amount(client, alice, ids):
    assert listed(client, alice, ids, sort="amount", order="desc") == [
        "rent", "power", "dinner", "books", "taxi", "lunch", "bus", "chai",
    ]
    assert listed(client, alice, ids, sort="amount", order="asc") == [
        "chai", "bus", "lunch", "taxi", "books", "dinner", "power", "rent",
    ]


def test_sort_by_created_at(client, alice, ids):
    assert listed(client, alice, ids, sort="created_at", order="asc") == [label for label, *_ in EXPENSES]


# --- pagination -----------------------------------------------------------


def test_pagination_walks_through_every_expense_once(client, alice, ids):
    seen = []
    for page in (1, 2, 3):
        response = client.get("/expenses", params={"page": page, "page_size": 3}, headers=alice)
        body = response.json()
        assert (body["total"], body["page"], body["page_size"], body["pages"]) == (8, page, 3, 3)
        seen.extend(item["id"] for item in body["items"])

    assert len(seen) == 8
    assert sorted(seen) == sorted(ids.values())


def test_page_sizes(client, alice, ids):
    assert listed(client, alice, ids, page=1, page_size=3) == ["books", "chai", "dinner"]
    assert listed(client, alice, ids, page=2, page_size=3) == ["taxi", "power", "lunch"]
    assert listed(client, alice, ids, page=3, page_size=3) == ["bus", "rent"]


def test_page_past_the_end_is_empty_but_keeps_the_totals(client, alice, ids):
    response = client.get("/expenses", params={"page": 9, "page_size": 3}, headers=alice)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 8, "page": 9, "page_size": 3, "pages": 3}


def test_total_counts_the_filtered_expenses(client, alice, ids):
    food = category_id(client, alice, "Food")

    body = client.get("/expenses", params={"category_id": food, "page_size": 2}, headers=alice).json()

    assert body["total"] == 3
    assert body["pages"] == 2
    assert len(body["items"]) == 2


def test_default_page_size_is_20(client, alice):
    for _ in range(21):
        add_expense(client, alice)

    body = client.get("/expenses", headers=alice).json()

    assert (len(body["items"]), body["total"], body["page_size"], body["pages"]) == (20, 21, 20, 2)


# --- invalid query parameters ----------------------------------------------


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"page": 0}, "query.page"),
        ({"page": -1}, "query.page"),
        ({"page": "two"}, "query.page"),
        ({"page_size": 0}, "query.page_size"),
        ({"page_size": 101}, "query.page_size"),
        ({"date_from": "2026-02-30"}, "query.date_from"),
        ({"date_to": "June"}, "query.date_to"),
        ({"min_amount": "-1"}, "query.min_amount"),
        ({"max_amount": "abc"}, "query.max_amount"),
        ({"max_amount": "1.234"}, "query.max_amount"),
        ({"category_id": "food"}, "query.category_id"),
        ({"payment_method": "cheque"}, "query.payment_method"),
        ({"sort": "note"}, "query.sort"),
        ({"order": "up"}, "query.order"),
        ({"q": "x" * 101}, "query.q"),
        ({"date_from": "2026-06-02", "date_to": "2026-06-01"}, "query.date_from"),
        ({"min_amount": "500", "max_amount": "100"}, "query.min_amount"),
    ],
)
def test_invalid_query_parameters(client, alice, params, field):
    response = client.get("/expenses", params=params, headers=alice)

    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["field"] == field


def test_page_size_limits_are_accepted(client, alice):
    assert client.get("/expenses", params={"page_size": 1}, headers=alice).status_code == 200
    assert client.get("/expenses", params={"page_size": 100}, headers=alice).status_code == 200
