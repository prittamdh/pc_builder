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
    matched_by: str = "name"


@router.get("", response_model=CompareResponse)
def compare_product(
    q: str = Query(..., description="Product query name to compare across stores"),
    product_id: int | None = Query(
        None,
        description="Anchor the comparison to a specific listing. Its canonical_id is used "
                    "to gather the same real-world product across every store.",
    ),
    db: Session = Depends(get_db),
):
    """Compare pricing and availability for one real-world product across all stores.

    Prefers the canonical group over a name substring search. Retailers title the
    same part very differently ("AMD Ryzen 7 7800X3D Processor with Radeon Graphics"
    vs "Amd Ryzen 7 7800X3D Gaming Processor Oem..."), so matching on the name finds
    only the listings that happen to share wording - for that CPU, 3 offers from one
    store instead of the 12 across nine stores that are actually the same chip.
    Falls back to the name search when no canonical id is available.
    """
    matched_by = "name"
    canonical_id = None

    if product_id is not None:
        anchor = db.get(Product, product_id)
        if anchor is not None and anchor.canonical_id:
            canonical_id = anchor.canonical_id
    if canonical_id is None:
        # Resolve the query to a listing, then use that listing's canonical group.
        anchor = db.scalars(
            select(Product).where(Product.name.ilike(f"%{q}%")).limit(1)
        ).first()
        if anchor is not None and anchor.canonical_id:
            canonical_id = anchor.canonical_id

    if canonical_id:
        stmt = select(Product).where(Product.canonical_id == canonical_id)
        matched_by = "canonical_id"
    else:
        stmt = select(Product).where(Product.name.ilike(f"%{q}%"))

    products = list(db.scalars(stmt))

    if not products:
        return CompareResponse(
            query=q,
            total_offers=0,
            offers=[],
            matched_by=matched_by,
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

    # Cheapest first: the whole point of comparing is finding the best price.
    offers.sort(key=lambda o: (not o.in_stock, o.price))

    return CompareResponse(
        query=q,
        total_offers=len(offers),
        lowest_price=lowest,
        highest_price=highest,
        average_price=avg,
        offers=offers,
        matched_by=matched_by,
    )
