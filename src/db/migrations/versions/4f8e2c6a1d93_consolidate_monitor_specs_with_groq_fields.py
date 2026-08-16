"""consolidate monitor_specs: rekey to canonical_id, add groq identity + metadata fields

Revision ID: 4f8e2c6a1d93
Revises: 9c1a4e7f2b30
Create Date: 2026-08-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4f8e2c6a1d93'
down_revision: Union[str, Sequence[str], None] = '9c1a4e7f2b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Same rework as cpu_specs: monitor_specs becomes one row per unique canonical_id
    (real monitor model) instead of per product_id (listing) - many stores list the
    same monitor model, and screen_size/resolution/refresh_rate/panel_type are
    properties of the model, not the listing.
    """
    op.drop_constraint('monitor_specs_product_id_fkey', 'monitor_specs', type_='foreignkey')
    op.drop_index(op.f('ix_monitor_specs_product_id'), table_name='monitor_specs', if_exists=True)
    op.drop_column('monitor_specs', 'product_id')

    op.add_column('monitor_specs', sa.Column('brand', sa.String(length=50), nullable=True))
    op.add_column('monitor_specs', sa.Column('model_number', sa.String(length=100), nullable=True))
    op.add_column('monitor_specs', sa.Column('confidence', sa.String(length=20), nullable=True))
    op.add_column('monitor_specs', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('monitor_specs', sa.Column('llm_model', sa.String(length=100), nullable=True))
    op.add_column('monitor_specs', sa.Column('raw_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('monitor_specs', sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'))
    op.add_column('monitor_specs', sa.Column('error', sa.Text(), nullable=True))

    op.create_index(op.f('ix_monitor_specs_brand'), 'monitor_specs', ['brand'], unique=False)
    op.create_index(op.f('ix_monitor_specs_model_number'), 'monitor_specs', ['model_number'], unique=False)
    op.create_index(op.f('ix_monitor_specs_status'), 'monitor_specs', ['status'], unique=False)

    op.execute("TRUNCATE TABLE monitor_specs RESTART IDENTITY;")

    op.alter_column('monitor_specs', 'canonical_id', existing_type=sa.String(length=255), nullable=False)
    op.create_unique_constraint('uq_monitor_specs_canonical_id', 'monitor_specs', ['canonical_id'])


def downgrade() -> None:
    """Restore product_id column (data cannot be reconstructed - manual re-run required)."""
    op.drop_constraint('uq_monitor_specs_canonical_id', 'monitor_specs', type_='unique')
    op.alter_column('monitor_specs', 'canonical_id', existing_type=sa.String(length=255), nullable=True)

    op.drop_index(op.f('ix_monitor_specs_status'), table_name='monitor_specs', if_exists=True)
    op.drop_index(op.f('ix_monitor_specs_model_number'), table_name='monitor_specs', if_exists=True)
    op.drop_index(op.f('ix_monitor_specs_brand'), table_name='monitor_specs', if_exists=True)

    op.drop_column('monitor_specs', 'error')
    op.drop_column('monitor_specs', 'status')
    op.drop_column('monitor_specs', 'raw_response')
    op.drop_column('monitor_specs', 'llm_model')
    op.drop_column('monitor_specs', 'notes')
    op.drop_column('monitor_specs', 'confidence')
    op.drop_column('monitor_specs', 'model_number')
    op.drop_column('monitor_specs', 'brand')

    op.add_column('monitor_specs', sa.Column('product_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_monitor_specs_product_id'), 'monitor_specs', ['product_id'], unique=True)
    op.create_foreign_key('monitor_specs_product_id_fkey', 'monitor_specs', 'products', ['product_id'], ['id'], ondelete='CASCADE')
