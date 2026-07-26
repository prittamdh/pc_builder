from typing import TYPE_CHECKING, Any, List
from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

try:
    from sqlalchemy.orm import Mapped, mapped_column
except ImportError:
    class Mapped:
        def __class_getitem__(cls, item):
            return Any
    from sqlalchemy import Column as mapped_column

from db.base import Base
from db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from db.models.price_history import PriceHistory


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    __table_args__ = (
        UniqueConstraint("sid", "pid", name="uq_products_sid_pid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Store
    sid: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Store specific unique identifier
    pid: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Product
    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    product_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    image_url: Mapped[str | None] = mapped_column(
        Text,
    )

    brand: Mapped[str | None] = mapped_column(
        String(255),
    )

    category: Mapped[str | None] = mapped_column(
        String(255),
    )

    description: Mapped[str | None] = mapped_column(
        Text,
    )

    specifications: Mapped[dict | None] = mapped_column(
        JSONB,
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        default="INR",
        nullable=False,
    )

    current_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
    )

    current_mrp: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
    )

    in_stock: Mapped[bool | None] = mapped_column(
        Boolean,
    )

    price_history: Mapped[List["PriceHistory"]] = relationship(
        "PriceHistory",
        back_populates="product",
        cascade="all, delete-orphan",
    )

    targets = relationship(
        "ScrapeTarget",
        secondary="product_targets",
        backref="products",
    )