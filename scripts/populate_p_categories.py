"""
Script to populate the standardized user-facing p_category column for all products in PostgreSQL.
"""
from db.session import SessionLocal
from sqlalchemy import text
from matching.category_classifier import CategoryClassifier


def populate_p_categories():
    with SessionLocal() as session:
        print("Populating user-facing p_category column across PostgreSQL products...")
        rows = session.execute(text("SELECT id, name, category FROM products;")).fetchall()
        print(f"  Fetched {len(rows)} products to classify...")

        updates = []
        for pid, title, raw_cat in rows:
            p_cat = CategoryClassifier.get_p_category(raw_cat, title)
            updates.append({"pid": pid, "pcat": p_cat})

        # Batch update
        stmt = text("UPDATE products SET p_category = :pcat WHERE id = :pid")
        session.execute(stmt, updates)
        session.commit()

        print("=" * 80)
        print("P_CATEGORY POPULATION COMPLETE!")


if __name__ == "__main__":
    populate_p_categories()
