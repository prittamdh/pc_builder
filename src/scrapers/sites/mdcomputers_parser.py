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

        cards = soup.select("div.product-grid-item")

        results: list[SearchResult] = []

        for card in cards:
            title = card.select_one("h3.product-entities-title a")

            name = title.get_text(strip=True)
            url = title["href"]

            image = card.select_one("img")["src"]

            price = self._parse_price(
                card.select_one("span.ins").get_text(strip=True)
            )

            mrp_element = card.select_one("span.del")
            mrp = (
                self._parse_price(mrp_element.get_text(strip=True))
                if mrp_element
                else None
            )

            results.append(
                SearchResult(
                    seller="MDComputers",
                    name=name,
                    url=url,
                    price=price,
                    mrp=mrp,
                    image=image,
                )
            )

        return results

    def parse_product(self, html: str):
        raise NotImplementedError