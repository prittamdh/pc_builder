from urllib.parse import quote_plus

from domain.store import Store
from scrapers.base_scraper import BaseScraper
from scrapers.generic_parser import GenericParser


class GenericScraper(BaseScraper):

    def __init__(self, client, store: Store):
        super().__init__(client)

        self.store = store
        self.parser = GenericParser(store)

    def scrape_search(self, query: str):

        url = self.store.search_endpoint.format(
            query=quote_plus(query)
        )

        response = self.client.get(url)

        return self.parser.parse_search(response.text)

    def scrape_product(self, path: str):

        url = path

        if not path.startswith("http"):
            url = f"{self.store.base_url}/{path.lstrip('/')}"

        response = self.client.get(url)

        return self.parser.parse_product(response.text)