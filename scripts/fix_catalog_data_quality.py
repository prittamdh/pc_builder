"""
Three targeted data-quality fixes found while surveying the catalog (2026-08-16).

1. Cabinet form factors were stored with inconsistent spellings ("E-ATX" vs "EATX",
   "mATX" vs "Micro ATX") and sometimes held a chassis SIZE ("Mid Tower", "SFF")
   instead of a form factor. The case-fit rule compares these by string identity, so
   the variants silently defeated the check.

2. Coolers whose entire supported-socket list is retired can't mount on anything
   buildable today, so they're flagged legacy like off-policy CPUs and boards. One
   cooler had "Intel/AMD" stored as its socket list, which names no socket at all -
   nulled so the fit rule treats it as unknown rather than comparing against garbage.

3. External USB drives sit in the Storage category. They're real products worth
   price tracking, but offering one as a build's internal drive is wrong, so they're
   marked so the builder can exclude them.

Idempotent: safe to re-run.
"""
import argparse
import re
import sys

from sqlalchemy import select

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.session import SessionLocal
from db.models.product import Product
from db.models.cabinet_title_extraction import CabinetTitleExtraction
from db.models.cooler_title_extraction import CoolerTitleExtraction
from db.models.storage_title_extraction import StorageTitleExtraction
from db.models.category_specs import CoolerSpecs
from matching.form_factor import normalize_form_factor
from matching.legacy_policy import is_cooler_legacy

# Interfaces that identify an external drive rather than an internal one.
EXTERNAL_INTERFACE_MARKERS = ("USB", "THUNDERBOLT", "EXTERNAL", "TYPE C", "TYPE-C")

# The interface field alone isn't sufficient: a portable drive is often an NVMe SSD in
# a USB enclosure, so it is honestly recorded as "NVMe" while still being external.
# The title is the reliable signal for those.
EXTERNAL_TITLE_MARKERS = ("EXTERNAL", "PORTABLE", "USB")


def fix_cabinet_form_factors(session, dry_run: bool) -> dict:
    stats = {"normalized": 0, "cleared": 0, "recovered_from_title": 0, "unchanged": 0}
    for ext in session.scalars(select(CabinetTitleExtraction).where(CabinetTitleExtraction.status == "ok")):
        before = ext.form_factor
        after = normalize_form_factor(before, ext.raw_title)

        if after == before:
            stats["unchanged"] += 1
            continue
        if after is None:
            stats["cleared"] += 1
        elif before is None or before.strip().upper() in {"MID TOWER", "MID-TOWER", "SFF", "MINI TOWER"}:
            stats["recovered_from_title"] += 1
        else:
            stats["normalized"] += 1

        if not dry_run:
            ext.form_factor = after
    return stats


def fix_coolers(session, dry_run: bool) -> dict:
    stats = {"flagged_legacy": 0, "nulled_bad_sockets": 0}

    for spec in session.scalars(select(CoolerSpecs).where(CoolerSpecs.supported_sockets.isnot(None))):
        sockets = spec.supported_sockets or ""
        # A value naming no socket at all is unusable for the fit rule. Match real
        # socket shapes rather than loose substrings: "AMD" contains "AM", so a naive
        # check reads the useless value "Intel/AMD" as naming the AM4/AM5 family.
        if not re.search(r"(LGA\s*\d{3,4}|\b\d{3,4}\b|\bAM[45]\b|\bs?TRX?[45]\b|\bSP[356]\b|\b115X\b)", sockets, re.IGNORECASE):
            stats["nulled_bad_sockets"] += 1
            if not dry_run:
                spec.supported_sockets = None
                spec.notes = ((spec.notes or "") + " [cleared 2026-08-16: value named no socket]").strip()
            continue

        if is_cooler_legacy(sockets):
            products = session.scalars(
                select(Product).where(Product.canonical_id == spec.canonical_id)
            ).all()
            for p in products:
                if not p.is_legacy:
                    stats["flagged_legacy"] += 1
                    if not dry_run:
                        p.is_legacy = True
    return stats


def fix_external_storage(session, dry_run: bool) -> dict:
    stats = {"marked_external": 0}
    external_product_ids = set()

    for ext in session.scalars(select(StorageTitleExtraction).where(StorageTitleExtraction.status == "ok")):
        interface = (ext.interface or "").upper()
        title = (ext.raw_title or "").upper()
        looks_external = (
            any(m in interface for m in EXTERNAL_INTERFACE_MARKERS)
            or any(m in title for m in EXTERNAL_TITLE_MARKERS)
        )
        if looks_external:
            external_product_ids.add(ext.product_id)

    for p in session.scalars(select(Product).where(Product.id.in_(external_product_ids))):
        if not p.is_legacy:
            stats["marked_external"] += 1
            if not dry_run:
                # Reuses is_legacy as the builder's "not offerable as a build part" flag.
                p.is_legacy = True
    return stats


def main(dry_run: bool) -> None:
    with SessionLocal() as session:
        print("=" * 78)
        print(f"CATALOG DATA-QUALITY FIXES {'(DRY RUN)' if dry_run else ''}")
        print("=" * 78)

        cab = fix_cabinet_form_factors(session, dry_run)
        print(f"  Cabinet form factors: {cab}")

        cool = fix_coolers(session, dry_run)
        print(f"  Coolers:              {cool}")

        stor = fix_external_storage(session, dry_run)
        print(f"  External storage:     {stor}")

        if not dry_run:
            session.commit()
            print("  committed.")
        print("=" * 78)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix cabinet form factors, dead-socket coolers, external storage.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
