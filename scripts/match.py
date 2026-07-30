"""
match.py
Combines normalize.py + schemas.py into the actual cross-store matching step.

Flow per category:
  1. Extract structured attributes for every listing (schemas.py)
  2. Block listings by (category, brand) — cheap partition, avoids O(n^2) across all stores
  3. Within a block, group listings whose CRITICAL fields are identical -> same canonical product
  4. Listings with incomplete critical fields fall into a manual-review queue instead of
     being auto-matched or auto-rejected

This intentionally does NOT do fuzzy/embedding matching yet — that's the next layer for
categories where regex extraction stays incomplete too often (cases, coolers, peripherals).
Rules-first gets you high precision on CPU/RAM/storage/PSU/GPU immediately.
"""

from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Any

from normalize import normalize_title
from schemas import extract_attributes


@dataclass
class Listing:
    store_id: str
    raw_title: str
    category: str
    price: float
    url: str
    specs: dict | None = None


@dataclass
class MatchResult:
    canonical_key: tuple
    category: str
    attributes: dict
    listings: list[Listing]
    needs_review: bool


def build_canonical_key(attrs: dict, critical_fields: list[str]) -> tuple:
    return tuple(attrs.get(f) for f in critical_fields)


def match_listings(listings: list[Listing]) -> list[MatchResult]:
    """Group raw store listings into canonical products, one category at a time."""
    by_category: dict[str, list[Listing]] = defaultdict(list)
    for l in listings:
        by_category[l.category].append(l)

    results: list[MatchResult] = []

    for category, cat_listings in by_category.items():
        groups: dict[tuple, list[tuple[Listing, dict]]] = defaultdict(list)
        review_queue: list[tuple[Listing, dict]] = []

        for listing in cat_listings:
            attrs = extract_attributes(category, listing.raw_title, listing.specs)
            attrs["normalized_title"] = normalize_title(listing.raw_title)

            if not attrs["_complete"]:
                review_queue.append((listing, attrs))
                continue

            key = build_canonical_key(attrs, attrs["_critical_fields"])
            groups[key].append((listing, attrs))

        for key, pairs in groups.items():
            results.append(MatchResult(
                canonical_key=key,
                category=category,
                attributes=pairs[0][1],
                listings=[p[0] for p in pairs],
                needs_review=False,
            ))

        for listing, attrs in review_queue:
            results.append(MatchResult(
                canonical_key=(),
                category=category,
                attributes=attrs,
                listings=[listing],
                needs_review=True,
            ))

    return results


if __name__ == "__main__":
    sample = [
        Listing("md_computers", "Intel Core i5-14600K (Box) Desktop Processor - LGA1700", "cpu", 32500, "url1"),
        Listing("primeabgb", "Intel i5 14600K 14th Gen CPU Box Pack", "cpu", 32800, "url2"),
        Listing("vedant", "Intel Core i5-13600K Processor", "cpu", 28000, "url3"),  # different model, must NOT merge
        Listing("md_computers", "Corsair Vengeance RGB 32GB (2x16GB) DDR5 6000MHz CL30", "ram", 11500, "url4"),
        Listing("primeabgb", "Corsair Vengeance RGB 32GB DDR5 RAM 6000 MHz Kit 2x16GB", "ram", 11800, "url5"),
        Listing("vedant", "Some Weird Unbranded RAM Stick 32GB", "ram", 9000, "url6"),  # incomplete -> review
    ]

    results = match_listings(sample)
    for r in results:
        tag = "REVIEW" if r.needs_review else "MATCHED"
        stores = [l.store_id for l in r.listings]
        print(f"[{tag}] {r.category} key={r.canonical_key} stores={stores}")
