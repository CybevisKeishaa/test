"""add tags and todo_tags, plus a status-filtered todo index

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS_INDEX = "ix_todos_user_id_completed_created_at"


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Case-insensitive uniqueness per user, enforced on lower(name) so "Work"
    # and "work" cannot both exist. A handler-side pre-check is not a
    # substitute: two concurrent creates both pass it before either commits.
    #
    # user_id leads, so this index also serves "list my tags" -- a separate
    # index on tags(user_id) would be redundant write cost.
    op.create_index(
        "uq_tags_user_id_lower_name",
        "tags",
        ["user_id", sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "todo_tags",
        sa.Column("todo_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["todo_id"], ["todos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        # Composite PK: a tag attaches to a todo at most once. It also indexes
        # todo_tags(todo_id) for free, as the leading column.
        sa.PrimaryKeyConstraint("todo_id", "tag_id"),
    )
    # The reverse lookup ("which todos carry this tag") cannot use the primary
    # key, because tag_id is not its leading column.
    op.create_index("ix_todo_tags_tag_id", "todo_tags", ["tag_id"])

    _create_status_index()


def _create_status_index() -> None:
    """Index for the status-filtered list.

    With user_id AND completed both pinned by equality, created_at can still
    satisfy the ORDER BY. This does not replace ix_todos_user_id_created_at:
    for the *unfiltered* list, `completed` sitting between the filter and the
    sort key would force a sort. See docs/DB_PERFORMANCE.md section 7.
    """
    bind = op.get_bind()

    if bind.dialect.name != "postgresql":
        op.create_index(
            STATUS_INDEX, "todos", ["user_id", "completed", "created_at", "id"]
        )
        return

    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {STATUS_INDEX} "
            "ON todos (user_id, completed, created_at DESC, id DESC)"
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {STATUS_INDEX}")
    else:
        op.drop_index(STATUS_INDEX, table_name="todos")

    op.drop_index("ix_todo_tags_tag_id", table_name="todo_tags")
    op.drop_table("todo_tags")
    op.drop_index("uq_tags_user_id_lower_name", table_name="tags")
    op.drop_table("tags")
