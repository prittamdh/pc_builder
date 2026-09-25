from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from db.base import Base

JOB_STATUSES = ("queued", "leased", "done", "failed", "blocked", "rejected")
JOB_TYPES = ("category_page", "product_page")


class ScrapeJob(Base):
    """One page for an agent to fetch. See docs/AGENT_PROTOCOL.md for the life cycle."""

    __tablename__ = "scrape_jobs"
    __table_args__ = (
        CheckConstraint(f"status IN {JOB_STATUSES}", name="ck_scrape_jobs_status"),
        CheckConstraint(f"job_type IN {JOB_TYPES}", name="ck_scrape_jobs_job_type"),
        # One live job per page: enqueueing a page that is already waiting or being
        # fetched is a no-op. Finished jobs don't count, so the next cycle can re-queue.
        Index(
            "uq_scrape_jobs_active_url", "store_id", "url", unique=True,
            postgresql_where=text("status IN ('queued', 'leased')"),
        ),
        Index("ix_scrape_jobs_queued", "store_id", "available_at", postgresql_where=text("status = 'queued'")),
        Index("ix_scrape_jobs_leased", "lease_expires_at", postgresql_where=text("status = 'leased'")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    # Only names from job_queue.ALLOWED_HEADERS; checked at enqueue.
    headers: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("scrape_targets.id", ondelete="SET NULL"), nullable=True,
    )
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True,
    )
    # The previous page of the same listing run. Pagination follows this chain to know
    # which product ids earlier pages already brought (plan 02-02).
    parent_job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("scrape_jobs.id", ondelete="SET NULL"), nullable=True,
    )

    status: Mapped[str] = mapped_column(String(12), server_default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"), nullable=False)
    # Retry backoff: a queued job is not handed out before this time.
    available_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # The current lease; all NULL unless status is 'leased'.
    lease_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("scrape_agents.id"), nullable=True)
    not_before: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # The last lease that uploaded a result, and what we told it. A repeat upload for
    # that lease gets this back instead of being processed again.
    result_lease_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    outcome: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
