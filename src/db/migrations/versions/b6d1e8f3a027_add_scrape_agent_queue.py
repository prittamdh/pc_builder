"""add scrape agent job queue

Revision ID: b6d1e8f3a027
Revises: f3c9a1d6b254
Create Date: 2026-09-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b6d1e8f3a027'
down_revision: Union[str, Sequence[str], None] = 'f3c9a1d6b254'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Plan 02-01: store pages are fetched by browser-extension agents that lease jobs
    from this queue (docs/AGENT_PROTOCOL.md). Every saved price records the agent and
    job that fetched it. pipeline_runs records the worker's scheduled tasks (02-03)."""
    op.create_table(
        "scrape_agents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("token_hash"),
    )

    op.create_table(
        "scrape_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=20), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("headers", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="queued", nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("available_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("not_before", sa.DateTime(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("result_lease_id", sa.String(length=36), nullable=True),
        sa.Column("outcome", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'leased', 'done', 'failed', 'blocked', 'rejected')",
            name="ck_scrape_jobs_status",
        ),
        sa.CheckConstraint("job_type IN ('category_page', 'product_page')", name="ck_scrape_jobs_job_type"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["scrape_targets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agent_id"], ["scrape_agents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_scrape_jobs_active_url", "scrape_jobs", ["store_id", "url"], unique=True,
        postgresql_where=sa.text("status IN ('queued', 'leased')"),
    )
    op.create_index(
        "ix_scrape_jobs_queued", "scrape_jobs", ["store_id", "available_at"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "ix_scrape_jobs_leased", "scrape_jobs", ["lease_expires_at"],
        postgresql_where=sa.text("status = 'leased'"),
    )

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("counts", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('running', 'ok', 'failed')", name="ck_pipeline_runs_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pipeline_runs_task_started", "pipeline_runs", ["task", "started_at"])

    op.add_column(
        "stores",
        sa.Column("min_fetch_interval_s", sa.Integer(), server_default=sa.text("10"), nullable=False),
    )
    op.add_column("stores", sa.Column("next_fetch_at", sa.DateTime(), nullable=True))
    op.create_check_constraint("ck_stores_min_fetch_interval", "stores", "min_fetch_interval_s >= 0")

    # Nullable, no default: adding them doesn't rewrite price_history's rows.
    op.add_column("price_history", sa.Column("agent_id", sa.Integer(), nullable=True))
    op.add_column("price_history", sa.Column("job_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_price_history_agent_id", "price_history", "scrape_agents", ["agent_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_price_history_job_id", "price_history", "scrape_jobs", ["job_id"], ["id"], ondelete="SET NULL",
    )
    # Partial: the 400k+ rows saved before agents have no agent and stay out of it.
    op.create_index(
        "ix_price_history_agent_id", "price_history", ["agent_id"],
        postgresql_where=sa.text("agent_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_price_history_agent_id", table_name="price_history", if_exists=True)
    op.drop_constraint("fk_price_history_job_id", "price_history", type_="foreignkey")
    op.drop_constraint("fk_price_history_agent_id", "price_history", type_="foreignkey")
    op.drop_column("price_history", "job_id")
    op.drop_column("price_history", "agent_id")

    op.drop_constraint("ck_stores_min_fetch_interval", "stores", type_="check")
    op.drop_column("stores", "next_fetch_at")
    op.drop_column("stores", "min_fetch_interval_s")

    op.drop_index("ix_pipeline_runs_task_started", table_name="pipeline_runs", if_exists=True)
    op.drop_table("pipeline_runs")
    op.drop_index("ix_scrape_jobs_leased", table_name="scrape_jobs", if_exists=True)
    op.drop_index("ix_scrape_jobs_queued", table_name="scrape_jobs", if_exists=True)
    op.drop_index("uq_scrape_jobs_active_url", table_name="scrape_jobs", if_exists=True)
    op.drop_table("scrape_jobs")
    op.drop_table("scrape_agents")
