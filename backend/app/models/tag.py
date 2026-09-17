import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.todo import Todo
    from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Association table. Its composite primary key is what makes a tag attachable
# to a todo exactly once; the separate index on tag_id serves the reverse
# lookup ("which todos carry this tag"), which the primary key cannot because
# tag_id is not its leading column.
todo_tags = Table(
    "todo_tags",
    Base.metadata,
    Column(
        "todo_id",
        ForeignKey("todos.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "tag_id",
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False, default=_utcnow),
    Index("ix_todo_tags_tag_id", "tag_id"),
)


class Tag(Base):
    """A user-owned label that can be attached to that user's todos."""

    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Case-insensitive uniqueness per user: "Work" and "work" are one tag.
    # Enforced on lower(name) in the database rather than by a pre-check in the
    # handler, because two concurrent creates both pass a pre-check before
    # either commits.
    #
    # This index also serves plain `WHERE user_id = ?` lookups, since user_id
    # is its leading column -- a separate index on tags(user_id) would be
    # redundant and would only add write cost.
    __table_args__ = (
        Index(
            "uq_tags_user_id_lower_name",
            "user_id",
            text("lower(name)"),
            unique=True,
        ),
    )

    user: Mapped["User"] = relationship("User", back_populates="tags")
    todos: Mapped[list["Todo"]] = relationship(
        "Todo",
        secondary=todo_tags,
        back_populates="tags",
    )

    def __repr__(self) -> str:
        return f"<Tag {self.name}>"
