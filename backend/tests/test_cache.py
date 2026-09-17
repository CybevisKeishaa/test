"""Regression tests for the Redis todo-list cache."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header_for


@pytest.mark.asyncio
async def test_cached_list_is_not_served_across_users(client: AsyncClient, redis):
    """One user's cached list must never be handed to another user.

    Regression: the cache key was the constant "todos:list". Whoever listed
    first populated it, and every other user was then served that same body --
    a complete breach of data isolation, invisible in the DB layer.
    """
    alice = await auth_header_for(client, "cache-alice@example.com")
    bob = await auth_header_for(client, "cache-bob@example.com")

    await client.post("/api/v1/todos", json={"title": "Alice secret"}, headers=alice)

    alice_list = await client.get("/api/v1/todos", headers=alice)
    assert [i["title"] for i in alice_list.json()["items"]] == ["Alice secret"]

    bob_list = await client.get("/api/v1/todos", headers=bob)
    assert bob_list.status_code == 200
    assert bob_list.json()["items"] == []
    assert bob_list.json()["total"] == 0
    assert "Alice secret" not in bob_list.text

    # Two distinct cache entries, not one shared one.
    assert len(redis.store) == 2


@pytest.mark.asyncio
async def test_cache_key_distinguishes_pages(client: AsyncClient):
    """Page 2 must not be served the cached body of page 1."""
    headers = await auth_header_for(client, "cache-pages@example.com")

    for title in ["one", "two", "three"]:
        await client.post("/api/v1/todos", json={"title": title}, headers=headers)

    page1 = await client.get("/api/v1/todos?page=1&size=2", headers=headers)
    page2 = await client.get("/api/v1/todos?page=2&size=2", headers=headers)

    assert len(page1.json()["items"]) == 2
    assert len(page2.json()["items"]) == 1

    page1_ids = {i["id"] for i in page1.json()["items"]}
    page2_ids = {i["id"] for i in page2.json()["items"]}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_create_invalidates_cached_list(client: AsyncClient, redis):
    """A new todo must appear immediately, not after the 5-minute TTL.

    Regression: no write path touched Redis, so the list stayed stale.
    """
    headers = await auth_header_for(client, "cache-create@example.com")

    await client.get("/api/v1/todos", headers=headers)
    assert redis.store, "first list should populate the cache"

    await client.post("/api/v1/todos", json={"title": "Fresh todo"}, headers=headers)
    assert redis.store == {}, "create must drop the cached pages"

    listed = await client.get("/api/v1/todos", headers=headers)
    assert [i["title"] for i in listed.json()["items"]] == ["Fresh todo"]


@pytest.mark.asyncio
async def test_update_invalidates_cached_list(client: AsyncClient):
    """An edited title must be visible on the next list call."""
    headers = await auth_header_for(client, "cache-update@example.com")

    created = await client.post(
        "/api/v1/todos", json={"title": "Before"}, headers=headers
    )
    todo_id = created.json()["id"]

    await client.get("/api/v1/todos", headers=headers)

    await client.put(
        f"/api/v1/todos/{todo_id}", json={"title": "After"}, headers=headers
    )

    listed = await client.get("/api/v1/todos", headers=headers)
    assert [i["title"] for i in listed.json()["items"]] == ["After"]


@pytest.mark.asyncio
async def test_delete_invalidates_cached_list(client: AsyncClient):
    """A deleted todo must disappear from the next list call."""
    headers = await auth_header_for(client, "cache-delete@example.com")

    created = await client.post(
        "/api/v1/todos", json={"title": "Doomed"}, headers=headers
    )
    todo_id = created.json()["id"]

    await client.get("/api/v1/todos", headers=headers)

    await client.delete(f"/api/v1/todos/{todo_id}", headers=headers)

    listed = await client.get("/api/v1/todos", headers=headers)
    assert listed.json()["items"] == []
    assert listed.json()["total"] == 0


@pytest.mark.asyncio
async def test_invalidation_is_scoped_to_the_writing_user(client: AsyncClient, redis):
    """One user's write must not flush another user's cached pages."""
    alice = await auth_header_for(client, "scope-alice@example.com")
    bob = await auth_header_for(client, "scope-bob@example.com")

    await client.get("/api/v1/todos", headers=alice)
    await client.get("/api/v1/todos", headers=bob)
    assert len(redis.store) == 2

    await client.post("/api/v1/todos", json={"title": "Bob todo"}, headers=bob)

    assert len(redis.store) == 1, "only Bob's cached page should be dropped"
