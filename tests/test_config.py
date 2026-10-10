import secrets

import pytest

from app.config import ConfigError, load_settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("JWT_SECRET", "DATABASE_URL", "ACCESS_TOKEN_EXPIRE_MINUTES", "BCRYPT_ROUNDS", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)


def test_missing_jwt_secret_stops_startup():
    with pytest.raises(ConfigError) as excinfo:
        load_settings(_env_file=None)
    assert "JWT_SECRET" in str(excinfo.value)


def test_short_jwt_secret_is_refused_and_not_echoed(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "too-short-secret")
    with pytest.raises(ConfigError) as excinfo:
        load_settings(_env_file=None)
    assert "JWT_SECRET" in str(excinfo.value)
    assert "too-short-secret" not in str(excinfo.value)


def test_settings_come_from_the_environment(monkeypatch):
    secret = secrets.token_urlsafe(48)
    monkeypatch.setenv("JWT_SECRET", secret)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./other.db")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "5")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, http://localhost:3000")

    settings = load_settings(_env_file=None)

    assert settings.jwt_secret.get_secret_value() == secret
    assert settings.database_url == "sqlite:///./other.db"
    assert settings.access_token_expire_minutes == 5
    assert settings.cors_origin_list == ["http://localhost:5173", "http://localhost:3000"]


def test_defaults_when_only_the_secret_is_set(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secrets.token_urlsafe(48))

    settings = load_settings(_env_file=None)

    assert settings.database_url == "sqlite:///./expenses.db"
    assert settings.access_token_expire_minutes == 30
    assert settings.cors_origin_list == []


def test_secret_is_hidden_in_repr(monkeypatch):
    secret = secrets.token_urlsafe(48)
    monkeypatch.setenv("JWT_SECRET", secret)

    assert secret not in repr(load_settings(_env_file=None))


def test_token_lifetime_must_be_positive(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "0")
    with pytest.raises(ConfigError):
        load_settings(_env_file=None)
