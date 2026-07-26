from typing import Any
from sqlalchemy import Boolean, Integer, String
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