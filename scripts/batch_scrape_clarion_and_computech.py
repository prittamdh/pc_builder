"""
Full batch scraper and normalizer script for Clarion Computers (sid=7) and Computech Store (sid=8).
Executes:
1. Multi-page category catalog extraction using GenericScraper.
2. Ingests ONLY 100% IN-STOCK products and price history into PostgreSQL with granular category names.
3. Runs component spec normalization across all categories.
"""
import time
from sqlalchemy import select

from db.session import SessionLocal
from db.models.store import Store
from db.models.scrape_target import ScrapeTarget
from scrapers.http_client import HttpClient
from scrapers.generic_scraper import GenericScraper
from services.search_service import SearchService
from services.scrape_target_service import ScrapeTargetService
from services.normalization_service import NormalizationService


def run_batch_pipeline_for_stores():
    print("=" * 80)
    print("STARTING BATCH SCRAPING PIPELINE FOR CLARION COMPUTERS & COMPUTECH STORE")
    print("=" * 80)

    start_time = time.time()

    with SessionLocal() as session:
        stores = session.scalars(select(Store).where(Store.name.in_(["clarion", "computechstore"]))).all()
        search_service = SearchService(session)
        target_service = ScrapeTargetService(session)

        with HttpClient() as client:
            for store in stores:
                targets = list(session.scalars(select(ScrapeTarget).where(ScrapeTarget.store_id == store.id)).all())
                print(f"\nScraping {len(targets)} Category Catalog targets for '{store.display_name}' (sid={store.id})...")

                scraper = GenericScraper(client, store)
                store_scraped = 0

                for idx, target in enumerate(targets, 1):
                    endpoint = target.target_value
                    hard_category = target.schedule_config.get("category") if isinstance(target.schedule_config, dict) else None

                    print(f"  [{idx}/{len(targets)}] Scraping '{endpoint}' -> Granular Category: '{hard_category}'...")

                    try:
                        results = scraper.scrape_category_all_pages(endpoint, max_pages=15)
                        instock_results = [r for r in results if r.in_stock]

                        if instock_results:
                            search_service.save_many(instock_results, target_id=target.id, hard_category=hard_category)
                            store_scraped += len(instock_results)
                            print(f"    -> Saved {len(instock_results)} IN-STOCK products for '{hard_category}'.")
                        else:
                            print(f"    -> 0 in-stock products found for '{endpoint}'.")

                        target_service.mark_scraped(target)
                    except Exception as e:
                        session.rollback()
                        print(f"    -> [Error] Failed scraping '{endpoint}': {e}")

                print(f"Total In-Stock Products Saved for '{store.display_name}': {store_scraped}")

    print("\n" + "=" * 80)
    print("STARTING COMPONENT SPECIFICATION NORMALIZATION")
    print("=" * 80)

    with SessionLocal() as session:
        norm_service = NormalizationService(session)
        norm_count = norm_service.normalize_all_unclassified(limit=10000)
        print(f"  -> Normalized specs for {norm_count} total database items.")

    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"CLARION & COMPUTECH PIPELINE FINISHED IN {elapsed:.1f} SECONDS!")
    print("=" * 80)


if __name__ == "__main__":
    run_batch_pipeline_for_stores()
