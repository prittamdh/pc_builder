"""
LLM-based RAM Title Extraction Model.
Staging table capturing Groq-extracted brand/series/capacity/speed/CL identity per
RAM product title, mirroring cpu_title_extractions for the RAM category.
"""
from typing import Any

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
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


class RAMTitleExtraction(Base, TimestampMixin):
    __tablename__ = "ram_title_extractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    canonical_id: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("canonical_parts.canonical_id", ondelete="SET NULL"), nullable=True, index=True
    )

    raw_title: Mapped[str] = mapped_column(Text, nullable=False)

    brand: Mapped[str | None] = mapped_column(String(50), index=True)
    series: Mapped[str | None] = mapped_column(String(100), index=True)
    memory_type: Mapped[str | None] = mapped_column(String(20), index=True)
    capacity_gb: Mapped[float | None] = mapped_column(Numeric(6, 2))
    modules: Mapped[int | None] = mapped_column(Integer)
    capacity_per_module_gb: Mapped[float | None] = mapped_column(Numeric(6, 2))
    speed_mhz: Mapped[int | None] = mapped_column(Integer)
    cl_timing: Mapped[str | None] = mapped_column(String(20))
    form_factor: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)

    llm_model: Mapped[str | None] = mapped_column(String(100))
    raw_response: Mapped[dict | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
