import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from domain.product import Product
from domain.search_result import SearchResult
from domain.store import Store


class GenericParser:
    def __init__(self, store: Store):
        self.store = store
        self.selectors = store.search_config.get("selectors", {}) if isinstance(store.search_config, dict) else {}
        self.attributes = store.search_config.get("attributes", {}) if isinstance(store.search_config, dict) else {}

    # First money-looking amount in a string: optional thousands separators, optional
    # decimals. Anchored on a digit so any currency prefix is skipped.
    _AMOUNT_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

    @staticmethod
    def _full_title(element) -> str:
        """The complete product name, preferring an attribute over elided text.

        Themes that clamp long names render the visible text cut short - PCStudio ships
        "TEAMGROUP T-FORCE DELTA RGB DDR5 6,000 M..." in the markup while carrying the
        whole name in a nested `<span title="...">`. Taking the visible text stored a
        truncated name for 1,793 products (15% of the catalog), which broke search,
        fed incomplete text to spec extraction - a DDR5-6000 CL30 kit came back as
        "CL3" because that is where the title stopped - and corrupted canonical keys
        built from the name.

        The attribute is only trusted when the visible text is actually elided and the
        attribute agrees with what is visible, so a theme using `title` for something
        unrelated (a tooltip, a category) can't overwrite a good name.
        """
        text = element.get_text(strip=True)
        if not text.rstrip().endswith(("...", "…")):
            return text

        stem = text.rstrip().rstrip(".…").strip()
        if not stem:
            return text

        candidates = []
        for node in [element, *element.find_all(True)]:
            for attribute in ("title", "aria-label", "alt"):
                value = (node.get(attribute) or "").strip()
                if len(value) > len(text) and value.startswith(stem[: min(len(stem), 20)]):
                    candidates.append(value)

        return max(candidates, key=len) if candidates else text

    def _image_near(self, link, card):
        """Image belonging to `link`'s product, searched outward from the link.

        Computech puts the thumbnail one level above the element this parser treats as
        the card, so `card.find("img")` returned nothing and 2,041 of that store's
        2,042 products were stored with no image at all.

        The walk stops as soon as an ancestor contains a second product link, because
        past that point the nearest image belongs to a *neighbouring* product. That is
        the same failure that once read an 80+ Gold rating off an adjacent listing's
        carousel, so the bound is the important part of this method, not the search.
        """
        node = card
        for _ in range(4):
            if node is None:
                break
            links = [
                other for other in node.find_all("a", href=True)
                if "/product/" in other["href"]
                and other.get_text(strip=True)
                and other.get_text(strip=True) != "View Product"
            ]
            if len(links) > 1 and links != [link]:
                break

            img = node.find("img")
            if img is not None:
                src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                if src and not src.startswith("data:"):
                    return urljoin(self.store.base_url, src)
            node = node.parent
        return None

    @staticmethod
    def _clean_price(text: str) -> Decimal:
        """First amount in `text`, or 0 if there isn't one.

        Stores write prices as "₹31,999", "Rs.31,999.00", "INR 31999" and often put
        more than one number in the element - TLG Gaming's `.price` container reads
        "Rs.31,999.00Ex Tax:Rs.27,117.80". Decimal() on any of those raises, and the
        previous version answered 0 for all of them, which is why all 163 of that
        store's products were priced zero.

        Taking the FIRST amount is deliberate: the displayed selling price leads, with
        tax-exclusive or struck-through figures following it.
        """
        match = GenericParser._AMOUNT_RE.search(str(text))
        if not match:
            return Decimal("0")

        try:
            return Decimal(match.group(0).replace(",", ""))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    def _parse_shopify_json(self, content: str) -> list[SearchResult]:
        try:
            data = json.loads(content)
        except Exception:
            return []

        products_json = data.get("products", [])
        results = []

        for p in products_json:
            title = p.get("title", "").strip()
            handle = p.get("handle", "").strip()
            variants = p.get("variants", [])
            if not title or not handle or not variants:
                continue

            variant = variants[0]
            price = variant.get("price")
            if price is None:
                continue

            mrp = variant.get("compare_at_price") or price
            in_stock = any(v.get("available", False) for v in variants)
            images = p.get("images", [])
            image_url = images[0].get("src") if images else None
            prod_url = f"{self.store.base_url.rstrip('/')}/products/{handle}"

            sr = SearchResult(
                store=self.store.name,
                sid=self.store.id,
                pid=handle,
                name=title,
                url=prod_url,
                image=image_url,
                currency=self.store.currency or "INR",
                price=float(price),
                mrp=float(mrp),
                in_stock=in_stock,
            )
            results.append(sr)

        return results

    def _parse_fleetcart_json(self, content: str) -> list[SearchResult]:
        try:
            data = json.loads(content)
        except Exception:
            return []

        products_json = data.get("products", {}).get("data", [])
        results = []

        for p in products_json:
            name = p.get("name", "").strip()
            slug = p.get("slug", "").strip()
            if not name or not slug:
                continue

            in_stock = bool(p.get("in_stock") and not p.get("is_out_of_stock"))
            if not in_stock:
                continue

            special = p.get("special_price") or {}
            normal = p.get("price") or {}

            price_val = special.get("amount") or normal.get("amount")
            if not price_val:
                continue

            price = float(price_val)
            mrp = float(normal.get("amount")) if normal.get("amount") else price

            base_img = p.get("base_image") or {}
            image_url = base_img.get("path") if isinstance(base_img, dict) else None

            prod_url = f"{self.store.base_url.rstrip('/')}/products/{slug}"

            sr = SearchResult(
                store=self.store.name,
                sid=self.store.id,
                pid=slug,
                name=name,
                url=prod_url,
                image=image_url,
                currency=self.store.currency or "INR",
                price=price,
                mrp=mrp,
                in_stock=in_stock,
            )
            results.append(sr)

        return results

    def _parse_computech_html(self, html: str) -> list[SearchResult]:
        soup = BeautifulSoup(html, "lxml")
        results = []

        product_links = [
            a for a in soup.find_all("a", href=True)
            if "/product/" in a["href"] and a.text.strip() and a.text.strip() != "View Product"
        ]

        seen_pids = set()

        for a in product_links:
            raw_title = a.text.strip()
            href = a["href"].strip()

            parts = [p for p in href.strip("/").split("/") if p]
            if not parts:
                continue
            pid = parts[-1]

            if pid in seen_pids:
                continue

            card = a.parent.parent
            card_text = card.text.strip()

            in_stock = ("In Stock" in card_text or "Low Stock" in card_text) and "Out of Stock" not in card_text
            if not in_stock:
                continue

            # The rupee sign is REQUIRED, not optional. card_text starts with the
            # product title, and titles are full of 4-6 digit numbers that are not
            # prices - memory speeds (6000MHz), model numbers (RX 7600, RTX 5080),
            # sockets (LGA1851), wattages (1000W). With the sign optional this took
            # the first such number and sold an RTX 5080 for its model number:
            # measured live on 2026-08-17, "RTX 5080" parsed as Rs 5,080 against a
            # real price of Rs 1,54,499, and 57% of this store's catalog carried a
            # price identical to a number in its own title.
            # Same failure as the PSU-efficiency carousel bug: an unanchored regex
            # over too much text returns a confident wrong answer.
            numbers = re.findall(r"₹\s*(\d{1,3}(?:,\d{3})+|\d{4,6})", card_text)
            clean_nums = []
            for n in numbers:
                val = self._clean_price(n)
                if val > 500:
                    clean_nums.append(val)

            # No rupee-marked amount means the price wasn't found. Skipping keeps the
            # listing out rather than inventing a number for it.
            if not clean_nums:
                continue

            price = clean_nums[0]
            mrp = clean_nums[1] if len(clean_nums) > 1 and clean_nums[1] >= price else price

            prod_url = urljoin(self.store.base_url, href)
            image_url = self._image_near(a, card)

            sr = SearchResult(
                store=self.store.name,
                sid=self.store.id,
                pid=pid,
                name=raw_title,
                url=prod_url,
                image=image_url,
                currency=self.store.currency or "INR",
                price=price,
                mrp=mrp,
                in_stock=in_stock,
            )
            results.append(sr)
            seen_pids.add(pid)

        return results

    def _parse_modx_nextjs_json(self, html: str) -> list[SearchResult]:
        match = re.search(r'"productData"\s*:\s*(\{.*?"data"\s*:\s*\[.*?\]\})', html)
        if not match:
            match = re.search(r'productData\\":(\{.*?\\"data\\":\[.*?\]\})', html)

        if not match:
            return []

        raw_json = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
        try:
            pdata = json.loads(raw_json)
        except Exception:
            return []

        prods = pdata.get("data", [])
        results = []

        for p in prods:
            name = (p.get("name") or "").strip()
            slug = (p.get("slug") or "").strip()
            if not name or not slug:
                continue

            stock_status = (p.get("stockStatus") or p.get("stock_status") or "").lower()
            in_stock = stock_status == "instock" or bool(p.get("inStock") or p.get("isAvailable"))
            if not in_stock:
                continue

            price_val = p.get("priceSale") or p.get("salePrice") or p.get("price")
            if not price_val:
                continue

            price = float(price_val)
            mrp_val = p.get("regularPrice") or p.get("mrp") or price_val
            mrp = float(mrp_val)

            prod_url = f"{self.store.base_url.rstrip('/')}/product/{slug}"
            imgs = p.get("images") or []
            image_url = None
            if isinstance(imgs, list) and imgs:
                first_img = imgs[0]
                if isinstance(first_img, dict):
                    image_url = first_img.get("url") or first_img.get("src")
                elif isinstance(first_img, str):
                    image_url = first_img

            sr = SearchResult(
                store=self.store.name,
                sid=self.store.id,
                pid=slug,
                name=name,
                url=prod_url,
                image=image_url,
                currency=self.store.currency or "INR",
                price=price,
                mrp=mrp,
                in_stock=in_stock,
            )
            results.append(sr)

        return results

    def parse_search(self, html: str):
        if self.store.name == "computechstore":
            return self._parse_computech_html(html)
        if self.store.name == "modxcomputers":
            return self._parse_modx_nextjs_json(html)

        platform = self.store.search_config.get("platform") if isinstance(self.store.search_config, dict) else None
        if platform == "shopify":
            return self._parse_shopify_json(html)
        elif platform == "fleetcart":
            return self._parse_fleetcart_json(html)

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

            link_elem = title if title.name == "a" else (title.find("a") or card.find("a"))
            raw_url = link_elem.get(self.attributes["url"], "") if link_elem else ""

            product_url = urljoin(
                self.store.base_url,
                raw_url
            )

            image_url = None

            if image:
                img_val = image.get(self.attributes.get("image", "src"), "")
                if not img_val or img_val.startswith("data:"):
                    img_val = image.get("data-src") or image.get("data-lazy-src") or image.get("data-srcset") or ""

                if img_val and not img_val.startswith("data:"):
                    image_url = urljoin(
                        self.store.base_url,
                        img_val
                    )

            clean_url = str(product_url).split("?")[0].rstrip("/")
            if "/product/" in clean_url:
                segs = [s for s in clean_url.split("/product/")[1].split("/") if s]
                cat_slugs = {
                    "processor", "cpu-cooler", "motherboard", "graphics-card",
                    "desktop-ram", "internal-hdd", "sata-ssd", "gen3-ssd",
                    "gen4-ssd", "gen5-ssd", "monitor", "cabinet", "smps",
                    "external-hdd", "external-ssd", "laptop-ram", "ram",
                    "storage", "hard-drive"
                }
                if segs and segs[0].lower() in cat_slugs and len(segs) > 1:
                    pid = segs[-1]
                elif segs and segs[-1].lower() in cat_slugs:
                    pid = segs[0]
                elif segs:
                    pid = segs[0]
                else:
                    pid = clean_url.split("/")[-1]
            elif clean_url:
                pid = clean_url.split("/")[-1]
            else:
                pid = title.get_text(strip=True).lower().replace(" ", "-")

            card_text = card.get_text().lower()
            is_out_of_stock = "out of stock" in card_text or "sold out" in card_text
            has_cart_btn = bool(card.select_one("button.add_to_cart_button") or "add to cart" in card_text or "cart.add" in str(card))
            in_stock = False if is_out_of_stock else (True if has_cart_btn else True)

            results.append(
                SearchResult(
                    store=self.store.name,
                    sid=self.store.id,
                    pid=pid,
                    name=self._full_title(title),
                    url=product_url,
                    price=self._clean_price(price.get_text()),
                    mrp=(
                        self._clean_price(mrp.get_text())
                        if mrp
                        else None
                    ),
                    image=image_url,
                    currency=self.store.currency,
                    in_stock=in_stock,
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

    def _parse_shopify_product_json(self, content: str) -> Product | None:
        try:
            data = json.loads(content)
        except Exception:
            return None

        p = data.get("product", {})
        if not p:
            return None

        title = p.get("title", "").strip()
        handle = p.get("handle", "").strip()
        vendor = p.get("vendor", "").strip() or None
        body_html = p.get("body_html", "")

        variants = p.get("variants", [])
        if not title or not handle or not variants:
            return None

        variant = variants[0]
        price = Decimal(str(variant.get("price", "0")))
        mrp_val = variant.get("compare_at_price")
        mrp = Decimal(str(mrp_val)) if mrp_val else mrp_val
        in_stock = any(v.get("available", False) for v in variants)

        images = p.get("images", [])
        image_url = images[0].get("src") if images else None
        prod_url = f"{self.store.base_url.rstrip('/')}/products/{handle}"

        return Product(
            store=self.store.name,
            sid=self.store.id,
            pid=handle,
            name=title,
            url=prod_url,
            image_url=image_url,
            brand=vendor,
            description=body_html,
            specifications={"vendor": vendor, "sku": variant.get("sku")},
            currency=self.store.currency or "INR",
            price=price,
            mrp=mrp,
            in_stock=in_stock,
        )

    def parse_product(self, html: str) -> Product | None:
        if self.store.product_config and self.store.product_config.get("platform") == "shopify":
            return self._parse_shopify_product_json(html)

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
        # schema.org allows a bare URL, a list, or an ImageObject - and a list *of*
        # ImageObjects. Unwrapping only the list left a dict here, and urljoin raised
        # TypeError on it, which failed the whole product parse for every PCStudio
        # page. Anything that isn't a usable string is dropped rather than guessed.
        image = data.get("image")

        if isinstance(image, list):
            image = image[0] if image else None

        if isinstance(image, dict):
            image = image.get("url") or image.get("contentUrl")

        image = urljoin(self.store.base_url, image) if isinstance(image, str) and image else None

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