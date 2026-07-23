from abc import ABC, abstractmethod

from scrapers.http_client import HttpClient


class BaseScraper(ABC):

    def __init__(self, client: HttpClient):
        self.client = client

    @abstractmethod
    def scrape_search(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def scrape_product(self, *args, **kwargs):
        raise NotImplementedError