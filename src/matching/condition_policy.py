"""Detects listings that are not sealed retail stock.

Indian retailers sell opened stock alongside new stock and mark it in the title:
"[RePacked]" (TPS Tech), "Open Box OEM" (Computech, EliteHubs, PrimeABGB). These units
are systematically cheaper than sealed ones, so a catalog that can't tell them apart
lets them win every price comparison and lead every cheapest-first sort - which is an
apples-to-oranges answer, the same shape of problem as an inflated MRP.

Flagged, never hidden: an open-box Threadripper at a real discount is a legitimate
thing to buy, and the buyer just has to be told what it is.

"RePacked" is TPS Tech's own term and their product pages don't define it; the listings
carry "Original Brand Warranty" and a 7-day return window, which puts it with open-box
rather than with used or refurbished goods.
"""

import re

NEW = None
OPEN_BOX = "open_box"
REPACKED = "repacked"
REFURBISHED = "refurbished"

# Ordered: the first match wins, so the more specific patterns come first. Each is
# anchored on wording retailers actually use, not on loose words - a bare "used" would
# match "used for gaming" in a description, so it requires a boundary and appears only
# in the refurbished group where the phrasing is unambiguous.
_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    (REPACKED, re.compile(r"\[?\s*re-?pack(ed|aged)?\s*\]?", re.I)),
    (OPEN_BOX, re.compile(r"\bopen[\s\-]?box\b", re.I)),
    (REFURBISHED, re.compile(r"\b(refurb(ished)?|renewed|pre[\s\-]?owned|second[\s\-]?hand)\b", re.I)),
)


def detect_condition(title: str | None) -> str | None:
    """Sale condition from the listing title, or None for ordinary sealed stock."""
    if not title:
        return NEW
    for condition, pattern in _PATTERNS:
        if pattern.search(title):
            return condition
    return NEW
