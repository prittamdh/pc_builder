"""
Search result model returned by all search scrapers.
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, HttpUrl


class SearchResult(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    seller: str
    name: str
    url: HttpUrl

    price: Decimal
    mrp: Decimal | None = None

    image: HttpUrl | None = None

    currency: str = "INR"

    in_stock: bool | None = None