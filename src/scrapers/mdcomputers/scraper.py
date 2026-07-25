from urllib.parse import quote_plus

from domain.store import Store
from scrapers.base_scraper import BaseScraper
from scrapers.mdcomputers.parser import MDComputersParser


class MDComputersScraper(BaseScraper):

    def __init__(self, client, store: Store):
        super().__init__(client)

        self.store = store
        self.parser = MDComputersParser(store)

    def scrape_search(self, query: str):

        url = (
            f"{self.store.base_url}"
            f"/catalogsearch/result/?q={quote_plus(query)}"
        )

        response = self.client.get(url)

        return self.parser.parse_search(response.text)

    def scrape_product(self, path: str):

        url = f"{self.store.base_url}/{path.lstrip('/')}"

        response = self.client.get(url)

        return self.parser.parse_product(response.text)