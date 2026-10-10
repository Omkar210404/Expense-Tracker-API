"""Every error, whatever raises it, has the same JSON shape."""

import pytest
from fastapi import Query
from fastapi.testclient import TestClient

from app.errors import AuthenticationError, ConflictError, InvalidInputError, NotFoundError


@pytest.fixture
def client(app):
    @app.get("/_test/not-found")
    def not_found():
        raise NotFoundError("Thing not found")

    @app.get("/_test/conflict")
    def conflict():
        raise ConflictError("Thing already exists")

    @app.get("/_test/unauthorized")
    def unauthorized():
        raise AuthenticationError()

    @app.get("/_test/invalid")
    def invalid():
        raise InvalidInputError("query.date_from", "date_from must not be after date_to")

    @app.get("/_test/validated")
    def validated(count: int = Query(ge=1)):
        return {"count": count}

    @app.get("/_test/crash")
    def crash():
        raise RuntimeError("secret internal detail")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def assert_error(response, status_code, code):
    assert response.status_code == status_code
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert list(body) == ["error"]
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    return body["error"]


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_not_found_error(client):
    error = assert_error(client.get("/_test/not-found"), 404, "not_found")
    assert error == {"code": "not_found", "message": "Thing not found"}


def test_conflict_error(client):
    error = assert_error(client.get("/_test/conflict"), 409, "conflict")
    assert error == {"code": "conflict", "message": "Thing already exists"}


def test_unauthorized_error_asks_for_a_bearer_token(client):
    response = client.get("/_test/unauthorized")
    assert_error(response, 401, "unauthorized")
    assert response.headers["www-authenticate"] == "Bearer"


def test_service_level_validation_error(client):
    error = assert_error(client.get("/_test/invalid"), 422, "validation_error")
    assert error["details"] == [
        {"field": "query.date_from", "message": "date_from must not be after date_to"}
    ]


def test_request_validation_error(client):
    error = assert_error(client.get("/_test/validated", params={"count": 0}), 422, "validation_error")
    assert error["message"] == "Request validation failed"
    assert error["details"] == [
        {"field": "query.count", "message": "Input should be greater than or equal to 1"}
    ]


def test_missing_parameter_is_a_validation_error(client):
    error = assert_error(client.get("/_test/validated"), 422, "validation_error")
    assert error["details"][0]["field"] == "query.count"


def test_unknown_route(client):
    assert_error(client.get("/no/such/route"), 404, "not_found")


def test_method_not_allowed(client):
    assert_error(client.delete("/health"), 405, "method_not_allowed")


def test_unexpected_error_hides_the_details(client):
    response = client.get("/_test/crash")
    error = assert_error(response, 500, "internal_error")
    assert error == {"code": "internal_error", "message": "Internal server error"}
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text
