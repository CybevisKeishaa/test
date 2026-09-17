import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_redis
from app.core.redis import RedisClient
from app.core.todo_cache import invalidate_todo_list_cache
from app.db.session import get_db
from app.models.user import User
from app.schemas.tag import TagCreate, TagListResponse, TagResponse, TagUpdate
from app.services.tag_service import (
    DuplicateTagName,
    create_tag,
    delete_tag,
    get_tag_by_id,
    get_tags,
    update_tag,
)

router = APIRouter()

TAG_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Tag not found",
)


def _duplicate_name_error(name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"You already have a tag named '{name}'",
    )


@router.get("", response_model=TagListResponse)
async def list_tags(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the authenticated user's tags, alphabetically."""
    tags = await get_tags(db, current_user.id)
    return TagListResponse(
        items=[TagResponse.model_validate(tag) for tag in tags],
        total=len(tags),
    )


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_new_tag(
    tag_data: TagCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a tag. Names are unique per user, ignoring case."""
    try:
        return await create_tag(db, tag_data, current_user.id)
    except DuplicateTagName:
        raise _duplicate_name_error(tag_data.name)
    except IntegrityError:
        # The unique index caught a race the pre-check could not.
        await db.rollback()
        raise _duplicate_name_error(tag_data.name)


@router.patch("/{tag_id}", response_model=TagResponse)
async def update_existing_tag(
    tag_id: uuid.UUID,
    tag_data: TagUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Rename or recolour a tag."""
    tag = await get_tag_by_id(db, tag_id, current_user.id)
    if not tag:
        raise TAG_NOT_FOUND

    try:
        updated = await update_tag(db, tag, tag_data)
    except DuplicateTagName as exc:
        raise _duplicate_name_error(str(exc))
    except IntegrityError:
        await db.rollback()
        raise _duplicate_name_error(tag_data.name or "")

    # Tags are embedded in every cached todo page, so a rename makes those
    # pages stale even though no todo row changed.
    await invalidate_todo_list_cache(redis, current_user.id)

    return updated


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_tag(
    tag_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Delete a tag and every todo-tag link that references it."""
    tag = await get_tag_by_id(db, tag_id, current_user.id)
    if not tag:
        raise TAG_NOT_FOUND

    await delete_tag(db, tag)
    await invalidate_todo_list_cache(redis, current_user.id)

    return None
