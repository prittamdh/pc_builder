"""
Queue a full re-scrape of every catalog target, ignoring their schedules.

Pass a store name or id to re-scrape just one, which is what you want after fixing a
single store's parser rather than re-pulling all ten:

    python scripts/re_scrape_all_stores.py computechstore
    python scripts/re_scrape_all_stores.py 8

Since plan 02-02 this only queues page 1 of each target. The browser-extension agents
fetch the pages, and the server saves each one and queues the next page while pages
keep bringing new products (pipeline/scrape_results.py). Watch progress in scrape_jobs.
"""
import sys

from sqlalchemy import select

from db.models.scrape_target import ScrapeTarget
from db.models.store import Store
from db.session import SessionLocal
from pipeline.scrape_planning import enqueue_targets


def run_master_rescrape(only_store: str | None = None) -> int:
    with SessionLocal() as session:
        stmt = select(Store).where(Store.active.is_(True))
        if only_store:
            stmt = (
                stmt.where(Store.id == int(only_store))
                if only_store.isdigit()
                else stmt.where(Store.name == only_store)
            )
        stores = list(session.scalars(stmt).all())
        if not stores:
            print(f"No active store matched '{only_store}'.")
            return 1

        total = 0
        for store in stores:
            targets = list(session.scalars(select(ScrapeTarget).where(ScrapeTarget.store_id == store.id)).all())
            queued = enqueue_targets(session, targets)
            total += queued
            print(f"{store.display_name} (sid={store.id}): queued page 1 of {queued}/{len(targets)} targets")
        print(f"Queued {total} jobs. Agents fetch them as each store's pacing allows.")
    return 0


if __name__ == "__main__":
    sys.exit(run_master_rescrape(sys.argv[1] if len(sys.argv) > 1 else None))
