from datetime import datetime

from db.session import SessionLocal
from scrapers.generic_scraper import GenericScraper
from scrapers.http_client import HttpClient
from services.scrape_target_service import ScrapeTargetService
from services.search_service import SearchService
from services.store_service import StoreService


def main():
    with SessionLocal() as session:
        target_service = ScrapeTargetService(session)
        store_service = StoreService(session)
        search_service = SearchService(session)

        due_targets = target_service.get_due_targets(limit=5)
        print(f"Found {len(due_targets)} due targets to process.\n")

        with HttpClient() as client:
            for target in due_targets:
                store = store_service.get(target.store_id)
                if not store or not store.active:
                    continue

                print("=" * 80)
                print(f"Store: {store.display_name} | Target: '{target.target_value}' (Max 2 Pages)")
                print("=" * 80)

                try:
                    scraper = GenericScraper(client, store)
                    results = scraper.scrape_search_all_pages(
                        query=target.target_value,
                        max_pages=2,
                    )

                    print(f"Total Unique Items Found Across Pages: {len(results)}")
                    if results:
                        search_service.save_many(results)
                        print(f"Saved {len(results)} items & price snapshots.")
                        print(f"Sample item: {results[0].name} - Price: {results[0].price}")

                    # Update last_scraped_at
                    target.last_scraped_at = datetime.utcnow()
                    session.commit()

                except Exception as e:
                    print(f"Error scraping target '{target.target_value}': {e}")

                print()


if __name__ == "__main__":
    main()
