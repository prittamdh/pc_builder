"""
Canonical Part Resolver Module.
Implements exact match, configurable fuzzy match, and thin identity canonical part creation in PostgreSQL.
"""
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from sqlalchemy import select

from configs.settings import FUZZY_MATCH_THRESHOLD
from db.models.canonical_part import CanonicalPart
from matching.canonical_key_builder import build_canonical_key, make_canonical_key_string, normalize_category


def calculate_fuzzy_score(s1: str, s2: str) -> float:
    """Calculates token-sort ratio between two key strings."""
    tokens1 = sorted(s1.lower().replace(":", " ").replace("_", " ").split())
    tokens2 = sorted(s2.lower().replace(":", " ").replace("_", " ").split())
    return SequenceMatcher(None, " ".join(tokens1), " ".join(tokens2)).ratio()


def resolve_canonical(title: str, category: str, session: Session, threshold: float | None = None) -> str:
    """
    Resolves raw title to canonical_id in PostgreSQL:
      1. Build category-specific canonical key dictionary & key string.
      2. Exact match against canonical_parts.canonical_id / key_fields.
      3. Fuzzy match against existing canonical_parts in same category using token-sort ratio (>= threshold).
      4. No match -> create new canonical_parts row (thin identity row) with status = 'NEEDS_REVIEW' if missing critical fields, else 'OK'.
    """
    match_threshold = threshold if threshold is not None else FUZZY_MATCH_THRESHOLD
    cat = normalize_category(category)
    key_dict = build_canonical_key(title, cat)
    canonical_id_candidate = make_canonical_key_string(cat, key_dict)

    # 1. Exact Match Lookup
    stmt = select(CanonicalPart).where(CanonicalPart.canonical_id == canonical_id_candidate)
    existing = session.scalar(stmt)
    if existing:
        return existing.canonical_id

    # Fallback Exact Match on category + key_fields JSONB
    stmt_cat = select(CanonicalPart).where(CanonicalPart.category == cat)
    existing_parts = session.scalars(stmt_cat).all()
    for cp in existing_parts:
        if cp.key_fields == key_dict:
            return cp.canonical_id

    # 2. Fuzzy Match against existing canonical parts in same category
    best_candidate = None
    best_score = 0.0
    for cp in existing_parts:
        score = calculate_fuzzy_score(canonical_id_candidate, cp.canonical_id)
        if score > best_score:
            best_score = score
            best_candidate = cp

    if best_candidate and best_score >= match_threshold:
        return best_candidate.canonical_id

    # 3. Create New Canonical Part (Thin Identity Row)
    has_unknown = any(val == "Unknown" for val in key_dict.values())
    status = "NEEDS_REVIEW" if has_unknown else "OK"
    brand = key_dict.get("brand", "Unknown")

    new_part = CanonicalPart(
        canonical_id=canonical_id_candidate,
        category=cat,
        brand=brand,
        key_fields=key_dict,
        from_title=list(key_dict.keys()),
        status=status
    )
    session.add(new_part)
    session.flush()

    return new_part.canonical_id
