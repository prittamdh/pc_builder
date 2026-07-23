"""
MDComputers scraper.
"""

from urllib.parse import quote_plus

from configs.config import Config
from models.base import BaseScraper


class MDComputersScraper(BaseScraper):

    def __init__(self):
        super().__init__()

        self.config = Config.site("mdcomputers")

        self.base_url = self.config["base_url"]

        self.search_url = self.config["search_url"]

        self.name = self.config["name"]

    def search(self, query: str):

        url = (
            self.base_url
            + self.search_url.format(
                query=quote_plus(query)
            )
        )

        response = self.downloader.get(url)

        return response.text

    def scrape_product(self, url: str):
        raise NotImplementedError