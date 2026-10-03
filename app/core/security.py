"""Password hashing and JWT handling.

Passwords are hashed with Argon2id (memory-hard, salted per password). Tokens
are HS256 JWTs: the algorithm is pinned on verification so a forged token
claiming ``alg=none`` or another algorithm is rejected.
"""

import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings
from app.core.errors import AuthenticationError

_hasher = PasswordHasher()  # Argon2id with the library's recommended parameters


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verification; returns False instead of raising."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache
def dummy_password_hash() -> str:
    """Hash verified when the username does not exist.

    Without it, "unknown user" would return much faster than "wrong password"
    and the timing difference would reveal which usernames are real.
    """
    return hash_password("dummy-password-for-timing-equalisation")


def create_access_token(*, user_id: str, role: str, settings: Settings) -> tuple[str, int]:
    """Return ``(token, expires_in_seconds)``."""
    now = datetime.now(UTC)
    expires_in = settings.jwt_expire_minutes * 60
    claims = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str, settings: Settings) -> dict:
    """Verify signature, expiry and required claims. Raises AuthenticationError."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],  # pinned: never trust the header's alg
            options={"require": ["sub", "exp", "iat", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("The access token has expired.", code="TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("The access token is invalid.", code="INVALID_TOKEN") from exc
