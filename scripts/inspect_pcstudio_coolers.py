"""
Script to inspect PCStudio products present in the cpu-cooler catalog URL
and compare their PIDs and categories in PostgreSQL.
"""
from scrapers.http_client import HttpClient
from scrapers.generic_scraper import GenericScraper
from db.session import SessionLocal
from db.models.store import Store
from db.models.product import Product
from sqlalchemy import select


def inspect_coolers():
    with SessionLocal() as session:
        store = session.scalar(select(Store).where(Store.name == "pcstudio"))
        if not store:
            print("[Error] Store PCStudio not found.")
            return

        with HttpClient() as client:
            scraper = GenericScraper(client, store)
            results = scraper.scrape_category_all_pages("product-category/cpu-cooler/?products-per-page=all")
            print(f"Scraped {len(results)} items from cpu-cooler catalog URL.")

            scraped_pids = {r.pid: r for r in results}

            # Fetch existing products for PCStudio
            db_products = session.scalars(select(Product).where(Product.sid == store.id)).all()
            db_map = {p.pid: p for p in db_products}

            print("\n" + "=" * 80)
            print("MATCHING PRODUCTS FOUND IN CPU-COOLER CATALOG URL:")
            print("=" * 80)

            matched_in_db = 0
            cat_counts = {}

            for pid, res in scraped_pids.items():
                if pid in db_map:
                    db_p = db_map[pid]
                    matched_in_db += 1
                    cat_counts[db_p.category] = cat_counts.get(db_p.category, 0) + 1
                    print(f"  PID: {pid[:45]:<45} | DB Category: {db_p.category:<12} | Name: {db_p.name[:50]}")
                else:
                    print(f"  PID: {pid[:45]:<45} | DB Category: [NOT IN DB]   | Name: {res.name[:50]}")

            print("\n" + "=" * 80)
            print(f"TOTAL CPU-COOLER ITEMS MATCHED IN DB: {matched_in_db}/{len(scraped_pids)}")
            print("DB CATEGORY BREAKDOWN FOR THESE COOLER PIDs:", cat_counts)
            print("=" * 80)


if __name__ == "__main__":
    inspect_coolers()
