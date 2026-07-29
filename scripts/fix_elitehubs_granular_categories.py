"""
Script to strictly enforce exact granular target categories for all EliteHubs products (sid=6)
in PostgreSQL directly from its 17 Category Catalog target configurations.
"""
from sqlalchemy import select
from db.session import SessionLocal
from db.models.store import Store
from db.models.scrape_target import ScrapeTarget
from db.models.product import Product
from db.models.product_target import ProductTarget


def fix_elitehubs_categories():
    with SessionLocal() as session:
        store = session.scalar(select(Store).where(Store.name == "elitehubs"))
        if not store:
            print("[Error] EliteHubs store not found.")
            return

        sid = store.id
        print(f"Enforcing granular categories for EliteHubs (store_id={sid})...")

        # Map target_id -> hard_category
        targets = session.scalars(select(ScrapeTarget).where(ScrapeTarget.store_id == sid)).all()
        target_cat_map = {}
        for t in targets:
            if isinstance(t.schedule_config, dict) and t.schedule_config.get("category"):
                target_cat_map[t.id] = t.schedule_config.get("category")
                print(f"  Target id={t.id} ('{t.target_value}') -> category = '{t.schedule_config.get('category')}'")

        # Fetch product_target links for EliteHubs
        pt_links = session.execute(
            select(ProductTarget.product_id, ProductTarget.target_id)
        ).fetchall()

        prod_target_cat = {pid: target_cat_map[tid] for pid, tid in pt_links if tid in target_cat_map}

        updated_count = 0
        products = session.scalars(select(Product).where(Product.sid == sid)).all()

        for p in products:
            if p.id in prod_target_cat:
                correct_cat = prod_target_cat[p.id]
                if p.category != correct_cat:
                    p.category = correct_cat
                    updated_count += 1

        session.commit()
        print("=" * 80)
        print(f"ELITEHUBS GRANULAR CATEGORY ENFORCEMENT COMPLETE: Updated {updated_count} products.")


if __name__ == "__main__":
    fix_elitehubs_categories()
