"""
Full batch scraper and normalizer script for MDComputers 16 Category Catalog targets.
Executes:
1. Scrapes all 16 category catalog endpoints up to 15 pages each.
2. Ingests products, price history, and keyword targets into PostgreSQL with hard category classification.
3. Enriches static product page details (description, specifications).
4. Normalizes component specs into 9 dedicated category spec tables.
"""
import time
from datetime import datetime, timezone
from sqlalchemy import select

from db.session import SessionLocal
from db.models.store import Store
from db.models.scrape_target import ScrapeTarget
from scrapers.http_client import HttpClient
from scrapers.generic_scraper import GenericScraper
from services.search_service import SearchService
from services.scrape_target_service import ScrapeTargetService
from services.product_service import ProductService
from services.normalization_service import NormalizationService


def run_full_mdcomputers_pipeline():
    print("=" * 80)
    print("STARTING FULL MDCOMPUTERS CATEGORY CATALOG SCRAPING PIPELINE")
    print("=" * 80)

    start_time = time.time()

    with SessionLocal() as session:
        store_service = Store(name="mdcomputers")
        store = session.scalar(select(Store).where(Store.name == "mdcomputers"))

        if not store:
            print("[Error] Store MDComputers not found.")
            return

        targets = list(session.scalars(select(ScrapeTarget).where(ScrapeTarget.store_id == store.id)).all())
        print(f"Found {len(targets)} Category Catalog targets for MDComputers.")

        search_service = SearchService(session)
        target_service = ScrapeTargetService(session)

        total_scraped_products = 0

        with HttpClient() as client:
            scraper = GenericScraper(client, store)

            for idx, target in enumerate(targets, 1):
                endpoint = target.target_value
                max_pages = target.schedule_config.get("max_pages", 15) if isinstance(target.schedule_config, dict) else 15
                hard_category = target.schedule_config.get("category") if isinstance(target.schedule_config, dict) else None

                print(f"\n[{idx}/{len(targets)}] Scraping Category: '{endpoint}' (Category: {hard_category}, Max Pages: {max_pages})...")

                try:
                    results = scraper.scrape_category_all_pages(endpoint=endpoint, max_pages=max_pages)
                    if results:
                        search_service.save_many(results, target_id=target.id, hard_category=hard_category)
                        total_scraped_products += len(results)
                        print(f"  -> Saved {len(results)} products for category '{hard_category}'.")
                    else:
                        print(f"  -> 0 products found for '{endpoint}'.")

                    target_service.mark_scraped(target)
                except Exception as e:
                    session.rollback()
                    print(f"  -> [Error] Failed scraping '{endpoint}': {e}")

    print("\n" + "=" * 80)
    print(f"PHASE 1 COMPLETE: Scraped & Saved {total_scraped_products} total products for MDComputers.")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # PHASE 2: STATIC METADATA ENRICHMENT
    # -------------------------------------------------------------------------
    print("\nSTARTING PHASE 2: Product Page Static Metadata Enrichment...")
    with SessionLocal() as session:
        product_service = ProductService(session)
        store = session.scalar(select(Store).where(Store.name == "mdcomputers"))

        unscraped = product_service.get_unscraped_products(limit=500)
        print(f"Found {len(unscraped)} MDComputers products needing page detail enrichment.")

        enriched_count = 0
        if unscraped:
            with HttpClient() as client:
                scraper = GenericScraper(client, store)
                for prod in unscraped:
                    try:
                        p_details = scraper.scrape_product(prod.product_url)
                        if p_details:
                            product_service.repository.update(
                                prod,
                                brand=p_details.brand or prod.brand,
                                description=p_details.description or prod.description,
                                specifications=p_details.specifications or prod.specifications,
                            )
                            enriched_count += 1
                    except Exception as e:
                        pass

                session.commit()

        print(f"  -> Enriched static details for {enriched_count} products.")

    # -------------------------------------------------------------------------
    # PHASE 3: COMPONENT SPEC NORMALIZATION
    # -------------------------------------------------------------------------
    print("\nSTARTING PHASE 3: Component Specification Normalization...")
    with SessionLocal() as session:
        norm_service = NormalizationService(session)
        normalized_count = norm_service.normalize_all_unclassified(limit=2000)
        print(f"  -> Normalized and populated category specs for {normalized_count} products.")

    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"MDCOMPUTERS FULL PIPELINE FINISHED IN {elapsed:.1f} SECONDS!")
    print("=" * 80)


if __name__ == "__main__":
    run_full_mdcomputers_pipeline()
