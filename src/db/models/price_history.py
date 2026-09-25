from datetime import datetime
from decimal import Decimal
from typing import Any
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, text
from sqlalchemy.orm import relationship

try:
    from sqlalchemy.orm import Mapped, mapped_column
except ImportError:
    class Mapped:
        def __class_getitem__(cls, item):
            return Any
    from sqlalchemy import Column as mapped_column

from db.base import Base


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        Index("ix_price_history_agent_id", "agent_id", postgresql_where=text("agent_id IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    mrp: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
    )

    in_stock: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    scraped_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    # Which agent fetched the page and for which job (NULL for rows saved before
    # agents). Lets one agent's data be found and removed after a revoke.
    agent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("scrape_agents.id"),
        nullable=True,
    )

    job_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("scrape_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    product = relationship(
        "Product",
        back_populates="price_history",
    )