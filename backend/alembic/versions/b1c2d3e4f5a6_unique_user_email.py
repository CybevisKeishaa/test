"""enforce unique user email

Revision ID: b1c2d3e4f5a6
Revises: a0790c76a129
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a0790c76a129"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Any pre-existing duplicates would abort the index build, so collapse them
    # first: keep the oldest account for each address and re-point its todos.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   email,
                   ROW_NUMBER() OVER (
                       PARTITION BY lower(email) ORDER BY created_at, id
                   ) AS rn,
                   FIRST_VALUE(id) OVER (
                       PARTITION BY lower(email) ORDER BY created_at, id
                   ) AS keep_id
            FROM users
        )
        UPDATE todos
        SET user_id = ranked.keep_id
        FROM ranked
        WHERE todos.user_id = ranked.id AND ranked.rn > 1
        """
    )
    op.execute(
        """
        DELETE FROM users
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY lower(email) ORDER BY created_at, id
                       ) AS rn
                FROM users
            ) dupes
            WHERE rn > 1
        )
        """
    )

    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
