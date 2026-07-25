from db.session import SessionLocal
from services.store_service import StoreService
from scrapers.http_client import HttpClient
from scrapers.generic_scraper import GenericScraper


def test_mdcomputers_search():
    with SessionLocal() as session:
        store = StoreService(session).get_by_name("mdcomputers")

        with HttpClient() as client:
            scraper = GenericScraper(client, store)

            results = scraper.scrape_search("rtx 5070")

            assert len(results) > 0
            assert results[0].name
            assert results[0].price > 0


def test_mdcomputers_product():
    with SessionLocal() as session:
        store = StoreService(session).get_by_name("mdcomputers")

        with HttpClient() as client:
            scraper = GenericScraper(client, store)

            results = scraper.scrape_search("rtx 5070")
            product = scraper.scrape_product(str(results[0].url))

            assert product.name
            assert product.price > 0
            assert product.brand is not None
            assert product.url is not None