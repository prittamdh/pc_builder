"""widen cabinet_title_extractions.form_factor column

Revision ID: 6e8f4a2b91c5
Revises: 151c8f2e9a04
Create Date: 2026-08-15 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6e8f4a2b91c5'
down_revision: Union[str, Sequence[str], None] = '151c8f2e9a04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """VARCHAR(20) was too narrow - titles listing multiple supported form factors
    (e.g. "Micro ATX/Mini ATX/ATX") exceeded it and crashed the extraction batch."""
    op.alter_column('cabinet_title_extractions', 'form_factor', type_=sa.String(length=100))


def downgrade() -> None:
    op.alter_column('cabinet_title_extractions', 'form_factor', type_=sa.String(length=20))
