"""
Search result model returned by all search scrapers.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, HttpUrl, model_validator


class SearchResult(BaseModel):
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
    price: Decimal
    mrp: Decimal | None = None
    currency: str = "INR"

    # Optional fields
    image: HttpUrl | None = None
    in_stock: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, values: dict):
        if isinstance(values, dict):
            # Fallback for store / seller
            if not values.get("store") and values.get("seller"):
                values["store"] = str(values["seller"]).lower()
            
            # Fallback for pid if missing or empty
            if not values.get("pid"):
                url = str(values.get("url", ""))
                if url:
                    clean_url = url.split("?")[0].rstrip("/")
                    if "/product/" in clean_url:
                        segs = [s for s in clean_url.split("/product/")[1].split("/") if s]
                        cat_slugs = {
                            "processor", "cpu-cooler", "motherboard", "graphics-card",
                            "desktop-ram", "internal-hdd", "sata-ssd", "gen3-ssd",
                            "gen4-ssd", "gen5-ssd", "monitor", "cabinet", "smps",
                            "external-hdd", "external-ssd", "laptop-ram", "ram",
                            "storage", "hard-drive"
                        }
                        if segs and segs[0].lower() in cat_slugs and len(segs) > 1:
                            values["pid"] = segs[-1]
                        elif segs and segs[-1].lower() in cat_slugs:
                            values["pid"] = segs[0]
                        elif segs:
                            values["pid"] = segs[0]
                        else:
                            values["pid"] = clean_url.split("/")[-1]
                    elif clean_url:
                        values["pid"] = clean_url.split("/")[-1]
                    else:
                        values["pid"] = str(values.get("name", "unknown"))
                else:
                    values["pid"] = str(values.get("name", "unknown"))
        return values