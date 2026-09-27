"""Daily check that no model mixes listings of different sizes (Phase 7, identity quality).

A model's listings must all be the same product. The size a title states is the
cheapest reliable test of that: a GPU model with both 8GB and 16GB listings, an SSD
model with 1TB and 2TB, a PSU model with 650W and 750W, is a wrong merge, and its
"from" price belongs to a different product. Found live on 2026-09-27 (GPU memory);
this keeps it from coming back unnoticed.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from db.session import SessionLocal
from matching.gpu_identity import memory_gb_from_title
from matching.size_from_title import psu_watts_from_title, storage_gb_from_title

SIZE_OF = {
    "GPU": memory_gb_from_title,
    "Storage": storage_gb_from_title,
    "Power Supply": psu_watts_from_title,
}


def size_conflicts(listings) -> dict[str, set]:
    """{canonical_id: sizes} for models whose listings state more than one size.
    `listings` is (p_category, canonical_id, title) rows."""
    sizes: dict[str, set] = defaultdict(set)
    for category, cid, title in listings:
        size_of = SIZE_OF.get(category)
        if size_of is None or not cid:
            continue
        size = size_of(title)
        if size is not None:
            sizes[cid].add(size)
    return {cid: s for cid, s in sizes.items() if len(s) > 1}


def check_identity_sizes():
    from db.models.product import Product

    with SessionLocal() as session:
        rows = session.execute(
            select(Product.p_category, Product.canonical_id, Product.name)
            .where(Product.p_category.in_(list(SIZE_OF)), Product.canonical_id.is_not(None))
        ).all()
    conflicts = size_conflicts(rows)
    if conflicts:
        sample = "; ".join(f"{cid} {sorted(s)}" for cid, s in sorted(conflicts.items())[:10])
        raise RuntimeError(f"{len(conflicts)} models mix listings of different sizes: {sample}")
    print(f"[Identity] {len(rows)} listings checked, no model mixes sizes")
