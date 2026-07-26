from datetime import datetime
from decimal import Decimal
from typing import Any
from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric
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

    id: Mapped[int] = mapped_column(primary_key=True)

    product_id: Mapped[int] = mapped_column(
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

    product = relationship(
        "Product",
        back_populates="price_history",
    )