"""add is_legacy flag to products

Revision ID: 7c4a1b8e5d02
Revises: 5e2b8c4f1a97
Create Date: 2026-08-16 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7c4a1b8e5d02'
down_revision: Union[str, Sequence[str], None] = '5e2b8c4f1a97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Marks parts that are off the supported-platform policy (see
    src/matching/legacy_policy.py) so the PC Builder can hide them while price
    tracking keeps working for the full catalog. Defaults to false so nothing is
    hidden until the backfill classifies it."""
    op.add_column(
        "products",
        sa.Column("is_legacy", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_products_is_legacy", "products", ["is_legacy"])


def downgrade() -> None:
    op.drop_index("ix_products_is_legacy", table_name="products", if_exists=True)
    op.drop_column("products", "is_legacy")
