"""initial_schema

Revision ID: 6b3dbe4850ce
Revises: 
Create Date: 2026-07-24 12:03:53.973271

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6b3dbe4850ce'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('stores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('domain', sa.String(), nullable=False),
        sa.Column('base_url', sa.String(), nullable=False),
        sa.Column('search_endpoint', sa.String(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('currency_symbol', sa.String(), nullable=False),
        sa.Column('search_config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('product_config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    op.create_table('scrape_targets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('target_type', sa.SmallInteger(), nullable=False),
        sa.Column('target_value', sa.Text(), nullable=False),
        sa.Column('schedule_type', sa.SmallInteger(), nullable=False),
        sa.Column('schedule_config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('priority', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('next_scrape_at', sa.DateTime(), nullable=False),
        sa.Column('last_scraped_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scrape_targets_next_scrape_at'), 'scrape_targets', ['next_scrape_at'], unique=False)
    op.create_index(op.f('ix_scrape_targets_store_id'), 'scrape_targets', ['store_id'], unique=False)

    op.create_table('products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sid', sa.Integer(), nullable=False),
        sa.Column('pid', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('product_url', sa.Text(), nullable=False),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('brand', sa.String(length=255), nullable=True),
        sa.Column('category', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('specifications', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('currency', sa.String(length=10), server_default='INR', nullable=False),
        sa.Column('current_price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('current_mrp', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('in_stock', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['sid'], ['stores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sid', 'pid', name='uq_products_sid_pid')
    )
    op.create_index(op.f('ix_products_sid'), 'products', ['sid'], unique=False)

    op.create_table('price_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('mrp', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('in_stock', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('scraped_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('price_history')
    op.drop_index(op.f('ix_products_sid'), table_name='products')
    op.drop_table('products')
    op.drop_index(op.f('ix_scrape_targets_store_id'), table_name='scrape_targets')
    op.drop_index(op.f('ix_scrape_targets_next_scrape_at'), table_name='scrape_targets')
    op.drop_table('scrape_targets')
    op.drop_table('stores')
