"""
Script to clear all product data for MDComputers (sid=1)
and reset scrape_targets next_scrape_at to NOW().
"""
from datetime import datetime, timezone
from sqlalchemy import text
from db.session import SessionLocal


def clear_mdcomputers_data():
    with SessionLocal() as session:
        print("Clearing MDComputers (sid=1) product data from PostgreSQL...")

        # Delete dependent spec tables
        spec_tables = [
            "cpu_specs", "gpu_specs", "motherboard_specs", "ram_specs",
            "ssd_specs", "psu_specs", "cabinet_specs", "cooler_specs", "monitor_specs"
        ]
        for tbl in spec_tables:
            res = session.execute(text(f"DELETE FROM {tbl} WHERE product_id IN (SELECT id FROM products WHERE sid = 1)"))
            print(f"  -> Deleted {res.rowcount} rows from {tbl}")

        # Delete product_targets junction records
        res = session.execute(text("DELETE FROM product_targets WHERE product_id IN (SELECT id FROM products WHERE sid = 1)"))
        print(f"  -> Deleted {res.rowcount} rows from product_targets")

        # Delete price_history records
        res = session.execute(text("DELETE FROM price_history WHERE product_id IN (SELECT id FROM products WHERE sid = 1)"))
        print(f"  -> Deleted {res.rowcount} rows from price_history")

        # Delete products
        res = session.execute(text("DELETE FROM products WHERE sid = 1"))
        print(f"  -> Deleted {res.rowcount} rows from products")

        # Reset scrape_targets execution timestamps for MDComputers (store_id=1)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        res = session.execute(
            text("UPDATE scrape_targets SET next_scrape_at = :now, last_scraped_at = NULL WHERE store_id = 1"),
            {"now": now}
        )
        print(f"  -> Reset {res.rowcount} Category Catalog targets for MDComputers to run immediately.")

        session.commit()
        print("Successfully cleared MDComputers data and reset category catalog scraper targets.")


if __name__ == "__main__":
    clear_mdcomputers_data()
