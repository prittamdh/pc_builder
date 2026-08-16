"""add cpu_title_extractions table

Revision ID: 151f1907b9b9
Revises: a1b2c3d4e5f6
Create Date: 2026-08-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '151f1907b9b9'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create cpu_title_extractions staging table for Groq LLM title extraction."""
    op.create_table(
        'cpu_title_extractions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('raw_title', sa.Text(), nullable=False),
        sa.Column('brand', sa.String(length=50), nullable=True),
        sa.Column('series', sa.String(length=100), nullable=True),
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
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', name='uq_cpu_title_extractions_product_id'),
    )
    op.create_index(op.f('ix_cpu_title_extractions_product_id'), 'cpu_title_extractions', ['product_id'], unique=True)
    op.create_index(op.f('ix_cpu_title_extractions_brand'), 'cpu_title_extractions', ['brand'], unique=False)
    op.create_index(op.f('ix_cpu_title_extractions_series'), 'cpu_title_extractions', ['series'], unique=False)
    op.create_index(op.f('ix_cpu_title_extractions_model_number'), 'cpu_title_extractions', ['model_number'], unique=False)
    op.create_index(op.f('ix_cpu_title_extractions_status'), 'cpu_title_extractions', ['status'], unique=False)


def downgrade() -> None:
    """Drop cpu_title_extractions table."""
    op.drop_index(op.f('ix_cpu_title_extractions_status'), table_name='cpu_title_extractions', if_exists=True)
    op.drop_index(op.f('ix_cpu_title_extractions_model_number'), table_name='cpu_title_extractions', if_exists=True)
    op.drop_index(op.f('ix_cpu_title_extractions_series'), table_name='cpu_title_extractions', if_exists=True)
    op.drop_index(op.f('ix_cpu_title_extractions_brand'), table_name='cpu_title_extractions', if_exists=True)
    op.drop_index(op.f('ix_cpu_title_extractions_product_id'), table_name='cpu_title_extractions', if_exists=True)
    op.drop_table('cpu_title_extractions')
