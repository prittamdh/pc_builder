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
            url = f"{self.store.base_url}/{path.lstrip('/')}"

        response = self.client.get(url)

        return self.parser.parse_product(response.text)