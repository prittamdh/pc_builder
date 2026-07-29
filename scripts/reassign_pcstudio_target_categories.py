"""
Script to assign category = 'CPU Cooler' for all products found directly inside
PCStudio's cpu-cooler catalog target URL.
"""
from sqlalchemy import select
from db.session import SessionLocal
from db.models.store import Store
from db.models.product import Product
from scrapers.http_client import HttpClient
from scrapers.generic_scraper import GenericScraper


def reassign_pcstudio_coolers():
    with SessionLocal() as session:
        store = session.scalar(select(Store).where(Store.name == "pcstudio"))
        if not store:
            print("[Error] Store PCStudio not found.")
            return

        with HttpClient() as client:
            scraper = GenericScraper(client, store)
            results = scraper.scrape_category_all_pages("product-category/cpu-cooler/?products-per-page=all")
            print(f"Scraped {len(results)} products directly from PCStudio cpu-cooler catalog URL.")

            scraped_pids = {r.pid for r in results}

            # Update category in DB
            db_products = session.scalars(select(Product).where(Product.sid == store.id)).all()
            reassigned = 0

            for p in db_products:
                if p.pid in scraped_pids and p.category != "CPU Cooler":
                    print(f"  Reassigning PID '{p.pid[:40]}' from '{p.category}' -> 'CPU Cooler' (Name: {p.name[:50]})")
                    p.category = "CPU Cooler"
                    reassigned += 1

            session.commit()
            print("=" * 80)
            print(f"REASSIGNMENT COMPLETE: Updated {reassigned} products to 'CPU Cooler'.")


if __name__ == "__main__":
    reassign_pcstudio_coolers()
