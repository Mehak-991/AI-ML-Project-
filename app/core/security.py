import hashlib
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import Settings
from app.core.exceptions import DataValidationError

# New hashes use Argon2id with the OWASP minimum parameters (19 MiB, 2 passes, 1 lane). PBKDF2 and
# bcrypt stay in the list only so accounts created before Argon2id still verify; they are marked
# deprecated, so `verify_and_rehash` upgrades them after the next successful login.
ARGON2_MEMORY_COST_KIB = 19_456
ARGON2_TIME_COST = 2
ARGON2_PARALLELISM = 1

pwd_context = CryptContext(
    schemes=["argon2", "pbkdf2_sha256", "bcrypt"],
    default="argon2",
    deprecated=["pbkdf2_sha256", "bcrypt"],
    argon2__type="ID",
    argon2__memory_cost=ARGON2_MEMORY_COST_KIB,
    argon2__time_cost=ARGON2_TIME_COST,
    argon2__parallelism=ARGON2_PARALLELISM,
)


# Verified when the email is unknown, so login spends comparable work either way and the
# response time does not reveal which accounts exist. Accounts still on a legacy hash verify
# faster until their next login upgrades them.
_DUMMY_PASSWORD_HASH = pwd_context.hash(uuid.uuid4().hex)


def verify_and_rehash(plain_password: str, hashed_password: str | None) -> tuple[bool, str | None]:
    """Check a password; also return a replacement hash when the stored one is outdated.

    The replacement is only produced after a successful check, so a wrong password never
    changes what is stored. Unknown accounts (no hash) spend the same work and fail.
    """
    if hashed_password is None:
        pwd_context.verify(plain_password, _DUMMY_PASSWORD_HASH)
        return False, None
    return pwd_context.verify_and_update(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash a plaintext password securely."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


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
    """Decode and verify a signed JWT access token."""
    secret = settings.JWT_SECRET_KEY.get_secret_value()
    payload = jwt.decode(
        token,
        secret,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token.")
    return payload


def generate_refresh_token() -> tuple[str, str]:
    """Generate a random refresh token and its SHA-256 database hash."""
    token = os.urandom(32).hex()
    token_hash = hash_token(token)
    return token, token_hash


def hash_token(token: str) -> str:
    """Hash a raw token string using SHA-256."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
