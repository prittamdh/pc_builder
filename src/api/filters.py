"""Shared query predicates for the product-facing endpoints."""

from db.models.product import Product


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
