from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class PriceHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    price: Decimal
    mrp: Decimal | None = None
    in_stock: bool
    scraped_at: datetime
