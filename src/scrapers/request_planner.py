"""Which URL and headers fetch a given store page (AGENT-07).

This is the "plan" half of what GenericScraper used to do in one step. Browser-extension
agents do the fetching now; the server plans each request here, queues it as a job, and
runs the unchanged GenericParser on whatever the agent uploads. GenericScraper uses the
same planner, so a local debug fetch and an agent job ask for exactly the same page.

`expects` says what a correct answer looks like ("json" or "html"). The upload check
uses it to refuse, say, an HTML error page where a Shopify products.json was due.
"""
from dataclasses import dataclass, field
from urllib.parse import quote_plus


# 100, not Shopify's maximum of 250: a 250-product EliteHubs page is up to 6 MB (full
# product descriptions), over the 5 MB upload cap, and was measured at 6.1 MB for
# motherboards on 2026-09-25. 100 per page keeps the largest near 2.5 MB.
SHOPIFY_PAGE_SIZE = 100


@dataclass(frozen=True)
class PlannedRequest:
    url: str
    headers: dict = field(default_factory=dict)
    expects: str = "html"


def search_platform(store) -> str | None:
    return store.search_config.get("platform") if isinstance(store.search_config, dict) else None


def product_platform(store) -> str | None:
    if isinstance(store.product_config, dict):
        return store.product_config.get("platform")
    if isinstance(store.search_config, dict):
        return store.search_config.get("platform")
    return None


def listing_expects(store) -> str:
    return "json" if search_platform(store) in ("shopify", "fleetcart") else "html"


def plan_search_page(store, query: str, page: int = 1) -> PlannedRequest:
    page_endpoint = store.search_config.get("page_endpoint")

    if page > 1 and page_endpoint:
        url = page_endpoint.format(
            query=quote_plus(query),
            page=page,
        )
    else:
        url = store.search_endpoint.format(
            query=quote_plus(query)
        )
    return PlannedRequest(url=url, expects=listing_expects(store))


def plan_product_page(store, path: str) -> PlannedRequest:
    url = path
    if not path.startswith("http"):
        url = f"{store.base_url.rstrip('/')}/{path.lstrip('/')}"

    platform = product_platform(store)
    if platform == "shopify" and not url.endswith(".json") and "?" not in url:
        url = f"{url.rstrip('/')}.json"

    # parse_product reads Shopify's product .json only when product_config names the
    # platform; every other product page is parsed from its HTML (JSON-LD).
    shopify_json = isinstance(store.product_config, dict) and store.product_config.get("platform") == "shopify"
    return PlannedRequest(url=url, expects="json" if shopify_json else "html")


def plan_category_page(store, endpoint: str, page: int = 1) -> PlannedRequest:
    platform = search_platform(store)

    if platform == "shopify":
        if endpoint.startswith("http"):
            url = endpoint
        else:
            clean_ep = endpoint.lstrip("/")
            if "products.json" in clean_ep:
                url = f"{store.base_url.rstrip('/')}/{clean_ep}"
                if page > 1:
                    url += f"&page={page}" if "?" in url else f"?page={page}"
            else:
                url = f"{store.base_url.rstrip('/')}/{clean_ep}/products.json?limit={SHOPIFY_PAGE_SIZE}"
                if page > 1:
                    url += f"&page={page}"
        return PlannedRequest(url=url, expects="json")

    if platform == "fleetcart":
        # Extract category slug from endpoint (e.g. product-category/desktop-processors -> desktop-processors)
        clean_ep = endpoint.strip("/").split("/")[-1]
        url = f"{store.base_url.rstrip('/')}/products?category={clean_ep}&page={page}"
        headers = {"Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest"}
        return PlannedRequest(url=url, headers=headers, expects="json")

    if store.name == "computechstore":
        base = endpoint if endpoint.startswith("http") else f"{store.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        if page == 1:
            url = base
        else:
            sep = "&" if "?" in base else "?"
            url = f"{base}{sep}page={page}&sort=newest"
        return PlannedRequest(url=url, headers={"HX-Request": "true"})

    if store.name == "modxcomputers":
        base = endpoint if endpoint.startswith("http") else f"{store.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        if "?" in base:
            url = f"{base}&page={page}" if page > 1 else base
        else:
            url = f"{base}?in_stock=true&page={page}" if page > 1 else f"{base}?in_stock=true"
        return PlannedRequest(url=url)

    if not endpoint.startswith("http"):
        base = f"{store.base_url}/{endpoint.lstrip('/')}"
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
    return PlannedRequest(url=url)
