"""Password hashing and JWT access tokens.

Both are thin wrappers around well-known libraries: `bcrypt` for passwords and
`PyJWT` for tokens. Nothing cryptographic is implemented here.
"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache

import bcrypt
import jwt

# The algorithm is fixed. It is passed explicitly when decoding, so a token
# cannot choose its own algorithm (for example "none").
JWT_ALGORITHM = "HS256"

# bcrypt reads at most 72 bytes of a password.
MAX_PASSWORD_BYTES = 72


class InvalidTokenError(Exception):
    """The token is malformed, expired, signed with another key, or has no subject."""


def hash_password(password: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds)).decode("ascii")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("ascii"))
    except ValueError:
        # Not a bcrypt hash, or the password is longer than bcrypt accepts.
        return False


@lru_cache
def _dummy_hash(rounds: int) -> str:
    return hash_password("no user has this password", rounds)


def verify_against_dummy(password: str, rounds: int = 12) -> None:
    """Spend the time of a real check when the email is unknown.

    Without this, a login for an unknown email would answer faster than one
    with a wrong password, which tells an attacker which emails are registered.
    """
    verify_password(password, _dummy_hash(rounds))


def create_access_token(user_id: int, *, secret: str, expires_minutes: int, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, *, secret: str) -> int:
    """Return the user id in the token, or raise InvalidTokenError."""
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError(str(exc)) from exc
