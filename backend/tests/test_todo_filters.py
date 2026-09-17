"""Filtering, tag scoping of the list, bulk status updates and their caching."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header_for

TODAY = datetime.now(timezone.utc).date()
TOMORROW = TODAY + timedelta(days=1)
YESTERDAY = TODAY - timedelta(days=1)


async def make_todo(
    client: AsyncClient, headers: dict, title: str, description: str | None = None
) -> dict:
    payload: dict = {"title": title}
    if description is not None:
        payload["description"] = description
    response = await client.post("/api/v1/todos", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def make_tag(client: AsyncClient, headers: dict, name: str) -> dict:
    response = await client.post("/api/v1/tags", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def set_completed(client: AsyncClient, headers: dict, todo_id: str, value: bool):
    response = await client.put(
        f"/api/v1/todos/{todo_id}", json={"completed": value}, headers=headers
    )
    assert response.status_code == 200


async def titles(client: AsyncClient, headers: dict, query: str = "") -> list[str]:
    response = await client.get(f"/api/v1/todos{query}", headers=headers)
    assert response.status_code == 200, response.text
    return [item["title"] for item in response.json()["items"]]


@pytest.fixture
async def user(client: AsyncClient) -> dict:
    return await auth_header_for(client, "filters@example.com")


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_status(client: AsyncClient, user):
    done = await make_todo(client, user, "finished")
    await make_todo(client, user, "pending")
    await set_completed(client, user, done["id"], True)

    assert await titles(client, user, "?status=completed") == ["finished"]
    assert await titles(client, user, "?status=active") == ["pending"]
    assert sorted(await titles(client, user, "?status=all")) == ["finished", "pending"]
    # No status behaves like "all".
    assert sorted(await titles(client, user)) == ["finished", "pending"]


@pytest.mark.asyncio
async def test_unknown_status_is_rejected(client: AsyncClient, user):
    response = await client.get("/api/v1/todos?status=maybe", headers=user)
    assert response.status_code == 422


# --------------------------------------------------------------------------
# tag
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_tag(client: AsyncClient, user):
    tag = await make_tag(client, user, "urgent")
    tagged = await make_todo(client, user, "tagged")
    await make_todo(client, user, "untagged")

    await client.post(
        f"/api/v1/todos/{tagged['id']}/tags", json={"tag_id": tag["id"]}, headers=user
    )

    assert await titles(client, user, f"?tag_id={tag['id']}") == ["tagged"]
    assert sorted(await titles(client, user)) == ["tagged", "untagged"]


@pytest.mark.asyncio
async def test_filter_by_another_users_tag_returns_nothing(client: AsyncClient, user):
    """A tag id is not a way to reach someone else's todos."""
    stranger = await auth_header_for(client, "filters-stranger@example.com")
    stranger_tag = await make_tag(client, stranger, "theirs")
    stranger_todo = await make_todo(client, stranger, "stranger todo")
    await client.post(
        f"/api/v1/todos/{stranger_todo['id']}/tags",
        json={"tag_id": stranger_tag["id"]},
        headers=stranger,
    )

    await make_todo(client, user, "my todo")

    assert await titles(client, user, f"?tag_id={stranger_tag['id']}") == []


@pytest.mark.asyncio
async def test_tags_are_returned_with_each_todo(client: AsyncClient, user):
    tag = await make_tag(client, user, "home")
    todo = await make_todo(client, user, "with tags")
    await client.post(
        f"/api/v1/todos/{todo['id']}/tags", json={"tag_id": tag["id"]}, headers=user
    )

    response = await client.get("/api/v1/todos", headers=user)
    item = response.json()["items"][0]
    assert [t["name"] for t in item["tags"]] == ["home"]


# --------------------------------------------------------------------------
# keyword
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keyword_matches_title_and_description(client: AsyncClient, user):
    await make_todo(client, user, "Buy milk")
    await make_todo(client, user, "Call plumber", "about the leaking tap")
    await make_todo(client, user, "Unrelated")

    assert await titles(client, user, "?keyword=milk") == ["Buy milk"]
    assert await titles(client, user, "?keyword=leaking") == ["Call plumber"]


@pytest.mark.asyncio
async def test_keyword_is_case_insensitive(client: AsyncClient, user):
    await make_todo(client, user, "Buy MILK")
    assert await titles(client, user, "?keyword=milk") == ["Buy MILK"]


@pytest.mark.asyncio
async def test_keyword_wildcards_are_literal(client: AsyncClient, user):
    """`%` must match a percent sign, not everything."""
    await make_todo(client, user, "50% off")
    await make_todo(client, user, "no discount")

    assert await titles(client, user, "?keyword=50%25") == ["50% off"]
    # A bare wildcard matches nothing, because it is escaped.
    assert await titles(client, user, "?keyword=%25%25%25") == []


@pytest.mark.asyncio
async def test_keyword_underscore_is_literal(client: AsyncClient, user):
    await make_todo(client, user, "snake_case")
    await make_todo(client, user, "snakeXcase")

    assert await titles(client, user, "?keyword=snake_case") == ["snake_case"]


# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_date_range(client: AsyncClient, user):
    await make_todo(client, user, "today's todo")

    assert await titles(client, user, f"?date_from={TODAY}") == ["today's todo"]
    # date_to is inclusive of the whole day, so today's rows are inside it.
    assert await titles(client, user, f"?date_to={TODAY}") == ["today's todo"]
    assert await titles(client, user, f"?date_from={TOMORROW}") == []
    assert await titles(client, user, f"?date_to={YESTERDAY}") == []
    assert await titles(client, user, f"?date_from={YESTERDAY}&date_to={TOMORROW}") == [
        "today's todo"
    ]


# --------------------------------------------------------------------------
# combinations and pagination
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filters_combine(client: AsyncClient, user):
    tag = await make_tag(client, user, "work")
    match = await make_todo(client, user, "Work report", "quarterly")
    other = await make_todo(client, user, "Work errand")
    await make_todo(client, user, "Home report")

    for todo in (match, other):
        await client.post(
            f"/api/v1/todos/{todo['id']}/tags",
            json={"tag_id": tag["id"]},
            headers=user,
        )
    await set_completed(client, user, match["id"], True)

    query = f"?status=completed&tag_id={tag['id']}&keyword=report&date_from={TODAY}"
    assert await titles(client, user, query) == ["Work report"]


@pytest.mark.asyncio
async def test_total_reflects_the_filter(client: AsyncClient, user):
    done = await make_todo(client, user, "one")
    await make_todo(client, user, "two")
    await make_todo(client, user, "three")
    await set_completed(client, user, done["id"], True)

    response = await client.get("/api/v1/todos?status=completed", headers=user)
    assert response.json()["total"] == 1

    response = await client.get("/api/v1/todos", headers=user)
    assert response.json()["total"] == 3


@pytest.mark.asyncio
async def test_page_size_alias_is_accepted(client: AsyncClient, user):
    """Tier 4 names the parameter `page_size`; `size` stays supported."""
    for name in ["a", "b", "c"]:
        await make_todo(client, user, name)

    by_alias = await client.get("/api/v1/todos?page=1&page_size=2", headers=user)
    assert by_alias.status_code == 200
    assert len(by_alias.json()["items"]) == 2
    assert by_alias.json()["size"] == 2

    by_size = await client.get("/api/v1/todos?page=1&size=2", headers=user)
    assert len(by_size.json()["items"]) == 2


@pytest.mark.asyncio
async def test_filtered_pagination_is_disjoint(client: AsyncClient, user):
    for index in range(3):
        todo = await make_todo(client, user, f"done-{index}")
        await set_completed(client, user, todo["id"], True)
    await make_todo(client, user, "still active")

    first = await client.get(
        "/api/v1/todos?status=completed&page=1&page_size=2", headers=user
    )
    second = await client.get(
        "/api/v1/todos?status=completed&page=2&page_size=2", headers=user
    )

    assert len(first.json()["items"]) == 2
    assert len(second.json()["items"]) == 1
    assert {i["id"] for i in first.json()["items"]}.isdisjoint(
        {i["id"] for i in second.json()["items"]}
    )
    assert "still active" not in [
        i["title"] for i in first.json()["items"] + second.json()["items"]
    ]


# --------------------------------------------------------------------------
# caching
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_key_includes_every_filter(client: AsyncClient, user, redis):
    """A filtered list must never be served a differently-filtered body."""
    done = await make_todo(client, user, "finished")
    await make_todo(client, user, "pending")
    await set_completed(client, user, done["id"], True)

    queries = [
        "",
        "?status=completed",
        "?status=active",
        "?keyword=fin",
        f"?date_from={TODAY}",
        "?page=1&page_size=1",
    ]
    for query in queries:
        await client.get(f"/api/v1/todos{query}", headers=user)

    assert len(redis.store) == len(queries), redis.store.keys()

    # And the cached bodies are still correct on the second, cached read.
    assert await titles(client, user, "?status=completed") == ["finished"]
    assert await titles(client, user, "?status=active") == ["pending"]


@pytest.mark.asyncio
async def test_attaching_a_tag_invalidates_the_cache(client: AsyncClient, user, redis):
    tag = await make_tag(client, user, "fresh")
    todo = await make_todo(client, user, "todo")

    await client.get("/api/v1/todos", headers=user)
    assert redis.store

    await client.post(
        f"/api/v1/todos/{todo['id']}/tags", json={"tag_id": tag["id"]}, headers=user
    )
    assert redis.store == {}

    response = await client.get("/api/v1/todos", headers=user)
    assert [t["name"] for t in response.json()["items"][0]["tags"]] == ["fresh"]


@pytest.mark.asyncio
async def test_detaching_a_tag_invalidates_the_cache(client: AsyncClient, user, redis):
    tag = await make_tag(client, user, "temp")
    todo = await make_todo(client, user, "todo")
    await client.post(
        f"/api/v1/todos/{todo['id']}/tags", json={"tag_id": tag["id"]}, headers=user
    )

    await client.get("/api/v1/todos", headers=user)
    await client.delete(f"/api/v1/todos/{todo['id']}/tags/{tag['id']}", headers=user)
    assert redis.store == {}

    response = await client.get("/api/v1/todos", headers=user)
    assert response.json()["items"][0]["tags"] == []


@pytest.mark.asyncio
async def test_renaming_a_tag_invalidates_the_cache(client: AsyncClient, user, redis):
    """Tags are embedded in the cached page, so a rename makes it stale."""
    tag = await make_tag(client, user, "before")
    todo = await make_todo(client, user, "todo")
    await client.post(
        f"/api/v1/todos/{todo['id']}/tags", json={"tag_id": tag["id"]}, headers=user
    )

    await client.get("/api/v1/todos", headers=user)
    assert redis.store

    await client.patch(
        f"/api/v1/tags/{tag['id']}", json={"name": "after"}, headers=user
    )
    assert redis.store == {}

    response = await client.get("/api/v1/todos", headers=user)
    assert [t["name"] for t in response.json()["items"][0]["tags"]] == ["after"]


@pytest.mark.asyncio
async def test_deleting_a_tag_invalidates_the_cache(client: AsyncClient, user, redis):
    tag = await make_tag(client, user, "doomed")
    todo = await make_todo(client, user, "todo")
    await client.post(
        f"/api/v1/todos/{todo['id']}/tags", json={"tag_id": tag["id"]}, headers=user
    )

    await client.get("/api/v1/todos", headers=user)
    await client.delete(f"/api/v1/tags/{tag['id']}", headers=user)
    assert redis.store == {}

    response = await client.get("/api/v1/todos", headers=user)
    assert response.json()["items"][0]["tags"] == []


# --------------------------------------------------------------------------
# bulk status
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_mark_completed(client: AsyncClient, user):
    ids = [(await make_todo(client, user, f"t{i}"))["id"] for i in range(3)]

    response = await client.patch(
        "/api/v1/todos/bulk-status",
        json={"todo_ids": ids, "completed": True},
        headers=user,
    )
    assert response.status_code == 200
    assert response.json() == {"updated": 3, "completed": True}

    assert sorted(await titles(client, user, "?status=completed")) == ["t0", "t1", "t2"]


@pytest.mark.asyncio
async def test_bulk_mark_active_again(client: AsyncClient, user):
    ids = [(await make_todo(client, user, f"t{i}"))["id"] for i in range(2)]
    await client.patch(
        "/api/v1/todos/bulk-status",
        json={"todo_ids": ids, "completed": True},
        headers=user,
    )

    response = await client.patch(
        "/api/v1/todos/bulk-status",
        json={"todo_ids": ids, "completed": False},
        headers=user,
    )
    assert response.status_code == 200
    assert await titles(client, user, "?status=completed") == []


@pytest.mark.asyncio
async def test_bulk_update_is_all_or_nothing_across_users(client: AsyncClient, user):
    """One foreign id must abort the whole batch, leaving nothing changed."""
    stranger = await auth_header_for(client, "bulk-stranger@example.com")
    mine = await make_todo(client, user, "mine")
    theirs = await make_todo(client, stranger, "theirs")

    response = await client.patch(
        "/api/v1/todos/bulk-status",
        json={"todo_ids": [mine["id"], theirs["id"]], "completed": True},
        headers=user,
    )
    assert response.status_code == 404

    # Neither todo moved.
    assert await titles(client, user, "?status=completed") == []
    assert await titles(client, stranger, "?status=completed") == []


@pytest.mark.asyncio
async def test_bulk_update_rejects_unknown_ids(client: AsyncClient, user):
    mine = await make_todo(client, user, "mine")
    missing = "00000000-0000-4000-8000-000000000000"

    response = await client.patch(
        "/api/v1/todos/bulk-status",
        json={"todo_ids": [mine["id"], missing], "completed": True},
        headers=user,
    )
    assert response.status_code == 404
    assert await titles(client, user, "?status=completed") == []


@pytest.mark.asyncio
async def test_bulk_update_deduplicates_ids(client: AsyncClient, user):
    todo = await make_todo(client, user, "once")

    response = await client.patch(
        "/api/v1/todos/bulk-status",
        json={"todo_ids": [todo["id"], todo["id"]], "completed": True},
        headers=user,
    )
    assert response.status_code == 200
    assert response.json()["updated"] == 1


@pytest.mark.asyncio
async def test_bulk_update_rejects_an_empty_list(client: AsyncClient, user):
    response = await client.patch(
        "/api/v1/todos/bulk-status",
        json={"todo_ids": [], "completed": True},
        headers=user,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_bulk_update_invalidates_the_cache(client: AsyncClient, user, redis):
    todo = await make_todo(client, user, "cached")

    await client.get("/api/v1/todos", headers=user)
    assert redis.store

    await client.patch(
        "/api/v1/todos/bulk-status",
        json={"todo_ids": [todo["id"]], "completed": True},
        headers=user,
    )
    assert redis.store == {}

    assert await titles(client, user, "?status=completed") == ["cached"]


@pytest.mark.asyncio
async def test_bulk_status_route_is_not_read_as_a_todo_id(client: AsyncClient, user):
    """`/todos/bulk-status` must not be captured by `/todos/{todo_id}`."""
    response = await client.patch(
        "/api/v1/todos/bulk-status",
        json={"todo_ids": ["00000000-0000-4000-8000-000000000000"], "completed": True},
        headers=user,
    )
    # 404 from the ownership check, not 422 from failing to parse a UUID path.
    assert response.status_code == 404
    assert response.json()["detail"] == "Todo not found"
