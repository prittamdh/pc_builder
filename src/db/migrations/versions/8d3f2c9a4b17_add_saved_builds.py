"""add saved_builds

Revision ID: 8d3f2c9a4b17
Revises: 7c4a1b8e5d02
Create Date: 2026-08-16 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '8d3f2c9a4b17'
down_revision: Union[str, Sequence[str], None] = '7c4a1b8e5d02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Assembled builds previously lived only in browser memory and were lost on
    refresh. Selections are stored as product ids rather than a price snapshot, so a
    saved build is re-costed against current prices every time it is opened."""
    op.create_table(
        "saved_builds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("share_token", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("selections", postgresql.JSONB(), nullable=False),
        sa.Column("was_compatible", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saved_builds_share_token", "saved_builds", ["share_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_saved_builds_share_token", table_name="saved_builds", if_exists=True)
    op.drop_table("saved_builds")
