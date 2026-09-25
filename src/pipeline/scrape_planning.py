"""Turn scrape targets and stale products into agent jobs (plan 02-02).

Only page 1 of a listing is queued here. Later pages are queued by the result
processor, and only while pages keep bringing new product ids (scrape_results.py).
"""
from datetime import datetime, timedelta

from sqlalchemy import exists, select

from common.enums.schedule_type import ScheduleType
from common.enums.target_type import TargetType
from db.models.price_history import PriceHistory
from db.models.product import Product
from db.models.scrape_target import ScrapeTarget
from db.models.store import Store
from pipeline.job_queue import insert_job, utcnow
from scrapers.request_planner import plan_category_page, plan_product_page, plan_search_page


def _next_due(target: ScrapeTarget, now: datetime) -> datetime:
    # Same schedule as ScrapeTargetService.mark_scraped.
    if target.schedule_type == int(ScheduleType.HOURLY):
        return now + timedelta(hours=1)
    return now + timedelta(days=1)


def enqueue_targets(session, targets, now: datetime | None = None) -> int:
    """Queue page 1 of each target now, ignoring its schedule. Commits. Returns how
    many jobs were new (a page already waiting isn't queued twice)."""
    now = now or utcnow()
    queued = 0
    for target in targets:
        store = session.get(Store, target.store_id)
        if target.target_type == int(TargetType.SEARCH):
            request = plan_search_page(store, target.target_value, 1)
        else:
            request = plan_category_page(store, target.target_value, 1)
        job_id = insert_job(
            session, store_id=store.id, job_type="category_page", url=request.url,
            headers=request.headers, page=1, target_id=target.id, now=now,
        )
        queued += job_id is not None
    session.commit()
    return queued


def enqueue_due_targets(session, now: datetime | None = None, limit: int = 500) -> int:
    """Queue page 1 for every enabled target that is due, on an active store, and move
    its next_scrape_at on by its schedule. Commits. Returns the number of new jobs."""
    now = now or utcnow()
    due = list(session.execute(
        select(ScrapeTarget)
        .join(Store, Store.id == ScrapeTarget.store_id)
        .where(
            ScrapeTarget.enabled.is_(True),
            ScrapeTarget.next_scrape_at <= now,
            Store.active.is_(True),
        )
        .order_by(ScrapeTarget.priority.desc(), ScrapeTarget.next_scrape_at)
        .limit(limit)
    ).scalars())
    for target in due:
        target.next_scrape_at = _next_due(target, now)
    return enqueue_targets(session, due, now=now)


def find_unseen_products(session, store_id: int, hours: int, now: datetime | None = None) -> list[Product]:
    """Products of a store with no price saved in the last `hours` - the ones a listing
    re-scrape didn't reach (out of stock on the site, or past the target's max_pages)."""
    now = now or utcnow()
    since = now - timedelta(hours=hours)
    recent = exists().where(PriceHistory.product_id == Product.id, PriceHistory.scraped_at >= since)
    return list(session.execute(
        select(Product).where(Product.sid == store_id, ~recent).order_by(Product.id)
    ).scalars())


def enqueue_products(session, products, now: datetime | None = None) -> int:
    """Queue a product_page job for each product. Commits. Returns the number of new jobs."""
    now = now or utcnow()
    queued = 0
    for product in products:
        store = session.get(Store, product.sid)
        request = plan_product_page(store, product.product_url)
        job_id = insert_job(
            session, store_id=store.id, job_type="product_page", url=request.url,
            headers=request.headers, product_id=product.id, now=now,
        )
        queued += job_id is not None
    session.commit()
    return queued
