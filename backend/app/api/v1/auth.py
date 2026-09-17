import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    INVALID_CREDENTIALS,
    get_current_user,
    get_redis,
    revoked_token_key,
    security_scheme,
)
from app.core.redis import RedisClient
from app.core.security import (
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    get_token_ttl_seconds,
    verify_password,
    verify_token,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import (
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.services.auth_service import create_user, get_user_by_email, get_user_by_id

router = APIRouter()

# Deliberately identical for "no such email" and "wrong password" so the
# endpoint cannot be used to enumerate which addresses have an account.
INVALID_LOGIN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid email or password",
    headers={"WWW-Authenticate": "Bearer"},
)


def _issue_tokens(user_id: str) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(data={"sub": user_id}),
        refresh_token=create_refresh_token(data={"sub": user_id}),
    )


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user."""
    existing_user = await get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    try:
        user = await create_user(db, user_data)
    except IntegrityError:
        # Two concurrent registrations for the same address race past the check
        # above; the unique index on users.email is the real guard.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    return _issue_tokens(str(user.id))


@router.post("/login", response_model=TokenResponse)
async def login(
    user_data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return tokens."""
    user = await get_user_by_email(db, user_data.email)

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise INVALID_LOGIN

    return _issue_tokens(str(user.id))


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Refresh access token using refresh token."""
    payload = verify_token(request.refresh_token, expected_type=REFRESH_TOKEN_TYPE)

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

    # The account may have been deleted since the refresh token was issued.
    if await get_user_by_id(db, user_uuid) is None:
        raise INVALID_CREDENTIALS

    # Rotate the refresh token: the presented one cannot be replayed.
    if jti:
        ttl = get_token_ttl_seconds(payload)
        if ttl > 0:
            await redis.set(revoked_token_key(jti), "1", ex=ttl)

    return _issue_tokens(user_id)


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    current_user: User = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
):
    """Log out by revoking the presented access token."""
    payload = verify_token(credentials.credentials, expected_type=ACCESS_TOKEN_TYPE)

    if payload is not None:
        jti = payload.get("jti")
        ttl = get_token_ttl_seconds(payload)
        # Only needs to outlive the token itself, so the blacklist stays bounded.
        if jti and ttl > 0:
            await redis.set(revoked_token_key(jti), "1", ex=ttl)

    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current user information."""
    return current_user
