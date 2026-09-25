"""
Clear the 80 PLUS tier on PSU title extractions whose own title does not state it.

Owner ruling 2026-09-25: "absent beats wrong". scripts/audit_psu_title_tier_grounding.py
puts every stored `psu_title_extractions.efficiency_rating` in a bucket; this script
clears exactly the rows in bucket a) cybenetics_leak (the title's only certification
wording is Cybenetics, which the prompt says to ignore) and b) no_tier_wording (the
tier word is nowhere in the title). The selection is the audit's own `classify_row`,
imported rather than copied, so the two can never drift apart.

Reversible: each cleared row gets a `notes` line recording the old value, the reason
and the date (`old_value_from_notes` reads it back).

The efficiency tier is part of the PSU canonical key, so clearing it can move a listing
to another group. Order of operations matters:

  1. Clear ALL selected rows first (this script, --apply).
  2. Then run scripts/rekey_psu_canonical_ids.py. Its reconcile_group_trims() refills
     a silent listing from same-model siblings that agree on exactly one trim.

Because every selected row is already blank when reconciliation runs, a cleared row can
only be re-filled from a sibling whose own tier survived the clear - never from another
row being cleared (e.g. the Antec Atom V550 V2 listings, all ungrounded, stay untiered).
`--preview-rekey` shows exactly that sequence: it applies the clear inside a transaction,
runs the re-key dry run in the same transaction, prints both, then rolls everything back.

Rows outside a)/b) are cleared only when named with --extra-ids (an owner decision).

Usage:
    python scripts/clear_ungrounded_psu_tiers.py                    # dry run
    python scripts/clear_ungrounded_psu_tiers.py --preview-rekey    # clear + re-key, rolled back
    python scripts/clear_ungrounded_psu_tiers.py --apply            # write the clear
"""
from __future__ import annotations

import argparse
import ast
import collections
import datetime
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import audit_psu_title_tier_grounding as audit  # noqa: E402
from matching.canonical_key_builder import normalize_efficiency_trim  # noqa: E402

SELECTED_BUCKETS = ("cybenetics_leak", "no_tier_wording")
NOTE_PREFIX = "tier cleared"
_REASONS = {
    "cybenetics_leak": "title states only a Cybenetics rating, no 80 PLUS tier",
    "no_tier_wording": "title states no tier at all",
    "extra_id": "named by owner decision (--extra-ids)",
}
_NOTE_OLD_VALUE = re.compile(
    rf"{re.escape(NOTE_PREFIX)} \d{{4}}-\d{{2}}-\d{{2}}: efficiency_rating was ('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")"
)
BATCH_SIZE = 50


# --- Pure logic (tested in tests/test_clear_ungrounded_psu_tiers.py) ----------------

def plan_clear(rows, extra_ids=()) -> list[tuple]:
    """(row, bucket) for every row whose stored tier this script clears, in input order.

    A row is selected when the audit puts it in a) or b). Rows named in `extra_ids` are
    selected too, labelled "extra_id". A row with no stored tier has nothing to clear.
    """
    extra_ids = set(extra_ids or ())
    plan = []
    for row in rows:
        if not (row.efficiency_rating or "").strip():
            continue
        bucket = audit.classify_row(row.raw_title, row.efficiency_rating)
        if bucket in SELECTED_BUCKETS:
            plan.append((row, bucket))
        elif row.product_id in extra_ids:
            plan.append((row, "extra_id"))
    return plan


def clearing_note(existing: str | None, old_value: str, bucket: str, when: str) -> str:
    """The notes value after clearing: the existing notes, kept, plus one new line."""
    entry = (f"{NOTE_PREFIX} {when}: efficiency_rating was {old_value!r}; "
             f"reason: {bucket} - {_REASONS[bucket]} "
             f"(scripts/clear_ungrounded_psu_tiers.py, owner ruling 2026-09-25)")
    return f"{existing}\n{entry}" if (existing or "").strip() else entry


def old_value_from_notes(notes: str | None) -> str | None:
    """The value the most recent clearing note recorded, for undoing it; None if none."""
    found = _NOTE_OLD_VALUE.findall(notes or "")
    return ast.literal_eval(found[-1]) if found else None


def _group_key(row) -> tuple:
    # Same grouping as matching.psu_identity.reconcile_group_trims.
    return ((row.brand or "").strip().lower(), (row.model_number or "").strip().lower(),
            row.wattage)


def refill_preview(rows, cleared_ids) -> dict:
    """What reconcile_group_trims() would do to each cleared row once ALL cleared rows
    are blank: the trim it would be filled with, "needs_review" when the remaining
    siblings disagree, or None when nothing is left to propagate.

    Mirrors reconciliation exactly: only status='ok' rows are read or written.
    """
    cleared_ids = set(cleared_ids)
    groups = collections.defaultdict(list)
    for row in rows:
        if row.status == "ok":
            groups[_group_key(row)].append(row)

    result = {pid: None for pid in cleared_ids}
    for members in groups.values():
        targets = [r for r in members if r.product_id in cleared_ids]
        if not targets:
            continue
        trims = {
            normalize_efficiency_trim(r.efficiency_rating)
            for r in members if r.product_id not in cleared_ids
        }
        trims.discard("")
        outcome = next(iter(trims)) if len(trims) == 1 else ("needs_review" if trims else None)
        for r in targets:
            result[r.product_id] = outcome
    return result


# --- DB -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Snap:
    """A plain copy of one extraction row, so a row deleted mid-run cannot break us."""
    id: int
    product_id: int
    canonical_id: str | None
    raw_title: str
    brand: str | None
    model_number: str | None
    wattage: int | None
    efficiency_rating: str | None
    llm_model: str | None
    status: str
    notes: str | None


def load_snapshot(session) -> list[Snap]:
    from sqlalchemy import select
    from db.models.psu_title_extraction import PSUTitleExtraction as T
    return [
        Snap(r.id, r.product_id, r.canonical_id, r.raw_title, r.brand, r.model_number,
             r.wattage, r.efficiency_rating, r.llm_model, r.status, r.notes)
        for r in session.scalars(select(T).order_by(T.id))
    ]


def _write_clear(session, plan, when) -> tuple[int, list[str]]:
    """Clears the planned rows in `session` without committing. A row that has been
    deleted, or whose tier changed since the snapshot, is skipped and reported."""
    from db.models.psu_title_extraction import PSUTitleExtraction as T
    cleared, skipped = 0, []
    for snap, bucket in plan:
        row = session.get(T, snap.id, with_for_update=True)
        if row is None:
            skipped.append(f"id={snap.id} product_id={snap.product_id}: row gone")
            continue
        if row.efficiency_rating != snap.efficiency_rating:
            skipped.append(f"id={snap.id} product_id={snap.product_id}: tier changed to "
                           f"{row.efficiency_rating!r} since the snapshot")
            continue
        row.notes = clearing_note(row.notes, snap.efficiency_rating, bucket, when)
        row.efficiency_rating = None
        cleared += 1
    session.flush()
    return cleared, skipped


def _print_plan(plan, refill) -> None:
    print(f"{'id':>5} {'product':>7}  {'bucket':16} {'old tier':15} {'llm_model':22} "
          f"{'after re-key':13} title")
    for snap, bucket in plan:
        after = refill.get(snap.product_id) or "(none)"
        print(f"{snap.id:>5} {snap.product_id:>7}  {bucket:16} {snap.efficiency_rating!r:15} "
              f"{snap.llm_model or '-':22} {after:13} {snap.raw_title}")
    print()
    print("by bucket:", dict(collections.Counter(b for _, b in plan)))
    print("predicted outcome once the re-key reconciles:",
          dict(collections.Counter(refill.get(s.product_id) or "(none)" for s, _ in plan)))


def _print_rekey_effect(session, plan, summary) -> None:
    from sqlalchemy import select, func
    from db.models.product import Product
    from db.models.psu_title_extraction import PSUTitleExtraction as T

    mapping = summary["mapping"]
    cleared_pids = {s.product_id for s, _ in plan}
    print()
    print("=" * 80)
    print("RE-KEY EFFECT ON THE CLEARED LISTINGS")
    print("=" * 80)
    for snap, _ in plan:
        row = session.get(T, snap.id)
        old, new, _ = mapping.get(snap.product_id, (snap.canonical_id, None, None))
        print(f"  {snap.product_id:>6}  tier now {row.efficiency_rating!r:10} status={row.status:12} "
              f"{old} -> {new if new else '(not re-keyed: status ' + row.status + ')'}")

    changed = {pid: v for pid, v in mapping.items() if v[0] != v[1]}
    outside = {pid: v for pid, v in changed.items() if pid not in cleared_pids}
    print(f"\n  listings re-pointed: {len(changed)} "
          f"({len(changed) - len(outside)} cleared, {len(outside)} other)")
    for pid, (old, new, _) in sorted(outside.items()):
        row = session.scalars(select(T).where(T.product_id == pid)).one()
        print(f"    other {pid:>6} {row.efficiency_rating!r:12} {old} -> {new} | {row.raw_title}")

    print("\n  splits:")
    for old, news in sorted(summary["splits"].items()):
        print(f"    {old} -> {sorted(news)}")
    print("  merges:")
    for new, olds in sorted(summary["merges"].items()):
        print(f"    {sorted(olds)} -> {new}")

    # Listings the re-key does not map (status != 'ok') but that point at an id it retires.
    retired = set(summary["orphan_cp"])
    stranded = session.execute(
        select(Product.id, Product.canonical_id).where(Product.canonical_id.in_(retired))
        .where(Product.id.not_in(list(mapping)))
    ).all() if retired else []
    print(f"\n  canonical ids retired: {len(retired)}; unmapped listings still pointing at one: "
          f"{len(stranded)} {stranded[:10]}")

    # psu_specs for every canonical id a cleared listing touches, before and after.
    spec_rows, spec_plan = summary["spec_rows"], summary["spec_plan"]
    touched_new = {mapping[p][1] for p in cleared_pids if p in mapping}
    touched_old = {mapping[p][0] for p in cleared_pids if p in mapping}
    print("\n  psu_specs for canonical ids the cleared listings end up in:")
    for cid in sorted(touched_new):
        src = spec_plan.get(cid)
        spec = spec_rows.get(src) if src else None
        how = ("kept" if src == cid else f"moved from {src}") if src else "none (Stage 2 needed)"
        rating = spec.efficiency_rating if spec else None
        llm = spec.llm_model if spec else None
        print(f"    {cid:55s} rating={rating!r:14} llm={llm!r:24} {how}")
    dropped = sorted(summary["spec_dropped"] & touched_old)
    print(f"  psu_specs dropped among the cleared listings' old ids: {len(dropped)} {dropped}")
    live = session.execute(select(func.count(func.distinct(Product.canonical_id))).where(
        Product.id.in_(list(mapping)))).scalar()
    print(f"  (live PSU canonical ids before: {live})")


def _print_audit_after(session) -> None:
    """The grounding audit's buckets as they would read after the clear and the re-key."""
    from sqlalchemy import select
    from db.models.psu_title_extraction import PSUTitleExtraction as T
    rows = session.scalars(select(T).where(T.efficiency_rating.is_not(None))).all()
    backed = audit.sibling_backed(rows)
    buckets = collections.defaultdict(list)
    for r in rows:
        buckets[audit.classify_row(r.raw_title, r.efficiency_rating)].append(r)
    print()
    print("=" * 80)
    print(f"AUDIT AS IT WOULD READ AFTER CLEAR + RE-KEY - {len(rows)} rows with a tier")
    print("=" * 80)
    for key in ("cybenetics_leak", "no_tier_wording", "other_ungrounded", "grounded"):
        n_backed = sum(1 for r in buckets[key] if r.product_id in backed)
        tail = (f" ({n_backed} sibling-backed, {len(buckets[key]) - n_backed} grounded nowhere)"
                if key != "grounded" else "")
        print(f"  {key:18s}: {len(buckets[key]):4d}{tail}")
        if key != "grounded":
            for r in buckets[key]:
                if r.product_id not in backed:
                    print(f"      grounded nowhere: {r.product_id} {r.efficiency_rating!r} | {r.raw_title}")


def run(apply: bool, preview_rekey: bool, extra_ids: set[int]) -> None:
    from sqlalchemy.exc import IntegrityError, OperationalError
    from db.session import SessionLocal

    when = datetime.date.today().isoformat()
    with SessionLocal() as session:
        snaps = load_snapshot(session)
        session.rollback()
    plan = plan_clear(snaps, extra_ids)
    refill = refill_preview(snaps, {s.product_id for s, _ in plan})

    mode = "APPLY" if apply else ("PREVIEW CLEAR + RE-KEY (rolled back)" if preview_rekey else "DRY RUN")
    print("=" * 80)
    print(f"CLEAR UNGROUNDED PSU TIERS ({mode}) - {len(plan)} rows of {len(snaps)}")
    print("=" * 80)
    _print_plan(plan, refill)

    if preview_rekey:
        import rekey_psu_canonical_ids as rekey_script
        with SessionLocal() as session:
            try:
                cleared, skipped = _write_clear(session, plan, when)
                print(f"\n(in-transaction) cleared {cleared}, skipped {len(skipped)} {skipped}\n")
                summary = rekey_script.rekey(apply=False, session=session)
                if summary:
                    _print_rekey_effect(session, plan, summary)
                # SessionLocal has autoflush off: push reconciliation's in-memory fills
                # into this (rolled-back) transaction so the audit below sees them.
                session.flush()
                _print_audit_after(session)
            finally:
                session.rollback()
        print("\nPreview - everything rolled back.")
        return

    if not apply:
        print("\nDry run - nothing written. --preview-rekey to see the re-key effect, --apply to write.")
        return

    total, skipped_all = 0, []
    for i in range(0, len(plan), BATCH_SIZE):
        batch = plan[i:i + BATCH_SIZE]
        with SessionLocal() as session:
            try:
                cleared, skipped = _write_clear(session, batch, when)
                session.commit()
                total += cleared
                skipped_all += skipped
            except (IntegrityError, OperationalError) as exc:
                session.rollback()
                skipped_all.append(f"batch {i // BATCH_SIZE}: {type(exc).__name__}: {exc}")
    print(f"\nApplied: cleared {total} of {len(plan)}; skipped {len(skipped_all)}")
    for s in skipped_all:
        print(f"  skipped {s}")
    print("Next: python scripts/rekey_psu_canonical_ids.py  (dry run, then --apply)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write the clear (default: dry run).")
    parser.add_argument("--preview-rekey", action="store_true",
                        help="Clear inside a transaction, run the re-key dry run on top, roll back.")
    parser.add_argument("--extra-ids", default="",
                        help="Comma-separated product ids outside buckets a)/b) to clear too "
                             "(only with an owner decision).")
    args = parser.parse_args()
    if args.apply and args.preview_rekey:
        parser.error("--apply and --preview-rekey are exclusive")
    extra = {int(x) for x in args.extra_ids.split(",") if x.strip()}
    run(args.apply, args.preview_rekey, extra)
