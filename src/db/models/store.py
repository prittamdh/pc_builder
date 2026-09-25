from typing import Any
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB

try:
    from sqlalchemy.orm import Mapped, mapped_column
except ImportError:
    class Mapped:
        def __class_getitem__(cls, item):
            return Any
    from sqlalchemy import Column as mapped_column

from db.base import Base


class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (
        CheckConstraint("min_fetch_interval_s >= 0", name="ck_stores_min_fetch_interval"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))

    domain: Mapped[str] = mapped_column(String(255), nullable=True)
    base_url: Mapped[str] = mapped_column(String(500), nullable=True)

    search_endpoint: Mapped[str] = mapped_column(String(500), nullable=False)

    currency: Mapped[str] = mapped_column(String(10), default="INR")
    currency_symbol: Mapped[str] = mapped_column(String(10), default="₹")

    search_config: Mapped[dict] = mapped_column(JSONB, nullable=True)
    product_config: Mapped[dict] = mapped_column(JSONB, nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Fetch pacing for scrape agents (plan 02-01). Every agent shares one budget per
    # store - they may all sit behind the owner's one home IP - so the gap is enforced
    # at lease time across all agents: next_fetch_at is the earliest start for the
    # store's next fetch, advanced by min_fetch_interval_s with each job handed out.
    min_fetch_interval_s: Mapped[int] = mapped_column(Integer, server_default=text("10"), nullable=False)
    next_fetch_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
