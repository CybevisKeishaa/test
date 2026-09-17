import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag
from app.models.todo import Todo
from app.schemas.tag import TagCreate, TagUpdate


class DuplicateTagName(Exception):
    """Raised when a user already has a tag with that name, ignoring case."""


async def get_tags(db: AsyncSession, user_id: uuid.UUID) -> list[Tag]:
    result = await db.execute(
        select(Tag).where(Tag.user_id == user_id).order_by(func.lower(Tag.name))
    )
    return list(result.scalars().all())


async def get_tag_by_id(
    db: AsyncSession, tag_id: uuid.UUID, user_id: uuid.UUID
) -> Tag | None:
    """Fetch a tag, scoped to its owner.

    As with todos, the owner is part of the WHERE clause rather than a check
    on the loaded row, so no code path can reach another user's tag.
    """
    result = await db.execute(
        select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _name_taken(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    query = select(Tag.id).where(
        Tag.user_id == user_id, func.lower(Tag.name) == name.lower()
    )
    if exclude_id is not None:
        query = query.where(Tag.id != exclude_id)
    result = await db.execute(query.limit(1))
    return result.scalar_one_or_none() is not None


async def create_tag(db: AsyncSession, data: TagCreate, user_id: uuid.UUID) -> Tag:
    # A friendly error for the ordinary case. The unique index on
    # (user_id, lower(name)) is the actual guarantee -- two concurrent creates
    # both pass this check before either commits, and the loser's
    # IntegrityError is translated by the router.
    if await _name_taken(db, user_id, data.name):
        raise DuplicateTagName(data.name)

    tag = Tag(name=data.name, color=data.color, user_id=user_id)
    db.add(tag)
    await db.flush()
    await db.refresh(tag)
    return tag


async def update_tag(db: AsyncSession, tag: Tag, data: TagUpdate) -> Tag:
    update_data = data.model_dump(exclude_unset=True)

    new_name = update_data.get("name")
    if new_name is not None and await _name_taken(
        db, tag.user_id, new_name, exclude_id=tag.id
    ):
        raise DuplicateTagName(new_name)

    for key, value in update_data.items():
        setattr(tag, key, value)

    await db.flush()
    await db.refresh(tag)
    return tag


async def delete_tag(db: AsyncSession, tag: Tag) -> None:
    # todo_tags rows go with it: the association FK is ON DELETE CASCADE, and
    # the ORM clears the secondary rows for the loaded relationship too.
    await db.delete(tag)
    await db.flush()


async def attach_tag(db: AsyncSession, todo: Todo, tag: Tag) -> Todo:
    """Attach a tag to a todo. Idempotent: attaching twice is not an error."""
    if all(existing.id != tag.id for existing in todo.tags):
        todo.tags.append(tag)
        await db.flush()
        await db.refresh(todo)
    return todo


async def detach_tag(db: AsyncSession, todo: Todo, tag_id: uuid.UUID) -> bool:
    """Detach a tag. Returns False when it was not attached."""
    for existing in list(todo.tags):
        if existing.id == tag_id:
            todo.tags.remove(existing)
            await db.flush()
            await db.refresh(todo)
            return True
    return False
