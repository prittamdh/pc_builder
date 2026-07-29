"""
Script to re-seed all 45 Category Catalog targets across all 4 stores with granular category names,
and update products.category in PostgreSQL to preserve raw category information 100%.
"""
import sys
sys.path.insert(0, ".")

from sqlalchemy import select
from db.session import SessionLocal
from db.models.store import Store
from db.models.scrape_target import ScrapeTarget
from db.models.product import Product
from db.models.product_target import ProductTarget
from scripts.seed_mdcomputers_category_targets import MDCOMPUTERS_CATALOG_TARGETS
from scripts.setup_primeabgb_catalog_targets import PRIMEABGB_CATALOG_TARGETS
from scripts.setup_vedant_catalog_targets import VEDANT_CATALOG_TARGETS
from scripts.setup_pcstudio_catalog_targets import PCSTUDIO_CATALOG_TARGETS


STORE_CONFIGS = [
    ("mdcomputers", MDCOMPUTERS_CATALOG_TARGETS),
    ("primeabgb", PRIMEABGB_CATALOG_TARGETS),
    ("vedant", VEDANT_CATALOG_TARGETS),
    ("pcstudio", PCSTUDIO_CATALOG_TARGETS),
]


def reseed_granular():
    with SessionLocal() as session:
        print("Updating scrape_targets with granular category names...")

        target_map = {}

        for store_name, targets_list in STORE_CONFIGS:
            store = session.scalar(select(Store).where(Store.name == store_name))
            if not store:
                continue

            existing_targets = session.scalars(select(ScrapeTarget).where(ScrapeTarget.store_id == store.id)).all()
            target_by_val = {t.target_value: t for t in existing_targets}

            for endpoint, category in targets_list:
                if endpoint in target_by_val:
                    t = target_by_val[endpoint]
                    cfg = dict(t.schedule_config) if isinstance(t.schedule_config, dict) else {}
                    cfg["category"] = category
                    t.schedule_config = cfg
                    target_map[t.id] = category

        session.flush()

        print("Updating products table with granular categories...")
        pt_links = session.execute(select(ProductTarget.product_id, ProductTarget.target_id)).fetchall()
        prod_target_cat = {pid: target_map[tid] for pid, tid in pt_links if tid in target_map}

        updated_prods = 0
        products = session.scalars(select(Product)).all()
        for p in products:
            if p.id in prod_target_cat:
                new_cat = prod_target_cat[p.id]
                if p.category != new_cat:
                    p.category = new_cat
                    updated_prods += 1

        session.commit()
        print("=" * 80)
        print(f"RESEED COMPLETE: Updated {len(target_map)} targets & {updated_prods} products.")


if __name__ == "__main__":
    reseed_granular()
