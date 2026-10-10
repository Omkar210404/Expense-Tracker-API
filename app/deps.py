"""Dependencies shared by the routers."""

from datetime import date, datetime, timezone

from fastapi import Request

from app.config import Settings


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_today() -> date:
    """Today's date in UTC. A dependency, so tests can fix it."""
    return datetime.now(timezone.utc).date()
