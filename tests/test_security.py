import secrets
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.security import (
    JWT_ALGORITHM,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

SECRET = secrets.token_urlsafe(48)
ROUNDS = 4


def test_hash_is_bcrypt_and_not_the_password():
    hashed = hash_password("correct horse battery", ROUNDS)
    assert hashed != "correct horse battery"
    assert hashed.startswith("$2b$04$")
    assert len(hashed) == 60


def test_same_password_hashes_differently_each_time():
    assert hash_password("correct horse battery", ROUNDS) != hash_password("correct horse battery", ROUNDS)


def test_verify_password():
    hashed = hash_password("correct horse battery", ROUNDS)
    assert verify_password("correct horse battery", hashed) is True
    assert verify_password("wrong password", hashed) is False
    assert verify_password("", hashed) is False


def test_verify_against_something_that_is_not_a_hash():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_verify_a_password_longer_than_bcrypt_accepts():
    hashed = hash_password("correct horse battery", ROUNDS)
    assert verify_password("x" * 100, hashed) is False


def test_non_ascii_passwords_work():
    hashed = hash_password("पासवर्ड-12345", ROUNDS)
    assert verify_password("पासवर्ड-12345", hashed) is True


def test_token_round_trip():
    token = create_access_token(42, secret=SECRET, expires_minutes=30)
    assert decode_access_token(token, secret=SECRET) == 42


def test_token_claims():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    token = create_access_token(42, secret=SECRET, expires_minutes=30, now=now)
    payload = jwt.decode(token, SECRET, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
    assert payload == {
        "sub": "42",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }


def test_expired_token_is_refused():
    long_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    token = create_access_token(42, secret=SECRET, expires_minutes=30, now=long_ago)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)


def test_token_signed_with_another_secret_is_refused():
    token = create_access_token(42, secret=secrets.token_urlsafe(48), expires_minutes=30)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)


def test_tampered_token_is_refused():
    token = create_access_token(42, secret=SECRET, expires_minutes=30)
    header, payload, signature = token.split(".")
    forged_payload = jwt.utils.base64url_encode(
        jwt.utils.base64url_decode(payload).replace(b'"42"', b'"43"')
    ).decode()
    with pytest.raises(InvalidTokenError):
        decode_access_token(f"{header}.{forged_payload}.{signature}", secret=SECRET)


def test_unsigned_token_is_refused():
    now = datetime.now(timezone.utc)
    unsigned = jwt.encode(
        {"sub": "42", "iat": now, "exp": now + timedelta(minutes=30)}, key=None, algorithm="none"
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(unsigned, secret=SECRET)


@pytest.mark.parametrize("missing", ["sub", "exp", "iat"])
def test_token_without_a_required_claim_is_refused(missing):
    now = datetime.now(timezone.utc)
    payload = {"sub": "42", "iat": now, "exp": now + timedelta(minutes=30)}
    del payload[missing]
    token = jwt.encode(payload, SECRET, algorithm=JWT_ALGORITHM)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)


def test_token_with_a_subject_that_is_not_a_user_id_is_refused():
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": "admin", "iat": now, "exp": now + timedelta(minutes=30)}, SECRET, algorithm=JWT_ALGORITHM
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer x"])
def test_garbage_is_refused(garbage):
    with pytest.raises(InvalidTokenError):
        decode_access_token(garbage, secret=SECRET)
