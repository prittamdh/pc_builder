"""
Price Comparison API Route.
Compares pricing, stock availability, and historical snapshots across retailer stores.
"""
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from db.models.price_history import PriceHistory
from db.models.product import Product
from db.models.store import Store

router = APIRouter(prefix="/compare", tags=["Comparison"])


class StoreOffer(BaseModel):
    sid: int
    store_name: str
    price: Decimal
    mrp: Decimal | None = None
    in_stock: bool
    url: str


class CompareResponse(BaseModel):
    query: str
    total_offers: int
    lowest_price: Decimal | None = None
    highest_price: Decimal | None = None
    average_price: Decimal | None = None
    offers: list[StoreOffer]


@router.get("", response_model=CompareResponse)
def compare_product(
    q: str = Query(..., description="Product query name to compare across stores"),
    db: Session = Depends(get_db),
):
    """Compare product pricing, availability, and offers across all 4 retailer stores."""
    stmt = select(Product).where(Product.name.ilike(f"%{q}%"))
    products = list(db.scalars(stmt))

    if not products:
        return CompareResponse(
            query=q,
            total_offers=0,
            offers=[],
        )

    offers = []
    prices = []

    for p in products:
        store = db.get(Store, p.sid)
        store_name = store.display_name if store else f"Store #{p.sid}"

        if p.current_price is not None:
            prices.append(p.current_price)

        offers.append(
            StoreOffer(
                sid=p.sid,
                store_name=store_name,
                price=p.current_price or Decimal(0),
                mrp=p.current_mrp,
                in_stock=p.in_stock if p.in_stock is not None else True,
                url=p.product_url,
            )
        )

    lowest = min(prices) if prices else None
    highest = max(prices) if prices else None
    avg = sum(prices) / Decimal(len(prices)) if prices else None

    return CompareResponse(
        query=q,
        total_offers=len(offers),
        lowest_price=lowest,
        highest_price=highest,
        average_price=avg,
        offers=offers,
    )
