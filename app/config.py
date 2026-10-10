"""Configuration, read from environment variables only.

A local `.env` file is also read, as a convenience for development. It is
git-ignored. Nothing here has a secret default: without JWT_SECRET the app
does not start.
"""

from functools import lru_cache

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_JWT_SECRET_LENGTH = 32


class ConfigError(RuntimeError):
    """The environment is missing a setting or holds an invalid one."""


class DatabaseSettings(BaseSettings):
    """The part of the configuration that migrations need."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./expenses.db"


class Settings(DatabaseSettings):
    jwt_secret: SecretStr = Field(min_length=MIN_JWT_SECRET_LENGTH)
    access_token_expire_minutes: int = Field(default=30, ge=1, le=60 * 24 * 7)
    # Cost factor for bcrypt. Lower it only to speed up tests.
    bcrypt_rounds: int = Field(default=12, ge=4, le=16)
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def load_settings(**overrides) -> Settings:
    """Build Settings, turning a validation failure into one readable message.

    The message names the variables and the problem but never the values, so a
    secret that is too short is not echoed into the logs.
    """
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']).upper()}: {error['msg']}"
            for error in exc.errors()
        )
        raise ConfigError(
            f"Invalid configuration ({problems}). See .env.example for the variables to set."
        ) from None


@lru_cache
def get_settings() -> Settings:
    return load_settings()
