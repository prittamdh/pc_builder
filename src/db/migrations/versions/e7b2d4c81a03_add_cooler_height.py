"""add cooler_specs.height_mm

An air cooler's height is what has to fit under a cabinet's max_cooler_height_mm. The
only size stored before was radiator_size_mm, which holds a fan size for air coolers and
a radiator length for AIOs - neither is a height, and a rule comparing it with the case
limit warned on every AIO. NULL for liquid coolers, whose fit is a radiator-mount
question instead.

Revision ID: e7b2d4c81a03
Revises: c4a1f7e2d910
"""
from alembic import op
import sqlalchemy as sa

revision = "e7b2d4c81a03"
down_revision = "c4a1f7e2d910"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cooler_specs", sa.Column("height_mm", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("cooler_specs", "height_mm")
