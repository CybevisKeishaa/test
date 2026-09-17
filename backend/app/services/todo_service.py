import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import todo_tags
from app.models.todo import Todo
from app.schemas.todo import TodoCreate, TodoStatusFilter


class TodosNotFound(Exception):
    """Raised when a bulk operation names todos the caller does not own."""


@dataclass(frozen=True)
class TodoFilters:
    """Everything that narrows the todo list.

    Kept as one object so the query builder and the cache key are driven by
    exactly the same values -- a filter that reaches one but not the other is
    how a cache serves the wrong rows.
    """

    status: TodoStatusFilter = TodoStatusFilter.all
    tag_id: uuid.UUID | None = None
    keyword: str | None = None
    date_from: date | None = None
    date_to: date | None = None

    def cache_fingerprint(self) -> dict[str, str]:
        """Stable, fully-determined representation for the cache key."""
        return {
            "status": self.status.value,
            "tag_id": str(self.tag_id) if self.tag_id else "",
            "keyword": (self.keyword or "").strip().lower(),
            "date_from": self.date_from.isoformat() if self.date_from else "",
            "date_to": self.date_to.isoformat() if self.date_to else "",
        }


def _escape_like(term: str) -> str:
    """Escape LIKE wildcards so a literal % or _ matches itself."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _end_of_day(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


def _apply_filters(query: Select, filters: TodoFilters) -> Select:
    if filters.status is TodoStatusFilter.completed:
        query = query.where(Todo.completed.is_(True))
    elif filters.status is TodoStatusFilter.active:
        query = query.where(Todo.completed.is_(False))

    if filters.tag_id is not None:
        # A todo carries a tag at most once (composite primary key on
        # todo_tags), so this join cannot duplicate rows.
        query = query.join(todo_tags, todo_tags.c.todo_id == Todo.id).where(
            todo_tags.c.tag_id == filters.tag_id
        )

    if filters.keyword:
        pattern = f"%{_escape_like(filters.keyword.strip())}%"
        query = query.where(
            or_(
                Todo.title.ilike(pattern, escape="\\"),
                Todo.description.ilike(pattern, escape="\\"),
            )
        )

    # Dates are whole days in UTC: date_to is inclusive, which is what a user
    # picking a range in a date picker means.
    if filters.date_from is not None:
        query = query.where(Todo.created_at >= _start_of_day(filters.date_from))
    if filters.date_to is not None:
        query = query.where(Todo.created_at <= _end_of_day(filters.date_to))

    return query


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
    filters: TodoFilters | None = None,
) -> tuple[list[Todo], int]:
    """Get a page of todos belonging to ``user_id``.

    Ordered by ``created_at DESC, id DESC`` so pagination is stable: without a
    total order Postgres may return a row on two different pages, or on none.
    """
    filters = filters or TodoFilters()

    query = _apply_filters(select(Todo).where(Todo.user_id == user_id), filters)
    query = query.order_by(Todo.created_at.desc(), Todo.id.desc())

    result = await db.execute(query.offset(skip).limit(limit))
    todos = list(result.scalars().all())

    count_query = _apply_filters(
        select(func.count(Todo.id)).select_from(Todo).where(Todo.user_id == user_id),
        filters,
    )
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


async def bulk_set_completed(
    db: AsyncSession,
    user_id: uuid.UUID,
    todo_ids: list[uuid.UUID],
    completed: bool,
) -> int:
    """Set `completed` on several todos in one transaction.

    Either every id belongs to the caller and all of them are updated, or
    nothing is. Silently skipping ids the caller does not own would report a
    success that did not happen to the rows they asked about.
    """
    owned = await db.execute(
        select(Todo.id).where(Todo.id.in_(todo_ids), Todo.user_id == user_id)
    )
    owned_ids = set(owned.scalars().all())

    if owned_ids != set(todo_ids):
        raise TodosNotFound()

    result = await db.execute(
        update(Todo)
        .where(Todo.id.in_(todo_ids), Todo.user_id == user_id)
        .values(completed=completed, updated_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    await db.flush()
    return result.rowcount or 0
