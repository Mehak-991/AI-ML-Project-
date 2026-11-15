import hashlib
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2 import exceptions as argon2_exceptions
from passlib.context import CryptContext

from app.core.config import Settings
from app.core.exceptions import DataValidationError

# New hashes: Argon2id (RFC 9106 low-memory profile: t=3, m=64 MiB, p=4).
_argon2 = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)
# Legacy hashes created before the Argon2id migration. Verified only, never produced;
# a successful login re-hashes them with Argon2id (see needs_rehash).
_legacy_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2id."""
    return _argon2.hash(password)


def _is_argon2(hashed_password: str) -> bool:
    return hashed_password.startswith("$argon2")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored Argon2id or legacy hash."""
    if _is_argon2(hashed_password):
        try:
            return _argon2.verify(hashed_password, plain_password)
        except argon2_exceptions.VerificationError:
            return False
        except argon2_exceptions.InvalidHashError:
            return False
    try:
        return _legacy_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


def needs_rehash(hashed_password: str) -> bool:
    """True for legacy hashes and Argon2 hashes with outdated parameters."""
    if not _is_argon2(hashed_password):
        return True
    try:
        return _argon2.check_needs_rehash(hashed_password)
    except argon2_exceptions.InvalidHashError:
        return True


# A constant hash to verify against when the account does not exist, so a login for an
# unknown email costs the same time as one for a known email (no user enumeration).
_DUMMY_HASH = _argon2.hash("timing-equaliser-not-a-real-password")


def verify_dummy_password(plain_password: str) -> None:
    verify_password(plain_password, _DUMMY_HASH)


def validate_password_strength(password: str) -> None:
    """Enforce minimum enterprise security password standards."""
    if len(password) < 8:
        raise DataValidationError("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", password):
        raise DataValidationError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise DataValidationError("Password must contain at least one lowercase letter.")
    if not re.search(r"[0-9]", password):
        raise DataValidationError("Password must contain at least one digit.")


def create_access_token(
    data: dict[str, Any], settings: Settings, expires_delta: timedelta | None = None
) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": now, "jti": uuid.uuid4().hex, "type": "access"})
    secret = settings.JWT_SECRET_KEY.get_secret_value()
    return jwt.encode(to_encode, secret, algorithm=settings.JWT_ALGORITHM)



def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Decode and verify a signed JWT access token (signature, expiry and token type)."""
    secret = settings.JWT_SECRET_KEY.get_secret_value()
    payload = jwt.decode(
        token,
        secret,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["exp", "iat", "sub"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return payload


def generate_refresh_token() -> tuple[str, str]:
    """Generate a random refresh token and its SHA-256 database hash."""
    token = os.urandom(32).hex()
    token_hash = hash_token(token)
    return token, token_hash


def hash_token(token: str) -> str:
    """Hash a raw token string using SHA-256."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
