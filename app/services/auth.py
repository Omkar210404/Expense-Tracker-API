from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AuthenticationError, ConflictError
from app.models import User
from app.repositories import users
from app.schemas.auth import Token, UserCreate
from app.services import categories as categories_service
from app.security import create_access_token, hash_password, verify_against_dummy, verify_password


def normalise_email(email: str) -> str:
    return email.strip().lower()


def register(db: Session, settings: Settings, data: UserCreate) -> User:
    email = normalise_email(data.email)
    if users.get_by_email(db, email) is not None:
        raise ConflictError("An account with this email already exists")

    user = users.add(db, email=email, hashed_password=hash_password(data.password, settings.bcrypt_rounds))
    # Same transaction as the user, so an account never exists without its categories.
    categories_service.create_defaults(db, user.id)
    try:
        db.commit()
    except IntegrityError:
        # Two registrations for the same email arrived at the same moment.
        db.rollback()
        raise ConflictError("An account with this email already exists") from None
    return user


def authenticate(db: Session, settings: Settings, email: str, password: str) -> User:
    """Return the user, or raise the same error whether the email or the password is wrong."""
    user = users.get_by_email(db, normalise_email(email))
    if user is None:
        verify_against_dummy(password, settings.bcrypt_rounds)
        raise AuthenticationError("Incorrect email or password")
    if not verify_password(password, user.hashed_password):
        raise AuthenticationError("Incorrect email or password")
    return user


def issue_token(settings: Settings, user: User) -> Token:
    token = create_access_token(
        user.id,
        secret=settings.jwt_secret.get_secret_value(),
        expires_minutes=settings.access_token_expire_minutes,
    )
    return Token(access_token=token, expires_in=settings.access_token_expire_minutes * 60)
