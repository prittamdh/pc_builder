"""add ram_title_extractions table

Revision ID: 27a4c9e1f8b3
Revises: 151f1907b9b9
Create Date: 2026-08-14 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '27a4c9e1f8b3'
down_revision: Union[str, Sequence[str], None] = '151f1907b9b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ram_title_extractions staging table for Groq LLM title extraction."""
    op.create_table(
        'ram_title_extractions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('raw_title', sa.Text(), nullable=False),
        sa.Column('brand', sa.String(length=50), nullable=True),
        sa.Column('series', sa.String(length=100), nullable=True),
        sa.Column('memory_type', sa.String(length=20), nullable=True),
        sa.Column('capacity_gb', sa.Numeric(6, 2), nullable=True),
        sa.Column('modules', sa.Integer(), nullable=True),
        sa.Column('speed_mhz', sa.Integer(), nullable=True),
        sa.Column('cl_timing', sa.String(length=20), nullable=True),
        sa.Column('form_factor', sa.String(length=20), nullable=True),
        sa.Column('confidence', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('llm_model', sa.String(length=100), nullable=True),
        sa.Column('raw_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', name='uq_ram_title_extractions_product_id'),
    )
    op.create_index(op.f('ix_ram_title_extractions_product_id'), 'ram_title_extractions', ['product_id'], unique=True)
    op.create_index(op.f('ix_ram_title_extractions_brand'), 'ram_title_extractions', ['brand'], unique=False)
    op.create_index(op.f('ix_ram_title_extractions_series'), 'ram_title_extractions', ['series'], unique=False)
    op.create_index(op.f('ix_ram_title_extractions_memory_type'), 'ram_title_extractions', ['memory_type'], unique=False)
    op.create_index(op.f('ix_ram_title_extractions_status'), 'ram_title_extractions', ['status'], unique=False)


def downgrade() -> None:
    """Drop ram_title_extractions table."""
    op.drop_index(op.f('ix_ram_title_extractions_status'), table_name='ram_title_extractions', if_exists=True)
    op.drop_index(op.f('ix_ram_title_extractions_memory_type'), table_name='ram_title_extractions', if_exists=True)
    op.drop_index(op.f('ix_ram_title_extractions_series'), table_name='ram_title_extractions', if_exists=True)
    op.drop_index(op.f('ix_ram_title_extractions_brand'), table_name='ram_title_extractions', if_exists=True)
    op.drop_index(op.f('ix_ram_title_extractions_product_id'), table_name='ram_title_extractions', if_exists=True)
    op.drop_table('ram_title_extractions')
