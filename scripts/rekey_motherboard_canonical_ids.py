"""
One-off migration: rebuild motherboard canonical_ids from the board designation.

The canonical key was brand + chipset + model_number, using the chipset exactly as the
Stage 1 model returned it. The model normalizes the variant letter away inconsistently,
which broke the key in both directions:

  over-merge  "MSI MPG B850 Edge Ti WiFi" (ATX, 4 DIMM) and "MSI MPG B850I Edge TI WiFi"
              (ITX, 2 DIMM) both became motherboard:msi:b850:mpg_edge_ti_wifi, so the ITX
              board inherited the ATX board's motherboard_specs row.
  under-merge  the same micro-ATX board came back as "B650M" on some listings and "B650"
              on others, splitting one real model across two canonical_ids.

The key now uses the board designation recovered from each listing's own title
(see matching.canonical_key_builder.resolve_board_designation), so no Stage 1 LLM re-run
is needed - brand, model_number and raw_title are already persisted per listing, and
recomputing from them is deterministic and free.

Existing motherboard_specs rows are carried across where the new group is demonstrably
the same board (pure rename, or a split where the original id survives); rows that can no
longer be attributed to a single board are dropped so Stage 2 re-extracts them.

Dry-run by default. Pass --apply to write.
"""
import argparse
import collections
import sys

from sqlalchemy import select

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart
from db.models.category_specs import MotherboardSpecs
from db.models.motherboard_title_extraction import MotherboardTitleExtraction
from matching.canonical_key_builder import (
    build_motherboard_key_dict, disambiguate_failed_key, make_canonical_key_string,
)
from matching.motherboard_identity import reconcile_group_form_factors


def plan(session):
    """Maps every extracted motherboard listing to its new canonical_id."""
    rows = session.scalars(
        select(MotherboardTitleExtraction).where(
            MotherboardTitleExtraction.canonical_id.is_not(None),
            MotherboardTitleExtraction.status == "ok",
        )
    ).all()

    mapping = {}          # product_id -> (old_id, new_id, key_dict)
    for row in rows:
        key_dict = build_motherboard_key_dict(
            row.brand, row.chipset, row.model_number, row.raw_title
        )
        key_dict = disambiguate_failed_key(key_dict, row.product_id)
        mapping[row.product_id] = (
            row.canonical_id, make_canonical_key_string("motherboard", key_dict), key_dict
        )
    return rows, mapping


def choose_spec_source(new_id: str, old_ids: set[str], new_by_old: dict[str, set[str]],
                       old_sizes: dict[str, int],
                       spec_rows: dict[str, MotherboardSpecs]) -> str | None:
    """
    Picks which old motherboard_specs row (if any) still describes this new group.

    A row may only carry over from an old group that did NOT split. A split group was
    two different boards sharing one spec row, and that row was extracted from whichever
    listings happened to be sampled - so it cannot be trusted for either side, including
    the side that kept the original id. Both get re-extracted instead.

    Groups that merely merged or were renamed keep their specs; where several clean old
    groups collapse into one, the largest one's row wins.
    """
    # An id that already owns a spec row keeps it - unless it split, in which case the
    # row describes an unknown one of the two boards and is no better than nothing.
    if new_id in spec_rows and new_by_old.get(new_id, {new_id}) == {new_id}:
        return new_id
    clean = [
        o for o in old_ids
        if o != new_id and o in spec_rows and new_by_old.get(o) == {new_id}
    ]
    if not clean:
        return None
    return max(clean, key=lambda o: old_sizes.get(o, 0))


def rekey(apply: bool = False):
    with SessionLocal() as session:
        print("=" * 80)
        print(f"MOTHERBOARD CANONICAL RE-KEY ({'APPLY' if apply else 'DRY RUN'})")
        print("=" * 80)

        rows, mapping = plan(session)
        old_ids_all = {old for old, _, _ in mapping.values()}
        new_by_old = collections.defaultdict(set)
        old_by_new = collections.defaultdict(set)
        old_sizes = collections.Counter()
        key_by_new = {}
        for old, new, kd in mapping.values():
            new_by_old[old].add(new)
            old_by_new[new].add(old)
            old_sizes[old] += 1
            key_by_new[new] = kd

        changed = {pid: v for pid, v in mapping.items() if v[0] != v[1]}
        splits = {o: n for o, n in new_by_old.items() if len(n) > 1}
        merges = {n: o for n, o in old_by_new.items() if len(o) > 1}

        print(f"  listings mapped:        {len(mapping)}")
        print(f"  canonical ids: {len(old_ids_all)} -> {len(old_by_new)}")
        print(f"  listings re-pointed:    {len(changed)}")
        print(f"  groups split:           {len(splits)}")
        print(f"  groups merged into one: {len(merges)}")

        # canonical_id is a global primary key, so a new id has to be checked against
        # every category, not just motherboards, before it can be inserted.
        existing_cp = {
            cp.canonical_id: cp for cp in session.scalars(
                select(CanonicalPart).where(
                    (CanonicalPart.category == "motherboard")
                    | (CanonicalPart.canonical_id.in_(list(old_by_new)))
                )
            )
        }
        foreign = [c for c, cp in existing_cp.items() if cp.category != "motherboard"]
        if foreign:
            raise SystemExit(
                f"Refusing to run: {len(foreign)} target canonical_id(s) already exist under a "
                f"different category, e.g. {foreign[:3]}"
            )
        # Destination ids can already carry a spec row from an earlier run, so they are
        # loaded too - a move must never collide with a row that is already there.
        spec_scope = old_ids_all | set(old_by_new)
        spec_rows = {
            s.canonical_id: s for s in session.scalars(
                select(MotherboardSpecs).where(MotherboardSpecs.canonical_id.in_(spec_scope))
            )
        } if spec_scope else {}

        to_create = [n for n in old_by_new if n not in existing_cp]
        spec_plan = {
            n: choose_spec_source(n, o, new_by_old, old_sizes, spec_rows)
            for n, o in old_by_new.items()
        }
        spec_moves = {n: s for n, s in spec_plan.items() if s is not None and s != n}
        spec_keeps = {n for n, s in spec_plan.items() if s == n}
        spec_needed = [n for n, s in spec_plan.items() if s is None]
        spec_dropped = set(spec_rows) - set(spec_plan.values())

        # Only retire rows this migration stranded. The 370-odd canonical_parts that
        # already had no listings before it ran are pre-existing cruft from earlier
        # pipeline runs - unrelated to this fix, so they are reported and left alone.
        orphan_cp = sorted(old_ids_all - set(old_by_new))
        pre_existing_orphans = len(existing_cp) - len(old_ids_all)

        print(f"  canonical_parts to create: {len(to_create)}")
        print(f"  canonical_parts retired:   {len(orphan_cp)}")
        print(f"  (pre-existing unreferenced canonical_parts, left as-is: {pre_existing_orphans})")
        print(f"  motherboard_specs kept:    {len(spec_keeps)}")
        print(f"  motherboard_specs moved:   {len(spec_moves)}")
        print(f"  motherboard_specs dropped: {len(spec_dropped)}")
        print(f"  models needing Stage 2:    {len(spec_needed)}")

        print("\n  sample splits:")
        for old, news in sorted(splits.items())[:12]:
            print(f"    {old}\n        -> {sorted(news)}")

        if not apply:
            print("\nDry run - nothing written. Re-run with --apply.")
            return

        # 1. Create the canonical_parts rows the new ids need, before anything points at them.
        titles_by_new = collections.defaultdict(list)
        for row in rows:
            titles_by_new[mapping[row.product_id][1]].append(row.raw_title)
        for new_id in to_create:
            kd = key_by_new[new_id]
            source = next((existing_cp[o] for o in sorted(old_by_new[new_id]) if o in existing_cp), None)
            session.add(CanonicalPart(
                canonical_id=new_id,
                category="motherboard",
                brand=kd.get("brand") or "Unknown",
                key_fields=kd,
                from_title=titles_by_new[new_id][:5],
                status=source.status if source is not None else "OK",
            ))
        session.flush()

        # 2. Refresh key_fields on the ids that survive, so they match the new key shape.
        for new_id, cp in existing_cp.items():
            if new_id in old_by_new:
                cp.key_fields = key_by_new[new_id]
        session.flush()

        # 3. Re-point the listings and their extraction rows.
        for row in rows:
            _, new_id, kd = mapping[row.product_id]
            row.canonical_id = new_id
            row.chipset = kd["chipset"] or row.chipset
        session.flush()
        for pid, (_, new_id, _) in mapping.items():
            session.execute(
                Product.__table__.update().where(Product.id == pid).values(canonical_id=new_id)
            )
        session.flush()

        # 4. Move spec rows that still describe their board; drop the unattributable ones.
        #    Deletes run first so a move can never collide with a row being retired.
        for old_id in sorted(spec_dropped):
            session.delete(spec_rows[old_id])
        session.flush()
        for new_id, old_id in sorted(spec_moves.items()):
            spec_rows[old_id].canonical_id = new_id
        session.flush()

        # 5. Retire canonical_parts nothing points at any more.
        for cid in orphan_cp:
            session.delete(existing_cp[cid])
        session.flush()

        stats = reconcile_group_form_factors(session)
        print(f"\n  form-factor reconciliation: {stats}")

        session.commit()
        print("\nApplied.")
        print(f"Next: python scripts/extract_motherboard_specs_groq.py   ({len(spec_needed)} models need Stage 2)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the changes (default is a dry run).")
    args = parser.parse_args()
    rekey(apply=args.apply)
