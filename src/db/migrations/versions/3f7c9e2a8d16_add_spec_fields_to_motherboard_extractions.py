"""add socket/memory_type/form_factor to motherboard_title_extractions

Revision ID: 3f7c9e2a8d16
Revises: 9a1e6d4f7b23
Create Date: 2026-08-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3f7c9e2a8d16'
down_revision: Union[str, Sequence[str], None] = '9a1e6d4f7b23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """These are frequently stated directly in motherboard titles ("AM5 ATX
    Motherboard", "DDR5 12-DIMM Support") but weren't captured initially - needed
    by the compatibility engine's socket/RAM-type/form-factor rules."""
    op.add_column('motherboard_title_extractions', sa.Column('socket', sa.String(length=50), nullable=True))
    op.add_column('motherboard_title_extractions', sa.Column('memory_type', sa.String(length=20), nullable=True))
    op.add_column('motherboard_title_extractions', sa.Column('form_factor', sa.String(length=20), nullable=True))
    op.create_index(op.f('ix_motherboard_title_extractions_socket'), 'motherboard_title_extractions', ['socket'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_motherboard_title_extractions_socket'), table_name='motherboard_title_extractions', if_exists=True)
    op.drop_column('motherboard_title_extractions', 'form_factor')
    op.drop_column('motherboard_title_extractions', 'memory_type')
    op.drop_column('motherboard_title_extractions', 'socket')
