"""add capacity_per_module_gb to ram_title_extractions

Revision ID: 6d2f8a91c4e7
Revises: 27a4c9e1f8b3
Create Date: 2026-08-14 13:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6d2f8a91c4e7'
down_revision: Union[str, Sequence[str], None] = '27a4c9e1f8b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add per-module (per-stick) capacity to distinguish kit quantity/each-size/total."""
    op.add_column('ram_title_extractions', sa.Column('capacity_per_module_gb', sa.Numeric(6, 2), nullable=True))


def downgrade() -> None:
    """Drop capacity_per_module_gb column."""
    op.drop_column('ram_title_extractions', 'capacity_per_module_gb')
