"""add cabinet_specs.radiator_sizes

Radiator lengths a cabinet supports at any mount, as a sorted comma list ("120,240,360").
Lets the builder check an AIO against the case - the old cooler rule compared the
radiator length with the tower-cooler height limit, which measures something else.

Revision ID: f3c9a1d6b254
Revises: e7b2d4c81a03
"""
from alembic import op
import sqlalchemy as sa

revision = "f3c9a1d6b254"
down_revision = "e7b2d4c81a03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cabinet_specs", sa.Column("radiator_sizes", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("cabinet_specs", "radiator_sizes")
