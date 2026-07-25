"""
Product model returned by product page scrapers.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, HttpUrl, model_validator


class Product(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    # Store information
    store: str          # mdcomputers, pcstudio, vedant, primeabgb
    sid: int = 1        # Database store id

    # Store-specific unique product identifier
    pid: str = ""

    # Product information
    name: str
    url: HttpUrl

    # Pricing
    price: Decimal | None = None
    mrp: Decimal | None = None
    currency: str = "INR"

    # Media
    image: HttpUrl | None = None

    # Availability
    in_stock: bool | None = None

    # Metadata
    brand: str | None = None
    category: str | None = None
    description: str | None = None

    # Specifications extracted from the product page
    specifications: dict[str, str] = {}

    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, values: dict):
        if isinstance(values, dict):
            # Fallback for store / seller
            if not values.get("store") and values.get("seller"):
                values["store"] = str(values["seller"]).lower()
            
            # Fallback for pid if missing or empty
            if not values.get("pid"):
                pid_val = values.get("sku")
                if not pid_val:
                    url = str(values.get("url", ""))
                    if url:
                        clean_url = url.split("?")[0].rstrip("/")
                        pid_val = clean_url.split("/")[-1] or "unknown"
                    else:
                        pid_val = str(values.get("name", "unknown"))
                values["pid"] = str(pid_val)
        return values