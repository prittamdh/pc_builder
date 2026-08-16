"""
Motherboard identity reconciliation.

Stage 1 stores one `motherboard_title_extractions` row per listing, and several
listings of the same board resolve to one canonical_id. `form_factor` is extracted
per listing, so a group can end up internally inconsistent - the same board tagged
ATX by one retailer's title, MATX by another's, and left null by a third. Since
`motherboard_specs` is keyed by canonical_id (one row per real model), that
inconsistency is by definition noise: a canonical group is one physical SKU and has
exactly one form factor.

This module collapses each group to a single value, preferring hard evidence (the
vendor's variant letter, then form factors stated literally in the listing titles)
over the model's per-listing guess.
"""
import collections

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.motherboard_title_extraction import MotherboardTitleExtraction
from matching.canonical_key_builder import (
    FORM_FACTOR_RANK,
    resolve_board_designation,
    resolve_motherboard_form_factor,
)


def _majority(values: list[str]) -> str | None:
    """Most common value; ties broken by FORM_FACTOR_RANK so the result is deterministic."""
    if not values:
        return None
    counts = collections.Counter(values)
    top = max(counts.values())
    tied = [v for v, n in counts.items() if n == top]
    if len(tied) == 1:
        return tied[0]
    return min(tied, key=lambda v: FORM_FACTOR_RANK.index(v) if v in FORM_FACTOR_RANK else len(FORM_FACTOR_RANK))


def resolve_group_form_factor(rows) -> str | None:
    """
    One form factor for one canonical group.

    Evidence-backed values (variant letter / literal title text) decide it outright.
    Only when no listing in the group offers any evidence does the model's own
    per-listing guess get a vote, since that is all there is left to go on.
    """
    evidence = [
        ff for r in rows
        if (ff := resolve_motherboard_form_factor(
            resolve_board_designation(r.chipset, r.raw_title), r.raw_title))
    ]
    if evidence:
        return _majority(evidence)
    return _majority([r.form_factor for r in rows if r.form_factor])


def reconcile_group_form_factors(session: Session, canonical_ids: list[str] | None = None) -> dict:
    """
    Rewrites `form_factor` on every listing of each canonical motherboard group to the
    group's single resolved value. Pass `canonical_ids` to limit the pass to groups
    touched by the current run; omit it to reconcile every group.

    Does not commit - the caller owns the transaction.
    """
    stmt = select(MotherboardTitleExtraction).where(
        MotherboardTitleExtraction.canonical_id.is_not(None)
    )
    if canonical_ids:
        stmt = stmt.where(MotherboardTitleExtraction.canonical_id.in_(canonical_ids))

    groups: dict[str, list] = collections.defaultdict(list)
    for row in session.scalars(stmt):
        groups[row.canonical_id].append(row)

    changed = 0
    cleared = 0
    for rows in groups.values():
        resolved = resolve_group_form_factor(rows)
        for row in rows:
            if row.form_factor != resolved:
                if resolved is None:
                    cleared += 1
                else:
                    changed += 1
                row.form_factor = resolved

    return {"groups": len(groups), "listings_updated": changed, "listings_cleared": cleared}
