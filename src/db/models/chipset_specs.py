"""
Chipset Specs Model (Tier 1 spec table for GPU and Motherboard chipsets).
"""
from typing import Any
from db.base import Base
from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

try:
    from sqlalchemy.orm import Mapped, mapped_column
except ImportError:
    class Mapped:
        def __class_getitem__(cls, item):
            return Any
    from sqlalchemy import Column as mapped_column


class ChipsetSpecs(Base):
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
    created_at: Mapped[Any] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    canonical_parts = relationship("CanonicalPart", back_populates="chipset_specs")
