"""Regression tests for cross-user data isolation on /todos."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header_for


async def _create_todo(
    client: AsyncClient, headers: dict[str, str], title: str, description: str = ""
) -> dict:
    response = await client.post(
        "/api/v1/todos",
        json={"title": title, "description": description},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def two_users(client: AsyncClient):
    """User A (owns a todo) and User B (owns nothing)."""
    alice = await auth_header_for(client, "alice@example.com")
    bob = await auth_header_for(client, "bob@example.com")
    todo = await _create_todo(client, alice, "Alice private todo", "secret")
    return alice, bob, todo


@pytest.mark.asyncio
async def test_user_cannot_read_another_users_todo(client: AsyncClient, two_users):
    """GET /todos/{id} must not serve a todo the caller does not own.

    Regression: the handler looked the todo up by id alone and never compared
    it against current_user, a textbook IDOR.
    """
    _alice, bob, todo = two_users

    response = await client.get(f"/api/v1/todos/{todo['id']}", headers=bob)
    assert response.status_code == 404
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_user_cannot_update_another_users_todo(client: AsyncClient, two_users):
    """PUT /todos/{id} must not let a stranger edit someone else's todo."""
    alice, bob, todo = two_users

    response = await client.put(
        f"/api/v1/todos/{todo['id']}",
        json={"title": "Hacked by Bob"},
        headers=bob,
    )
    assert response.status_code == 404

    # And the row is genuinely untouched.
    owner_view = await client.get(f"/api/v1/todos/{todo['id']}", headers=alice)
    assert owner_view.status_code == 200
    assert owner_view.json()["title"] == "Alice private todo"


@pytest.mark.asyncio
async def test_user_cannot_delete_another_users_todo(client: AsyncClient, two_users):
    """DELETE /todos/{id} must not let a stranger destroy someone else's data."""
    alice, bob, todo = two_users

    response = await client.delete(f"/api/v1/todos/{todo['id']}", headers=bob)
    assert response.status_code == 404

    owner_view = await client.get(f"/api/v1/todos/{todo['id']}", headers=alice)
    assert owner_view.status_code == 200


@pytest.mark.asyncio
async def test_todo_list_only_contains_own_todos(client: AsyncClient, two_users):
    """GET /todos must return only the caller's rows."""
    _alice, bob, todo = two_users

    await _create_todo(client, bob, "Bob own todo")

    response = await client.get("/api/v1/todos", headers=bob)
    assert response.status_code == 200
    data = response.json()

    titles = [item["title"] for item in data["items"]]
    assert titles == ["Bob own todo"]
    assert data["total"] == 1
    assert todo["id"] not in [item["id"] for item in data["items"]]


@pytest.mark.asyncio
async def test_unauthenticated_requests_are_rejected(client: AsyncClient, two_users):
    """Every todo route requires a bearer token."""
    _alice, _bob, todo = two_users

    assert (await client.get("/api/v1/todos")).status_code == 403
    assert (await client.get(f"/api/v1/todos/{todo['id']}")).status_code == 403
    assert (await client.post("/api/v1/todos", json={"title": "x"})).status_code == 403
    assert (await client.delete(f"/api/v1/todos/{todo['id']}")).status_code == 403
