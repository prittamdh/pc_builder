"""
Group-level reconciliation of PSU efficiency trims.

Putting the trim in the canonical key fixes the over-merge (ASUS ships "TUF Gaming
750W" in both Bronze and Gold, and without the trim those were one group inheriting
whichever rating was written last). On its own it creates the opposite fault.

Retailers are inconsistent about printing the rating: of the listings for Ant Esports
FG650 V2 650W, some titles say "80+ Gold" and some say nothing at all. Keyed naively,
that one real unit splits into `...:fg650_v2:650w` and `...:gold:fg650_v2:650w` - an
under-merge, and exactly the B650/B650M fault the motherboard path had to solve.

The distinction that resolves it is how many *different* trims a model shows:

  one trim stated   -> the silent listings are the same unit with a terser title, so the
                       trim propagates to them. One group.
  two or more       -> a genuinely multi-trim model. A listing naming none cannot be
                       attributed to either, so it keeps an empty trim and is flagged for
                       review rather than being guessed into one of them.
  none stated       -> nothing to reconcile; the group keys without a trim as before.

Grouping is by brand + model_number + wattage - the old canonical key - because that is
precisely the set the trim is being used to subdivide.
"""
from __future__ import annotations

import collections

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.psu_title_extraction import PSUTitleExtraction
from matching.canonical_key_builder import normalize_efficiency_trim


def _group_key(row: PSUTitleExtraction) -> tuple:
    return (
        (row.brand or "").strip().lower(),
        (row.model_number or "").strip().lower(),
        row.wattage,
    )


def resolve_group_trim(rows) -> str | None:
    """
    The single trim a group of listings agrees on, or None when there is no single one.

    None covers both "nobody stated a trim" and "listings disagree" - in either case
    there is nothing to propagate, which is what the caller needs to know.
    """
    stated = {normalize_efficiency_trim(r.efficiency_rating) for r in rows}
    stated.discard("")
    return stated.pop() if len(stated) == 1 else None


def reconcile_group_trims(session: Session, product_ids: list[int] | None = None) -> dict:
    """
    Fills the efficiency trim on listings whose title omitted it, where the rest of the
    same model agrees on exactly one.

    Pass `product_ids` to limit the pass to listings touched by the current run; omit it
    to reconcile everything. Does not commit - the caller owns the transaction.

    Only ever writes to listings that stated no trim. A title that names a tier is
    evidence and is never overwritten by its neighbours, so a genuine Bronze listing
    cannot be rewritten to Gold by a more numerous sibling.
    """
    stmt = select(PSUTitleExtraction).where(PSUTitleExtraction.status == "ok")
    if product_ids:
        stmt = stmt.where(PSUTitleExtraction.product_id.in_(product_ids))

    groups: dict[tuple, list] = collections.defaultdict(list)
    for row in session.scalars(stmt):
        groups[_group_key(row)].append(row)

    filled = 0
    ambiguous_groups = 0
    ambiguous_listings = 0

    for rows in groups.values():
        trims = {normalize_efficiency_trim(r.efficiency_rating) for r in rows}
        trims.discard("")
        silent = [r for r in rows if not normalize_efficiency_trim(r.efficiency_rating)]

        if len(trims) == 1 and silent:
            trim = next(iter(trims))
            for row in silent:
                row.efficiency_rating = trim
                filled += 1
        elif len(trims) > 1 and silent:
            # A multi-trim model whose listing names no tier. Leaving the trim empty keeps
            # it out of both tiered groups, which is correct - but it is a real gap, so it
            # is surfaced rather than left looking settled.
            ambiguous_groups += 1
            ambiguous_listings += len(silent)
            for row in silent:
                row.status = "needs_review"

    return {
        "groups": len(groups),
        "listings_filled": filled,
        "ambiguous_groups": ambiguous_groups,
        "ambiguous_listings": ambiguous_listings,
    }


def find_trim_conflicts(session) -> list[dict]:
    """
    Canonical PSU groups whose key trim contradicts the trim Stage 2 extracted.

    The two come from different evidence: the key trim is read off listing titles in
    Stage 1, while psu_specs.efficiency_rating is extracted in Stage 2 from the model
    name grounded in real listing text. When they disagree, Stage 1 almost certainly
    mis-read a title and manufactured a group that should not exist.

    MSI's MAG A750GL is the worked example - "GL" is MSI's own marker for Gold, yet a
    stray listing keyed a Bronze group. Stage 2 then reported Gold for both halves, so
    the split is visible without knowing anything about MSI's naming.

    Read-only; returns rows for a human to judge rather than merging anything. A
    conflict is evidence of a bad group, not proof of which side is right.
    """
    from db.models.canonical_part import CanonicalPart
    from db.models.category_specs import PSUSpecs

    rows = session.execute(
        select(CanonicalPart.canonical_id, CanonicalPart.key_fields, PSUSpecs.efficiency_rating)
        .join(PSUSpecs, PSUSpecs.canonical_id == CanonicalPart.canonical_id)
        .where(CanonicalPart.category == "psu", PSUSpecs.status == "ok")
    ).all()

    conflicts = []
    for canonical_id, key_fields, spec_rating in rows:
        key_trim = normalize_efficiency_trim((key_fields or {}).get("efficiency"))
        spec_trim = normalize_efficiency_trim(spec_rating)
        # Only a genuine disagreement counts. A group with no trim in its key is the
        # untiered case, which is expected and already handled by reconciliation.
        if key_trim and spec_trim and key_trim != spec_trim:
            conflicts.append({
                "canonical_id": canonical_id,
                "key_trim": key_trim,
                "spec_trim": spec_trim,
            })
    return conflicts
