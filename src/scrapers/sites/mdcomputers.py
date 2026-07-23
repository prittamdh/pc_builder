from scrapers.base_scraper import BaseScraper
from scrapers.sites.mdcomputers_parser import MDComputersParser


class MDComputersScraper(BaseScraper):

    BASE_URL = "https://mdcomputers.in"

    def __init__(self, client):
        super().__init__(client)
        self.parser = MDComputersParser()

    def scrape_search(self, path: str):

        response = self.client.get(
            f"{self.BASE_URL}/catalog/{path}"
        )

        # Temporary: save the raw HTML
        with open("mdcomputers.html", "w", encoding="utf-8") as f:
            f.write(response.text)

        return self.parser.parse_search(response.text)

    def scrape_product(self, path: str):
        response = self.client.get(
            f"{self.BASE_URL}/{path}"
        )

        return self.parser.parse_product(response.text)