"""rekey cpu_specs to canonical_id instead of product_id

Revision ID: 9c1a4e7f2b30
Revises: 3b7e5f2a9c81
Create Date: 2026-08-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9c1a4e7f2b30'
down_revision: Union[str, Sequence[str], None] = '3b7e5f2a9c81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Physical specs (TDP/cores/clocks/socket/etc) are properties of the CPU MODEL, not
    the listing - re-extracting them per product_id was wasteful (599 listings collapse
    to ~120 unique models) and risked inconsistent answers for the same real chip.
    cpu_specs becomes one row per unique canonical_id; products join via
    products.canonical_id (existing FK) instead of a 1:1 product_id link.
    """
    op.drop_constraint('cpu_specs_product_id_fkey', 'cpu_specs', type_='foreignkey')
    op.drop_index(op.f('ix_cpu_specs_product_id'), table_name='cpu_specs', if_exists=True)
    op.drop_column('cpu_specs', 'product_id')

    op.alter_column('cpu_specs', 'canonical_id', existing_type=sa.String(length=255), nullable=False)
    op.create_unique_constraint('uq_cpu_specs_canonical_id', 'cpu_specs', ['canonical_id'])

    # Table was already empty from the prior migration's TRUNCATE; nothing to backfill.


def downgrade() -> None:
    """Restore product_id column (data cannot be reconstructed - manual re-run required)."""
    op.drop_constraint('uq_cpu_specs_canonical_id', 'cpu_specs', type_='unique')
    op.alter_column('cpu_specs', 'canonical_id', existing_type=sa.String(length=255), nullable=True)

    op.add_column('cpu_specs', sa.Column('product_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_cpu_specs_product_id'), 'cpu_specs', ['product_id'], unique=True)
    op.create_foreign_key('cpu_specs_product_id_fkey', 'cpu_specs', 'products', ['product_id'], ['id'], ondelete='CASCADE')
