"""
One-time repair: recompute canonical_id for listings that got falsely merged into a
shared "Unknown" bucket (see disambiguate_failed_key in canonical_key_builder.py).
Reuses already-stored extraction data from each category's *_title_extractions table -
no new LLM calls needed, since the raw brand/model fields were already correct, only
the canonical key computation was flawed.
"""
import sys

sys.path.insert(0, "src")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select, func

from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart
from db.models.cpu_title_extraction import CPUTitleExtraction
from db.models.monitor_title_extraction import MonitorTitleExtraction
from db.models.gpu_title_extraction import GPUTitleExtraction
from db.models.storage_title_extraction import StorageTitleExtraction
from db.models.cooler_title_extraction import CoolerTitleExtraction
from db.models.cabinet_title_extraction import CabinetTitleExtraction
from db.models.psu_title_extraction import PSUTitleExtraction
from db.models.motherboard_title_extraction import MotherboardTitleExtraction
from matching.canonical_key_builder import make_canonical_key_string, disambiguate_failed_key


def key_dict_for(category: str, ext) -> dict:
    if category == "cpu":
        return {"category": "cpu", "brand": ext.brand or "Unknown", "series": ext.series or "", "model_number": ext.model_number or ""}
    if category == "monitor":
        return {"category": "monitor", "brand": ext.brand or "Unknown", "model_number": ext.model_number or ""}
    if category == "gpu":
        return {"category": "gpu", "aib_brand": ext.brand or "Unknown", "chipset": ext.chipset or "", "variant_model": ext.variant or ""}
    if category == "storage":
        cap = f"{ext.capacity_gb}gb" if ext.capacity_gb else ""
        return {"category": "storage", "brand": ext.brand or "Unknown", "series": ext.model_number or "", "capacity": cap, "interface": ext.interface or ""}
    if category == "cooler":
        return {"category": "cooler", "brand": ext.brand or "Unknown", "model_number": ext.model_number or ""}
    if category == "case":
        return {"category": "case", "brand": ext.brand or "Unknown", "model_number": ext.model_number or "", "color": ext.color or ""}
    if category == "psu":
        watt = f"{ext.wattage}w" if ext.wattage else ""
        return {"category": "psu", "brand": ext.brand or "Unknown", "model_number": ext.model_number or "", "wattage": watt}
    if category == "motherboard":
        return {"category": "motherboard", "brand": ext.brand or "Unknown", "chipset": ext.chipset or "", "model_number": ext.model_number or ""}
    raise ValueError(category)


CATEGORY_TABLES = {
    "cpu": CPUTitleExtraction,
    "monitor": MonitorTitleExtraction,
    "gpu": GPUTitleExtraction,
    "storage": StorageTitleExtraction,
    "cooler": CoolerTitleExtraction,
    "case": CabinetTitleExtraction,
    "psu": PSUTitleExtraction,
    "motherboard": MotherboardTitleExtraction,
}


def fix_category(session, category: str):
    ext_model = CATEGORY_TABLES[category]

    # Find "Unknown" canonical groups in this category that have more than one
    # product attached - these are the real collisions (a single-listing Unknown
    # group isn't colliding with anything, so leave it alone).
    collision_ids = session.execute(
        select(Product.canonical_id)
        .join(CanonicalPart, CanonicalPart.canonical_id == Product.canonical_id)
        .where(CanonicalPart.category == category, CanonicalPart.brand == "Unknown")
        .group_by(Product.canonical_id)
        .having(func.count(Product.id) > 1)
    ).scalars().all()

    if not collision_ids:
        print(f"[{category}] no collisions found.")
        return 0

    total_relinked = 0
    for old_canonical_id in collision_ids:
        products = session.scalars(select(Product).where(Product.canonical_id == old_canonical_id)).all()
        for product in products:
            ext = session.scalar(select(ext_model).where(ext_model.product_id == product.id))
            if ext is None:
                continue

            key_dict = key_dict_for(category, ext)
            key_dict = disambiguate_failed_key(key_dict, product.id)
            new_canonical_id = make_canonical_key_string(category, key_dict)

            if new_canonical_id == old_canonical_id:
                continue  # still collides for some reason - leave as-is, don't lose data

            cp = session.scalar(select(CanonicalPart).where(CanonicalPart.canonical_id == new_canonical_id))
            if cp is None:
                cp = CanonicalPart(
                    canonical_id=new_canonical_id,
                    category=category,
                    brand=key_dict.get("brand") or key_dict.get("aib_brand") or "Unknown",
                    key_fields=key_dict,
                    from_title=[product.name],
                    status="NEEDS_REVIEW",
                )
                session.add(cp)
                session.flush()

            product.canonical_id = new_canonical_id
            ext.canonical_id = new_canonical_id
            total_relinked += 1

        session.flush()
        # Clean up the old collision bucket if nothing points to it anymore.
        remaining = session.scalar(select(func.count(Product.id)).where(Product.canonical_id == old_canonical_id))
        if remaining == 0:
            old_cp = session.scalar(select(CanonicalPart).where(CanonicalPart.canonical_id == old_canonical_id))
            if old_cp:
                session.delete(old_cp)

    session.commit()
    print(f"[{category}] relinked {total_relinked} listings out of {len(collision_ids)} collision group(s).")
    return total_relinked


if __name__ == "__main__":
    with SessionLocal() as session:
        print("=" * 80)
        print("CANONICAL COLLISION REPAIR")
        print("=" * 80)
        grand_total = 0
        for cat in CATEGORY_TABLES:
            grand_total += fix_category(session, cat)
        print("=" * 80)
        print(f"TOTAL RELINKED: {grand_total}")
        print("=" * 80)
