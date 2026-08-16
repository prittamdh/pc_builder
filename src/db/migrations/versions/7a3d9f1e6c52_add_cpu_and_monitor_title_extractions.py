"""add cpu_title_extractions and monitor_title_extractions (per-listing identity tables)

Revision ID: 7a3d9f1e6c52
Revises: 4f8e2c6a1d93
Create Date: 2026-08-15 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7a3d9f1e6c52'
down_revision: Union[str, Sequence[str], None] = '4f8e2c6a1d93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_title_extraction_table(table_name: str, series_column: bool):
    columns = [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('canonical_id', sa.String(length=255), nullable=True),
        sa.Column('raw_title', sa.Text(), nullable=False),
        sa.Column('brand', sa.String(length=50), nullable=True),
    ]
    if series_column:
        columns.append(sa.Column('series', sa.String(length=100), nullable=True))
    columns += [
        sa.Column('model_number', sa.String(length=100), nullable=True),
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
    if series_column:
        op.create_index(op.f(f'ix_{table_name}_series'), table_name, ['series'], unique=False)
    op.create_index(op.f(f'ix_{table_name}_model_number'), table_name, ['model_number'], unique=False)
    op.create_index(op.f(f'ix_{table_name}_status'), table_name, ['status'], unique=False)


def upgrade() -> None:
    """
    Restore per-listing identity tables (product_id + canonical_id + extracted fields),
    kept deliberately separate from the *_specs tables (physical specs, out of scope
    for now / sourced elsewhere) - consolidation is deferred until there's more data
    and clearer usage patterns to design around.
    """
    _create_title_extraction_table('cpu_title_extractions', series_column=True)
    _create_title_extraction_table('monitor_title_extractions', series_column=False)


def downgrade() -> None:
    """Drop both per-listing identity tables."""
    op.drop_table('monitor_title_extractions')
    op.drop_table('cpu_title_extractions')
