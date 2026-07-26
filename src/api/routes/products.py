from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas.price_history import PriceHistoryOut
from api.schemas.product import ProductListResponse, ProductOut
from db.models.price_history import PriceHistory
from db.models.product import Product

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=ProductListResponse)
def list_products(
    q: str | None = Query(None, description="Search query string"),
    sid: int | None = Query(None, description="Filter by store ID"),
    in_stock: bool | None = Query(None, description="Filter by in-stock status"),
    min_price: Decimal | None = Query(None, description="Minimum current price"),
    max_price: Decimal | None = Query(None, description="Maximum current price"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
):
    """Search and filter products across all stores."""
    stmt = select(Product)

    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    if sid is not None:
        stmt = stmt.where(Product.sid == sid)
    if in_stock is not None:
        stmt = stmt.where(Product.in_stock == in_stock)
    if min_price is not None:
        stmt = stmt.where(Product.current_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.current_price <= max_price)

    # Count total matching items
    count_stmt = select(Product.id).where(stmt.whereclause) if stmt.whereclause is not None else select(Product.id)
    total = len(list(db.scalars(count_stmt)))

    # Apply pagination
    offset = (page - 1) * size
    stmt = stmt.offset(offset).limit(size).order_by(Product.updated_at.desc())
    items = list(db.scalars(stmt))

    return ProductListResponse(
        total=total,
        items=items,
        page=page,
        size=size,
    )


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Retrieve detailed product details by database primary key."""
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found",
        )
    return product


@router.get("/{product_id}/history", response_model=list[PriceHistoryOut])
def get_product_price_history(product_id: int, db: Session = Depends(get_db)):
    """Retrieve price history snapshots for a product."""
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found",
        )

    stmt = (
        select(PriceHistory)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.scraped_at.asc())
    )
    return list(db.scalars(stmt))
