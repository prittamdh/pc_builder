"""Check, parse and save one agent upload (plan 02-02, AGENT-06/07/08/09).

`process_upload` is the `process` callback for job_queue.complete(). It runs inside
complete()'s transaction and never commits, so a page's prices and its job's new status
are saved together or not at all.

The server trusts an upload less than its own fetches. Before anything is parsed:

    fetch error, HTTP 429 or 5xx          -> retry (re-queued with backoff)
    body over 5 MB                        -> rejected
    final URL not on the store's domain   -> rejected
    challenge page, redirect to a login   -> blocked
    HTTP 401/403                          -> blocked
    HTTP 404/410                          -> listing: page 1 failed, later pages end the
                                             listing; product page: out of stock
    other non-2xx                         -> failed
    content type not what the platform serves (JSON vs HTML) -> rejected

Then the unchanged GenericParser runs. A parser crash is `rejected` (retrying the same
page won't help); page 1 parsing to 0 products is `failed`, never a quiet "empty".
Each price must be usable (above 0) and within PRICE_CEILING, or that one item is
dropped and counted.
"""
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy.orm import object_session

from common.enums.target_type import TargetType
from db.models.price_history import PriceHistory
from db.models.product import Product
from db.models.scrape_job import ScrapeJob
from db.models.scrape_target import ScrapeTarget
from db.models.store import Store
from pipeline.job_queue import host_belongs_to_store, insert_job, utcnow
from scrapers.generic_parser import GenericParser
from scrapers.generic_scraper import _is_challenge_body
from scrapers.request_planner import listing_expects, plan_category_page, plan_product_page, plan_search_page
from services.search_service import SearchService

MAX_BODY_BYTES = 5 * 1024 * 1024
# Above any single consumer PC part these stores sell (the dearest listings are
# workstation GPUs and Threadrippers at a few lakh). A price past it is a parse error
# - a merged number, a part code read as a price - not a real price.
PRICE_CEILING = Decimal("2000000")
DEFAULT_MAX_PAGES = 2  # what the Airflow DAG used when a target sets none
_LOGIN_PATHS = ("/login", "/signin", "/sign-in", "/account/login", "route=account/login", "my-account")


@dataclass(frozen=True)
class Upload:
    final_url: str | None
    http_status: int | None
    content_type: str | None
    body: str | None
    error: str | None = None

    @classmethod
    def coerce(cls, upload) -> "Upload":
        if isinstance(upload, cls):
            return upload
        get = upload.get if isinstance(upload, dict) else (lambda k, d=None: getattr(upload, k, d))
        return cls(
            final_url=get("final_url"),
            http_status=get("http_status"),
            content_type=get("content_type"),
            body=get("body"),
            error=get("error"),
        )


def _outcome(status: str, reason: str | None = None, **counts) -> dict:
    return {"status": status, "reason": reason, **counts}


def _looks_like_login(final_url: str) -> bool:
    parts = urlsplit(final_url)
    where = f"{parts.path}?{parts.query}".lower()
    return any(p in where for p in _LOGIN_PATHS)


def check_upload(store: Store, up: Upload, expects: str) -> dict | None:
    """The outcome for an upload that must not be parsed, or None if it may be.

    A 404/410 outcome carries "http_status" so callers can treat "gone" their own way.
    """
    if up.error or up.http_status is None:
        return _outcome("retry", f"fetch error: {up.error or 'no HTTP status'}")
    body = up.body or ""
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        return _outcome("rejected", "body over 5 MB")
    host = (urlsplit(up.final_url or "").hostname or "").lower()
    if not host or not host_belongs_to_store(host, (store.domain or "").lower()):
        return _outcome("rejected", f"final URL host {host or '(none)'!r} is not {store.domain}")
    if _is_challenge_body(body):
        return _outcome("blocked", f"challenge page (HTTP {up.http_status})")
    if _looks_like_login(up.final_url):
        return _outcome("blocked", "redirected to a login page")
    status = up.http_status
    if status == 429 or status >= 500:
        return _outcome("retry", f"HTTP {status}")
    if status in (401, 403):
        return _outcome("blocked", f"HTTP {status}")
    if status in (404, 410):
        return _outcome("failed", f"HTTP {status}", http_status=status)
    if not 200 <= status < 300:
        return _outcome("failed", f"HTTP {status}")
    content_type = (up.content_type or "").lower()
    wanted = "json" if expects == "json" else "html"
    if wanted not in content_type:
        return _outcome("rejected", f"content type {up.content_type!r}, expected {wanted}")
    return None


def _usable(price) -> bool:
    return price is not None and Decimal(price) > 0 and Decimal(price) <= PRICE_CEILING


def process_upload(job: ScrapeJob, upload) -> dict:
    session = object_session(job)
    up = Upload.coerce(upload)
    store = session.get(Store, job.store_id)
    if job.job_type == "product_page":
        return _process_product(session, job, store, up)
    return _process_listing(session, job, store, up)


def _seen_pids(session, job: ScrapeJob) -> set[str]:
    """Product ids already brought by earlier pages of this listing run."""
    seen: set[str] = set()
    parent_id = job.parent_job_id
    while parent_id is not None:
        parent = session.get(ScrapeJob, parent_id)
        if parent is None:
            break
        seen.update((parent.outcome or {}).get("pids", []))
        parent_id = parent.parent_job_id
    return seen


def _plan_next_page(store, target: ScrapeTarget, page: int):
    if target.target_type == int(TargetType.SEARCH):
        return plan_search_page(store, target.target_value, page)
    return plan_category_page(store, target.target_value, page)


def _max_pages(target: ScrapeTarget) -> int:
    config = target.schedule_config if isinstance(target.schedule_config, dict) else {}
    if target.target_type == int(TargetType.SEARCH):
        return DEFAULT_MAX_PAGES  # the DAG never read max_pages for search targets
    return int(config.get("max_pages", DEFAULT_MAX_PAGES))


def _process_listing(session, job: ScrapeJob, store: Store, up: Upload) -> dict:
    page = job.page or 1
    gate = check_upload(store, up, listing_expects(store))
    if gate is not None:
        if gate.pop("http_status", None) is not None and page > 1:
            # Past the last page some stores answer 404 (WooCommerce /page/N/). The
            # earlier pages were saved; this just ends the listing.
            return _outcome("done", f"{gate['reason']} on page {page}: end of listing",
                            saved=0, next_job_id=None, pids=[])
        return gate

    try:
        results = GenericParser(store).parse_search(up.body)
    except Exception as exc:
        return _outcome("rejected", f"parse error: {type(exc).__name__}: {exc}")

    if not results and page == 1:
        return _outcome("failed", "page 1 parsed to 0 products")

    seen = _seen_pids(session, job)
    fresh = {}
    for r in results:
        if r.pid not in seen:
            fresh[r.pid] = r  # later duplicates on the same page win, as in save_many

    target = session.get(ScrapeTarget, job.target_id) if job.target_id else None
    hard_category = target.schedule_config.get("category") if target and isinstance(target.schedule_config, dict) else None
    service = SearchService(session)
    saved = dropped = 0
    for r in fresh.values():
        if not _usable(r.price):
            dropped += 1
            continue
        if service.save(r, target_id=job.target_id, hard_category=hard_category, agent_id=job.agent_id, job_id=job.id):
            saved += 1

    next_job_id = None
    if fresh and target is not None and page < _max_pages(target):
        request = _plan_next_page(store, target, page + 1)
        next_job_id = insert_job(
            session, store_id=store.id, job_type="category_page", url=request.url,
            headers=request.headers, page=page + 1, target_id=target.id, parent_job_id=job.id,
        )
    if target is not None:
        target.last_scraped_at = job.not_before or utcnow()  # when the agent fetched it

    return _outcome(
        "done", None, parsed=len(results), new=len(fresh), saved=saved, dropped_prices=dropped,
        next_job_id=next_job_id, pids=sorted(fresh),
    )


def _process_product(session, job: ScrapeJob, store: Store, up: Upload) -> dict:
    product = session.get(Product, job.product_id) if job.product_id else None
    if product is None:
        return _outcome("failed", "the product for this job no longer exists")

    gate = check_upload(store, up, plan_product_page(store, product.product_url).expects)
    if gate is not None:
        if gate.pop("http_status", None) is not None:
            # Only the store saying the page doesn't exist marks it unavailable - never
            # our parser failing (see scripts/repair_unseen_products.py history).
            product.in_stock = False
            return _outcome("done", f"{gate['reason']}: marked out of stock", saved=0)
        return gate

    try:
        parsed = GenericParser(store).parse_product(up.body)
    except Exception as exc:
        return _outcome("rejected", f"parse error: {type(exc).__name__}: {exc}")
    if parsed is None or parsed.price is None:
        return _outcome("rejected", "product page had no price")
    if not _usable(parsed.price):
        return _outcome("rejected", f"unusable price {parsed.price}")

    product.current_price = float(parsed.price)
    product.current_mrp = float(parsed.mrp) if parsed.mrp is not None else None
    product.in_stock = bool(parsed.in_stock)
    # Product pages carry a JSON-LD image; a listing repaired this way had none before.
    if not (product.image_url or "").strip() and parsed.image:
        product.image_url = str(parsed.image)
    session.add(PriceHistory(
        product_id=product.id,
        price=Decimal(parsed.price),
        mrp=Decimal(parsed.mrp) if parsed.mrp is not None else None,
        in_stock=bool(parsed.in_stock),
        agent_id=job.agent_id,
        job_id=job.id,
    ))
    return _outcome("done", None, saved=1, price=str(parsed.price))
