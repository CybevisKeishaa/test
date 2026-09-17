import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.schemas.tag import TagResponse

MAX_BULK_TODOS = 200


class TodoStatusFilter(str, Enum):
    """`?status=` on the todo list."""

    all = "all"
    active = "active"
    completed = "completed"


class TodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None


class TodoUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    completed: bool | None = None


class TodoResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    completed: bool
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    user_email: str | None = None
    tags: list[TagResponse] = []

    model_config = {"from_attributes": True}


class TodoListResponse(BaseModel):
    items: list[TodoResponse]
    total: int
    page: int
    size: int


class TodoBulkStatusUpdate(BaseModel):
    todo_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=MAX_BULK_TODOS)
    completed: bool

    @field_validator("todo_ids")
    @classmethod
    def deduplicate(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        """Collapse repeats, preserving order.

        The same id twice is not an error worth rejecting, but it would make
        the `updated` count in the response misleading.
        """
        seen: set[uuid.UUID] = set()
        unique: list[uuid.UUID] = []
        for todo_id in value:
            if todo_id not in seen:
                seen.add(todo_id)
                unique.append(todo_id)
        return unique


class TodoBulkStatusResponse(BaseModel):
    updated: int
    completed: bool
