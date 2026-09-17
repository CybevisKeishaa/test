"""index todos for per-user paginated listing

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-17 00:00:00.000000

todos had no index at all beyond its primary key, so the two queries behind
GET /todos both fell back to a sequential scan over the whole table:

    SELECT ... FROM todos WHERE user_id = $1
      ORDER BY created_at DESC, id DESC OFFSET $2 LIMIT $3
    SELECT count(*) FROM todos WHERE user_id = $1

(user_id, created_at DESC, id DESC) serves both. The leading column satisfies
the filter, and the trailing columns match the ORDER BY exactly, so Postgres
reads the rows already in order and stops at LIMIT instead of sorting the
user's entire history. The count query is answered by the same index.

Column order matters: the README suggests (user_id, completed, created_at),
but with `completed` sitting between the filter and the sort key, an
unfiltered list cannot use the index for ordering and pays a sort anyway.
That index becomes worth adding alongside this one when status filtering
exists -- not instead of it.

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "ix_todos_user_id_created_at"


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name != "postgresql":
        # SQLite (used by the test suite) has no CONCURRENTLY and no DESC
        # index support worth the complexity.
        op.create_index(INDEX_NAME, "todos", ["user_id", "created_at", "id"])
        return

    # CONCURRENTLY cannot run inside a transaction, and alembic wraps each
    # migration in one. A plain CREATE INDEX takes an ACCESS EXCLUSIVE lock
    # for the whole build, which on a million-row todos table blocks every
    # read and write until it finishes.
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
            "ON todos (user_id, created_at DESC, id DESC)"
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name != "postgresql":
        op.drop_index(INDEX_NAME, table_name="todos")
        return

    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")
