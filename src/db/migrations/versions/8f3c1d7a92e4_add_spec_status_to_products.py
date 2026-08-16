"""add spec_status to products

Revision ID: 8f3c1d7a92e4
Revises: 6d2f8a91c4e7
Create Date: 2026-08-14 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8f3c1d7a92e4'
down_revision: Union[str, Sequence[str], None] = '6d2f8a91c4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add spec_status traceability column to products: pending/extracted/needs_review/failed."""
    op.add_column('products', sa.Column('spec_status', sa.String(length=20), nullable=False, server_default='pending'))
    op.create_index(op.f('ix_products_spec_status'), 'products', ['spec_status'], unique=False)


def downgrade() -> None:
    """Drop spec_status column."""
    op.drop_index(op.f('ix_products_spec_status'), table_name='products', if_exists=True)
    op.drop_column('products', 'spec_status')
