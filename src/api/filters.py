"""Shared query predicates for the product-facing endpoints."""

from sqlalchemy import select

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
