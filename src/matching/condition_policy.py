"""Detects listings that are not sealed retail stock.

Indian retailers sell opened stock alongside new stock and mark it in the title:
"[RePacked]" (TPS Tech), "Open Box OEM" (Computech, EliteHubs, PrimeABGB). These units
are systematically cheaper than sealed ones, so a catalog that can't tell them apart
lets them win every price comparison and lead every cheapest-first sort - which is an
apples-to-oranges answer, the same shape of problem as an inflated MRP.

Owner decision 2026-10-02: only new, retail-boxed stock is listed. Every condition
here is hidden from the catalog, the builder and price comparison (api.filters.
is_new_stock). That includes OEM/tray CPUs: new chips, but sold without the retail box
and cooler, and the owner chose to count them as not new.

"RePacked" is TPS Tech's own term and their product pages don't define it; the listings
carry "Original Brand Warranty" and a 7-day return window, which puts it with open-box
rather than with used or refurbished goods.
"""

import re

NEW = None
OPEN_BOX = "open_box"
REPACKED = "repacked"
REFURBISHED = "refurbished"
OEM = "oem"

# Ordered: the first match wins, so the more specific patterns come first. Each is
# anchored on wording retailers actually use, not on loose words - a bare "used" would
# match "used for gaming" in a description, so it requires a boundary and appears only
# in the refurbished group where the phrasing is unambiguous.
_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    (REPACKED, re.compile(r"\[?\s*re-?pack(ed|aged)?\s*\]?", re.I)),
    (OPEN_BOX, re.compile(r"\bopen[\s\-]?box\b", re.I)),
    (REFURBISHED, re.compile(r"\b(refurb(ished)?|renewed|pre[\s\-]?owned|second[\s\-]?hand)\b", re.I)),
    (OEM, re.compile(r"\boem\b", re.I)),
)

# Only a CPU is sold "tray" or in a multipack; a cabinet's "drive tray" is a part.
_CPU_OEM = re.compile(r"\b(tray|multi[\s\-]?pack|mpk)\b", re.I)


def detect_condition(title: str | None, p_category: str | None = None) -> str | None:
    """Sale condition from the listing title, or None for new retail stock."""
    if not title:
        return NEW
    for condition, pattern in _PATTERNS:
        if pattern.search(title):
            return condition
    if (p_category or "").upper() == "CPU" and _CPU_OEM.search(title):
        return OEM
    return NEW
