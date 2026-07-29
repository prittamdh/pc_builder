"""
Full batch scraper and normalizer script for EliteHubs (Shopify Store).
Executes:
1. Scrapes all 17 category catalog collection endpoints via Shopify products.json API.
2. Ingests products, price history, and target links into PostgreSQL with 100% granular categories.
3. Normalizes component specs into dedicated category spec tables.
"""
import time
from sqlalchemy import select

from db.session import SessionLocal
from db.models.store import Store
from db.models.scrape_target import ScrapeTarget
from domain.search_result import SearchResult
from scrapers.http_client import HttpClient
from scrapers.generic_scraper import GenericScraper
from services.search_service import SearchService
from services.scrape_target_service import ScrapeTargetService
from services.normalization_service import NormalizationService


def scrape_shopify_collection(client: HttpClient, store: Store, endpoint: str) -> list[SearchResult]:
    url = f"https://elitehubs.com/{endpoint}/products.json?limit=250"
    response = client.get(url)
    if response.status_code != 200:
        return []

    data = response.json()
    products_json = data.get("products", [])
    results = []

    for p in products_json:
        title = p.get("title", "").strip()
        handle = p.get("handle", "").strip()
        if not title or not handle:
            continue

        variants = p.get("variants", [])
        if not variants:
            continue

        variant = variants[0]
        price = variant.get("price")
        if price is None:
            continue

        mrp = variant.get("compare_at_price") or price
        in_stock = any(v.get("available", False) for v in variants)

        images = p.get("images", [])
        image_url = images[0].get("src") if images else None

        prod_url = f"https://elitehubs.com/products/{handle}"

        sr = SearchResult(
            store=store.name,
            sid=store.id,
            pid=handle,
            name=title,
            url=prod_url,
            image=image_url,
            currency="INR",
            price=float(price),
            mrp=float(mrp),
            in_stock=in_stock,
        )
        results.append(sr)

    return results


def run_full_elitehubs_pipeline():
    print("=" * 80)
    print("STARTING FULL ELITEHUBS CATEGORY CATALOG SCRAPING PIPELINE")
    print("=" * 80)

    start_time = time.time()

    with SessionLocal() as session:
        store = session.scalar(select(Store).where(Store.name == "elitehubs"))
        if not store:
            print("[Error] Store EliteHubs not found.")
            return

        targets = list(session.scalars(select(ScrapeTarget).where(ScrapeTarget.store_id == store.id)).all())
        print(f"Found {len(targets)} Category Catalog targets for EliteHubs.")

        search_service = SearchService(session)
        target_service = ScrapeTargetService(session)

        total_scraped_products = 0

        with HttpClient() as client:
            scraper = GenericScraper(client, store)

            for idx, target in enumerate(targets, 1):
                endpoint = target.target_value
                hard_category = target.schedule_config.get("category") if isinstance(target.schedule_config, dict) else None

                print(f"\n[{idx}/{len(targets)}] Scraping Category: '{endpoint}' (Granular Category: '{hard_category}')...")

                try:
                    results = scraper.scrape_category_all_pages(endpoint, max_pages=15)
                    if results:
                        search_service.save_many(results, target_id=target.id, hard_category=hard_category)
                        total_scraped_products += len(results)
                        print(f"  -> Saved {len(results)} products for '{hard_category}'.")
                    else:
                        print(f"  -> 0 products found for '{endpoint}'.")

                    target_service.mark_scraped(target)
                except Exception as e:
                    session.rollback()
                    print(f"  -> [Error] Failed scraping '{endpoint}': {e}")

    print("\n" + "=" * 80)
    print(f"PHASE 1 COMPLETE: Scraped & Saved {total_scraped_products} total products for EliteHubs.")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # PHASE 2: COMPONENT SPEC NORMALIZATION
    # -------------------------------------------------------------------------
    print("\nSTARTING PHASE 2: Component Specification Normalization...")
    with SessionLocal() as session:
        norm_service = NormalizationService(session)
        normalized_count = norm_service.normalize_all_unclassified(limit=8000)
        print(f"  -> Normalized and populated category specs for {normalized_count} total database products.")

    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"ELITEHUBS FULL PIPELINE FINISHED IN {elapsed:.1f} SECONDS!")
    print("=" * 80)


if __name__ == "__main__":
    run_full_elitehubs_pipeline()
