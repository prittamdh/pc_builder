"""
Canonical Part Model (Layer between raw scraped listings and spec extraction).
"""
from typing import TYPE_CHECKING, List, Any
from sqlalchemy import ForeignKey, String, Text
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
from sqlalchemy import DateTime, ForeignKey, String, Text, func

if TYPE_CHECKING:
    from db.models.chipset_specs import ChipsetSpecs
    from db.models.product import Product


class CanonicalPart(Base):
    """
    Canonical Part table holding deduplicated real-world products.
    """
    __tablename__ = "canonical_parts"

    canonical_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    brand: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    key_fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    chipset_id: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("chipset_specs.chipset_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    from_title: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="OK", index=True)
    created_at: Mapped[Any] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    chipset_specs = relationship("ChipsetSpecs", back_populates="canonical_parts")
    listings = relationship("Product", back_populates="canonical_part")
