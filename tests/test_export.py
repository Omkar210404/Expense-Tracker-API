import csv
import io

import pytest

from app.services.export import neutralise
from tests.conftest import add_expense, category_id

HEADER = ["id", "date", "amount", "category", "payment_method", "note"]


def export(client, headers, **params):
    response = client.get("/expenses/export", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response


def rows(response):
    return list(csv.reader(io.StringIO(response.text)))


def test_export_headers(client, alice):
    response = export(client, alice)

    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="expenses.csv"'


def test_export_with_no_expenses_is_just_the_header(client, alice):
    assert export(client, alice).text == "id,date,amount,category,payment_method,note\r\n"


def test_export_rows_oldest_first(client, alice):
    lunch = add_expense(client, alice, amount="250", date="2026-06-10", category="Food", payment_method="upi", note="Lunch")
    rent = add_expense(client, alice, amount="12000.5", date="2026-05-01", category="Housing", payment_method="bank_transfer", note="May rent")
    chai = add_expense(client, alice, amount="20", date="2026-06-10", category="Food", payment_method="cash")

    assert rows(export(client, alice)) == [
        HEADER,
        [str(rent["id"]), "2026-05-01", "12000.50", "Housing", "bank_transfer", "May rent"],
        [str(lunch["id"]), "2026-06-10", "250.00", "Food", "upi", "Lunch"],
        [str(chai["id"]), "2026-06-10", "20.00", "Food", "cash", ""],
    ]


def test_export_is_not_paginated(client, alice):
    for _ in range(120):
        add_expense(client, alice)

    assert len(rows(export(client, alice))) == 121


def test_export_ignores_pagination_parameters(client, alice):
    for _ in range(3):
        add_expense(client, alice)

    assert len(rows(export(client, alice, page=2, page_size=1))) == 4


@pytest.mark.parametrize(
    "note",
    [
        "Dinner, drinks and dessert",
        'She said "keep the change"',
        "First line\nSecond line",
        "Semi;colon and\ttab",
        "Café ☕ ₹500 खाना",
        "  not trimmed inside  the note",
    ],
)
def test_awkward_notes_survive_the_round_trip(client, alice, note):
    created = add_expense(client, alice, note=note)

    exported = rows(export(client, alice))

    assert len(exported) == 2
    assert exported[1][5] == created["note"]


def test_export_applies_the_same_filters_as_the_list(client, alice):
    add_expense(client, alice, amount="100", date="2026-05-01", category="Food", payment_method="cash", note="May food")
    add_expense(client, alice, amount="200", date="2026-06-01", category="Food", payment_method="card", note="June food")
    add_expense(client, alice, amount="300", date="2026-06-02", category="Transport", payment_method="card", note="June taxi")
    food = category_id(client, alice, "Food")

    def notes(**params):
        return [row[5] for row in rows(export(client, alice, **params))[1:]]

    assert notes() == ["May food", "June food", "June taxi"]
    assert notes(date_from="2026-06-01") == ["June food", "June taxi"]
    assert notes(date_to="2026-05-31") == ["May food"]
    assert notes(category_id=food) == ["May food", "June food"]
    assert notes(min_amount="150", max_amount="250") == ["June food"]
    assert notes(payment_method="card") == ["June food", "June taxi"]
    assert notes(q="TAXI") == ["June taxi"]
    assert notes(category_id=food, payment_method="card") == ["June food"]
    assert notes(q="nothing") == []


def test_export_refuses_invalid_filters(client, alice):
    for params in ({"date_from": "2026-06-02", "date_to": "2026-06-01"}, {"min_amount": "abc"}):
        response = client.get("/expenses/export", params=params, headers=alice)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_export_is_not_mistaken_for_an_expense_id(client, alice):
    # /expenses/export is declared before /expenses/{expense_id}.
    assert client.get("/expenses/export", headers=alice).headers["content-type"].startswith("text/csv")


def test_export_needs_a_token(client):
    response = client.get("/expenses/export")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# --- spreadsheet formula injection ------------------------------------------


@pytest.mark.parametrize(
    ("text", "safe"),
    [
        ("=SUM(A1:A9)", "'=SUM(A1:A9)"),
        ("+91 98765 43210", "'+91 98765 43210"),
        ("-50 refund", "'-50 refund"),
        ("@home", "'@home"),
        ("\tTabbed", "'\tTabbed"),
        ("Lunch = good", "Lunch = good"),
        ("Lunch", "Lunch"),
        ("", ""),
        (None, ""),
    ],
)
def test_neutralise(text, safe):
    assert neutralise(text) == safe


def test_formula_in_a_note_is_exported_as_text(client, alice):
    add_expense(client, alice, note='=HYPERLINK("http://example.com","click")')

    assert rows(export(client, alice))[1][5] == '\'=HYPERLINK("http://example.com","click")'


def test_formula_in_a_category_name_is_exported_as_text(client, alice):
    response = client.post("/categories", json={"name": "=cmd"}, headers=alice)
    add_expense(client, alice, category_id=response.json()["id"])

    assert rows(export(client, alice))[1][3] == "'=cmd"


def test_the_stored_note_is_not_changed_by_the_export(client, alice):
    created = add_expense(client, alice, note="=1+1")
    export(client, alice)

    assert client.get(f"/expenses/{created['id']}", headers=alice).json()["note"] == "=1+1"
