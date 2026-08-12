"""add canonical parts chipset specs and products canonical_id

Revision ID: a1b2c3d4e5f6
Revises: 94ff4e0a9e14
Create Date: 2026-08-12 19:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '94ff4e0a9e14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to include canonical matching tables and spec table foreign keys."""
    # 1. Create chipset_specs table
    op.create_table(
        'chipset_specs',
        sa.Column('chipset_id', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('specs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False, server_default='manual'),
        sa.Column('verified', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('chipset_id')
    )
    op.create_index(op.f('ix_chipset_specs_category'), 'chipset_specs', ['category'], unique=False)

    # 2. Create canonical_parts table (thin identity table, specs live in relational category tables)
    op.create_table(
        'canonical_parts',
        sa.Column('canonical_id', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('brand', sa.String(length=255), nullable=False),
        sa.Column('key_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('chipset_id', sa.String(length=255), nullable=True),
        sa.Column('from_title', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='OK'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['chipset_id'], ['chipset_specs.chipset_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('canonical_id')
    )
    op.create_index(op.f('ix_canonical_parts_category'), 'canonical_parts', ['category'], unique=False)
    op.create_index(op.f('ix_canonical_parts_brand'), 'canonical_parts', ['brand'], unique=False)
    op.create_index(op.f('ix_canonical_parts_chipset_id'), 'canonical_parts', ['chipset_id'], unique=False)
    op.create_index(op.f('ix_canonical_parts_status'), 'canonical_parts', ['status'], unique=False)

    # 3. Add canonical_id to products table
    op.add_column('products', sa.Column('canonical_id', sa.String(length=255), nullable=True))
    op.create_foreign_key(
        'fk_products_canonical_id',
        'products',
        'canonical_parts',
        ['canonical_id'],
        ['canonical_id'],
        ondelete='SET NULL'
    )
    op.create_index(op.f('ix_products_canonical_id'), 'products', ['canonical_id'], unique=False)

    # 4. Add canonical_id to 9 category-specific spec tables
    spec_tables = [
        'cpu_specs', 'gpu_specs', 'motherboard_specs', 'ram_specs',
        'ssd_specs', 'psu_specs', 'cabinet_specs', 'cooler_specs', 'monitor_specs'
    ]
    for table_name in spec_tables:
        op.add_column(table_name, sa.Column('canonical_id', sa.String(length=255), nullable=True))
        op.create_foreign_key(
            f'fk_{table_name}_canonical_id',
            table_name,
            'canonical_parts',
            ['canonical_id'],
            ['canonical_id'],
            ondelete='CASCADE'
        )
        op.create_index(op.f(f'ix_{table_name}_canonical_id'), table_name, ['canonical_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    spec_tables = [
        'cpu_specs', 'gpu_specs', 'motherboard_specs', 'ram_specs',
        'ssd_specs', 'psu_specs', 'cabinet_specs', 'cooler_specs', 'monitor_specs'
    ]
    for table_name in spec_tables:
        op.drop_index(op.f(f'ix_{table_name}_canonical_id'), table_name=table_name, if_exists=True)
        op.drop_constraint(f'fk_{table_name}_canonical_id', table_name, type_='foreignkey')
        op.drop_column(table_name, 'canonical_id')

    op.drop_index(op.f('ix_products_canonical_id'), table_name='products', if_exists=True)
    op.drop_constraint('fk_products_canonical_id', 'products', type_='foreignkey')
    op.drop_column('products', 'canonical_id')

    op.drop_index(op.f('ix_canonical_parts_status'), table_name='canonical_parts', if_exists=True)
    op.drop_index(op.f('ix_canonical_parts_chipset_id'), table_name='canonical_parts', if_exists=True)
    op.drop_index(op.f('ix_canonical_parts_brand'), table_name='canonical_parts', if_exists=True)
    op.drop_index(op.f('ix_canonical_parts_category'), table_name='canonical_parts', if_exists=True)
    op.drop_table('canonical_parts')

    op.drop_index(op.f('ix_chipset_specs_category'), table_name='chipset_specs', if_exists=True)
    op.drop_table('chipset_specs')
