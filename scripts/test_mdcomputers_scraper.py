from db.session import SessionLocal
from services.store_service import StoreService
from scrapers.http_client import HttpClient
from scrapers.generic_scraper import GenericScraper


def main():
    with SessionLocal() as session:

        store_service = StoreService(session)

        store = store_service.get_by_name("mdcomputers")

        if store is None:
            raise Exception("Store not found")

        with HttpClient() as client:

            scraper = GenericScraper(client, store)

            results = scraper.scrape_search("rtx 5070")

        print(f"\nFound {len(results)} products\n")

        for product in results[:10]:
            print("-" * 80)
            print(f"Name : {product.name}")
            print(f"Price: {product.price}")
            print(f"MRP  : {product.mrp}")
            print(f"URL  : {product.url}")
            print(f"Image: {product.image}")


if __name__ == "__main__":
    main()