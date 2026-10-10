"""User A cannot read or change user B's data, through any endpoint.

Alice owns a private category, an expense and a budget. Bob is logged in with
his own token and tries every route against Alice's ids.
"""

import re

import pytest

from tests.conftest import add_expense, category_id

PUBLIC_ROUTES = {("GET", "/health"), ("POST", "/auth/register"), ("POST", "/auth/login")}

ALICE_NOTE = "alice-secret-note"
ALICE_CATEGORY = "Alice private"
ALICE_AMOUNT = "4321.00"
ALICE_BUDGET = "7777.00"


@pytest.fixture
def alices(client, alice):
    """Alice's data. Returns the ids Bob will try to reach."""
    private = client.post("/categories", json={"name": ALICE_CATEGORY}, headers=alice).json()
    expense = add_expense(
        client, alice, category_id=private["id"], amount=ALICE_AMOUNT, date="2026-06-10", note=ALICE_NOTE
    )
    food_expense = add_expense(client, alice, category="Food", amount="111.00", date="2026-06-11", note=ALICE_NOTE)
    budget = client.post(
        "/budgets", json={"category_id": private["id"], "month": "2026-06", "amount": ALICE_BUDGET}, headers=alice
    ).json()
    return {
        "category": private["id"],
        "food": category_id(client, alice, "Food"),
        "expense": expense["id"],
        "food_expense": food_expense["id"],
        "budget": budget["id"],
    }


def snapshot(client, headers):
    """Everything a user can read about their own data."""
    return {
        "categories": client.get("/categories", headers=headers).json(),
        "expenses": client.get("/expenses", params={"page_size": 100}, headers=headers).json(),
        "budgets": client.get("/budgets", headers=headers).json(),
        "status": client.get("/budgets/status", params={"month": "2026-06"}, headers=headers).json(),
        "monthly": client.get("/summary/monthly", headers=headers).json(),
        "by_category": client.get("/summary/categories", headers=headers).json(),
        "trends": client.get("/summary/trends", headers=headers).json(),
        "csv": client.get("/expenses/export", headers=headers).text,
    }


def assert_not_found(response, message):
    assert response.status_code == 404, response.text
    assert response.json() == {"error": {"code": "not_found", "message": message}}


# --- no route is left open ---------------------------------------------------


def test_every_route_except_the_public_ones_needs_a_token(client, app):
    # The list of routes comes from the app's own OpenAPI schema, so a route
    # added later is covered without touching this test.
    checked = 0
    for template, operations in app.openapi()["paths"].items():
        path = re.sub(r"\{[^}]+\}", "1", template)
        for method in operations:
            if (method.upper(), template) in PUBLIC_ROUTES:
                continue
            response = client.request(method, path)
            assert response.status_code == 401, f"{method} {template} answered {response.status_code}"
            assert response.json()["error"]["code"] == "unauthorized"
            checked += 1
    # 24 endpoints in total, 3 of them public.
    assert checked == 21


def test_a_valid_token_is_still_needed_for_another_users_id(client, alices):
    for path in (f"/expenses/{alices['expense']}", f"/categories/{alices['category']}", f"/budgets/{alices['budget']}"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer forged.token.value"}).status_code == 401


# --- direct access by id -----------------------------------------------------


def test_bob_cannot_read_alices_expense(client, alices, bob):
    assert_not_found(client.get(f"/expenses/{alices['expense']}", headers=bob), "Expense not found")


def test_bob_cannot_change_alices_expense(client, alice, alices, bob):
    before = client.get(f"/expenses/{alices['expense']}", headers=alice).json()

    response = client.patch(f"/expenses/{alices['expense']}", json={"amount": "1", "note": "hacked"}, headers=bob)

    assert_not_found(response, "Expense not found")
    assert client.get(f"/expenses/{alices['expense']}", headers=alice).json() == before


def test_bob_cannot_delete_alices_expense(client, alice, alices, bob):
    assert_not_found(client.delete(f"/expenses/{alices['expense']}", headers=bob), "Expense not found")
    assert client.get(f"/expenses/{alices['expense']}", headers=alice).status_code == 200


def test_bob_cannot_read_alices_category(client, alices, bob):
    assert_not_found(client.get(f"/categories/{alices['category']}", headers=bob), "Category not found")
    assert_not_found(client.get(f"/categories/{alices['food']}", headers=bob), "Category not found")


def test_bob_cannot_rename_alices_category(client, alice, alices, bob):
    response = client.patch(f"/categories/{alices['category']}", json={"name": "hacked"}, headers=bob)

    assert_not_found(response, "Category not found")
    assert client.get(f"/categories/{alices['category']}", headers=alice).json()["name"] == ALICE_CATEGORY


def test_bob_cannot_delete_alices_category(client, alice, alices, bob):
    empty = client.post("/categories", json={"name": "Alice empty"}, headers=alice).json()

    # One in use, one empty: neither may give Bob a different answer.
    assert_not_found(client.delete(f"/categories/{alices['category']}", headers=bob), "Category not found")
    assert_not_found(client.delete(f"/categories/{empty['id']}", headers=bob), "Category not found")
    assert client.get(f"/categories/{empty['id']}", headers=alice).status_code == 200


def test_bob_cannot_read_alices_budget(client, alices, bob):
    assert_not_found(client.get(f"/budgets/{alices['budget']}", headers=bob), "Budget not found")


def test_bob_cannot_change_alices_budget(client, alice, alices, bob):
    response = client.patch(f"/budgets/{alices['budget']}", json={"amount": "1"}, headers=bob)

    assert_not_found(response, "Budget not found")
    assert client.get(f"/budgets/{alices['budget']}", headers=alice).json()["amount"] == ALICE_BUDGET


def test_bob_cannot_delete_alices_budget(client, alice, alices, bob):
    assert_not_found(client.delete(f"/budgets/{alices['budget']}", headers=bob), "Budget not found")
    assert client.get(f"/budgets/{alices['budget']}", headers=alice).status_code == 200


def test_another_users_id_looks_exactly_like_a_missing_id(client, alices, bob):
    """The answer must not reveal that the id exists."""
    for kind in ("expenses", "categories", "budgets"):
        theirs = client.get(f"/{kind}/{alices[kind.rstrip('s').replace('categorie', 'category')]}", headers=bob)
        missing = client.get(f"/{kind}/987654", headers=bob)
        assert theirs.status_code == missing.status_code == 404
        assert theirs.json() == missing.json()


# --- using another user's category -------------------------------------------


def test_bob_cannot_create_an_expense_in_alices_category(client, alice, alices, bob):
    body = {"amount": "10", "category_id": alices["category"], "date": "2026-06-10", "payment_method": "cash"}

    theirs = client.post("/expenses", json=body, headers=bob)
    missing = client.post("/expenses", json={**body, "category_id": 987654}, headers=bob)

    assert theirs.status_code == missing.status_code == 422
    assert theirs.json() == missing.json()
    assert theirs.json()["error"]["details"] == [{"field": "body.category_id", "message": "Category not found"}]
    assert client.get("/expenses", headers=bob).json()["total"] == 0
    assert client.get("/expenses", headers=alice).json()["total"] == 2


def test_bob_cannot_move_his_expense_into_alices_category(client, alices, bob):
    own = add_expense(client, bob, category="Food")

    response = client.patch(f"/expenses/{own['id']}", json={"category_id": alices["category"]}, headers=bob)

    assert response.status_code == 422
    assert client.get(f"/expenses/{own['id']}", headers=bob).json()["category_name"] == "Food"


def test_bob_cannot_set_a_budget_on_alices_category(client, alice, alices, bob):
    body = {"category_id": alices["food"], "month": "2026-07", "amount": "100"}

    theirs = client.post("/budgets", json=body, headers=bob)
    missing = client.post("/budgets", json={**body, "category_id": 987654}, headers=bob)

    assert theirs.status_code == missing.status_code == 422
    assert theirs.json() == missing.json()
    assert client.get("/budgets", headers=bob).json() == []
    assert len(client.get("/budgets", headers=alice).json()) == 1


def test_filtering_by_alices_category_shows_bob_nothing(client, alices, bob):
    for category in (alices["category"], alices["food"]):
        listed = client.get("/expenses", params={"category_id": category}, headers=bob).json()
        assert (listed["items"], listed["total"]) == ([], 0)
        exported = client.get("/expenses/export", params={"category_id": category}, headers=bob).text
        assert exported.count("\n") == 1  # the header only


# --- lists, summaries and export ---------------------------------------------


def test_bob_sees_none_of_alices_data_anywhere(client, alices, bob):
    """A new user next to a user with data sees exactly what a new user sees."""
    seen = snapshot(client, bob)

    assert seen["expenses"] == {"items": [], "total": 0, "page": 1, "page_size": 100, "pages": 0}
    assert seen["budgets"] == []
    assert seen["status"]["items"] == []
    assert seen["status"]["unbudgeted"] == []
    assert seen["status"]["total_spent"] == "0.00"
    assert seen["monthly"] == {"months": [], "total": "0.00", "count": 0}
    assert seen["by_category"]["categories"] == []
    assert seen["by_category"]["total"] == "0.00"
    assert seen["trends"]["total"] == "0.00"
    assert seen["csv"] == "id,date,amount,category,payment_method,note\r\n"
    assert ALICE_CATEGORY not in [category["name"] for category in seen["categories"]]

    everything = repr(seen)
    for secret in (ALICE_NOTE, ALICE_CATEGORY, ALICE_AMOUNT, ALICE_BUDGET):
        assert secret not in everything


def test_bobs_numbers_count_only_bobs_expenses(client, alice, alices, bob):
    # Both users have a "Food" category and spend in June 2026.
    # Alice: 4321.00 (private) + 111.00 (Food). Bob: 50.00 + 25.50 = 75.50 (Food), budget 200.
    bob_food = category_id(client, bob, "Food")
    add_expense(client, bob, category_id=bob_food, amount="50.00", date="2026-06-10", note="bob coffee")
    add_expense(client, bob, category_id=bob_food, amount="25.50", date="2026-06-12", note="bob snack")
    client.post("/budgets", json={"category_id": bob_food, "month": "2026-06", "amount": "200"}, headers=bob)

    seen = snapshot(client, bob)

    assert seen["expenses"]["total"] == 2
    assert sorted(item["note"] for item in seen["expenses"]["items"]) == ["bob coffee", "bob snack"]
    assert [(item["category_name"], item["spent"], item["percent_used"]) for item in seen["status"]["items"]] == [
        ("Food", "75.50", 37.8)  # 75.50 / 200 = 37.75 -> 37.8
    ]
    assert seen["status"]["total_spent"] == "75.50"
    assert seen["monthly"] == {"months": [{"month": "2026-06", "total": "75.50", "count": 2}], "total": "75.50", "count": 2}
    assert [(row["category_name"], row["total"], row["share"]) for row in seen["by_category"]["categories"]] == [
        ("Food", "75.50", 100.0)
    ]
    assert seen["trends"]["months"][-1]["total"] == "75.50"
    assert seen["csv"].count("\n") == 3
    assert ALICE_NOTE not in repr(seen)

    # And Alice's numbers do not include Bob's.
    alice_seen = snapshot(client, alice)
    assert alice_seen["expenses"]["total"] == 2
    assert alice_seen["monthly"]["total"] == "4432.00"
    assert "bob" not in repr(alice_seen)


def test_search_does_not_reach_another_users_notes(client, alices, bob):
    listed = client.get("/expenses", params={"q": "alice"}, headers=bob).json()

    assert listed["total"] == 0


def test_the_two_users_have_separate_categories_with_the_same_names(client, alice, alices, bob):
    alice_food = alices["food"]
    bob_food = category_id(client, bob, "Food")
    assert alice_food != bob_food

    # Bob renames and then deletes his own "Food". Alice's is untouched.
    assert client.patch(f"/categories/{bob_food}", json={"name": "Bob food"}, headers=bob).status_code == 200
    assert client.delete(f"/categories/{bob_food}", headers=bob).status_code == 204
    assert client.get(f"/categories/{alice_food}", headers=alice).json()["name"] == "Food"

    # A name Alice already uses is free for Bob.
    assert client.post("/categories", json={"name": ALICE_CATEGORY}, headers=bob).status_code == 201


def test_alices_data_is_unchanged_after_all_of_bobs_attempts(client, alice, alices, bob):
    before = snapshot(client, alice)

    for method, path, body in [
        ("patch", f"/expenses/{alices['expense']}", {"amount": "1", "note": "hacked"}),
        ("delete", f"/expenses/{alices['expense']}", None),
        ("delete", f"/expenses/{alices['food_expense']}", None),
        ("patch", f"/categories/{alices['category']}", {"name": "hacked"}),
        ("delete", f"/categories/{alices['category']}", None),
        ("patch", f"/budgets/{alices['budget']}", {"amount": "1"}),
        ("delete", f"/budgets/{alices['budget']}", None),
        ("post", "/expenses", {"amount": "10", "category_id": alices["category"], "date": "2026-06-10", "payment_method": "cash"}),
        ("post", "/budgets", {"category_id": alices["category"], "month": "2026-05", "amount": "100"}),
    ]:
        response = client.request(method, path, json=body, headers=bob)
        assert response.status_code in (404, 422), f"{method} {path} answered {response.status_code}"

    assert snapshot(client, alice) == before
