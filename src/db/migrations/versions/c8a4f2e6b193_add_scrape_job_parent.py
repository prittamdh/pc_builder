"""add scrape_jobs.parent_job_id

Revision ID: c8a4f2e6b193
Revises: b6d1e8f3a027
Create Date: 2026-09-25 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c8a4f2e6b193'
down_revision: Union[str, Sequence[str], None] = 'b6d1e8f3a027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Plan 02-02: the server drives pagination. Page N+1 is queued only if page N
    brought product ids no earlier page of the same run did, and the run's earlier
    pages are found by following parent_job_id."""
    op.add_column("scrape_jobs", sa.Column("parent_job_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_scrape_jobs_parent_job_id", "scrape_jobs", "scrape_jobs", ["parent_job_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_scrape_jobs_parent_job_id", "scrape_jobs", type_="foreignkey")
    op.drop_column("scrape_jobs", "parent_job_id")
