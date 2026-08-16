"""
Populate ssd_specs (canonical_id-keyed) directly from storage_title_extractions.
No LLM calls needed: capacity/interface are stated in the title and already extracted
in Stage 1. read/write speeds and form_factor are left null - they're deep spec-sheet
numbers that retailer titles rarely state, and guessing them would be worse than empty.
Re-runnable: upserts by canonical_id.
"""
import argparse
import sys

from sqlalchemy import select

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.session import SessionLocal
from db.models.canonical_part import CanonicalPart
from db.models.storage_title_extraction import StorageTitleExtraction
from db.models.category_specs import SSDSpecs

CONF_RANK = {"high": 3, "medium": 2, "low": 1, None: 0}


def populate_ssd_specs(reprocess_all: bool = False):
    with SessionLocal() as session:
        print("=" * 80)
        print("POPULATE ssd_specs FROM storage_title_extractions (no API calls)")
        print("=" * 80)

        stmt = select(CanonicalPart).where(CanonicalPart.category == "storage")
        if not reprocess_all:
            stmt = stmt.where(CanonicalPart.canonical_id.notin_(select(SSDSpecs.canonical_id)))
        canonical_parts = session.scalars(stmt).all()
        print(f"Found {len(canonical_parts)} canonical Storage models to populate (reprocess_all={reprocess_all}).")

        filled = 0
        skipped = 0
        for cp in canonical_parts:
            extractions = session.scalars(
                select(StorageTitleExtraction).where(
                    StorageTitleExtraction.canonical_id == cp.canonical_id,
                    StorageTitleExtraction.status == "ok",
                )
            ).all()
            if not extractions:
                skipped += 1
                continue

            def completeness(e: StorageTitleExtraction) -> tuple:
                return (CONF_RANK.get(e.confidence, 0), sum(f is not None for f in [e.capacity_gb, e.interface]))

            best = max(extractions, key=completeness)

            existing = session.scalar(select(SSDSpecs).where(SSDSpecs.canonical_id == cp.canonical_id))
            if existing is None:
                existing = SSDSpecs(canonical_id=cp.canonical_id, status="pending")
                session.add(existing)

            existing.brand = best.brand
            existing.capacity_gb = int(best.capacity_gb) if best.capacity_gb is not None else None
            existing.interface = best.interface
            existing.confidence = best.confidence
            existing.notes = "Derived from storage_title_extractions (capacity/interface are stated in titles). read/write speeds and form_factor intentionally left null - not reliably available."
            existing.llm_model = best.llm_model
            existing.status = "ok"
            existing.error = None
            filled += 1

        session.commit()
        print("=" * 80)
        print(f"  Populated: {filled}")
        print(f"  Skipped (no ok extraction row): {skipped}")
        print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate ssd_specs from storage_title_extractions (no API calls).")
    parser.add_argument("--all", action="store_true", help="Repopulate all canonical Storage models.")
    args = parser.parse_args()

    populate_ssd_specs(reprocess_all=args.all)
