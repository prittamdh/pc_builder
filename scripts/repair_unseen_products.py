"""Refresh products a catalog re-scrape never reached, by queueing their own pages.

A category re-scrape only walks listing pages, so anything that has fallen off them -
out of stock on the site, or past the target's `max_pages` - keeps whatever price it
was last given. That is normally harmless, but after a parser fix it means the bad
values survive in exactly the rows the re-scrape cannot correct.

Membership is decided by price_history, not by `products.updated_at`: `save()` writes
a history row on every scrape even when the product row itself is unchanged, so "has
no history row since the run started" is the only precise test for "never seen".
`updated_at` cannot distinguish "not seen" from "seen but identical".

Since plan 02-02 this only queues `product_page` jobs; the browser-extension agents
fetch the pages and the server saves them (pipeline/scrape_results.py). A 404/410 from
the store marks the product out of stock; any other failure leaves it unchanged.

    python scripts/repair_unseen_products.py computechstore
    python scripts/repair_unseen_products.py computechstore --hours 3 --dry-run
"""
import argparse
import sys

from sqlalchemy import select

from db.models.store import Store
from db.session import SessionLocal
from pipeline.scrape_planning import enqueue_products, find_unseen_products


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("store", help="store name or id")
    ap.add_argument("--hours", type=int, default=3,
                    help="how far back the re-scrape run started (default 3)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with SessionLocal() as db:
        stmt = select(Store)
        stmt = (stmt.where(Store.id == int(args.store)) if args.store.isdigit()
                else stmt.where(Store.name == args.store))
        store = db.scalar(stmt)
        if store is None:
            print(f"No store matched '{args.store}'.")
            return 1

        targets = find_unseen_products(db, store.id, args.hours)
        print(f"{store.display_name} (sid={store.id}): "
              f"{len(targets)} products not seen in the last {args.hours}h")
        if not targets:
            return 0
        if args.dry_run:
            for p in targets[:20]:
                print(f"  would queue  {str(p.current_price):>10}  {p.name[:52]}")
            return 0

        queued = enqueue_products(db, targets)
        print(f"queued {queued} product_page jobs ({len(targets) - queued} already waiting)")
        if not store.active:
            print("note: this store is inactive, so agents won't be given these jobs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
