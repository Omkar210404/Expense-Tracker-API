import pytest

from app.services.categories import DEFAULT_CATEGORIES
from tests.conftest import category_id


def names(client, headers):
    return [category["name"] for category in client.get("/categories", headers=headers).json()]


def test_new_user_gets_the_default_categories(client, alice):
    response = client.get("/categories", headers=alice)

    assert response.status_code == 200
    categories = response.json()
    assert sorted(category["name"] for category in categories) == sorted(DEFAULT_CATEGORIES)
    assert all(category["is_default"] for category in categories)
    assert set(categories[0]) == {"id", "name", "is_default", "created_at"}


def test_categories_are_listed_alphabetically(client, alice):
    client.post("/categories", json={"name": "groceries"}, headers=alice)

    listed = names(client, alice)
    assert listed == sorted(listed, key=str.casefold)
    assert "groceries" in listed


def test_create_category(client, alice):
    response = client.post("/categories", json={"name": "Groceries"}, headers=alice)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Groceries"
    assert body["is_default"] is False
    assert client.get(f"/categories/{body['id']}", headers=alice).json() == body


def test_create_trims_the_name(client, alice):
    response = client.post("/categories", json={"name": "  Groceries  "}, headers=alice)

    assert response.json()["name"] == "Groceries"


@pytest.mark.parametrize("name", ["Food", "food", "FOOD", "  Food "])
def test_duplicate_name_is_a_conflict_whatever_the_case(client, alice, name):
    response = client.post("/categories", json={"name": name}, headers=alice)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_duplicate_check_handles_non_ascii_names(client, alice):
    assert client.post("/categories", json={"name": "Épicerie"}, headers=alice).status_code == 201
    assert client.post("/categories", json={"name": "épicerie"}, headers=alice).status_code == 409


@pytest.mark.parametrize("body", [{"name": ""}, {"name": "   "}, {"name": "x" * 51}, {}, {"name": None}])
def test_create_refuses_an_invalid_name(client, alice, body):
    response = client.post("/categories", json=body, headers=alice)

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "body.name"


def test_rename_category(client, alice):
    food = category_id(client, alice, "Food")

    response = client.patch(f"/categories/{food}", json={"name": "Eating out"}, headers=alice)

    assert response.status_code == 200
    assert response.json()["name"] == "Eating out"
    assert "Food" not in names(client, alice)


def test_rename_may_change_only_the_case(client, alice):
    food = category_id(client, alice, "Food")

    response = client.patch(f"/categories/{food}", json={"name": "FOOD"}, headers=alice)

    assert response.status_code == 200
    assert response.json()["name"] == "FOOD"


def test_rename_to_an_existing_name_is_a_conflict(client, alice):
    food = category_id(client, alice, "Food")

    response = client.patch(f"/categories/{food}", json={"name": "transport"}, headers=alice)

    assert response.status_code == 409


def test_delete_category(client, alice):
    food = category_id(client, alice, "Food")

    response = client.delete(f"/categories/{food}", headers=alice)

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/categories/{food}", headers=alice).status_code == 404
    assert "Food" not in names(client, alice)


def test_deleted_name_can_be_used_again(client, alice):
    client.delete(f"/categories/{category_id(client, alice, 'Food')}", headers=alice)

    assert client.post("/categories", json={"name": "Food"}, headers=alice).status_code == 201


def test_unknown_category_is_not_found(client, alice):
    for response in (
        client.get("/categories/999999", headers=alice),
        client.patch("/categories/999999", json={"name": "X"}, headers=alice),
        client.delete("/categories/999999", headers=alice),
    ):
        assert response.status_code == 404
        assert response.json()["error"] == {"code": "not_found", "message": "Category not found"}


@pytest.mark.parametrize("bad_id", ["abc", "0", "-1", "1.5", "99999999999999999999"])
def test_invalid_id_is_a_validation_error(client, alice, bad_id):
    response = client.get(f"/categories/{bad_id}", headers=alice)

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "path.category_id"


def test_categories_need_a_token(client):
    assert client.get("/categories").status_code == 401
    assert client.post("/categories", json={"name": "X"}).status_code == 401
    assert client.get("/categories/1").status_code == 401
    assert client.patch("/categories/1", json={"name": "X"}).status_code == 401
    assert client.delete("/categories/1").status_code == 401
