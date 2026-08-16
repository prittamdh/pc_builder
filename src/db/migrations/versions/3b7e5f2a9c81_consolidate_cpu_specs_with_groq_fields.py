"""consolidate cpu_specs with groq identity and llm metadata fields

Revision ID: 3b7e5f2a9c81
Revises: 8f3c1d7a92e4
Create Date: 2026-08-14 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3b7e5f2a9c81'
down_revision: Union[str, Sequence[str], None] = '8f3c1d7a92e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Consolidate cpu_specs to be the single source of truth per CPU product:
    identity (brand/series/model_number) + physical specs + LLM extraction metadata.
    Replaces the now-superseded cpu_title_extractions staging table.
    """
    op.add_column('cpu_specs', sa.Column('brand', sa.String(length=50), nullable=True))
    op.add_column('cpu_specs', sa.Column('series', sa.String(length=100), nullable=True))
    op.add_column('cpu_specs', sa.Column('model_number', sa.String(length=100), nullable=True))
    op.add_column('cpu_specs', sa.Column('confidence', sa.String(length=20), nullable=True))
    op.add_column('cpu_specs', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('cpu_specs', sa.Column('llm_model', sa.String(length=100), nullable=True))
    op.add_column('cpu_specs', sa.Column('raw_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('cpu_specs', sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'))
    op.add_column('cpu_specs', sa.Column('error', sa.Text(), nullable=True))

    op.create_index(op.f('ix_cpu_specs_brand'), 'cpu_specs', ['brand'], unique=False)
    op.create_index(op.f('ix_cpu_specs_series'), 'cpu_specs', ['series'], unique=False)
    op.create_index(op.f('ix_cpu_specs_model_number'), 'cpu_specs', ['model_number'], unique=False)
    op.create_index(op.f('ix_cpu_specs_status'), 'cpu_specs', ['status'], unique=False)

    # Old regex-populated rows carry no reliable data (verified near-empty) - clear so the
    # fresh Groq batch repopulates cleanly rather than merging with stale/empty rows.
    op.execute("TRUNCATE TABLE cpu_specs RESTART IDENTITY;")

    op.drop_table('cpu_title_extractions')


def downgrade() -> None:
    """Recreate cpu_title_extractions and drop the consolidated columns from cpu_specs."""
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

    op.drop_index(op.f('ix_cpu_specs_status'), table_name='cpu_specs', if_exists=True)
    op.drop_index(op.f('ix_cpu_specs_model_number'), table_name='cpu_specs', if_exists=True)
    op.drop_index(op.f('ix_cpu_specs_series'), table_name='cpu_specs', if_exists=True)
    op.drop_index(op.f('ix_cpu_specs_brand'), table_name='cpu_specs', if_exists=True)

    op.drop_column('cpu_specs', 'error')
    op.drop_column('cpu_specs', 'status')
    op.drop_column('cpu_specs', 'raw_response')
    op.drop_column('cpu_specs', 'llm_model')
    op.drop_column('cpu_specs', 'notes')
    op.drop_column('cpu_specs', 'confidence')
    op.drop_column('cpu_specs', 'model_number')
    op.drop_column('cpu_specs', 'series')
    op.drop_column('cpu_specs', 'brand')
