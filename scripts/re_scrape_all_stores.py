"""
Master Re-Scraping Script across all 10 Retailer Stores.
Re-scrapes all catalog endpoints and updates products.category with the exact raw category
assigned to each catalog target, without string pattern normalization.
"""
import time
from db.session import SessionLocal
from db.models.store import Store
from db.models.scrape_target import ScrapeTarget
from sqlalchemy import select
from scrapers.http_client import HttpClient
from scrapers.generic_scraper import GenericScraper
from services.search_service import SearchService


def run_master_rescrape():
    print("=" * 80)
    print("STARTING MASTER RE-SCRAPING PIPELINE ACROSS ALL 10 STORES")
    print("=" * 80)
    start_time = time.time()

    with SessionLocal() as session:
        stores = list(session.scalars(select(Store).where(Store.active == True)).all())
        search_service = SearchService(session)

        with HttpClient() as client:
            for store in stores:
                targets = list(session.scalars(select(ScrapeTarget).where(ScrapeTarget.store_id == store.id)).all())
                if not targets:
                    continue

                print(f"\nRe-Scraping {len(targets)} catalog targets for '{store.display_name}' (sid={store.id})...")
                scraper = GenericScraper(client, store)

                for idx, target in enumerate(targets, 1):
                    endpoint = target.target_value
                    max_pages = 15
                    hard_category = None

                    if isinstance(target.schedule_config, dict):
                        max_pages = target.schedule_config.get("max_pages", 15)
                        hard_category = target.schedule_config.get("category")

                    try:
                        results = scraper.scrape_category_all_pages(endpoint=endpoint, max_pages=max_pages)
                        if results:
                            search_service.save_many(results, target_id=target.id, hard_category=hard_category)
                            print(f"  [{idx}/{len(targets)}] '{endpoint}' -> Saved {len(results)} products (Category: {hard_category})")
                    except Exception as e:
                        print(f"  [{idx}/{len(targets)}] Error scraping '{endpoint}': {e}")

                session.commit()

    elapsed = time.time() - start_time
    print("=" * 80)
    print(f"MASTER RE-SCRAPE FINISHED IN {elapsed:.1f} SECONDS!")
    print("=" * 80)


if __name__ == "__main__":
    run_master_rescrape()
