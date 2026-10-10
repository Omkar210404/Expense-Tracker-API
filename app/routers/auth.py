from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.deps import AppSettings, CurrentUser, DbSession
from app.schemas.auth import Token, UserCreate, UserOut
from app.schemas.common import error_responses
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=201,
    summary="Create an account",
    responses=error_responses(409, 422),
)
def register(data: UserCreate, db: DbSession, settings: AppSettings):
    """Create an account. The new user gets a set of default categories."""
    return auth_service.register(db, settings, data)


@router.post(
    "/login",
    response_model=Token,
    summary="Log in and get an access token",
    responses=error_responses(401, 422),
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession, settings: AppSettings):
    """OAuth2 password form. Put the email in the `username` field."""
    user = auth_service.authenticate(db, settings, form.username, form.password)
    return auth_service.issue_token(settings, user)


@router.get("/me", response_model=UserOut, summary="The logged-in user", responses=error_responses(401))
def me(user: CurrentUser):
    return user
