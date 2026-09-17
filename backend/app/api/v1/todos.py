import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_redis
from app.core.redis import RedisClient
from app.db.session import get_db
from app.models.user import User
from app.schemas.todo import TodoCreate, TodoListResponse, TodoResponse, TodoUpdate
from app.services.todo_service import (
    create_todo,
    delete_todo,
    get_todo_by_id,
    get_todos,
    update_todo,
)

router = APIRouter()

CACHE_TTL = 300  # 5 minutes
MAX_PAGE_SIZE = 100

TODO_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Todo not found",
)


def todo_list_cache_key(user_id: uuid.UUID, page: int, size: int) -> str:
    """Cache key for one page of one user's todo list.

    The owner and the pagination window are both part of the key: a single
    shared key would serve one user's todos to every other user, and would also
    serve page 1 for every page request.
    """
    return f"todos:list:{user_id}:page={page}:size={size}"


async def invalidate_todo_list_cache(redis: RedisClient, user_id: uuid.UUID) -> None:
    """Drop every cached page for this user after a write."""
    await redis.delete_pattern(f"todos:list:{user_id}:*")


@router.get("", response_model=TodoListResponse)
async def list_todos(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get paginated list of todos."""
    skip = (page - 1) * size

    cache_key = todo_list_cache_key(current_user.id, page, size)

    cached = await redis.get(cache_key)
    if cached:
        return TodoListResponse(**json.loads(cached))

    todos, total = await get_todos(db, user_id=current_user.id, skip=skip, limit=size)

    # Every row is filtered on user_id == current_user.id, so the owner's email
    # is already in hand -- the previous per-row User query was a pure N+1.
    items = [
        TodoResponse(
            id=todo.id,
            title=todo.title,
            description=todo.description,
            completed=todo.completed,
            user_id=todo.user_id,
            created_at=todo.created_at,
            updated_at=todo.updated_at,
            user_email=current_user.email,
        )
        for todo in todos
    ]

    response = TodoListResponse(items=items, total=total, page=page, size=size)

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
