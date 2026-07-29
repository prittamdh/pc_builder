from urllib.parse import quote_plus

from domain.store import Store
from scrapers.base_scraper import BaseScraper
from scrapers.generic_parser import GenericParser


class GenericScraper(BaseScraper):

    def __init__(self, client, store: Store):
        super().__init__(client)

        self.store = store
        self.parser = GenericParser(store)

    def scrape_search(self, query: str, page: int = 1):
        page_endpoint = self.store.search_config.get("page_endpoint")

        if page > 1 and page_endpoint:
            url = page_endpoint.format(
                query=quote_plus(query),
                page=page,
            )
        else:
            url = self.store.search_endpoint.format(
                query=quote_plus(query)
            )

        response = self.client.get(url)

        return self.parser.parse_search(response.text)

    def scrape_search_all_pages(self, query: str, max_pages: int = 3):
        all_results = []
        seen_pids = set()

        for page in range(1, max_pages + 1):
            try:
                results = self.scrape_search(query, page=page)
            except Exception:
                break

            if not results:
                break

            new_results = [r for r in results if r.pid not in seen_pids]
            if not new_results:
                break

            for r in new_results:
                seen_pids.add(r.pid)

            all_results.extend(new_results)

        return all_results

    def scrape_product(self, path: str):
        url = path
        if not path.startswith("http"):
            url = f"{self.store.base_url.rstrip('/')}/{path.lstrip('/')}"

        platform = None
        if isinstance(self.store.product_config, dict):
            platform = self.store.product_config.get("platform")
        elif isinstance(self.store.search_config, dict):
            platform = self.store.search_config.get("platform")

        if platform == "shopify" and not url.endswith(".json") and "?" not in url:
            url = f"{url.rstrip('/')}.json"

        response = self.client.get(url)
        return self.parser.parse_product(response.text)

    def scrape_category(self, endpoint: str, page: int = 1):
        platform = self.store.search_config.get("platform") if isinstance(self.store.search_config, dict) else None

        if platform == "shopify":
            if endpoint.startswith("http"):
                url = endpoint
            else:
                clean_ep = endpoint.lstrip("/")
                if "products.json" in clean_ep:
                    url = f"{self.store.base_url.rstrip('/')}/{clean_ep}"
                    if page > 1:
                        url += f"&page={page}" if "?" in url else f"?page={page}"
                else:
                    url = f"{self.store.base_url.rstrip('/')}/{clean_ep}/products.json?limit=250"
                    if page > 1:
                        url += f"&page={page}"
            response = self.client.get(url)
            return self.parser.parse_search(response.text)

        if platform == "fleetcart":
            # Extract category slug from endpoint (e.g. product-category/desktop-processors -> desktop-processors)
            clean_ep = endpoint.strip("/").split("/")[-1]
            url = f"{self.store.base_url.rstrip('/')}/products?category={clean_ep}&page={page}"
            headers = {"Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest"}
            response = self.client.get(url, headers=headers)
            return self.parser.parse_search(response.text)

        if self.store.name == "computechstore":
            base = endpoint if endpoint.startswith("http") else f"{self.store.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
            if page == 1:
                url = base
            else:
                sep = "&" if "?" in base else "?"
                url = f"{base}{sep}page={page}&sort=newest"
            headers = {"HX-Request": "true"}
            response = self.client.get(url, headers=headers)
            return self.parser.parse_search(response.text)

        if self.store.name == "modxcomputers":
            base = endpoint if endpoint.startswith("http") else f"{self.store.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
            if "?" in base:
                url = f"{base}&page={page}" if page > 1 else base
            else:
                url = f"{base}?in_stock=true&page={page}" if page > 1 else f"{base}?in_stock=true"
            response = self.client.get(url)
            return self.parser.parse_search(response.text)

        if not endpoint.startswith("http"):
            base = f"{self.store.base_url}/{endpoint.lstrip('/')}"
        else:
            base = endpoint

        if page == 1:
            url = base
        else:
            if "buy-online-price-india" in base or "product-category" in base or "/page/" in base:
                # WooCommerce path pagination format: /page/{page}/
                if "?" in base:
                    path_part, query_part = base.split("?", 1)
                    path_part = path_part.rstrip("/")
                    url = f"{path_part}/page/{page}/?{query_part}"
                else:
                    path_part = base.rstrip("/")
                    url = f"{path_part}/page/{page}/"
            else:
                # OpenCart query pagination format: ?page={page}
                url = f"{base}?page={page}" if "?" not in base else f"{base}&page={page}"

        response = self.client.get(url)
        return self.parser.parse_search(response.text)

    def scrape_category_all_pages(self, endpoint: str, max_pages: int = 15):
        all_results = []
        seen_pids = set()

        for page in range(1, max_pages + 1):
            try:
                results = self.scrape_category(endpoint, page=page)
            except Exception:
                break

            if not results:
                break

            new_results = [r for r in results if r.pid not in seen_pids]
            if not new_results:
                break

            for r in new_results:
                seen_pids.add(r.pid)

            all_results.extend(new_results)

        return all_results