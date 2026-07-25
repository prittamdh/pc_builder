from abc import ABC, abstractmethod

from scrapers.http_client import HttpClient


class BaseScraper(ABC):

    def __init__(self, client: HttpClient):
        self.client = client

    @abstractmethod
    def scrape_search(self, query: str):
        """Scrape search results for a query."""
        raise NotImplementedError

    @abstractmethod
    def scrape_product(self, url: str):
        """Scrape a product page."""
        raise NotImplementedError