"""
Apply the supported-platform policy (matching/legacy_policy.py) to products.is_legacy.

Runs off already-extracted spec/identity data, so it needs no API calls and is safe
to re-run after new products are scraped. Flagged products stay fully price-tracked;
they're only hidden from the PC Builder's component pickers.
"""
import argparse
import sys

from sqlalchemy import select

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart
from db.models.category_specs import CPUSpecs, RAMSpecs
from db.models.motherboard_title_extraction import MotherboardTitleExtraction
from db.models.ram_title_extraction import RAMTitleExtraction
from matching.legacy_policy import is_cpu_legacy, is_motherboard_legacy, is_ram_legacy


def classify(dry_run: bool = False) -> None:
    with SessionLocal() as session:
        print("=" * 80)
        print("CLASSIFY LEGACY PRODUCTS (supported-platform policy)")
        print("=" * 80)

        # --- CPUs: series/model from canonical_parts, socket from cpu_specs ---
        cpu_socket = {
            s.canonical_id: s.socket
            for s in session.scalars(select(CPUSpecs))
        }
        cpu_keys = {
            cp.canonical_id: (cp.key_fields or {})
            for cp in session.scalars(select(CanonicalPart).where(CanonicalPart.category == "cpu"))
        }

        legacy_cpu_ids = set()
        for cid, kf in cpu_keys.items():
            if is_cpu_legacy(kf.get("series"), kf.get("model_number"), cpu_socket.get(cid)):
                legacy_cpu_ids.add(cid)

        # --- Motherboards: socket from the per-listing extraction ---
        legacy_mobo_products = set()
        for ext in session.scalars(select(MotherboardTitleExtraction).where(MotherboardTitleExtraction.status == "ok")):
            if is_motherboard_legacy(ext.socket):
                legacy_mobo_products.add(ext.product_id)

        # --- RAM: memory_type, preferring the canonical spec, else the listing ---
        ram_type_by_canonical = {
            s.canonical_id: s.memory_type for s in session.scalars(select(RAMSpecs))
        }
        legacy_ram_products = set()
        for ext in session.scalars(select(RAMTitleExtraction).where(RAMTitleExtraction.status == "ok")):
            mem = ram_type_by_canonical.get(ext.canonical_id) or ext.memory_type
            if is_ram_legacy(mem):
                legacy_ram_products.add(ext.product_id)

        # PSUs whose brand couldn't be resolved. Two of these turned out not to be
        # power supplies at all (a soundbar and a speaker), and an unidentifiable PSU is
        # the one part you least want in a build - it's the component whose failure can
        # damage everything attached to it. Hidden until identity extraction can name
        # the brand; several are real regional makes (Dawg, Coconut) the model doesn't
        # recognise yet, so this is a recognition gap rather than a judgement on them.
        unbranded_psu_products = set()
        for cp in session.scalars(select(CanonicalPart).where(CanonicalPart.category == "psu")):
            brand = (cp.brand or "").strip()
            if not brand or brand.upper() == "UNKNOWN":
                for prod in session.scalars(select(Product).where(Product.canonical_id == cp.canonical_id)):
                    unbranded_psu_products.add(prod.id)

        counts = {"CPU": 0, "Motherboard": 0, "RAM": 0, "PSU (no brand)": 0}
        cleared = 0

        products = session.scalars(
            select(Product).where(Product.p_category.in_(["CPU", "Motherboard", "RAM", "Power Supply"]))
        ).all()

        for p in products:
            if p.p_category == "Power Supply":
                legacy = p.id in unbranded_psu_products
                bucket = "PSU (no brand)"
            elif p.p_category == "CPU":
                # The canonical pass covers everything identity extraction could name.
                # When it failed there is no series to test, so fall back to the
                # product's own title - that is how a 7th-gen Core i5 with
                # canonical_id 'cpu:unknown' stayed visible and led the cheapest-first
                # CPU listing. is_cpu_legacy only reads the title when the series is
                # blank, and reads it per brand.
                legacy = p.canonical_id in legacy_cpu_ids
                if not legacy:
                    key_fields = cpu_keys.get(p.canonical_id) or {}
                    if not (key_fields.get("series") or "").strip():
                        legacy = is_cpu_legacy(
                            None, None, cpu_socket.get(p.canonical_id), p.name
                        )
                bucket = "CPU"
            elif p.p_category == "Motherboard":
                legacy = p.id in legacy_mobo_products
                bucket = "Motherboard"
            else:
                legacy = p.id in legacy_ram_products
                bucket = "RAM"

            if legacy and not p.is_legacy:
                counts[bucket] += 1
                if not dry_run:
                    p.is_legacy = True
            elif legacy and p.is_legacy:
                counts[bucket] += 1
            elif not legacy and p.is_legacy:
                cleared += 1
                if not dry_run:
                    p.is_legacy = False

        if not dry_run:
            session.commit()

        print(f"  Scanned:            {len(products)} products across CPU/Motherboard/RAM/PSU")
        print(f"  Flagged legacy:     {counts}  (total {sum(counts.values())})")
        print(f"  Un-flagged:         {cleared}")
        print(f"  Mode:               {'DRY RUN (no writes)' if dry_run else 'committed'}")
        print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flag off-policy legacy products so the PC Builder hides them.")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without writing.")
    args = parser.parse_args()
    classify(dry_run=args.dry_run)
