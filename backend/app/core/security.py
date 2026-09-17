import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update(
        {"exp": expire, "type": ACCESS_TOKEN_TYPE, "jti": str(uuid.uuid4())}
    )
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
    to_encode.update(
        {"exp": expire, "type": REFRESH_TOKEN_TYPE, "jti": str(uuid.uuid4())}
    )
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str, expected_type: str | None = None) -> dict[str, Any] | None:
    """Verify and decode a JWT token.

    Signature *and* expiration are always enforced: a token whose ``exp`` has
    passed is rejected. When ``expected_type`` is given, the token's ``type``
    claim must match it, so a long-lived refresh token can never be replayed as
    an access token.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        return None

    if expected_type is not None and payload.get("type") != expected_type:
        return None

    return payload


def get_token_ttl_seconds(payload: dict[str, Any]) -> int:
    """Seconds left before ``payload`` expires (0 once it has expired)."""
    exp = payload.get("exp")
    if exp is None:
        return 0
    remaining = datetime.fromtimestamp(exp, tz=timezone.utc) - datetime.now(
        timezone.utc
    )
    return max(int(remaining.total_seconds()), 0)
