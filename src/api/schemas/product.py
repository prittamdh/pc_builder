from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, HttpUrl


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sid: int
    pid: str
    name: str
    product_url: str
    image_url: str | None = None
    brand: str | None = None
    category: str | None = None
    p_category: str | None = None
    description: str | None = None
    specifications: dict | None = None
    currency: str
    current_price: Decimal | None = None
    current_mrp: Decimal | None = None
    in_stock: bool | None = None
    target_ids: list[int] = []
    keywords: list[str] = []
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    total: int
    items: list[ProductOut]
    page: int
    size: int
