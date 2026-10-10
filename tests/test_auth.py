import secrets
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import User
from app.security import create_access_token
from tests.conftest import PASSWORD, auth_headers, login, register


def stored_user(app, email):
    with app.state.session_factory() as db:
        return db.scalar(select(User).where(User.email == email))


# --- registration ---------------------------------------------------------


def test_register_returns_the_user_without_the_password(client):
    response = register(client, "alice@example.com")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "created_at"}
    assert body["email"] == "alice@example.com"
    assert PASSWORD not in response.text


def test_password_is_stored_as_a_bcrypt_hash(client, app):
    register(client, "alice@example.com")

    hashed = stored_user(app, "alice@example.com").hashed_password
    assert hashed != PASSWORD
    assert hashed.startswith("$2b$")


def test_register_duplicate_email_is_a_conflict(client):
    register(client, "alice@example.com")
    response = register(client, "alice@example.com")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_email_is_case_insensitive(client):
    register(client, "Alice@Example.com")

    assert register(client, "alice@example.com").status_code == 409
    assert login(client, "ALICE@EXAMPLE.COM").status_code == 200


@pytest.mark.parametrize("email", ["not-an-email", "alice@", "@example.com", ""])
def test_register_refuses_an_invalid_email(client, email):
    response = register(client, email)

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "body.email"


def test_register_refuses_a_short_password(client):
    response = register(client, "alice@example.com", password="short")

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "body.password"


def test_register_refuses_a_password_longer_than_bcrypt_reads(client):
    response = register(client, "alice@example.com", password="x" * 73)

    assert response.status_code == 422
    assert "72 bytes" in response.json()["error"]["details"][0]["message"]


def test_register_accepts_a_72_byte_password(client):
    assert register(client, "alice@example.com", password="x" * 72).status_code == 201
    assert login(client, "alice@example.com", password="x" * 72).status_code == 200


def test_validation_error_does_not_echo_the_password(client):
    response = client.post("/auth/register", json={"email": "not-an-email", "password": "hunter2-secret"})

    assert response.status_code == 422
    assert "hunter2-secret" not in response.text


def test_register_needs_both_fields(client):
    response = client.post("/auth/register", json={})

    assert response.status_code == 422
    fields = {detail["field"] for detail in response.json()["error"]["details"]}
    assert fields == {"body.email", "body.password"}


# --- login ----------------------------------------------------------------


def test_login_returns_a_bearer_token(client):
    register(client, "alice@example.com")
    response = login(client, "alice@example.com")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 30 * 60
    assert body["access_token"].count(".") == 2


def test_wrong_password_and_unknown_email_look_the_same(client):
    register(client, "alice@example.com")

    wrong_password = login(client, "alice@example.com", password="wrong password")
    unknown_email = login(client, "nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["error"] == {
        "code": "unauthorized",
        "message": "Incorrect email or password",
    }


def test_login_with_an_over_long_password_is_refused_not_an_error(client):
    register(client, "alice@example.com")

    assert login(client, "alice@example.com", password="x" * 200).status_code == 401


def test_login_needs_the_form_fields(client):
    response = client.post("/auth/login", data={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- using the token -------------------------------------------------------


def test_me_returns_the_logged_in_user(client, alice):
    response = client.get("/auth/me", headers=alice)

    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"


def test_each_token_belongs_to_its_own_user(client, alice, bob):
    assert client.get("/auth/me", headers=alice).json()["email"] == "alice@example.com"
    assert client.get("/auth/me", headers=bob).json()["email"] == "bob@example.com"


def assert_unauthorized(response):
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.headers["www-authenticate"] == "Bearer"


def test_no_token(client):
    assert_unauthorized(client.get("/auth/me"))


@pytest.mark.parametrize(
    "header",
    ["Bearer not.a.token", "Bearer ", "Basic YWxpY2U6cGFzc3dvcmQ=", "not-a-header"],
)
def test_malformed_token(client, header):
    assert_unauthorized(client.get("/auth/me", headers={"Authorization": header}))


def test_expired_token(client, app, settings, alice):
    user = stored_user(app, "alice@example.com")
    expired = create_access_token(
        user.id,
        secret=settings.jwt_secret.get_secret_value(),
        expires_minutes=30,
        now=datetime.now(timezone.utc) - timedelta(hours=2),
    )

    assert_unauthorized(client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}))


def test_token_signed_with_another_secret(client, app, alice):
    user = stored_user(app, "alice@example.com")
    forged = create_access_token(user.id, secret=secrets.token_urlsafe(48), expires_minutes=30)

    assert_unauthorized(client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"}))


def test_token_of_a_deleted_user(client, app, alice):
    with app.state.session_factory() as db:
        db.delete(db.scalar(select(User).where(User.email == "alice@example.com")))
        db.commit()

    assert_unauthorized(client.get("/auth/me", headers=alice))


def test_token_from_one_deployment_does_not_work_on_another(client, alice, tmp_path):
    """A second app with its own secret refuses the first app's token."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.database import Base
    from app.main import create_app

    other = create_app(
        Settings(
            _env_file=None,
            jwt_secret=secrets.token_urlsafe(48),
            database_url=f"sqlite:///{(tmp_path / 'other.db').as_posix()}",
            bcrypt_rounds=4,
        )
    )
    Base.metadata.create_all(other.state.engine)
    try:
        with TestClient(other) as other_client:
            auth_headers(other_client, "alice@example.com")
            assert_unauthorized(other_client.get("/auth/me", headers=alice))
    finally:
        other.state.engine.dispose()
