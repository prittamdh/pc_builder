"""add p_category column to products

Revision ID: 94ff4e0a9e14
Revises: 6e382c2f1976
Create Date: 2026-07-30 01:33:27.305158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94ff4e0a9e14'
down_revision: Union[str, Sequence[str], None] = '6e382c2f1976'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('products', sa.Column('p_category', sa.String(), nullable=True))
    op.create_index(op.f('ix_products_p_category'), 'products', ['p_category'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_products_p_category'), table_name='products')
    op.drop_column('products', 'p_category')
