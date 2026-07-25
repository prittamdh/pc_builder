from db.session import SessionLocal
from services.store_service import StoreService
from scrapers.http_client import HttpClient
from scrapers.generic_scraper import GenericScraper


def main():
    with SessionLocal() as session:
        store = StoreService(session).get_by_name("mdcomputers")

        with HttpClient() as client:
            scraper = GenericScraper(client, store)

            results = scraper.scrape_search("rtx 5070")

            if not results:
                print("No products found.")
                return

            print(f"Found {len(results)} products\n")

            product_url = str(results[0].url)
            print(f"Scraping: {product_url}\n")

            product = scraper.scrape_product(product_url)

            print("=" * 80)
            print(product.model_dump())
            print("=" * 80)


if __name__ == "__main__":
    main()