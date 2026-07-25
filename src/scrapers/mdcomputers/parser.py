from decimal import Decimal

from bs4 import BeautifulSoup

from domain.search_result import SearchResult
from scrapers.base_parser import BaseParser


class MDComputersParser(BaseParser):

    @staticmethod
    def _parse_price(text: str) -> Decimal:
        return Decimal(
            text.replace("₹", "")
            .replace(",", "")
            .strip()
        )

    def parse_search(self, html: str) -> list[SearchResult]:
        soup = BeautifulSoup(html, "lxml")

        cfg = self.search_config

        cards = soup.select(cfg["product_card"])

        results = []

        for card in cards:

            title = card.select_one(cfg["title"])

            if title is None:
                continue

            name = title.get_text(strip=True)

            url = title.get(cfg["url_attribute"])

            image_element = card.select_one(cfg["image"])
            image = (
                image_element.get(cfg["image_attribute"])
                if image_element
                else None
            )

            price = self._parse_price(
                card.select_one(cfg["price"]).get_text(strip=True)
            )

            mrp_element = card.select_one(cfg["mrp"])

            mrp = (
                self._parse_price(mrp_element.get_text(strip=True))
                if mrp_element
                else None
            )

            results.append(
                SearchResult(
                    seller=self.store.display_name,
                    name=name,
                    url=url,
                    image=image,
                    price=price,
                    mrp=mrp,
                )
            )

        return results

    def parse_product(self, html: str):
        raise NotImplementedError