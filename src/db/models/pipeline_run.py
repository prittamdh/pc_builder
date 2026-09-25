from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class PipelineRun(Base):
    """One run of one scheduled worker task (plan 02-03), read by /health/pipeline."""

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'ok', 'failed')", name="ck_pipeline_runs_status"),
        Index("ix_pipeline_runs_task_started", "task", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
