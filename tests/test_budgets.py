import pytest

from tests.conftest import add_expense, category_id


def set_budget(client, headers, category, month, amount):
    response = client.post(
        "/budgets",
        json={"category_id": category_id(client, headers, category), "month": month, "amount": amount},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def status(client, headers, month):
    response = client.get("/budgets/status", params={"month": month}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def item(report, category_name):
    return next(entry for entry in report["items"] if entry["category_name"] == category_name)


# --- CRUD -----------------------------------------------------------------


def test_create_budget(client, alice):
    food = category_id(client, alice, "Food")

    response = client.post(
        "/budgets", json={"category_id": food, "month": "2026-06", "amount": "5000"}, headers=alice
    )

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "category_id": food,
        "category_name": "Food",
        "month": "2026-06",
        "amount": "5000.00",
    }
    assert client.get(f"/budgets/{body['id']}", headers=alice).json() == body


def test_duplicate_budget_is_a_conflict(client, alice):
    set_budget(client, alice, "Food", "2026-06", "5000")

    response = client.post(
        "/budgets",
        json={"category_id": category_id(client, alice, "Food"), "month": "2026-06", "amount": "7000"},
        headers=alice,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert "Food" in response.json()["error"]["message"]


def test_same_category_may_have_a_budget_in_each_month(client, alice):
    set_budget(client, alice, "Food", "2026-05", "4000")
    set_budget(client, alice, "Food", "2026-06", "5000")
    set_budget(client, alice, "Transport", "2026-06", "1500")

    assert len(client.get("/budgets", headers=alice).json()) == 3


def test_a_budget_may_be_set_for_a_future_month(client, alice):
    assert set_budget(client, alice, "Food", "2027-01", "5000")["month"] == "2027-01"


def test_list_budgets_newest_month_first_then_by_category(client, alice):
    set_budget(client, alice, "Transport", "2026-06", "1500")
    set_budget(client, alice, "Food", "2026-05", "4000")
    set_budget(client, alice, "Food", "2026-06", "5000")

    listed = [(b["month"], b["category_name"]) for b in client.get("/budgets", headers=alice).json()]

    assert listed == [("2026-06", "Food"), ("2026-06", "Transport"), ("2026-05", "Food")]


def test_list_budgets_for_one_month(client, alice):
    set_budget(client, alice, "Food", "2026-05", "4000")
    set_budget(client, alice, "Food", "2026-06", "5000")

    response = client.get("/budgets", params={"month": "2026-05"}, headers=alice)

    assert [(b["month"], b["amount"]) for b in response.json()] == [("2026-05", "4000.00")]


def test_change_budget_amount(client, alice):
    budget = set_budget(client, alice, "Food", "2026-06", "5000")

    response = client.patch(f"/budgets/{budget['id']}", json={"amount": "6500.50"}, headers=alice)

    assert response.status_code == 200
    assert response.json() == {**budget, "amount": "6500.50"}


def test_delete_budget(client, alice):
    budget = set_budget(client, alice, "Food", "2026-06", "5000")

    assert client.delete(f"/budgets/{budget['id']}", headers=alice).status_code == 204
    assert client.get(f"/budgets/{budget['id']}", headers=alice).status_code == 404
    assert client.get("/budgets", headers=alice).json() == []
    # The category and month are free again.
    set_budget(client, alice, "Food", "2026-06", "5000")


def test_unknown_budget_is_not_found(client, alice):
    for response in (
        client.get("/budgets/999999", headers=alice),
        client.patch("/budgets/999999", json={"amount": "1"}, headers=alice),
        client.delete("/budgets/999999", headers=alice),
    ):
        assert response.status_code == 404
        assert response.json()["error"] == {"code": "not_found", "message": "Budget not found"}


def test_deleting_a_category_deletes_its_budgets(client, alice):
    budget = set_budget(client, alice, "Health", "2026-06", "2000")

    client.delete(f"/categories/{category_id(client, alice, 'Health')}", headers=alice)

    assert client.get(f"/budgets/{budget['id']}", headers=alice).status_code == 404


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"month": "2026-13"}, "body.month"),
        ({"month": "2026-6"}, "body.month"),
        ({"month": "June 2026"}, "body.month"),
        ({"month": "2026-06-01"}, "body.month"),
        ({"month": "1999-12"}, "body.month"),
        ({"month": None}, "body.month"),
        ({"amount": 0}, "body.amount"),
        ({"amount": "-100"}, "body.amount"),
        ({"amount": "10.999"}, "body.amount"),
        ({"category_id": 999999}, "body.category_id"),
        ({"category_id": "food"}, "body.category_id"),
    ],
)
def test_create_refuses_invalid_input(client, alice, change, field):
    body = {"category_id": category_id(client, alice, "Food"), "month": "2026-06", "amount": "5000"}
    body.update(change)

    response = client.post("/budgets", json=body, headers=alice)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"][0]["field"] == field
    assert client.get("/budgets", headers=alice).json() == []


@pytest.mark.parametrize("amount", [0, "-1", "1.999", None])
def test_update_refuses_an_invalid_amount(client, alice, amount):
    budget = set_budget(client, alice, "Food", "2026-06", "5000")

    response = client.patch(f"/budgets/{budget['id']}", json={"amount": amount}, headers=alice)

    assert response.status_code == 422
    assert client.get(f"/budgets/{budget['id']}", headers=alice).json() == budget


@pytest.mark.parametrize("month", ["2026-13", "06-2026", "", "2026"])
def test_status_and_list_refuse_an_invalid_month(client, alice, month):
    for path in ("/budgets/status", "/budgets"):
        response = client.get(path, params={"month": month}, headers=alice)
        assert response.status_code == 422, path
        assert response.json()["error"]["details"][0]["field"] == "query.month"


def test_status_needs_a_month(client, alice):
    response = client.get("/budgets/status", headers=alice)

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "query.month"


def test_budgets_need_a_token(client):
    assert client.get("/budgets").status_code == 401
    assert client.post("/budgets", json={}).status_code == 401
    assert client.get("/budgets/status", params={"month": "2026-06"}).status_code == 401
    assert client.get("/budgets/1").status_code == 401
    assert client.patch("/budgets/1", json={}).status_code == 401
    assert client.delete("/budgets/1").status_code == 401


# --- spent vs budget, against hand-worked values ----------------------------


def test_status_under_budget(client, alice):
    # Budget 5000. Spent 1200.00 + 49.50 = 1249.50. Remaining 3750.50.
    # 1249.50 / 5000 = 24.99% -> 25.0 at one decimal.
    budget = set_budget(client, alice, "Food", "2026-06", "5000")
    add_expense(client, alice, category="Food", amount="1200.00", date="2026-06-02")
    add_expense(client, alice, category="Food", amount="49.50", date="2026-06-14")

    report = status(client, alice, "2026-06")

    assert report["month"] == "2026-06"
    assert report["items"] == [
        {
            "budget_id": budget["id"],
            "category_id": budget["category_id"],
            "category_name": "Food",
            "budget": "5000.00",
            "spent": "1249.50",
            "remaining": "3750.50",
            "percent_used": 25.0,
            "over_budget": False,
        }
    ]
    assert report["totals"] == {
        "budget": "5000.00", "spent": "1249.50", "remaining": "3750.50", "percent_used": 25.0,
    }
    assert report["unbudgeted"] == []
    assert report["unbudgeted_spent"] == "0.00"
    assert report["total_spent"] == "1249.50"


def test_status_exactly_at_budget_is_not_over(client, alice):
    set_budget(client, alice, "Transport", "2026-06", "1500")
    add_expense(client, alice, category="Transport", amount="1000", date="2026-06-01")
    add_expense(client, alice, category="Transport", amount="500", date="2026-06-10")

    entry = item(status(client, alice, "2026-06"), "Transport")

    assert (entry["spent"], entry["remaining"], entry["percent_used"], entry["over_budget"]) == (
        "1500.00", "0.00", 100.0, False,
    )


def test_status_over_budget(client, alice):
    # Budget 1500, spent 1500.01: over by one paisa.
    set_budget(client, alice, "Transport", "2026-06", "1500")
    add_expense(client, alice, category="Transport", amount="1500.01", date="2026-06-01")

    entry = item(status(client, alice, "2026-06"), "Transport")

    assert (entry["spent"], entry["remaining"], entry["over_budget"]) == ("1500.01", "-0.01", True)


def test_status_well_over_budget(client, alice):
    # Budget 800, spent 2000: remaining -1200, 250% used.
    set_budget(client, alice, "Entertainment", "2026-06", "800")
    add_expense(client, alice, category="Entertainment", amount="2000", date="2026-06-07")

    entry = item(status(client, alice, "2026-06"), "Entertainment")

    assert (entry["remaining"], entry["percent_used"], entry["over_budget"]) == ("-1200.00", 250.0, True)


def test_status_budget_with_no_expenses(client, alice):
    set_budget(client, alice, "Health", "2026-06", "2000")

    entry = item(status(client, alice, "2026-06"), "Health")

    assert (entry["spent"], entry["remaining"], entry["percent_used"], entry["over_budget"]) == (
        "0.00", "2000.00", 0.0, False,
    )


def test_status_counts_only_expenses_inside_the_month(client, alice):
    set_budget(client, alice, "Food", "2026-05", "3000")
    add_expense(client, alice, category="Food", amount="111", date="2026-04-30")  # day before
    add_expense(client, alice, category="Food", amount="200", date="2026-05-01")  # first day
    add_expense(client, alice, category="Food", amount="300", date="2026-05-31")  # last day
    add_expense(client, alice, category="Food", amount="999", date="2026-06-01")  # day after

    assert item(status(client, alice, "2026-05"), "Food")["spent"] == "500.00"


def test_status_uses_only_that_months_budgets(client, alice):
    set_budget(client, alice, "Food", "2026-05", "3000")
    set_budget(client, alice, "Food", "2026-06", "5000")
    add_expense(client, alice, category="Food", amount="100", date="2026-06-03")

    may, june = status(client, alice, "2026-05"), status(client, alice, "2026-06")

    assert (item(may, "Food")["budget"], item(may, "Food")["spent"]) == ("3000.00", "0.00")
    assert (item(june, "Food")["budget"], item(june, "Food")["spent"]) == ("5000.00", "100.00")


def test_status_lists_spending_in_categories_without_a_budget(client, alice):
    # Budgets: Food 5000, Transport 1500 -> 6500.
    # Budgeted spending: Food 1000 + Transport 400 = 1400. Remaining 5100. 1400/6500 = 21.54% -> 21.5.
    # Unbudgeted: Shopping 750 + 250 = 1000, Health 300 -> 1300, largest first.
    # Everything: 2700.
    set_budget(client, alice, "Food", "2026-06", "5000")
    set_budget(client, alice, "Transport", "2026-06", "1500")
    add_expense(client, alice, category="Food", amount="1000", date="2026-06-01")
    add_expense(client, alice, category="Transport", amount="400", date="2026-06-02")
    add_expense(client, alice, category="Health", amount="300", date="2026-06-03")
    add_expense(client, alice, category="Shopping", amount="750", date="2026-06-04")
    add_expense(client, alice, category="Shopping", amount="250", date="2026-06-05")

    report = status(client, alice, "2026-06")

    assert [entry["category_name"] for entry in report["items"]] == ["Food", "Transport"]
    assert report["totals"] == {
        "budget": "6500.00", "spent": "1400.00", "remaining": "5100.00", "percent_used": 21.5,
    }
    assert [(entry["category_name"], entry["spent"]) for entry in report["unbudgeted"]] == [
        ("Shopping", "1000.00"),
        ("Health", "300.00"),
    ]
    assert report["unbudgeted_spent"] == "1300.00"
    assert report["total_spent"] == "2700.00"


def test_status_for_a_month_with_nothing(client, alice):
    assert status(client, alice, "2026-06") == {
        "month": "2026-06",
        "items": [],
        "totals": {"budget": "0.00", "spent": "0.00", "remaining": "0.00", "percent_used": None},
        "unbudgeted": [],
        "unbudgeted_spent": "0.00",
        "total_spent": "0.00",
    }


def test_status_follows_changes_to_expenses_and_budgets(client, alice):
    budget = set_budget(client, alice, "Food", "2026-06", "1000")
    expense = add_expense(client, alice, category="Food", amount="600", date="2026-06-01")
    assert item(status(client, alice, "2026-06"), "Food")["percent_used"] == 60.0

    client.patch(f"/expenses/{expense['id']}", json={"amount": "1200"}, headers=alice)
    assert item(status(client, alice, "2026-06"), "Food")["over_budget"] is True

    client.patch(f"/budgets/{budget['id']}", json={"amount": "2400"}, headers=alice)
    entry = item(status(client, alice, "2026-06"), "Food")
    assert (entry["percent_used"], entry["over_budget"]) == (50.0, False)

    client.delete(f"/expenses/{expense['id']}", headers=alice)
    assert item(status(client, alice, "2026-06"), "Food")["spent"] == "0.00"


def test_status_sums_small_amounts_exactly(client, alice):
    # Ten expenses of 0.10 are exactly 1.00. With floats this sum is 0.9999999999999999.
    set_budget(client, alice, "Food", "2026-06", "1")
    for _ in range(10):
        add_expense(client, alice, category="Food", amount="0.10", date="2026-06-01")

    entry = item(status(client, alice, "2026-06"), "Food")

    assert (entry["spent"], entry["remaining"], entry["percent_used"], entry["over_budget"]) == (
        "1.00", "0.00", 100.0, False,
    )
