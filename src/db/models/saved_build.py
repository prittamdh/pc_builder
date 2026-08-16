"""
Saved PC builds.

A build a user assembles currently lives only in browser memory and is lost on
refresh, so there is no way to keep one, come back to it, or send it to someone.
This stores the slot->product mapping under a short opaque share token.

Component choices are stored as product ids, not a price snapshot: prices move
constantly across the ten stores, and the point of the tool is the current best
price, so a saved build is re-costed on every load.
"""
from typing import Any

from sqlalchemy import Boolean, Integer, String, Text
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


class SavedBuild(Base, TimestampMixin):
    __tablename__ = "saved_builds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # URL-safe random token. Unguessable so a shared link doesn't expose other
    # people's builds by incrementing an id.
    share_token: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)

    name: Mapped[str | None] = mapped_column(String(120))

    # {"cpu": 4089, "motherboard": 4867, ...} - slot key to products.id.
    selections: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Compatibility verdict at save time, kept for display only. The build is
    # re-validated on load, since spec data and stock change underneath it.
    was_compatible: Mapped[bool | None] = mapped_column(Boolean)
    notes: Mapped[str | None] = mapped_column(Text)
