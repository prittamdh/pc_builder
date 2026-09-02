import re
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import String, func, nullslast, or_, select
from sqlalchemy.dialects.postgresql import INTERVAL
from sqlalchemy.orm import Session

from api.deps import get_db
from api.filters import has_usable_price
from api.spec_filters import (
    ENUM,
    RANGE,
    apply_spec_filters,
    parse_spec_params,
    spec_model_for,
)
from api.schemas.price_history import PriceHistoryOut
from api.schemas.product import ProductListResponse, ProductOut
from db.models.price_history import PriceHistory
from db.models.product import Product
from db.models.store import Store

router = APIRouter(prefix="/products", tags=["Products"])

# Deliberately no "discount" option. MRP is widely inflated by Indian retailers to
# manufacture a headline discount, so ordering by (mrp - price) would rank the least
# honest listings first - the opposite of what this tool is for.
SORT_OPTIONS = ("recent", "price_asc", "price_desc", "name_asc")


def _order_by(sort: str):
    """Ordering clause for `sort`, always with a unique tiebreaker.

    `id` is appended because offset pagination over a non-unique sort key is
    unstable: rows sharing an `updated_at` (a whole scrape batch shares one) can
    repeat on one page and vanish from the next.
    """
    clauses = {
        "recent": (Product.updated_at.desc(),),
        # NULLS LAST so unpriced listings never lead a price sort.
        "price_asc": (nullslast(Product.current_price.asc()),),
        "price_desc": (nullslast(Product.current_price.desc()),),
        "name_asc": (Product.name.asc(),),
    }[sort]
    return (*clauses, Product.id.asc())


def _search_conditions(q: str) -> list:
    """Match every token in `q`, against either the title as written or the title
    with punctuation and spacing stripped out.

    Store titles spell model numbers inconsistently - "RTX 4070", "RTX4070",
    "RTX-4070" all occur - so a single ILIKE on the raw query silently misses
    whichever spelling the shopper didn't happen to type. Matching per token also
    makes word order irrelevant: "4070 asus" finds "ASUS ... RTX 4070".
    """
    squashed_name = func.regexp_replace(func.lower(Product.name), r"[^a-z0-9]", "", "g")

    conditions = []
    for token in q.split():
        variants = [Product.name.ilike(f"%{token}%")]
        squashed_token = re.sub(r"[^a-z0-9]", "", token.lower())
        if squashed_token:
            variants.append(squashed_name.like(f"%{squashed_token}%"))
        conditions.append(or_(*variants))
    return conditions


@router.get("", response_model=ProductListResponse)
def list_products(
    request: Request,
    q: str | None = Query(None, description="Search query string"),
    sid: int | None = Query(None, description="Filter by store ID"),
    category: str | None = Query(None, description="Filter by raw category"),
    p_category: str | None = Query(None, description="Filter by standardized production category"),
    in_stock: bool | None = Query(None, description="Filter by in-stock status"),
    include_legacy: bool = Query(
        False,
        description="Include off-policy legacy parts (pre-10th-gen Intel, pre-3000 Ryzen, "
                    "retired sockets, pre-DDR4 memory). Hidden everywhere by default; pass "
                    "true to browse them. Their price history is unaffected either way.",
    ),
    min_price: Decimal | None = Query(None, description="Minimum current price"),
    max_price: Decimal | None = Query(None, description="Maximum current price"),
    include_unpriced: bool = Query(
        False,
        description=(
            "Include listings whose price is missing or zero. Hidden by default: a "
            "zero is a failed scrape, not a cheap part, and it leads every price sort."
        ),
    ),
    sort: str = Query(
        "recent",
        description=(
            "Result ordering: recent (default, most recently scraped), price_asc, "
            "price_desc, name_asc. No discount sort - see SORT_OPTIONS."
        ),
    ),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
):
    """Search and filter products across all stores."""
    if sort not in SORT_OPTIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"sort must be one of {', '.join(SORT_OPTIONS)}",
        )

    conditions = []

    if q:
        conditions.extend(_search_conditions(q))
    if sid is not None:
        conditions.append(Product.sid == sid)
    if category:
        conditions.append(Product.category.ilike(f"%{category}%"))
    if p_category:
        conditions.append(func.lower(Product.p_category) == p_category.lower())
    if in_stock is not None:
        conditions.append(Product.in_stock == in_stock)
    if not include_legacy:
        conditions.append(Product.is_legacy.is_(False))
    if not include_unpriced:
        conditions.append(has_usable_price())
    if min_price is not None:
        conditions.append(Product.current_price >= min_price)
    if max_price is not None:
        conditions.append(Product.current_price <= max_price)

    # Spec filters (socket, VRAM, wattage...) need a join to the category's spec table,
    # which is only meaningful once a category has been chosen.
    spec_model, spec_fields = spec_model_for(p_category)
    parsed_specs = (
        parse_spec_params(request.query_params, spec_fields) if spec_model else []
    )

    def _with_specs(stmt):
        if not parsed_specs:
            return stmt
        stmt = stmt.join(
            spec_model, spec_model.canonical_id == Product.canonical_id
        )
        return apply_spec_filters(stmt, spec_model, parsed_specs)

    # Count total matching items
    count_stmt = select(func.count(Product.id))
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    total = db.scalar(_with_specs(count_stmt)) or 0

    # Apply pagination
    stmt = select(Product)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = _with_specs(stmt)

    offset = (page - 1) * size
    stmt = stmt.order_by(*_order_by(sort)).offset(offset).limit(size)
    items = list(db.scalars(stmt))

    product_outs = []
    for p in items:
        p_out = ProductOut.model_validate(p)
        p_out.target_ids = [t.id for t in p.targets] if hasattr(p, "targets") else []
        p_out.keywords = [t.target_value for t in p.targets] if hasattr(p, "targets") else []
        product_outs.append(p_out)

    return ProductListResponse(
        total=total,
        items=product_outs,
        page=page,
        size=size,
    )


def _group_key():
    """Group listings by model, falling back to the listing itself.

    A NULL canonical_id means identity extraction couldn't name the part. Those must
    stay separate: lumping unidentified parts together would merge genuinely different
    products, and this catalog has already been burned by that (71 unrelated GPUs, PSUs
    and coolers once collapsed into one "unknown" bucket).
    """
    return func.coalesce(
        Product.canonical_id, func.concat("product:", func.cast(Product.id, String))
    )


@router.get("/models")
def list_product_models(
    request: Request,
    q: str | None = Query(None),
    p_category: str | None = Query(None),
    sid: int | None = Query(None, description="Only models this store carries"),
    in_stock_only: bool = Query(True),
    min_price: Decimal | None = Query(None),
    max_price: Decimal | None = Query(None),
    include_legacy: bool = Query(False),
    sort: str = Query("price_asc"),
    page: int = Query(1, ge=1),
    size: int = Query(24, ge=1, le=60),
    db: Session = Depends(get_db),
):
    """The catalog, one entry per model rather than one per listing.

    Searching "9060 XT 16GB" returned 56 rows for what are ~25 cards, the same product
    repeated once per shop. That is the wall of near-identical cards a comparison site
    exists to collapse: the useful unit is "this card, from ₹X, at N shops".

    Aggregation happens in SQL so paging is over models, not listings - grouping a page
    of listings in Python would give pages of wildly differing size and miss cheaper
    offers that fell beyond the page boundary.
    """
    if sort not in ("price_asc", "price_desc", "name_asc"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sort must be price_asc, price_desc or name_asc",
        )

    conditions = [has_usable_price()]
    if q:
        conditions.extend(_search_conditions(q))
    if p_category:
        conditions.append(func.lower(Product.p_category) == p_category.lower())
    if in_stock_only:
        conditions.append(Product.in_stock.is_(True))
    if not include_legacy:
        conditions.append(Product.is_legacy.is_(False))
    if min_price is not None:
        conditions.append(Product.current_price >= min_price)
    if max_price is not None:
        conditions.append(Product.current_price <= max_price)

    spec_model, spec_fields = spec_model_for(p_category)
    parsed_specs = (
        parse_spec_params(request.query_params, spec_fields) if spec_model else []
    )

    key = _group_key().label("group_key")

    def base(select_stmt):
        stmt = select_stmt.where(*conditions)
        if parsed_specs:
            stmt = stmt.join(
                spec_model, spec_model.canonical_id == Product.canonical_id
            )
            stmt = apply_spec_filters(stmt, spec_model, parsed_specs)
        return stmt

    # A store filter restricts which models appear, but prices still come from every
    # shop - otherwise "cheapest at MDComputers" would silently hide a cheaper offer.
    if sid is not None:
        carried = base(select(_group_key())).where(Product.sid == sid).distinct()
        conditions.append(key.in_(carried))

    grouped = base(
        select(
            key,
            func.min(Product.current_price).label("best_price"),
            func.max(Product.current_price).label("worst_price"),
            func.count(Product.id).label("offer_count"),
            func.min(Product.name).label("any_name"),
        )
    ).group_by(key)

    total = db.scalar(
        select(func.count()).select_from(grouped.subquery())
    ) or 0

    order = {
        "price_asc": nullslast(func.min(Product.current_price).asc()),
        "price_desc": nullslast(func.min(Product.current_price).desc()),
        "name_asc": func.min(Product.name).asc(),
    }[sort]
    rows = db.execute(
        grouped.order_by(order, key.asc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    if not rows:
        # Keep the real total: a page past the end still has to tell the client how
        # many models matched, or the pager collapses to "0 results" on overshoot.
        return {"total": total, "items": [], "page": page, "size": size}

    # Pull every listing for this page's models in one query, then pick the cheapest
    # as the card's representative.
    keys = [r.group_key for r in rows]
    listings = list(db.scalars(base(select(Product)).where(key.in_(keys))))
    store_names = {
        s.id: (s.display_name or s.name) for s in db.scalars(select(Store))
    }

    by_key: dict[str, list[Product]] = {}
    for product in listings:
        by_key.setdefault(product.canonical_id or f"product:{product.id}", []).append(product)

    items = []
    for row in rows:
        group = sorted(
            by_key.get(row.group_key, []),
            key=lambda p: (float(p.current_price), p.condition is not None),
        )
        if not group:
            continue
        cheapest = group[0]
        items.append({
            "group_key": row.group_key,
            # Shortest title carries the least store-specific boilerplate.
            "name": min((p.name for p in group), key=len),
            "p_category": cheapest.p_category,
            "image_url": next((p.image_url for p in group if p.image_url), None),
            "best_price": float(row.best_price),
            "highest_price": float(row.worst_price),
            "offer_count": row.offer_count,
            "condition": cheapest.condition,
            "cheapest": {
                "id": cheapest.id,
                "store": store_names.get(cheapest.sid, "Retailer"),
                "price": float(cheapest.current_price),
                "mrp": float(cheapest.current_mrp) if cheapest.current_mrp else None,
                "url": cheapest.product_url,
                "in_stock": cheapest.in_stock,
            },
        })

    return {"total": total, "items": items, "page": page, "size": size}


@router.get("/stats")
def get_catalog_stats(db: Session = Depends(get_db)):
    """Headline numbers for the catalog, measured rather than written.

    These are the site's credibility claims, so every one is a live count. A stat bar
    with hardcoded figures is the fastest way to make a price tracker look fake, and it
    goes stale the moment a retailer is added.
    """
    products = db.scalar(
        select(func.count(Product.id)).where(
            Product.is_legacy.is_(False), has_usable_price()
        )
    ) or 0
    stores = db.scalar(select(func.count(Store.id)).where(Store.active.is_(True))) or 0
    snapshots = db.scalar(select(func.count(PriceHistory.id))) or 0
    latest = db.scalar(select(func.max(PriceHistory.scraped_at)))

    return {
        "products": products,
        "stores": stores,
        "price_snapshots": snapshots,
        "last_updated": latest.isoformat() if latest else None,
    }


@router.get("/facets")
def list_spec_facets(
    request: Request,
    p_category: str = Query(..., description="Category to describe filters for"),
    q: str | None = Query(None),
    min_price: Decimal | None = Query(None),
    max_price: Decimal | None = Query(None),
    sid: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """Filters for a category, narrowed by whatever is already selected.

    The filters are hierarchical: `SPEC_FILTERS` lists each category's fields in the
    order the decisions actually get made (socket before form factor before chipset),
    and every facet's options and counts are computed against the *currently filtered*
    set. So choosing AM5 leaves only AM5 chipsets to choose from, and the counts beside
    each option are what you will really get.

    Each facet is computed with every other filter applied but **not its own**. That is
    what lets a shopper switch from AM5 to LGA1700 directly instead of having to clear
    the socket filter first - if a facet constrained itself, selecting a value would
    collapse its own list to that single option.

    Any filter can be skipped. Nothing below a skipped filter narrows, so a shopper who
    doesn't care which socket they end up on can go straight to core count.
    """
    spec_model, spec_fields = spec_model_for(p_category)
    if spec_model is None:
        return {"p_category": p_category, "filters": [], "applied": {}}

    parsed = parse_spec_params(request.query_params, spec_fields)

    product_conditions = [
        func.lower(Product.p_category) == p_category.lower(),
        Product.is_legacy.is_(False),
        Product.in_stock.is_(True),
        has_usable_price(),
        Product.canonical_id.is_not(None),
    ]
    if q:
        product_conditions.extend(_search_conditions(q))
    if min_price is not None:
        product_conditions.append(Product.current_price >= min_price)
    if max_price is not None:
        product_conditions.append(Product.current_price <= max_price)
    if sid is not None:
        product_conditions.append(Product.sid == sid)

    matching_models = (
        select(Product.canonical_id)
        .where(*product_conditions)
        .distinct()
        .subquery()
    )

    def scoped(stmt, exclude_column: str):
        """`stmt` joined to the catalog and narrowed by every filter but one."""
        stmt = stmt.join(
            matching_models,
            matching_models.c.canonical_id == spec_model.canonical_id,
        )
        others = [f for f in parsed if f[0] != exclude_column]
        return apply_spec_filters(stmt, spec_model, others)

    filters = []
    for name, (column_name, kind) in spec_fields.items():
        column = getattr(spec_model, column_name)

        if kind == ENUM:
            rows = db.execute(
                scoped(select(column, func.count()), column_name)
                .where(column.is_not(None), column != "")
                .group_by(column)
                .order_by(func.count().desc(), column.asc())
            ).all()
            if rows:
                filters.append({
                    "name": name,
                    "kind": ENUM,
                    "options": [{"value": v, "count": c} for v, c in rows],
                })
        else:
            low, high = db.execute(
                scoped(select(func.min(column), func.max(column)), column_name)
                .where(column.is_not(None))
            ).one()
            if low is not None and high is not None and low != high:
                filters.append({
                    "name": name,
                    "kind": RANGE,
                    "min": float(low),
                    "max": float(high),
                })

    # Echo what is active so the UI can show removable chips without re-deriving it.
    applied = {}
    for column_name, kind, op, value in parsed:
        key = column_name if op == "eq" else f"{column_name}_{op}"
        applied[key] = value

    return {"p_category": p_category, "filters": filters, "applied": applied}


@router.get("/{product_id}/price-series")
def get_price_series(
    product_id: int,
    days: int = Query(90, ge=1, le=365, description="Window size in days"),
    db: Session = Depends(get_db),
):
    """Daily price series and summary stats for one listing.

    Aggregated per day rather than returned raw: the DAG snapshots every 15 minutes,
    so a month of history is thousands of points describing a line that mostly doesn't
    move. Each day carries its low and high so genuine intra-day movement still shows.

    `lowest`/`highest` describe what this listing has actually sold for, which is the
    honest reference point for "is this a deal". MRP is not used for that comparison -
    it is routinely inflated to manufacture a discount, so the observed floor is the
    only trustworthy baseline.
    """
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    since = func.now() - func.cast(f"{days} days", INTERVAL)
    day = func.date_trunc("day", PriceHistory.scraped_at)

    rows = db.execute(
        select(
            day.label("day"),
            func.min(PriceHistory.price).label("low"),
            func.max(PriceHistory.price).label("high"),
            # Last reading of the day is what the listing closed at.
            func.max(PriceHistory.scraped_at).label("last_seen"),
        )
        .where(PriceHistory.product_id == product_id, PriceHistory.scraped_at >= since)
        .group_by(day)
        .order_by(day)
    ).all()

    points = [
        {
            "date": r.day.date().isoformat(),
            "low": float(r.low),
            "high": float(r.high),
        }
        for r in rows
        if r.low is not None
    ]

    stats: dict = {"points": len(points)}
    if points:
        lows = [p["low"] for p in points]
        highs = [p["high"] for p in points]
        lowest = min(lows)
        current = float(product.current_price) if product.current_price else points[-1]["low"]

        stats.update({
            "current": current,
            "lowest": lowest,
            "highest": max(highs),
            "lowest_date": min(points, key=lambda p: p["low"])["date"],
            "at_lowest": current <= lowest,
            # How much above its own floor the listing is right now.
            "pct_above_lowest": round((current - lowest) / lowest * 100, 1) if lowest else None,
        })

    return {
        "product_id": product_id,
        "name": product.name,
        "currency": product.currency,
        "days": days,
        "points": points,
        "stats": stats,
    }


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Retrieve detailed product details by database primary key."""
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found",
        )
    p_out = ProductOut.model_validate(product)
    p_out.target_ids = [t.id for t in product.targets] if hasattr(product, "targets") else []
    p_out.keywords = [t.target_value for t in product.targets] if hasattr(product, "targets") else []
    return p_out


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
