"""
One-time wiring: RAM was extracted before the canonical_id grouping pattern existed.
This recomputes canonical keys from the ALREADY-STORED ram_title_extractions data
(brand/series/memory_type/capacity/modules/speed/cl_timing/form_factor) - no new LLM
calls needed, since the raw identity fields were already extracted correctly.
Re-runnable: skips products that already have a canonical_id unless --all.
"""
import argparse
import sys

sys.path.insert(0, "src")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart
from db.models.ram_title_extraction import RAMTitleExtraction
from matching.canonical_key_builder import make_canonical_key_string, disambiguate_failed_key


def key_dict_for(ext: RAMTitleExtraction) -> dict:
    cap = f"{ext.capacity_gb}gb" if ext.capacity_gb else ""
    modules = f"{ext.modules}x" if ext.modules else ""
    speed = f"{ext.speed_mhz}mhz" if ext.speed_mhz else ""
    return {
        "category": "ram",
        "brand": ext.brand or "Unknown",
        "series": ext.series or "",
        "memory_type": ext.memory_type or "",
        "capacity": cap,
        "modules": modules,
        "speed_mhz": speed,
        "cl_timing": ext.cl_timing or "",
        "form_factor": ext.form_factor or "",
    }


def wire_ram_canonical(reprocess_all: bool = False):
    with SessionLocal() as session:
        print("=" * 80)
        print("WIRE RAM INTO CANONICAL GROUPING (from stored extraction data, no API calls)")
        print("=" * 80)

        stmt = select(RAMTitleExtraction).where(RAMTitleExtraction.status == "ok")
        if not reprocess_all:
            stmt = stmt.where(RAMTitleExtraction.canonical_id.is_(None))
        extractions = session.scalars(stmt).all()
        total = len(extractions)
        print(f"Found {total} RAM extraction rows needing canonical linkage (reprocess_all={reprocess_all}).")

        canonical_cache: dict[str, CanonicalPart] = {}
        linked = 0

        for i, ext in enumerate(extractions, start=1):
            product = session.get(Product, ext.product_id)
            if product is None:
                continue

            key_dict = key_dict_for(ext)
            key_dict = disambiguate_failed_key(key_dict, product.id)
            canonical_id = make_canonical_key_string("ram", key_dict)

            cp = canonical_cache.get(canonical_id)
            if cp is None:
                cp = session.scalar(select(CanonicalPart).where(CanonicalPart.canonical_id == canonical_id))
            if cp is None:
                conf = ext.confidence
                cp = CanonicalPart(
                    canonical_id=canonical_id,
                    category="ram",
                    brand=key_dict["brand"],
                    key_fields=key_dict,
                    from_title=[ext.raw_title],
                    status="NEEDS_REVIEW" if conf == "low" else "OK",
                )
                session.add(cp)
                session.flush()
            canonical_cache[canonical_id] = cp

            product.canonical_id = canonical_id
            ext.canonical_id = canonical_id
            if ext.confidence == "low" and product.spec_status != "extracted":
                product.spec_status = "needs_review"
            elif product.spec_status == "pending":
                product.spec_status = "extracted"

            linked += 1
            if i % 200 == 0 or i == total:
                session.commit()
                print(f"[{i}/{total}] linked={linked} | unique canonical IDs so far: {len(canonical_cache)}")

        session.commit()
        print("=" * 80)
        print("WIRING COMPLETE")
        print(f"  Total linked:         {linked}")
        print(f"  Unique canonical IDs: {len(canonical_cache)}")
        print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wire RAM extractions into canonical_parts grouping.")
    parser.add_argument("--all", action="store_true", help="Reprocess all RAM extractions, including already-linked ones.")
    args = parser.parse_args()

    wire_ram_canonical(reprocess_all=args.all)
