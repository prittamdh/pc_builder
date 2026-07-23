"""
Search result model returned by all search scrapers.
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, HttpUrl


class SearchResult(BaseModel):
    """Represents a single product from a search page."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    seller: str
    name: str
    url: HttpUrl

    price: Decimal

    image: Optional[HttpUrl] = None

    currency: str = "INR"

    in_stock: Optional[bool] = None