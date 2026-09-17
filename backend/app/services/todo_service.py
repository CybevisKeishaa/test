import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.todo import Todo
from app.schemas.todo import TodoCreate


async def create_todo(
    db: AsyncSession, todo_data: TodoCreate, user_id: uuid.UUID
) -> Todo:
    todo = Todo(
        title=todo_data.title,
        description=todo_data.description,
        user_id=user_id,
    )
    db.add(todo)
    await db.flush()
    await db.refresh(todo)
    return todo


async def get_todos(
    db: AsyncSession,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Todo], int]:
    """Get all todos with pagination for a specific user."""
    query = select(Todo).where(Todo.user_id == user_id).offset(skip).limit(limit)
    result = await db.execute(query)
    todos = list(result.scalars().all())

    count_query = select(func.count()).select_from(Todo).where(Todo.user_id == user_id)
    total = await db.execute(count_query)

    return todos, total.scalar_one()


async def get_todo_by_id(
    db: AsyncSession, todo_id: uuid.UUID, user_id: uuid.UUID
) -> Todo | None:
    """Fetch a todo, scoped to its owner.

    ``user_id`` is part of the WHERE clause rather than a check on the loaded
    row, so there is no code path that can read another user's todo at all.
    """
    result = await db.execute(
        select(Todo).where(Todo.id == todo_id, Todo.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_todo(db: AsyncSession, todo: Todo, update_data: dict) -> Todo:
    for key, value in update_data.items():
        setattr(todo, key, value)
    await db.flush()
    await db.refresh(todo)
    return todo


async def delete_todo(db: AsyncSession, todo: Todo) -> None:
    await db.delete(todo)
    await db.flush()
