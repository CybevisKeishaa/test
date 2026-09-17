import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
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


def get_redis():
    return redis_client


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = verify_token(token, expected_type=ACCESS_TOKEN_TYPE)

    if payload is None:
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
