"""
CLI script to batch enrich static metadata (brand, category, description, specifications)
for products missing detailed product page attributes.
"""
from db.connection import engine
from db.session import SessionLocal
from scrapers.generic_scraper import GenericScraper
from scrapers.http_client import HttpClient
from services.product_service import ProductService
from services.store_service import StoreService


def main(limit: int = 20):
    with SessionLocal() as session:
        product_service = ProductService(session)
        store_service = StoreService(session)

        unscraped = product_service.get_unscraped_products(limit=limit)
        print(f"[Enrichment Script] Found {len(unscraped)} unscraped products to enrich.")

        if not unscraped:
            print("[Enrichment Script] All products already contain static metadata.")
            return

        enriched_count = 0
        with HttpClient() as client:
            for db_product in unscraped:
                store = store_service.get(db_product.sid)
                if not store or not store.active:
                    continue

                print(f"[Enrichment Script] Scraping product page: {db_product.name}")
                try:
                    scraper = GenericScraper(client, store)
                    p_details = scraper.scrape_product(db_product.product_url)
                    if p_details:
                        product_service.save(p_details)
                        enriched_count += 1
                        print(f"  -> Enriched: brand='{p_details.brand}', specs={len(p_details.specifications or {})}")
                except Exception as e:
                    print(f"  -> Error enriching '{db_product.name}': {e}")

        print(f"[Enrichment Script] Completed enriching {enriched_count} / {len(unscraped)} products.")


if __name__ == "__main__":
    main()
