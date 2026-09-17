import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import RedisClient, redis_client
from app.core.security import ACCESS_TOKEN_TYPE, verify_token
from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import get_user_by_id

security_scheme = HTTPBearer()

INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid authentication token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_redis() -> RedisClient:
    return redis_client


def revoked_token_key(jti: str) -> str:
    return f"auth:revoked:{jti}"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> User:
    token = credentials.credentials
    payload = verify_token(token, expected_type=ACCESS_TOKEN_TYPE)

    if payload is None:
        raise INVALID_CREDENTIALS

    jti = payload.get("jti")
    if jti and await redis.exists(revoked_token_key(jti)):
        raise INVALID_CREDENTIALS

    user_id = payload.get("sub")
    if user_id is None:
        raise INVALID_CREDENTIALS

    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        raise INVALID_CREDENTIALS

    user = await get_user_by_id(db, user_uuid)
    if user is None:
        raise INVALID_CREDENTIALS

    return user
