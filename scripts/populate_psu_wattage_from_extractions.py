"""Copy PSU wattage from title extractions into psu_specs.

`psu_title_extractions.wattage` has been populated all along (980 of 1,016 rows), but
`psu_specs.wattage` was never filled from it - all 446 rows were NULL. Nothing surfaced
this because nothing read the column until the catalog gained spec filters, at which
point "wattage" was the one PSU filter that silently failed to appear.

Wattage is the first thing anyone picks a PSU by, so this is a zero-API-cost backfill
of the most useful filter in that category.

Only fills gaps by default; --overwrite replaces existing values.
"""
import argparse
import sys
from collections import Counter

from sqlalchemy import select

from db.session import SessionLocal
from db.models.category_specs import PSUSpecs
from db.models.psu_title_extraction import PSUTitleExtraction


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--overwrite", action="store_true",
                    help="replace wattage values that are already set")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    stats = Counter()
    with SessionLocal() as db:
        # One canonical_id can have several extractions (one per listing). They agree
        # on wattage by construction - it is part of the canonical key - so the first
        # non-null is safe to take.
        wattage_by_canonical: dict[str, int] = {}
        for canonical_id, wattage in db.execute(
            select(PSUTitleExtraction.canonical_id, PSUTitleExtraction.wattage)
            .where(
                PSUTitleExtraction.canonical_id.is_not(None),
                PSUTitleExtraction.wattage.is_not(None),
            )
        ):
            wattage_by_canonical.setdefault(canonical_id, wattage)

        specs = list(db.scalars(select(PSUSpecs)))
        for spec in specs:
            wattage = wattage_by_canonical.get(spec.canonical_id)
            if wattage is None:
                stats["no_extraction"] += 1
                continue
            if spec.wattage is not None and not args.overwrite:
                stats["already_set"] += 1
                continue
            if spec.wattage == wattage:
                stats["unchanged"] += 1
                continue
            if not args.dry_run:
                spec.wattage = wattage
            stats["filled"] += 1

        if args.dry_run:
            db.rollback()
        else:
            db.commit()

    print(f"psu_specs rows: {len(specs)}")
    for key in ("filled", "already_set", "unchanged", "no_extraction"):
        print(f"  {key}: {stats[key]}")
    if args.dry_run:
        print("(dry run - nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
