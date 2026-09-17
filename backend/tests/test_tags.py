"""Tag CRUD, per-user uniqueness and tag/todo mapping."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header_for


async def create_tag(
    client: AsyncClient, headers: dict, name: str, color: str | None = None
):
    payload: dict = {"name": name}
    if color is not None:
        payload["color"] = color
    return await client.post("/api/v1/tags", json=payload, headers=headers)


async def create_todo(client: AsyncClient, headers: dict, title: str) -> dict:
    response = await client.post(
        "/api/v1/todos", json={"title": title}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def owner(client: AsyncClient) -> dict:
    return await auth_header_for(client, "tag-owner@example.com")


@pytest.mark.asyncio
async def test_create_tag(client: AsyncClient, owner):
    response = await create_tag(client, owner, "Work", "#4F46E5")
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Work"
    assert data["color"] == "#4f46e5"  # normalised
    assert "id" in data


@pytest.mark.asyncio
async def test_tag_name_is_trimmed(client: AsyncClient, owner):
    response = await create_tag(client, owner, "  Errands  ")
    assert response.status_code == 201
    assert response.json()["name"] == "Errands"


@pytest.mark.asyncio
async def test_blank_tag_name_is_rejected(client: AsyncClient, owner):
    assert (await create_tag(client, owner, "   ")).status_code == 422


@pytest.mark.asyncio
async def test_invalid_colour_is_rejected(client: AsyncClient, owner):
    assert (await create_tag(client, owner, "Bad", "not-a-colour")).status_code == 422


@pytest.mark.asyncio
async def test_duplicate_tag_name_is_rejected_ignoring_case(client: AsyncClient, owner):
    """ "Work" and "work" are the same tag for one user."""
    assert (await create_tag(client, owner, "Work")).status_code == 201

    for variant in ["Work", "work", "WORK", "  wOrK "]:
        response = await create_tag(client, owner, variant)
        assert response.status_code == 409, variant


@pytest.mark.asyncio
async def test_database_rejects_duplicate_tag_names(client: AsyncClient, db_session):
    """The unique index on (user_id, lower(name)), not just the pre-check.

    Two concurrent creates both pass the handler's lookup before either
    commits; only the constraint stops the second.
    """
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.models.tag import Tag
    from app.models.user import User

    headers = await auth_header_for(client, "tag-race@example.com")
    assert (await create_tag(client, headers, "Home")).status_code == 201

    user = (
        await db_session.execute(
            select(User).where(User.email == "tag-race@example.com")
        )
    ).scalar_one()

    db_session.add(Tag(name="HOME", user_id=user.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_two_users_may_share_a_tag_name(client: AsyncClient, owner):
    """Uniqueness is per user, not global."""
    other = await auth_header_for(client, "tag-other@example.com")

    assert (await create_tag(client, owner, "Work")).status_code == 201
    assert (await create_tag(client, other, "Work")).status_code == 201


@pytest.mark.asyncio
async def test_list_returns_only_own_tags(client: AsyncClient, owner):
    other = await auth_header_for(client, "tag-stranger@example.com")
    await create_tag(client, owner, "Owner tag")
    await create_tag(client, other, "Stranger tag")

    response = await client.get("/api/v1/tags", headers=other)
    assert response.status_code == 200
    data = response.json()
    assert [item["name"] for item in data["items"]] == ["Stranger tag"]
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_tags_are_listed_alphabetically(client: AsyncClient, owner):
    for name in ["zebra", "Apple", "mango"]:
        await create_tag(client, owner, name)

    response = await client.get("/api/v1/tags", headers=owner)
    assert [item["name"] for item in response.json()["items"]] == [
        "Apple",
        "mango",
        "zebra",
    ]


@pytest.mark.asyncio
async def test_rename_tag(client: AsyncClient, owner):
    tag_id = (await create_tag(client, owner, "Old")).json()["id"]

    response = await client.patch(
        f"/api/v1/tags/{tag_id}", json={"name": "New"}, headers=owner
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New"


@pytest.mark.asyncio
async def test_rename_to_an_existing_name_is_rejected(client: AsyncClient, owner):
    await create_tag(client, owner, "Work")
    other_id = (await create_tag(client, owner, "Home")).json()["id"]

    response = await client.patch(
        f"/api/v1/tags/{other_id}", json={"name": "WORK"}, headers=owner
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_renaming_a_tag_to_its_own_name_is_allowed(client: AsyncClient, owner):
    """The uniqueness check must exclude the row being updated."""
    tag_id = (await create_tag(client, owner, "Work")).json()["id"]

    response = await client.patch(
        f"/api/v1/tags/{tag_id}",
        json={"name": "Work", "color": "#111111"},
        headers=owner,
    )
    assert response.status_code == 200
    assert response.json()["color"] == "#111111"


@pytest.mark.asyncio
async def test_user_cannot_read_update_or_delete_another_users_tag(
    client: AsyncClient, owner
):
    stranger = await auth_header_for(client, "tag-intruder@example.com")
    tag_id = (await create_tag(client, owner, "Private")).json()["id"]

    patched = await client.patch(
        f"/api/v1/tags/{tag_id}", json={"name": "Hacked"}, headers=stranger
    )
    assert patched.status_code == 404

    deleted = await client.delete(f"/api/v1/tags/{tag_id}", headers=stranger)
    assert deleted.status_code == 404

    # Still intact for its owner.
    listed = await client.get("/api/v1/tags", headers=owner)
    assert [item["name"] for item in listed.json()["items"]] == ["Private"]


@pytest.mark.asyncio
async def test_delete_tag_removes_it_from_todos(client: AsyncClient, owner):
    tag_id = (await create_tag(client, owner, "Temporary")).json()["id"]
    todo = await create_todo(client, owner, "Tagged todo")

    attached = await client.post(
        f"/api/v1/todos/{todo['id']}/tags", json={"tag_id": tag_id}, headers=owner
    )
    assert attached.status_code == 200
    assert [t["name"] for t in attached.json()["tags"]] == ["Temporary"]

    assert (
        await client.delete(f"/api/v1/tags/{tag_id}", headers=owner)
    ).status_code == 204

    # The todo survives; only the link is gone.
    response = await client.get(f"/api/v1/todos/{todo['id']}", headers=owner)
    assert response.status_code == 200
    assert response.json()["tags"] == []


@pytest.mark.asyncio
async def test_attaching_another_users_tag_is_rejected(client: AsyncClient, owner):
    """A user must not be able to put someone else's tag on their own todo."""
    stranger = await auth_header_for(client, "tag-borrower@example.com")
    foreign_tag_id = (await create_tag(client, owner, "Owner only")).json()["id"]

    own_todo = await create_todo(client, stranger, "Stranger todo")

    response = await client.post(
        f"/api/v1/todos/{own_todo['id']}/tags",
        json={"tag_id": foreign_tag_id},
        headers=stranger,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_tagging_another_users_todo_is_rejected(client: AsyncClient, owner):
    stranger = await auth_header_for(client, "todo-tagger@example.com")
    owner_todo = await create_todo(client, owner, "Owner todo")
    stranger_tag_id = (await create_tag(client, stranger, "Mine")).json()["id"]

    response = await client.post(
        f"/api/v1/todos/{owner_todo['id']}/tags",
        json={"tag_id": stranger_tag_id},
        headers=stranger,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_attaching_twice_is_idempotent(client: AsyncClient, owner):
    tag_id = (await create_tag(client, owner, "Once")).json()["id"]
    todo = await create_todo(client, owner, "Todo")

    for _ in range(2):
        response = await client.post(
            f"/api/v1/todos/{todo['id']}/tags", json={"tag_id": tag_id}, headers=owner
        )
        assert response.status_code == 200

    assert len(response.json()["tags"]) == 1


@pytest.mark.asyncio
async def test_detach_tag(client: AsyncClient, owner):
    tag_id = (await create_tag(client, owner, "Detachable")).json()["id"]
    todo = await create_todo(client, owner, "Todo")
    await client.post(
        f"/api/v1/todos/{todo['id']}/tags", json={"tag_id": tag_id}, headers=owner
    )

    response = await client.delete(
        f"/api/v1/todos/{todo['id']}/tags/{tag_id}", headers=owner
    )
    assert response.status_code == 204

    fetched = await client.get(f"/api/v1/todos/{todo['id']}", headers=owner)
    assert fetched.json()["tags"] == []

    # The tag itself still exists.
    listed = await client.get("/api/v1/tags", headers=owner)
    assert listed.json()["total"] == 1


@pytest.mark.asyncio
async def test_detaching_a_tag_that_is_not_attached_is_404(client: AsyncClient, owner):
    tag_id = (await create_tag(client, owner, "Unattached")).json()["id"]
    todo = await create_todo(client, owner, "Todo")

    response = await client.delete(
        f"/api/v1/todos/{todo['id']}/tags/{tag_id}", headers=owner
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_tag_routes_require_authentication(client: AsyncClient):
    assert (await client.get("/api/v1/tags")).status_code == 403
    assert (await client.post("/api/v1/tags", json={"name": "x"})).status_code == 403
