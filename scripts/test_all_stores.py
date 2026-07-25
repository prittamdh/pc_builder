from db.session import SessionLocal
from services.store_service import StoreService
from services.search_service import SearchService
from scrapers.http_client import HttpClient
from scrapers.generic_scraper import GenericScraper


def main():
    with SessionLocal() as session:
        stores = StoreService(session).get_all()
        search_service = SearchService(session)

        with HttpClient() as client:
            for store in stores:
                print("=" * 80)
                print(store.display_name)

                try:
                    scraper = GenericScraper(client, store)

                    results = scraper.scrape_search("rtx 5070")

                    print(f"Products found : {len(results)}")

                    search_service.save_many(results)

                    print(f"Saved {len(results)} products.")

                    if results:
                        print(f"First product : {results[0].name}")
                        print(f"Price         : {results[0].price}")

                except Exception as e:
                    print(f"FAILED : {e}")

                print()


if __name__ == "__main__":
    main()