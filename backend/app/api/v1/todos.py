import json
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_redis
from app.core.redis import RedisClient
from app.core.todo_cache import (
    CACHE_TTL,
    invalidate_todo_list_cache,
    todo_list_cache_key,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.tag import TodoTagAttach
from app.schemas.todo import (
    TodoBulkStatusResponse,
    TodoBulkStatusUpdate,
    TodoCreate,
    TodoListResponse,
    TodoResponse,
    TodoStatusFilter,
    TodoUpdate,
)
from app.services.tag_service import attach_tag, detach_tag, get_tag_by_id
from app.services.todo_service import (
    TodoFilters,
    TodosNotFound,
    bulk_set_completed,
    create_todo,
    delete_todo,
    get_todo_by_id,
    get_todos,
    update_todo,
)

router = APIRouter()

MAX_PAGE_SIZE = 100

TODO_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Todo not found",
)
TAG_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Tag not found",
)


def _with_owner_email(todo, email: str) -> TodoResponse:
    return TodoResponse.model_validate(todo).model_copy(update={"user_email": email})


@router.get("", response_model=TodoListResponse)
async def list_todos(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    page_size: int | None = Query(
        None, ge=1, le=MAX_PAGE_SIZE, description="Alias for `size`; takes precedence."
    ),
    status_filter: TodoStatusFilter = Query(TodoStatusFilter.all, alias="status"),
    tag_id: uuid.UUID | None = Query(None),
    keyword: str | None = Query(None, max_length=200),
    date_from: date | None = Query(None, description="Inclusive, UTC day"),
    date_to: date | None = Query(None, description="Inclusive, UTC day"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get a filtered, paginated list of todos."""
    effective_size = page_size if page_size is not None else size
    skip = (page - 1) * effective_size

    filters = TodoFilters(
        status=status_filter,
        tag_id=tag_id,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
    )

    cache_key = todo_list_cache_key(current_user.id, page, effective_size, filters)

    cached = await redis.get(cache_key)
    if cached:
        return TodoListResponse(**json.loads(cached))

    todos, total = await get_todos(
        db,
        user_id=current_user.id,
        skip=skip,
        limit=effective_size,
        filters=filters,
    )

    # Every row is filtered on user_id == current_user.id, so the owner's email
    # is already in hand -- the previous per-row User query was a pure N+1.
    items = [_with_owner_email(todo, current_user.email) for todo in todos]

    response = TodoListResponse(
        items=items, total=total, page=page, size=effective_size
    )

    await redis.set(cache_key, response.model_dump_json(), ex=CACHE_TTL)

    return response


@router.post("", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
async def create_new_todo(
    todo_data: TodoCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Create a new todo item."""
    todo = await create_todo(db, todo_data, current_user.id)
    await invalidate_todo_list_cache(redis, current_user.id)
    return todo


@router.patch("/bulk-status", response_model=TodoBulkStatusResponse)
async def bulk_update_status(
    payload: TodoBulkStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Mark several todos completed or active in one transaction.

    Declared before `/{todo_id}` so "bulk-status" is never read as an id.
    """
    try:
        updated = await bulk_set_completed(
            db, current_user.id, payload.todo_ids, payload.completed
        )
    except TodosNotFound:
        # All or nothing: if any id is not the caller's, nothing is written.
        # 404 rather than 403, so the response does not confirm which ids exist.
        raise TODO_NOT_FOUND

    await invalidate_todo_list_cache(redis, current_user.id)

    return TodoBulkStatusResponse(updated=updated, completed=payload.completed)


@router.get("/{todo_id}", response_model=TodoResponse)
async def get_todo(
    todo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific todo by ID."""
    todo = await get_todo_by_id(db, todo_id, current_user.id)
    if not todo:
        # 404 rather than 403: telling a stranger "this exists but is not
        # yours" leaks which todo ids are real.
        raise TODO_NOT_FOUND

    return todo


@router.put("/{todo_id}", response_model=TodoResponse)
async def update_existing_todo(
    todo_id: uuid.UUID,
    todo_data: TodoUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Update a todo item."""
    todo = await get_todo_by_id(db, todo_id, current_user.id)
    if not todo:
        raise TODO_NOT_FOUND

    # exclude_unset keeps a partial update partial: a request that only carries
    # a title must not blank out the description. Fields that ARE sent are
    # applied as-is, so completed=false is persisted like any other value.
    update_data = todo_data.model_dump(exclude_unset=True)

    updated_todo = await update_todo(db, todo, update_data)
    await invalidate_todo_list_cache(redis, current_user.id)

    return updated_todo


@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_todo(
    todo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Delete a todo item."""
    todo = await get_todo_by_id(db, todo_id, current_user.id)
    if not todo:
        raise TODO_NOT_FOUND

    await delete_todo(db, todo)
    await invalidate_todo_list_cache(redis, current_user.id)

    return None


@router.post("/{todo_id}/tags", response_model=TodoResponse)
async def attach_tag_to_todo(
    todo_id: uuid.UUID,
    payload: TodoTagAttach,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Attach one of the caller's tags to one of the caller's todos.

    Both lookups are owner-scoped, so a user can neither tag someone else's
    todo nor put someone else's tag on their own.
    """
    todo = await get_todo_by_id(db, todo_id, current_user.id)
    if not todo:
        raise TODO_NOT_FOUND

    tag = await get_tag_by_id(db, payload.tag_id, current_user.id)
    if not tag:
        raise TAG_NOT_FOUND

    # Idempotent: attaching a tag that is already on the todo is a no-op, not
    # an error -- the end state the caller asked for is the one they get.
    updated = await attach_tag(db, todo, tag)
    await invalidate_todo_list_cache(redis, current_user.id)

    return updated


@router.delete("/{todo_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_tag_from_todo(
    todo_id: uuid.UUID,
    tag_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Remove a tag from a todo. The tag itself is not deleted."""
    todo = await get_todo_by_id(db, todo_id, current_user.id)
    if not todo:
        raise TODO_NOT_FOUND

    if not await detach_tag(db, todo, tag_id):
        raise TAG_NOT_FOUND

    await invalidate_todo_list_cache(redis, current_user.id)

    return None
