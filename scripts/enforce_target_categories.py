"""
Script to strictly enforce product categories based on the ScrapeTarget
from which each product was ingested.
"""
from db.session import SessionLocal
from db.models.product import Product
from db.models.scrape_target import ScrapeTarget
from db.models.product_target import ProductTarget
from sqlalchemy import select


def enforce_target_categories():
    with SessionLocal() as session:
        print("Enforcing categories strictly based on ScrapeTarget definitions...")

        # Build map of target_id -> hard_category
        targets = session.scalars(select(ScrapeTarget)).all()
        target_cat_map = {}
        for t in targets:
            if isinstance(t.schedule_config, dict) and t.schedule_config.get("category"):
                target_cat_map[t.id] = t.schedule_config.get("category")

        # Fetch all product_target links
        pt_links = session.execute(
            select(ProductTarget.product_id, ProductTarget.target_id)
        ).fetchall()

        prod_targets = {}
        for pid, tid in pt_links:
            if tid in target_cat_map:
                prod_targets[pid] = target_cat_map[tid]

        updated = 0
        products = session.scalars(select(Product)).all()
        for p in products:
            if p.id in prod_targets:
                correct_cat = prod_targets[p.id]
                if p.category != correct_cat:
                    safe_name = p.name[:45].encode("ascii", "ignore").decode("ascii")
                    print(f"  Fixing product id={p.id}: '{p.category}' -> '{correct_cat}' (Name: {safe_name})")
                    p.category = correct_cat
                    updated += 1

        session.commit()
        print("=" * 80)
        print(f"TARGET CATEGORY ENFORCEMENT COMPLETE: Updated {updated} products.")


if __name__ == "__main__":
    enforce_target_categories()
