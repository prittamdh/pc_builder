from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func

try:
    from sqlalchemy.orm import Mapped, mapped_column
except ImportError:
    class Mapped:
        def __class_getitem__(cls, item):
            return Any
    from sqlalchemy import Column as mapped_column

from db.base import Base


class ProductTarget(Base):
    __tablename__ = "product_targets"

    __table_args__ = (
        UniqueConstraint("product_id", "target_id", name="uq_product_targets_product_target"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scrape_targets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
