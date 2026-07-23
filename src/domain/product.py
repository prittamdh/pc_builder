"""
Product model returned by product page scrapers.
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, HttpUrl


class Product(BaseModel):
    """Represents a complete product."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    # Basic Information
    seller: str
    name: str
    brand: Optional[str] = None

    # URLs
    url: HttpUrl
    image: Optional[HttpUrl] = None

    # Pricing
    price: Decimal
    currency: str = "INR"

    # Availability
    in_stock: Optional[bool] = None

    # Product Metadata
    sku: Optional[str] = None
    model_number: Optional[str] = None

    # Technical Specifications
    specifications: dict[str, str] = {}

    # Additional Information
    description: Optional[str] = None

    # Ratings
    rating: Optional[float] = None
    review_count: Optional[int] = None