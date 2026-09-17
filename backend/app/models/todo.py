import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.tag import todo_tags

if TYPE_CHECKING:
    from app.models.tag import Tag
    from app.models.user import User


class Todo(Base):
    """Todo model."""

    __tablename__ = "todos"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Matches the filter and the sort of the paginated list query exactly, so
    # Postgres reads the page already ordered instead of sorting the user's
    # whole history. See alembic revision c2d3e4f5a6b7.
    __table_args__ = (
        Index(
            "ix_todos_user_id_created_at",
            "user_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
        # For the status-filtered list: user_id and completed are both pinned
        # by equality, so created_at can still satisfy the ORDER BY. The index
        # above stays for the *unfiltered* list, where `completed` sitting
        # between the filter and the sort key would force a sort.
        Index(
            "ix_todos_user_id_completed_created_at",
            "user_id",
            "completed",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )

    # Relationships
    user: Mapped["User"] = relationship(  # noqa: F821
        "User",
        back_populates="todos",
        lazy="select",
    )
    # selectin: tags are rendered with every todo, and one extra query for the
    # whole page beats one lazy load per row.
    tags: Mapped[list["Tag"]] = relationship(  # noqa: F821
        "Tag",
        secondary=todo_tags,
        back_populates="todos",
        lazy="selectin",
        order_by="Tag.name",
    )

    def __repr__(self) -> str:
        return f"<Todo {self.title}>"
