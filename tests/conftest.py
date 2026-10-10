"""Shared fixtures: an app on a temporary SQLite file, a client, and logged-in users."""

import os
import secrets
from datetime import date

# app.main builds an app at import time and needs a secret for that. It is
# generated here at run time, so no secret is written in the repository.
os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(48))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

from app.config import Settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.deps import get_today  # noqa: E402
from app.main import create_app  # noqa: E402

# Tests never read the clock. This is "today" for every request.
TODAY = date(2026, 6, 15)

PASSWORD = "correct horse battery"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret=secrets.token_urlsafe(48),
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        bcrypt_rounds=4,
    )


@pytest.fixture
def app(settings):
    app = create_app(settings)

    @event.listens_for(app.state.engine, "connect")
    def skip_disk_sync(dbapi_connection, connection_record):
        # The file is thrown away after the test, so waiting for the disk on
        # every commit only makes the suite slow.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA synchronous=OFF")
        cursor.close()

    Base.metadata.create_all(app.state.engine)
    app.dependency_overrides[get_today] = lambda: TODAY
    yield app
    # Windows cannot delete the temporary file while a connection is open.
    app.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def register(client, email: str, password: str = PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client, email: str, password: str = PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def auth_headers(client, email: str) -> dict:
    """Register a new user, log in, and return the Authorization header."""
    assert register(client, email).status_code == 201
    token = login(client, email).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def alice(client) -> dict:
    return auth_headers(client, "alice@example.com")


@pytest.fixture
def bob(client) -> dict:
    return auth_headers(client, "bob@example.com")


def category_id(client, headers: dict, name: str) -> int:
    """The id of one of the user's categories, by name."""
    for category in client.get("/categories", headers=headers).json():
        if category["name"] == name:
            return category["id"]
    raise AssertionError(f"no category named {name}")


def add_expense(client, headers: dict, **fields) -> dict:
    """Create an expense. `category` may be given by name."""
    body = {"amount": "100.00", "date": "2026-06-10", "payment_method": "cash"}
    body.update(fields)
    if "category" in body:
        body["category_id"] = category_id(client, headers, body.pop("category"))
    elif "category_id" not in body:
        body["category_id"] = category_id(client, headers, "Food")
    response = client.post("/expenses", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()
