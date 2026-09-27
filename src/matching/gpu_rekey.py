"""One-time re-key of existing GPU listings onto matching/gpu_identity.py's keys.

New listings get the new key from the extraction step. Listings extracted before it
keep their old, memory-less key until this runs. It uses each listing's stored LLM
extraction (brand, chipset, variant) plus its title, so no LLM calls are made.

Spec rows follow the listings: a model that is split (8GB and 16GB) copies the old
row to each half and sets memory_size_gb from the key; a model that gains listings
from a spelling twin keeps its own row. Models left with no listings are deleted,
and their spec rows with them (ON DELETE CASCADE).
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.canonical_part import CanonicalPart
from db.models.category_specs import GPUSpecs
from db.models.gpu_title_extraction import GPUTitleExtraction
from db.models.product import Product
from matching.canonical_key_builder import disambiguate_failed_key, make_canonical_key_string
from matching.gpu_identity import gpu_key_fields

_SPEC_COPY_SKIP = {"id", "canonical_id", "created_at", "updated_at"}


def plan(session: Session) -> list[tuple[Product, GPUTitleExtraction, str, dict]]:
    """(product, extraction, new canonical_id, key fields) for every listing whose
    key changes."""
    rows = session.execute(
        select(Product, GPUTitleExtraction)
        .join(GPUTitleExtraction, GPUTitleExtraction.product_id == Product.id)
        .where(GPUTitleExtraction.status == "ok")
    ).all()
    moves = []
    for product, ext in rows:
        fields = disambiguate_failed_key(
            gpu_key_fields(ext.brand, ext.chipset, ext.variant, product.name), product.id
        )
        new_id = make_canonical_key_string("gpu", fields)
        if new_id != product.canonical_id:
            moves.append((product, ext, new_id, fields))
    return moves


def rekey_gpus(session: Session, dry_run: bool = True) -> dict:
    moves = plan(session)
    by_new: dict[str, set] = defaultdict(set)
    by_old: dict[str, set] = defaultdict(set)
    for product, _, new_id, _ in moves:
        by_new[new_id].add(product.canonical_id)
        by_old[product.canonical_id].add(new_id)
    stats = {
        "listings_moved": len(moves),
        "old_models_split": sum(1 for v in by_old.values() if len(v) > 1),
        "new_models": len(by_new),
    }
    if dry_run:
        stats["moves"] = [(p.id, p.name, p.canonical_id, new) for p, _, new, _ in moves]
        return stats

    parts = {cp.canonical_id: cp for cp in session.scalars(
        select(CanonicalPart).where(CanonicalPart.canonical_id.in_(list(by_new) + list(by_old))))}
    specs = {sp.canonical_id: sp for sp in session.scalars(
        select(GPUSpecs).where(GPUSpecs.canonical_id.in_(list(by_new) + list(by_old))))}

    for product, ext, new_id, fields in moves:
        old_id = product.canonical_id
        if new_id not in parts:
            old_part = parts.get(old_id)
            parts[new_id] = CanonicalPart(
                canonical_id=new_id, category="gpu", brand=fields["aib_brand"],
                key_fields=fields, from_title=[product.name],
                status=old_part.status if old_part else "OK",
            )
            session.add(parts[new_id])
            session.flush()
        if new_id not in specs and old_id in specs:
            old = specs[old_id]
            copy = GPUSpecs(canonical_id=new_id, **{
                c.name: getattr(old, c.name) for c in GPUSpecs.__table__.columns
                if c.name not in _SPEC_COPY_SKIP
            })
            session.add(copy)
            specs[new_id] = copy
        if new_id in specs and "memory" in fields:
            specs[new_id].memory_size_gb = int(fields["memory"][:-2])
        product.canonical_id = new_id
        ext.canonical_id = new_id
    session.flush()

    # Models nothing points at any more.
    still_used = set(session.scalars(
        select(Product.canonical_id).where(Product.canonical_id.in_(list(by_old)))))
    orphans = [cid for cid in by_old if cid not in still_used and cid in parts]
    for cid in orphans:
        session.delete(parts[cid])
    session.flush()
    stats["models_deleted"] = len(orphans)
    return stats
