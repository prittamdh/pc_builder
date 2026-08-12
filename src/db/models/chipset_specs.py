"""
Chipset Specs Model (Tier 1 spec table for GPU and Motherboard chipsets).
"""
from typing import Any
from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from db.models.mixins import TimestampMixin


class ChipsetSpecs(Base, TimestampMixin):
    """
    Tier 1 Chipset Specs table (e.g. keyed by 'rtx_4070', 'b650').
    Extracted/looked up once per chipset.
    """
    __tablename__ = "chipset_specs"

    chipset_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    specs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="manual")
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    canonical_parts = relationship("CanonicalPart", back_populates="chipset_specs")
