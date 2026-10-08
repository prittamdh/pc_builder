"""Shared query predicates for the product-facing endpoints."""

import re

from sqlalchemy import func, or_, select

from db.models.product import Product
from db.models.store import Store


def from_active_store():
    """True for listings whose store is active.

    A store is set inactive when its prices can no longer be refreshed (PCStudio went
    behind a Cloudflare bot check on 2026-09-25, last price 2026-08-17). Its old prices
    would otherwise show as current. The flag is read at query time, so re-enabling the
    store brings its listings back with no other change.
    """
    return Product.sid.in_(select(Store.id).where(Store.active.is_(True)))


def is_new_stock():
    """True for new, retail-boxed listings: no open box, repacked, refurbished or
    OEM/tray (matching/condition_policy.py). Owner decision 2026-10-02: only new stock
    is listed anywhere on the site."""
    return Product.condition.is_(None)


def is_listed():
    """What the site shows: new stock from an active store."""
    return from_active_store() & is_new_stock()


def has_usable_price():
    """True for listings carrying a real, positive price.

    A zero price is not a cheap price - it means the scraper captured nothing. It has
    to be treated as absent rather than as a very low number, because a 0 sorts to the
    front of every price-ascending listing and silently subtracts a whole component
    from a build total.

    This is a guard, not a fix. As of 2026-08-17 all 163 of TLG Gaming's (sid 11)
    products are priced 0.00 while flagged in stock, which is a scraper defect in that
    store's OpenCart/Journal 3 parser, not a property of the market.
    """
    return Product.current_price.is_not(None) & (Product.current_price > 0)


def search_conditions(q: str) -> list:
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
