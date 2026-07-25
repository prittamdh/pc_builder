from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from db.base import Base


class ScrapeTarget(Base):
    __tablename__ = "scrape_targets"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id"),
        nullable=False,
        index=True,
    )

    target_type: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    target_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    schedule_type: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    schedule_config: Mapped[dict] = mapped_column(
        JSONB,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )

    priority: Mapped[int] = mapped_column(
        SmallInteger,
        server_default=text("0"),
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        nullable=False,
    )

    next_scrape_at: Mapped[datetime] = mapped_column(
        nullable=False,
        index=True,
    )

    last_scraped_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )