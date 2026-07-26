import json
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from domain.product import Product
from domain.search_result import SearchResult
from domain.store import Store


class GenericParser:
    def __init__(self, store: Store):
        self.store = store

        self.selectors = store.search_config["selectors"]
        self.attributes = store.search_config["attributes"]

    @staticmethod
    def _clean_price(text: str) -> Decimal:
        cleaned = (
            str(text)
            .replace("₹", "")
            .replace(",", "")
            .strip()
        )

        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return Decimal("0")

    def parse_search(self, html: str):
        soup = BeautifulSoup(html, "lxml")

        results = []

        for card in soup.select(self.selectors["product_card"]):

            title = card.select_one(self.selectors["title"])
            prices = card.select(self.selectors["price"])
            price = prices[-1] if prices else None
            mrp = card.select_one(self.selectors["mrp"])
            image = card.select_one(self.selectors["image"])

            if title is None or price is None:
                continue

            product_url = urljoin(
                self.store.base_url,
                title.get(self.attributes["url"], "")
            )

            image_url = None

            if image:
                image_url = urljoin(
                    self.store.base_url,
                    image.get(self.attributes["image"], "")
                )

            pid = (
                card.get("data-product-id")
                or product_url.split("?")[0].rstrip("/").split("/")[-1]
            )

            results.append(
                SearchResult(
                    store=self.store.name,
                    sid=self.store.id,
                    pid=pid,
                    name=title.get_text(strip=True),
                    url=product_url,
                    price=self._clean_price(price.get_text()),
                    mrp=(
                        self._clean_price(mrp.get_text())
                        if mrp
                        else None
                    ),
                    image=image_url,
                    currency=self.store.currency,
                )
            )

        return results

    def _find_product_json_ld(self, soup: BeautifulSoup):
        scripts = soup.find_all(
            "script",
            attrs={"type": "application/ld+json"},
        )

        for script in scripts:
            if not script.string:
                continue

            try:
                data = json.loads(script.string)
            except Exception:
                continue

            items = data if isinstance(data, list) else [data]

            for item in items:
                if (
                    isinstance(item, dict)
                    and item.get("@type") == "Product"
                ):
                    return item

        return None

    def parse_product(self, html: str) -> Product:
        soup = BeautifulSoup(html, "lxml")

        data = self._find_product_json_ld(soup)

        if data is None:
            raise ValueError("No Product JSON-LD found.")

        offers = data.get("offers", {})

        # ---------- URL ----------
        url = data.get("url")

        if not url:
            canonical = soup.find("link", rel="canonical")
            if canonical:
                url = canonical.get("href")

        if not url:
            og = soup.find(
                "meta",
                attrs={"property": "og:url"},
            )
            if og:
                url = og.get("content")

        if url:
            url = urljoin(self.store.base_url, url)
        else:
            url = self.store.base_url

        # ---------- Brand ----------
        brand = data.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")

        # ---------- Image ----------
        image = data.get("image")

        if isinstance(image, list):
            image = image[0] if image else None

        if image:
            image = urljoin(self.store.base_url, image)

        # ---------- Stock ----------
        availability = (
            offers.get("availability", "")
            .lower()
        )

        in_stock = "instock" in availability

        # ---------- Specs ----------
        specifications = {}

        for key in (
            "model",
            "mpn",
            "gtin",
            "gtin8",
            "gtin12",
            "gtin13",
            "gtin14",
        ):
            value = data.get(key)

            if value:
                specifications[key] = value

        pid = (
            data.get("sku")
            or (url.split("?")[0].rstrip("/").split("/")[-1] if url else data.get("name", ""))
        )

        return Product(
            store=self.store.name,
            sid=self.store.id,
            pid=str(pid),
            name=data.get("name", ""),
            url=url,
            price=self._clean_price(
                offers.get("price", "0")
            ),
            mrp=None,
            image=image,
            currency=offers.get(
                "priceCurrency",
                self.store.currency,
            ),
            in_stock=in_stock,
            brand=brand,
            description=data.get("description"),
            specifications=specifications,
        )