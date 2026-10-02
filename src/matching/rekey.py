"""Move existing listings onto a category's new identity keys (Phase 7).

New listings get new keys from the extraction step; listings extracted earlier keep
their old key until this runs. It recomputes each key from the listing's stored LLM
extraction plus its title, so no LLM calls are made.

Spec rows follow the listings: a new model copies the spec row of the model its first
listing came from; a model that only gains listings keeps its own row. Models left
with no listings are deleted, and their spec rows with them (ON DELETE CASCADE).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.canonical_part import CanonicalPart
from db.models.product import Product
from matching.canonical_key_builder import disambiguate_failed_key, make_canonical_key_string

_SPEC_COPY_SKIP = {"id", "canonical_id", "created_at", "updated_at"}


def rekey(session: Session, *, category: str, extraction_model, specs_model,
          fields_for: Callable, brand_field: str = "brand", dry_run: bool = True,
          on_spec: Callable | None = None) -> dict:
    """fields_for(extraction, product) -> key fields. on_spec(spec_row, fields) may
    adjust a spec row from the key (e.g. memory size)."""
    rows = session.execute(
        select(Product, extraction_model)
        .join(extraction_model, extraction_model.product_id == Product.id)
        .where(extraction_model.status == "ok")
    ).all()
    moves = []
    for product, ext in rows:
        fields = disambiguate_failed_key(fields_for(ext, product), product.id)
        new_id = make_canonical_key_string(category, fields)
        if new_id != product.canonical_id:
            moves.append((product, ext, new_id, fields))

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

    ids = list(by_new) + list(by_old)
    parts = {cp.canonical_id: cp for cp in session.scalars(
        select(CanonicalPart).where(CanonicalPart.canonical_id.in_(ids)))}
    specs = {sp.canonical_id: sp for sp in session.scalars(
        select(specs_model).where(specs_model.canonical_id.in_(ids)))}

    for product, ext, new_id, fields in moves:
        old_id = product.canonical_id
        if new_id not in parts:
            old_part = parts.get(old_id)
            parts[new_id] = CanonicalPart(
                canonical_id=new_id, category=category, brand=fields.get(brand_field),
                key_fields=fields, from_title=[product.name],
                status=old_part.status if old_part else "OK",
            )
            session.add(parts[new_id])
            session.flush()
        if new_id not in specs and old_id in specs:
            old = specs[old_id]
            copy = specs_model(canonical_id=new_id, **{
                c.name: getattr(old, c.name) for c in specs_model.__table__.columns
                if c.name not in _SPEC_COPY_SKIP
            })
            session.add(copy)
            specs[new_id] = copy
        if on_spec and new_id in specs:
            on_spec(specs[new_id], fields)
        product.canonical_id = new_id
        ext.canonical_id = new_id
    session.flush()

    still_used = set(session.scalars(
        select(Product.canonical_id).where(Product.canonical_id.in_(list(by_old)))))
    orphans = [cid for cid in by_old if cid not in still_used and cid in parts]
    for cid in orphans:
        session.delete(parts[cid])
    session.flush()
    stats["models_deleted"] = len(orphans)
    return stats


def rekey_cpus(session: Session, dry_run: bool = True) -> dict:
    from db.models.category_specs import CPUSpecs
    from db.models.cpu_title_extraction import CPUTitleExtraction
    from matching.cpu_identity import cpu_key_fields

    return rekey(
        session, category="cpu", extraction_model=CPUTitleExtraction, specs_model=CPUSpecs,
        fields_for=lambda e, p: cpu_key_fields(e.brand, e.series, e.model_number, p.name),
        dry_run=dry_run,
    )
