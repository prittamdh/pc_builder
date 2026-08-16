"""
Populate ram_specs (canonical_id-keyed) directly from ram_title_extractions.
No LLM calls needed: RAM's Stage-1 identity extraction already captures every field
ram_specs holds (memory_type/speed/capacity/modules/CL), because those ARE the RAM
identity - unlike CPUs or GPUs, a RAM kit has no meaningful physical spec beyond what
its own name states. Values are taken from the highest-confidence extraction row per
canonical_id, since many listings map to the same real kit.
Re-runnable: upserts by canonical_id.
"""
import argparse
import sys

from sqlalchemy import select

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.session import SessionLocal
from db.models.canonical_part import CanonicalPart
from db.models.ram_title_extraction import RAMTitleExtraction
from db.models.category_specs import RAMSpecs

CONF_RANK = {"high": 3, "medium": 2, "low": 1, None: 0}


def populate_ram_specs(reprocess_all: bool = False):
    with SessionLocal() as session:
        print("=" * 80)
        print("POPULATE ram_specs FROM ram_title_extractions (no API calls)")
        print("=" * 80)

        stmt = select(CanonicalPart).where(CanonicalPart.category == "ram")
        if not reprocess_all:
            stmt = stmt.where(CanonicalPart.canonical_id.notin_(select(RAMSpecs.canonical_id)))
        canonical_parts = session.scalars(stmt).all()
        print(f"Found {len(canonical_parts)} canonical RAM models to populate (reprocess_all={reprocess_all}).")

        filled = 0
        skipped = 0
        for cp in canonical_parts:
            extractions = session.scalars(
                select(RAMTitleExtraction).where(
                    RAMTitleExtraction.canonical_id == cp.canonical_id,
                    RAMTitleExtraction.status == "ok",
                )
            ).all()
            if not extractions:
                skipped += 1
                continue

            # Prefer the most confident extraction, then the one with the most fields filled.
            def completeness(e: RAMTitleExtraction) -> tuple:
                fields = [e.memory_type, e.speed_mhz, e.capacity_gb, e.modules, e.cl_timing]
                return (CONF_RANK.get(e.confidence, 0), sum(f is not None for f in fields))

            best = max(extractions, key=completeness)

            existing = session.scalar(select(RAMSpecs).where(RAMSpecs.canonical_id == cp.canonical_id))
            if existing is None:
                existing = RAMSpecs(canonical_id=cp.canonical_id, status="pending")
                session.add(existing)

            existing.brand = best.brand
            existing.memory_type = best.memory_type
            existing.speed_mhz = best.speed_mhz
            existing.capacity_gb = int(best.capacity_gb) if best.capacity_gb is not None else None
            existing.modules = best.modules
            # cl_timing is stored as e.g. "CL16" in extractions; latency_cl is an int column.
            if best.cl_timing:
                digits = "".join(ch for ch in str(best.cl_timing) if ch.isdigit())
                existing.latency_cl = int(digits) if digits else None
            else:
                existing.latency_cl = None
            existing.confidence = best.confidence
            existing.notes = "Derived from ram_title_extractions (RAM identity fully determines its specs; no LLM recall involved)."
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
    parser = argparse.ArgumentParser(description="Populate ram_specs from ram_title_extractions (no API calls).")
    parser.add_argument("--all", action="store_true", help="Repopulate all canonical RAM models.")
    args = parser.parse_args()

    populate_ram_specs(reprocess_all=args.all)
