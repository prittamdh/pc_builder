"""add title_extractions tables for gpu, storage, cooler, cabinet, psu, motherboard

Revision ID: 151c8f2e9a04
Revises: 7a3d9f1e6c52
Create Date: 2026-08-15 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '151c8f2e9a04'
down_revision: Union[str, Sequence[str], None] = '7a3d9f1e6c52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_title_extraction_table(table_name: str, extra_columns: list[sa.Column]):
    """Common shape: product_id + canonical_id relation, raw_title, brand, category-
    specific identity fields, LLM metadata. Mirrors cpu_title_extractions."""
    columns = [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('canonical_id', sa.String(length=255), nullable=True),
        sa.Column('raw_title', sa.Text(), nullable=False),
        sa.Column('brand', sa.String(length=50), nullable=True),
        *extra_columns,
        sa.Column('confidence', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('llm_model', sa.String(length=100), nullable=True),
        sa.Column('raw_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['canonical_id'], ['canonical_parts.canonical_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', name=f'uq_{table_name}_product_id'),
    ]
    op.create_table(table_name, *columns)
    op.create_index(op.f(f'ix_{table_name}_product_id'), table_name, ['product_id'], unique=True)
    op.create_index(op.f(f'ix_{table_name}_canonical_id'), table_name, ['canonical_id'], unique=False)
    op.create_index(op.f(f'ix_{table_name}_brand'), table_name, ['brand'], unique=False)
    op.create_index(op.f(f'ix_{table_name}_status'), table_name, ['status'], unique=False)
    for col in extra_columns:
        if col.name in ('model_number', 'chipset', 'variant'):
            op.create_index(op.f(f'ix_{table_name}_{col.name}'), table_name, [col.name], unique=False)


def upgrade() -> None:
    """Per-listing identity tables for the 6 remaining major categories, matching the
    cpu/monitor_title_extractions pattern - product_id + canonical_id relation,
    identity fields only (no physical specs, sourced elsewhere for now)."""
    _create_title_extraction_table('gpu_title_extractions', [
        sa.Column('chipset', sa.String(length=100), nullable=True),
        sa.Column('variant', sa.String(length=150), nullable=True),
    ])
    _create_title_extraction_table('storage_title_extractions', [
        sa.Column('model_number', sa.String(length=100), nullable=True),
        sa.Column('capacity_gb', sa.Integer(), nullable=True),
        sa.Column('interface', sa.String(length=20), nullable=True),
    ])
    _create_title_extraction_table('cooler_title_extractions', [
        sa.Column('model_number', sa.String(length=100), nullable=True),
        sa.Column('cooler_type', sa.String(length=20), nullable=True),
        sa.Column('size_mm', sa.Integer(), nullable=True),
    ])
    _create_title_extraction_table('cabinet_title_extractions', [
        sa.Column('model_number', sa.String(length=100), nullable=True),
        sa.Column('color', sa.String(length=50), nullable=True),
        sa.Column('form_factor', sa.String(length=20), nullable=True),
    ])
    _create_title_extraction_table('psu_title_extractions', [
        sa.Column('model_number', sa.String(length=100), nullable=True),
        sa.Column('wattage', sa.Integer(), nullable=True),
        sa.Column('efficiency_rating', sa.String(length=20), nullable=True),
    ])
    _create_title_extraction_table('motherboard_title_extractions', [
        sa.Column('chipset', sa.String(length=50), nullable=True),
        sa.Column('model_number', sa.String(length=100), nullable=True),
    ])


def downgrade() -> None:
    """Drop all 6 per-listing identity tables."""
    op.drop_table('motherboard_title_extractions')
    op.drop_table('psu_title_extractions')
    op.drop_table('cabinet_title_extractions')
    op.drop_table('cooler_title_extractions')
    op.drop_table('storage_title_extractions')
    op.drop_table('gpu_title_extractions')
