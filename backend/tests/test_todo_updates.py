"""Regression tests for todo update semantics."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header_for


@pytest.fixture
async def todo_with_description(client: AsyncClient):
    headers = await auth_header_for(client, "updates@example.com")
    response = await client.post(
        "/api/v1/todos",
        json={"title": "Original title", "description": "Original description"},
        headers=headers,
    )
    assert response.status_code == 201
    return headers, response.json()


@pytest.mark.asyncio
async def test_completed_can_be_set_back_to_false(
    client: AsyncClient, todo_with_description
):
    """Un-checking a todo must persist.

    Regression: the handler guarded the assignment with `if todo_data.completed:`,
    so the falsy value False was silently discarded and a completed todo could
    never be reopened.
    """
    headers, todo = todo_with_description

    completed = await client.put(
        f"/api/v1/todos/{todo['id']}", json={"completed": True}, headers=headers
    )
    assert completed.status_code == 200
    assert completed.json()["completed"] is True

    reopened = await client.put(
        f"/api/v1/todos/{todo['id']}", json={"completed": False}, headers=headers
    )
    assert reopened.status_code == 200
    assert reopened.json()["completed"] is False

    # Survives a re-read, not just the response body.
    fetched = await client.get(f"/api/v1/todos/{todo['id']}", headers=headers)
    assert fetched.json()["completed"] is False


@pytest.mark.asyncio
async def test_partial_update_preserves_untouched_fields(
    client: AsyncClient, todo_with_description
):
    """Sending only a title must not blank the description.

    Regression: model_dump() without exclude_unset filled every absent optional
    field with None, so any partial update wiped the rest of the row.
    """
    headers, todo = todo_with_description

    response = await client.put(
        f"/api/v1/todos/{todo['id']}", json={"title": "New title"}, headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New title"
    assert data["description"] == "Original description"


@pytest.mark.asyncio
async def test_partial_update_preserves_completed_flag(
    client: AsyncClient, todo_with_description
):
    """A title-only edit must not silently reopen a completed todo."""
    headers, todo = todo_with_description

    await client.put(
        f"/api/v1/todos/{todo['id']}", json={"completed": True}, headers=headers
    )

    response = await client.put(
        f"/api/v1/todos/{todo['id']}", json={"title": "Renamed"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["completed"] is True


@pytest.mark.asyncio
async def test_description_can_be_cleared_explicitly(
    client: AsyncClient, todo_with_description
):
    """An explicit null must still clear the field."""
    headers, todo = todo_with_description

    response = await client.put(
        f"/api/v1/todos/{todo['id']}", json={"description": None}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["description"] is None
    assert response.json()["title"] == "Original title"


@pytest.mark.asyncio
async def test_todo_list_is_ordered_newest_first(client: AsyncClient):
    """Pagination needs a total order to be stable."""
    headers = await auth_header_for(client, "ordering@example.com")

    for title in ["first", "second", "third"]:
        await client.post("/api/v1/todos", json={"title": title}, headers=headers)

    response = await client.get("/api/v1/todos", headers=headers)
    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["third", "second", "first"]


@pytest.mark.asyncio
async def test_oversized_page_size_is_rejected(client: AsyncClient):
    """`size` is capped so one request cannot pull the whole table."""
    headers = await auth_header_for(client, "pagesize@example.com")

    response = await client.get("/api/v1/todos?size=10000", headers=headers)
    assert response.status_code == 422
