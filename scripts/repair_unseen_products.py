"""Refresh products a catalog re-scrape never reached, by fetching their own pages.

A category re-scrape only walks listing pages, so anything that has fallen off them -
out of stock on the site, or past the target's `max_pages` - keeps whatever price it
was last given. That is normally harmless, but after a parser fix it means the bad
values survive in exactly the rows the re-scrape cannot correct.

Membership is decided by price_history, not by `products.updated_at`: `save()` writes
a history row on every scrape even when the product row itself is unchanged, so "has
no history row since the run started" is the only precise test for "never seen".
`updated_at` cannot distinguish "not seen" from "seen but identical".

    python scripts/repair_unseen_products.py computechstore
    python scripts/repair_unseen_products.py computechstore --hours 3 --dry-run
"""
import argparse
import sys
from decimal import Decimal

from sqlalchemy import select, text

from db.session import SessionLocal
from db.models.price_history import PriceHistory
from db.models.product import Product
from db.models.store import Store
from scrapers.http_client import HttpClient
from scrapers.generic_scraper import GenericScraper


def _is_gone(exc: BaseException) -> bool:
    """True only when the store says the page does not exist.

    Deliberately narrow: marking a product unavailable is a claim about the store's
    inventory, so it must come from the store, not from our own parser falling over.
    """
    for err in (exc, getattr(exc, "__cause__", None), getattr(exc, "__context__", None)):
        status = getattr(err, "code", None) or getattr(
            getattr(err, "response", None), "status_code", None
        )
        if status in (404, 410):
            return True
    return False


def find_unseen(db, sid: int, hours: int) -> list[Product]:
    ids = db.scalars(
        text(
            """
            SELECT p.id FROM products p
            WHERE p.sid = :sid AND NOT EXISTS (
                SELECT 1 FROM price_history h
                WHERE h.product_id = p.id
                  AND h.scraped_at >= now() - (:hours * interval '1 hour')
            )
            ORDER BY p.id
            """
        ),
        {"sid": sid, "hours": hours},
    ).all()
    return list(db.scalars(select(Product).where(Product.id.in_(ids)))) if ids else []


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

        targets = find_unseen(db, store.id, args.hours)
        print(f"{store.display_name} (sid={store.id}): "
              f"{len(targets)} products not seen in the last {args.hours}h")
        if not targets:
            return 0
        if args.dry_run:
            for p in targets[:20]:
                print(f"  would refetch  {str(p.current_price):>10}  {p.name[:52]}")
            return 0

        changed = delisted = failed = 0
        with HttpClient() as client:
            scraper = GenericScraper(client, store)

            for idx, product in enumerate(targets, 1):
                try:
                    parsed = scraper.scrape_product(product.product_url)
                except Exception as exc:
                    # Only a 404/410 means the listing is genuinely gone. Any other
                    # failure - a parser bug, a timeout, a blocked request - says
                    # nothing about the product, and treating it as a delisting once
                    # marked 61 in-stock PCStudio products unavailable because a
                    # TypeError in the image handling failed every page.
                    if _is_gone(exc):
                        product.in_stock = False
                        delisted += 1
                        print(f"  [{idx}/{len(targets)}] gone -> out of stock: "
                              f"{product.name[:44]}")
                    else:
                        failed += 1
                        print(f"  [{idx}/{len(targets)}] fetch/parse failed "
                              f"({type(exc).__name__}: {exc}) - left unchanged: "
                              f"{product.name[:40]}")
                    continue

                if parsed is None or parsed.price is None:
                    failed += 1
                    print(f"  [{idx}/{len(targets)}] unparseable: {product.name[:44]}")
                    continue

                old = product.current_price
                product.current_price = float(parsed.price)
                product.current_mrp = float(parsed.mrp) if parsed.mrp is not None else None
                product.in_stock = bool(parsed.in_stock)

                # Product pages carry a JSON-LD image. Not copying it left every
                # product repaired this way with no picture at all - which is how
                # Computech ended up with imageless cards even after a re-scrape.
                if not (product.image_url or "").strip() and parsed.image:
                    product.image_url = str(parsed.image)

                db.add(PriceHistory(
                    product_id=product.id,
                    price=Decimal(parsed.price),
                    mrp=Decimal(parsed.mrp) if parsed.mrp is not None else None,
                    in_stock=bool(parsed.in_stock),
                ))

                if old is None or float(old) != float(parsed.price):
                    changed += 1
                    print(f"  [{idx}/{len(targets)}] {str(old):>10} -> "
                          f"{str(parsed.price):>10}  {product.name[:44]}")

                if idx % 25 == 0:
                    db.commit()

            db.commit()

        print(f"\nprice changed: {changed} | delisted: {delisted} | failed: {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
