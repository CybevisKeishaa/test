"""Regression tests for the authentication bugs fixed in this branch."""

from datetime import timedelta

import pytest
from httpx import AsyncClient
from jose import jwt

from app.core.config import settings
from app.core.security import create_access_token
from tests.conftest import auth_header_for, register_user


async def _user_id(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    return response.json()["id"]


@pytest.mark.asyncio
async def test_expired_access_token_is_rejected(client: AsyncClient):
    """An access token past its `exp` must not authenticate anyone.

    Regression: verify_token passed options={"verify_exp": False}, so every
    token ever issued stayed valid forever.
    """
    headers = await auth_header_for(client, "expired@example.com")
    user_id = await _user_id(client, headers)

    expired = create_access_token(
        data={"sub": user_id}, expires_delta=timedelta(minutes=-1)
    )

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_signed_with_another_secret_is_rejected(client: AsyncClient):
    """A token forged with the wrong signing key must be rejected."""
    headers = await auth_header_for(client, "forged@example.com")
    user_id = await _user_id(client, headers)

    forged = jwt.encode(
        {"sub": user_id, "type": "access"},
        "not-the-real-secret",
        algorithm=settings.JWT_ALGORITHM,
    )

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_cannot_be_used_as_access_token(client: AsyncClient):
    """The long-lived refresh token must not open the API on its own.

    Regression: get_current_user never inspected the `type` claim, so a 7-day
    refresh token worked anywhere a 30-minute access token did.
    """
    tokens = await register_user(client, "refresh-as-access@example.com")

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_token_cannot_be_used_to_refresh(client: AsyncClient):
    """The mirror case: an access token must not be accepted by /refresh."""
    tokens = await register_user(client, "access-as-refresh@example.com")

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_does_not_reveal_whether_email_exists(client: AsyncClient):
    """Wrong password and unknown address must be indistinguishable.

    Regression: an unknown email returned 404 "User with this email not found"
    while a wrong password returned 401, turning login into an account oracle.
    """
    await register_user(client, "enumerate@example.com", "password123")

    wrong_password = await client.post(
        "/api/v1/auth/login",
        json={"email": "enumerate@example.com", "password": "wrong-password"},
    )
    unknown_email = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password"},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


@pytest.mark.asyncio
async def test_logout_revokes_the_access_token(client: AsyncClient):
    """After logout the presented token must stop working.

    Regression: logout returned a success message and did nothing, so a stolen
    token remained valid for its full lifetime.
    """
    headers = await auth_header_for(client, "revoke@example.com")

    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    logout = await client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 200

    after = await client.get("/api/v1/auth/me", headers=headers)
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_is_rotated_on_use(client: AsyncClient):
    """A refresh token must be single-use."""
    tokens = await register_user(client, "rotate@example.com")

    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert first.status_code == 200

    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_email_registration_is_rejected(client: AsyncClient):
    """users.email is unique, so the address cannot be claimed twice.

    Regression: no unique constraint existed, and a second account with the
    same address made get_user_by_email raise MultipleResultsFound on login.
    """
    await register_user(client, "dupe@example.com")

    second = await client.post(
        "/api/v1/auth/register",
        json={"email": "dupe@example.com", "password": "password123"},
    )
    assert second.status_code == 400

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "dupe@example.com", "password": "password123"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_refresh_token_for_deleted_user_is_rejected(
    client: AsyncClient, db_session
):
    """A refresh token must stop working once the account is gone."""
    from sqlalchemy import delete

    from app.models.user import User

    tokens = await register_user(client, "deleted@example.com")

    await db_session.execute(delete(User).where(User.email == "deleted@example.com"))
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_password_shorter_than_minimum_is_rejected(client: AsyncClient):
    """Registration must enforce a minimum password length."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "short@example.com", "password": "abc"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unverifiable_long_password_is_rejected(client: AsyncClient):
    """bcrypt truncates past 72 bytes, so longer passwords must not be accepted."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "long@example.com", "password": "a" * 100},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_database_rejects_duplicate_emails(client: AsyncClient, db_session):
    """The unique index, not just the handler's pre-check, is what guarantees it.

    Two concurrent registrations can both pass the "does this email exist?"
    lookup before either commits; only a constraint stops the second one.
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.user import User

    await register_user(client, "constraint@example.com")

    db_session.add(User(email="constraint@example.com", hashed_password="irrelevant"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
