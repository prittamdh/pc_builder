"""
Base class for all scrapers.
"""

from abc import ABC, abstractmethod

from scrapers.http_client import Downloader


class BaseScraper(ABC):
    """Abstract base class for all e-commerce scrapers."""

    def __init__(self) -> None:
        self.downloader = Downloader()

    @abstractmethod
    def search(self, query: str) -> list:
        """
        Search for products.

        Args:
            query: Search keyword.

        Returns:
            List of search results.
        """
        raise NotImplementedError

    @abstractmethod
    def scrape_product(self, url: str):
        """
        Scrape a product page.

        Args:
            url: Product URL.

        Returns:
            Product details.
        """
        raise NotImplementedError

    def close(self) -> None:
        self.downloader.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()