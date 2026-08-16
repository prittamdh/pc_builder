"""add canonical_id to ram_title_extractions

Revision ID: 9a1e6d4f7b23
Revises: 6e8f4a2b91c5
Create Date: 2026-08-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9a1e6d4f7b23'
down_revision: Union[str, Sequence[str], None] = '6e8f4a2b91c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """RAM was extracted before the canonical_id grouping pattern existed - bring it
    in line with the other 8 categories so duplicate RAM listings across stores
    collapse into one canonical model."""
    op.add_column('ram_title_extractions', sa.Column('canonical_id', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_ram_title_extractions_canonical_id'), 'ram_title_extractions', ['canonical_id'], unique=False)
    op.create_foreign_key(
        'fk_ram_title_extractions_canonical_id', 'ram_title_extractions', 'canonical_parts',
        ['canonical_id'], ['canonical_id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_ram_title_extractions_canonical_id', 'ram_title_extractions', type_='foreignkey')
    op.drop_index(op.f('ix_ram_title_extractions_canonical_id'), table_name='ram_title_extractions', if_exists=True)
    op.drop_column('ram_title_extractions', 'canonical_id')
