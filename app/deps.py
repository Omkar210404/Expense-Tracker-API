"""Dependencies shared by the routers."""

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import get_db
from app.errors import AuthenticationError
from app.models import User
from app.repositories import users
from app.security import InvalidTokenError, decode_access_token

# auto_error is off so a missing token goes through AuthenticationError and
# gets the same JSON error format as everything else.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_today() -> date:
    """Today's date in UTC. A dependency, so tests can fix it."""
    return datetime.now(timezone.utc).date()


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> User:
    if not token:
        raise AuthenticationError("Not authenticated")
    try:
        user_id = decode_access_token(token, secret=settings.jwt_secret.get_secret_value())
    except InvalidTokenError:
        raise AuthenticationError("Invalid or expired token") from None

    user = users.get_by_id(db, user_id)
    if user is None:
        # The token is genuine but the account no longer exists.
        raise AuthenticationError("Invalid or expired token")
    return user


DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Today = Annotated[date, Depends(get_today)]
