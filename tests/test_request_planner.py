"""The request planner (plan 02-02, AGENT-07): one test per platform GenericScraper supports.

These URLs were checked equal to the pre-split GenericScraper for every real target and
pages 1-3 (788 requests, 0 differences) when the planner was extracted on 2026-09-25.
The one deliberate change since: Shopify collections ask for 100 products a page, not
250, to keep uploads under the 5 MB cap (see SHOPIFY_PAGE_SIZE).
"""
from types import SimpleNamespace

from scrapers.request_planner import plan_category_page, plan_product_page, plan_search_page


def _store(name="shop", base="https://shop.example.in", search_config=None, product_config=None,
           search_endpoint="https://shop.example.in/search?q={query}"):
    return SimpleNamespace(
        name=name, base_url=base, search_config=search_config or {}, product_config=product_config,
        search_endpoint=search_endpoint,
    )


def test_shopify_collection_slug_becomes_products_json():
    store = _store(base="https://elitehubs.com", search_config={"platform": "shopify"})
    p1 = plan_category_page(store, "collections/processor", 1)
    p2 = plan_category_page(store, "collections/processor", 2)
    assert p1.url == "https://elitehubs.com/collections/processor/products.json?limit=100"
    assert p2.url == "https://elitehubs.com/collections/processor/products.json?limit=100&page=2"
    assert p1.expects == "json" and p1.headers == {}


def test_shopify_explicit_products_json_endpoint():
    store = _store(base="https://www.tpstech.in", search_config={"platform": "shopify"})
    assert plan_category_page(store, "collections/gpu/products.json?limit=250", 3).url == (
        "https://www.tpstech.in/collections/gpu/products.json?limit=250&page=3"
    )


def test_fleetcart_uses_the_json_api_with_its_headers():
    store = _store(base="https://shop.clarioncomputers.in", search_config={"platform": "fleetcart"})
    p = plan_category_page(store, "product-category/desktop-processors/", 2)
    assert p.url == "https://shop.clarioncomputers.in/products?category=desktop-processors&page=2"
    assert p.headers == {"Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest"}
    assert p.expects == "json"


def test_computech_is_an_htmx_partial():
    store = _store(name="computechstore", base="https://computechstore.in")
    p1 = plan_category_page(store, "/c/processor", 1)
    p2 = plan_category_page(store, "/c/processor", 2)
    assert p1.url == "https://computechstore.in/c/processor"
    assert p2.url == "https://computechstore.in/c/processor?page=2&sort=newest"
    assert p1.headers == {"HX-Request": "true"}
    assert p1.expects == "html"


def test_modx_asks_for_in_stock_only():
    store = _store(name="modxcomputers", base="https://modxcomputers.com")
    assert plan_category_page(store, "processors", 1).url == "https://modxcomputers.com/processors?in_stock=true"
    assert plan_category_page(store, "processors", 2).url == "https://modxcomputers.com/processors?in_stock=true&page=2"


def test_woocommerce_paginates_by_path():
    store = _store(base="https://www.primeabgb.com")
    assert plan_category_page(store, "buy-online-price-india/cpu-processor/", 1).url == (
        "https://www.primeabgb.com/buy-online-price-india/cpu-processor/"
    )
    assert plan_category_page(store, "buy-online-price-india/cpu-processor/?per_page=48", 2).url == (
        "https://www.primeabgb.com/buy-online-price-india/cpu-processor/page/2/?per_page=48"
    )


def test_opencart_paginates_by_query():
    store = _store(base="https://mdcomputers.in")
    assert plan_category_page(store, "catalog/processor", 2).url == "https://mdcomputers.in/catalog/processor?page=2"
    assert plan_category_page(store, "catalog/processor?limit=100", 2).url == (
        "https://mdcomputers.in/catalog/processor?limit=100&page=2"
    )
    assert plan_category_page(store, "catalog/processor", 1).expects == "html"


def test_search_uses_the_page_endpoint_after_page_one():
    store = _store(search_config={"page_endpoint": "https://shop.example.in/search?q={query}&page={page}"})
    assert plan_search_page(store, "rtx 4060", 1).url == "https://shop.example.in/search?q=rtx+4060"
    assert plan_search_page(store, "rtx 4060", 2).url == "https://shop.example.in/search?q=rtx+4060&page=2"


def test_shopify_product_page_is_its_json():
    store = _store(base="https://elitehubs.com", search_config={"platform": "shopify"},
                   product_config={"platform": "shopify"})
    p = plan_product_page(store, "https://elitehubs.com/products/ryzen-5-7600")
    assert p.url == "https://elitehubs.com/products/ryzen-5-7600.json"
    assert p.expects == "json"


def test_html_product_page_resolves_a_relative_path():
    store = _store(base="https://mdcomputers.in/")
    p = plan_product_page(store, "/product/ryzen-5-7600")
    assert p.url == "https://mdcomputers.in/product/ryzen-5-7600"
    assert p.expects == "html"
