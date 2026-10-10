import pytest

from tests.conftest import add_expense, category_id


def expense_body(client, headers, **overrides):
    body = {
        "amount": "249.50",
        "category_id": category_id(client, headers, "Food"),
        "date": "2026-06-10",
        "note": "Lunch",
        "payment_method": "upi",
    }
    body.update(overrides)
    return body


def post(client, headers, **overrides):
    return client.post("/expenses", json=expense_body(client, headers, **overrides), headers=headers)


def assert_invalid(response, field):
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert field in [detail["field"] for detail in error["details"]]


# --- create ---------------------------------------------------------------


def test_create_expense(client, alice):
    food = category_id(client, alice, "Food")

    response = post(client, alice)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id", "amount", "category_id", "category_name", "date", "note",
        "payment_method", "created_at", "updated_at",
    }
    assert body["amount"] == "249.50"
    assert body["category_id"] == food
    assert body["category_name"] == "Food"
    assert body["date"] == "2026-06-10"
    assert body["note"] == "Lunch"
    assert body["payment_method"] == "upi"


@pytest.mark.parametrize(
    ("sent", "stored"),
    [("12", "12.00"), ("12.5", "12.50"), (12, "12.00"), (12.5, "12.50"), ("0.01", "0.01"), ("9999999.99", "9999999.99")],
)
def test_amount_is_accepted_as_number_or_string_and_returned_with_two_decimals(client, alice, sent, stored):
    response = post(client, alice, amount=sent)

    assert response.status_code == 201
    assert response.json()["amount"] == stored


@pytest.mark.parametrize("amount", [0, "0", "0.00", -5, "-0.01", "12.345", 12.345, "10000000", "abc", None, ""])
def test_create_refuses_an_invalid_amount(client, alice, amount):
    assert_invalid(post(client, alice, amount=amount), "body.amount")


@pytest.mark.parametrize("date", ["2026-02-30", "2026-13-01", "10/06/2026", "yesterday", "", None, 20260610])
def test_create_refuses_an_invalid_date(client, alice, date):
    assert_invalid(post(client, alice, date=date), "body.date")


def test_date_may_be_today_or_one_day_ahead(client, alice):
    # "Today" is 2026-06-15 in the tests.
    assert post(client, alice, date="2026-06-15").status_code == 201
    assert post(client, alice, date="2026-06-16").status_code == 201


def test_create_refuses_a_date_further_in_the_future(client, alice):
    response = post(client, alice, date="2026-06-17")

    assert_invalid(response, "body.date")
    assert response.json()["error"]["details"][0]["message"] == "Date must not be in the future"


def test_create_refuses_a_date_before_2000(client, alice):
    assert post(client, alice, date="2000-01-01").status_code == 201
    assert_invalid(post(client, alice, date="1999-12-31"), "body.date")


@pytest.mark.parametrize("method", ["cheque", "CASH", "", None])
def test_create_refuses_an_unknown_payment_method(client, alice, method):
    assert_invalid(post(client, alice, payment_method=method), "body.payment_method")


@pytest.mark.parametrize("method", ["cash", "card", "upi", "bank_transfer", "wallet", "other"])
def test_every_payment_method_is_accepted(client, alice, method):
    assert post(client, alice, payment_method=method).json()["payment_method"] == method


def test_create_refuses_a_note_that_is_too_long(client, alice):
    assert post(client, alice, note="x" * 500).status_code == 201
    assert_invalid(post(client, alice, note="x" * 501), "body.note")


def test_note_is_optional_and_blank_becomes_null(client, alice):
    body = expense_body(client, alice)
    del body["note"]
    assert client.post("/expenses", json=body, headers=alice).json()["note"] is None
    assert post(client, alice, note="   ").json()["note"] is None
    assert post(client, alice, note=None).json()["note"] is None


def test_note_is_trimmed(client, alice):
    assert post(client, alice, note="  Lunch  ").json()["note"] == "Lunch"


def test_create_refuses_an_unknown_category(client, alice):
    response = post(client, alice, category_id=999999)

    assert_invalid(response, "body.category_id")
    assert response.json()["error"]["details"][0]["message"] == "Category not found"


@pytest.mark.parametrize("missing", ["amount", "category_id", "date", "payment_method"])
def test_create_needs_every_required_field(client, alice, missing):
    body = expense_body(client, alice)
    del body[missing]

    assert_invalid(client.post("/expenses", json=body, headers=alice), f"body.{missing}")


def test_body_that_is_not_json_is_a_validation_error(client, alice):
    response = client.post(
        "/expenses", content="not json", headers={**alice, "Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- read -----------------------------------------------------------------


def test_get_expense(client, alice):
    created = post(client, alice).json()

    response = client.get(f"/expenses/{created['id']}", headers=alice)

    assert response.status_code == 200
    assert response.json() == created


def test_unknown_expense_is_not_found(client, alice):
    for response in (
        client.get("/expenses/999999", headers=alice),
        client.patch("/expenses/999999", json={"note": "x"}, headers=alice),
        client.delete("/expenses/999999", headers=alice),
    ):
        assert response.status_code == 404
        assert response.json()["error"] == {"code": "not_found", "message": "Expense not found"}


@pytest.mark.parametrize("bad_id", ["abc", "0", "-1", "99999999999999999999"])
def test_invalid_expense_id_is_a_validation_error(client, alice, bad_id):
    assert_invalid(client.get(f"/expenses/{bad_id}", headers=alice), "path.expense_id")


# --- update ---------------------------------------------------------------


def test_update_one_field_leaves_the_others(client, alice):
    created = post(client, alice).json()

    response = client.patch(f"/expenses/{created['id']}", json={"amount": "300"}, headers=alice)

    assert response.status_code == 200
    updated = response.json()
    assert updated["amount"] == "300.00"
    for field in ("id", "category_id", "category_name", "date", "note", "payment_method", "created_at"):
        assert updated[field] == created[field]
    assert client.get(f"/expenses/{created['id']}", headers=alice).json() == updated


def test_update_every_field(client, alice):
    created = post(client, alice).json()
    transport = category_id(client, alice, "Transport")

    response = client.patch(
        f"/expenses/{created['id']}",
        json={
            "amount": "80.25",
            "category_id": transport,
            "date": "2026-05-31",
            "note": "Taxi",
            "payment_method": "cash",
        },
        headers=alice,
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["amount"] == "80.25"
    assert updated["category_id"] == transport
    assert updated["category_name"] == "Transport"
    assert updated["date"] == "2026-05-31"
    assert updated["note"] == "Taxi"
    assert updated["payment_method"] == "cash"
    assert updated["updated_at"] >= created["updated_at"]


def test_update_can_clear_the_note(client, alice):
    created = post(client, alice).json()

    response = client.patch(f"/expenses/{created['id']}", json={"note": None}, headers=alice)

    assert response.status_code == 200
    assert response.json()["note"] is None


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"amount": 0}, "body.amount"),
        ({"amount": "-1"}, "body.amount"),
        ({"amount": "1.999"}, "body.amount"),
        ({"date": "2026-02-30"}, "body.date"),
        ({"date": "2026-06-17"}, "body.date"),
        ({"payment_method": "cheque"}, "body.payment_method"),
        ({"category_id": 999999}, "body.category_id"),
        ({"note": "x" * 501}, "body.note"),
    ],
)
def test_update_validates_like_create(client, alice, change, field):
    created = post(client, alice).json()

    assert_invalid(client.patch(f"/expenses/{created['id']}", json=change, headers=alice), field)
    assert client.get(f"/expenses/{created['id']}", headers=alice).json() == created


@pytest.mark.parametrize("field", ["amount", "category_id", "date", "payment_method"])
def test_update_refuses_null_for_a_required_field(client, alice, field):
    created = post(client, alice).json()

    response = client.patch(f"/expenses/{created['id']}", json={field: None}, headers=alice)

    assert response.status_code == 422
    assert f"{field} cannot be null" in response.text
    assert client.get(f"/expenses/{created['id']}", headers=alice).json() == created


# --- delete ---------------------------------------------------------------


def test_delete_expense(client, alice):
    created = post(client, alice).json()

    response = client.delete(f"/expenses/{created['id']}", headers=alice)

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/expenses/{created['id']}", headers=alice).status_code == 404
    assert client.delete(f"/expenses/{created['id']}", headers=alice).status_code == 404


# --- categories and expenses together --------------------------------------


def test_category_in_use_cannot_be_deleted(client, alice):
    food = category_id(client, alice, "Food")
    expense = add_expense(client, alice, category_id=food)

    response = client.delete(f"/categories/{food}", headers=alice)

    assert response.status_code == 409
    assert "1 expense" in response.json()["error"]["message"]

    client.delete(f"/expenses/{expense['id']}", headers=alice)
    assert client.delete(f"/categories/{food}", headers=alice).status_code == 204


def test_renaming_a_category_shows_on_its_expenses(client, alice):
    food = category_id(client, alice, "Food")
    expense = add_expense(client, alice, category_id=food)

    client.patch(f"/categories/{food}", json={"name": "Eating out"}, headers=alice)

    assert client.get(f"/expenses/{expense['id']}", headers=alice).json()["category_name"] == "Eating out"


def test_expenses_need_a_token(client):
    assert client.get("/expenses").status_code == 401
    assert client.post("/expenses", json={}).status_code == 401
    assert client.get("/expenses/1").status_code == 401
    assert client.patch("/expenses/1", json={}).status_code == 401
    assert client.delete("/expenses/1").status_code == 401
