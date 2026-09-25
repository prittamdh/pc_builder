"""A blocked/failed page must never look like a clean run.

PCStudio incident (2026-09-25): every request 403'd behind a Cloudflare challenge, but
`GenericScraper.scrape_category_all_pages` caught the resulting exception per page and
`break`-ed, returning an empty list with no trace of the real error. The caller
(`execute_due_scrape_targets`) treats an empty result as nothing-to-save and still marks
the target scraped - so `last_scraped_at` advanced every cycle for 5+ weeks while no price
was ever saved, and the failure was invisible until the freshness check was added.

These tests pin the fix: a failed *first* page must raise (so the caller marks the target
failed and does not advance `last_scraped_at`), a legitimate empty-but-200 first page must
still return `[]` (0 in stock is real data, not a failure), and a failure on a *later* page
must keep the pages already fetched while logging the status and page number rather than
silently finishing clean.
"""
import pytest

from domain.store import Store
from domain.search_result import SearchResult
from scrapers.generic_scraper import GenericScraper, ScrapeFetchError


PCSTUDIO_SEARCH_CONFIG = {
    # Same shape as the real DB row for store id=2 (product_card/price/image), except
    # "title" is loosened from the real "li.title a" to ".title a" - the real selector
    # relies on markup this fixture doesn't need to reproduce exactly (these tests exercise
    # GenericScraper's fetch-failure handling, not GenericParser's PCStudio-specific
    # markup quirks, which is already covered by the truncated-title fix/tests).
    "selectors": {
        "mrp": "del .woocommerce-Price-amount",
        "image": "img",
        "price": "ins .woocommerce-Price-amount, .price .woocommerce-Price-amount",
        "title": ".title a",
        "product_card": "ul.products > li.product",
    },
    "attributes": {"url": "href", "image": "src"},
    "page_endpoint": "https://www.pcstudio.in/page/{page}/?s={query}&post_type=product",
}

CHALLENGE_BODY = (
    '<!DOCTYPE html><html><head><title>Just a moment...</title></head>'
    '<body>Enable JavaScript and cookies to continue</body></html>'
)

EMPTY_LISTING_BODY = "<html><body><ul class='products'></ul></body></html>"

ONE_PRODUCT_BODY = """
<html><body>
<ul class="products">
  <li class="product">
    <span class="title"><a href="/product/rtx-5070/">Zotac RTX 5070</a></span>
    <span class="price"><ins><span class="woocommerce-Price-amount">54999</span></ins></span>
    <img src="https://www.pcstudio.in/img/rtx5070.jpg">
  </li>
</ul>
</body></html>
"""


def make_store(name: str = "pcstudio") -> Store:
    return Store(
        id=2,
        name=name,
        display_name="PCStudio" if name == "pcstudio" else name,
        domain="pcstudio.in",
        base_url="https://www.pcstudio.in",
        currency="INR",
        currency_symbol="₹",
        search_config=PCSTUDIO_SEARCH_CONFIG,
        product_config={},
        active=True,
    )


class FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class FakeHTTPError(Exception):
    """Mirrors curl_cffi's HTTPError: carries the real response on `.response`."""

    def __init__(self, response: FakeResponse):
        self.response = response
        super().__init__(f"HTTP Error {response.status_code}:")


class ScriptedClient:
    """Returns a scripted response (or raises) per call, in order."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        status, body = self.script.pop(0)
        if status >= 400:
            raise FakeHTTPError(FakeResponse(status, body))
        return FakeResponse(status, body)


class TestFirstPageBlocked:
    def test_403_on_page_1_raises_and_names_the_store(self):
        client = ScriptedClient([(403, CHALLENGE_BODY)])
        scraper = GenericScraper(client, make_store())

        with pytest.raises(ScrapeFetchError) as excinfo:
            scraper.scrape_category_all_pages("product-category/processor/", max_pages=3)

        err = excinfo.value
        assert err.page == 1
        assert err.status == 403
        assert "PCStudio" in str(err)
        assert "403" in str(err)
        # Only page 1 was ever requested - pagination must not continue past a blocked start.
        assert len(client.calls) == 1

    def test_failed_first_page_does_not_look_like_zero_results(self):
        """A ScrapeFetchError, not a silent [], is what a caller must see - so it can
        avoid treating the target as successfully scraped."""
        client = ScriptedClient([(403, CHALLENGE_BODY)])
        scraper = GenericScraper(client, make_store())

        with pytest.raises(ScrapeFetchError):
            scraper.scrape_category_all_pages("product-category/processor/")


class TestLegitimateEmptyListing:
    def test_200_empty_listing_returns_empty_list_without_raising(self):
        client = ScriptedClient([(200, EMPTY_LISTING_BODY)])
        scraper = GenericScraper(client, make_store())

        results = scraper.scrape_category_all_pages("product-category/processor/", max_pages=3)

        assert results == []
        # A real 0-in-stock page must not be retried as if it were a failure.
        assert len(client.calls) == 1


class TestLaterPageFailure:
    def test_403_on_page_3_keeps_pages_1_and_2(self, capsys):
        client = ScriptedClient([
            (200, ONE_PRODUCT_BODY),
            (200, ONE_PRODUCT_BODY.replace("rtx-5070", "rtx-5080").replace("54999", "134999")),
            (403, CHALLENGE_BODY),
        ])
        scraper = GenericScraper(client, make_store())

        results = scraper.scrape_category_all_pages("product-category/processor/", max_pages=5)

        # Both good pages happen to describe the same pid in this fixture's URL scheme in
        # some stores, but here they're distinct products, so both must survive.
        assert len(results) == 2
        assert len(client.calls) == 3

        # Must be logged, not a silent break: the page number and status must appear.
        out = capsys.readouterr().out
        assert "page 3" in out
        assert "403" in out
