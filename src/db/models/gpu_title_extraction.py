"""Per-listing GPU identity extraction table. See cpu_title_extraction.py for the pattern."""
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

try:
    from sqlalchemy.orm import Mapped, mapped_column
except ImportError:
    class Mapped:
        def __class_getitem__(cls, item):
            return Any
    from sqlalchemy import Column as mapped_column

from db.base import Base
from db.models.mixins import TimestampMixin


class GPUTitleExtraction(Base, TimestampMixin):
    __tablename__ = "gpu_title_extractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    canonical_id: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("canonical_parts.canonical_id", ondelete="SET NULL"), nullable=True, index=True
    )

    raw_title: Mapped[str] = mapped_column(Text, nullable=False)

    brand: Mapped[str | None] = mapped_column(String(50), index=True)
    chipset: Mapped[str | None] = mapped_column(String(100), index=True)
    variant: Mapped[str | None] = mapped_column(String(150), index=True)
    confidence: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)

    llm_model: Mapped[str | None] = mapped_column(String(100))
    raw_response: Mapped[dict | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
