from typing import Any
from sqlalchemy import Boolean, String
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

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))

    domain: Mapped[str]
    base_url: Mapped[str]

    search_endpoint: Mapped[str] = mapped_column(nullable=False)

    currency: Mapped[str] = mapped_column(default="INR")
    currency_symbol: Mapped[str] = mapped_column(default="₹")

    search_config: Mapped[dict] = mapped_column(JSONB)
    product_config: Mapped[dict] = mapped_column(JSONB)

    active: Mapped[bool] = mapped_column(Boolean, default=True)