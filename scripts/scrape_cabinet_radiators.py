"""
Fill cabinet radiator support (cabinet_specs.radiator_sizes) from retailer product pages.

Same safeguards as scrape_cabinet_clearance.py: the LLM reads only the page text around
radiator terms and must quote the exact span each size came from; a size whose quote is
not on the page, or which does not name it, is discarded. Sizes are unioned across mounts
(front/top/side/rear) and across up to --pages pages - a page often lists only some
mounts, so a union loses nothing true, and anything outside the standard radiator lengths
is dropped.

A model whose pages yield nothing is marked "Radiator pages checked <date>" in
raw_response so the scheduled run does not re-fetch it; --recheck ignores the marker.

Dry-run by default. Pass --apply to write.
"""
import argparse
import sys
from datetime import date
from types import SimpleNamespace

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart
from db.models.category_specs import CabinetSpecs
from matching.cabinet_clearance import (
    RADIATOR_SIZES_MM, RADIATOR_TERMS, format_radiator_sizes, is_grounded,
)
from scrapers.http_client import HttpClient
from services.groq_extraction_service import GroqExtractionError, default_service

sys.path.insert(0, "scripts")
from scrape_cabinet_clearance import fetch_pages  # noqa: E402

CHECKED_KEY = "radiator_pages_checked"

PROMPT = """Each input is a PC cabinet's listing title plus text excerpts from its retailer product page.
List every radiator length the cabinet supports, at any mount (front, top, side, rear, bottom).
Return STRICT JSON only: {"results": [{"index": number, "radiators": [{"size_mm": number, "quote": string}, ...]}, ...]}
CRITICAL: "index" MUST equal the input's number (1-based). One result per input.
Rules:
- Use ONLY what the excerpt states. Never use your own knowledge of the case. Nothing stated -> "radiators": [].
- Each quote must be copied VERBATIM from the excerpt (a short span, 5-80 characters) and must contain that size.
  One quote may cover several sizes ("Front: 120/240/360mm" supports 120, 240 and 360).
- Only radiator/AIO/liquid-cooling support. Ignore fan-only mounts, GPU lengths, cooler heights and case dimensions.
- Ignore any other product's specs that appear in the excerpt."""


def live_case_models(session, recheck: bool):
    listings = (
        select(Product.canonical_id, func.count().label("n"))
        .where(Product.canonical_id.like("case:%"))
        .group_by(Product.canonical_id)
        .subquery()
    )
    stmt = (
        select(CanonicalPart, listings.c.n, CabinetSpecs)
        .join(listings, listings.c.canonical_id == CanonicalPart.canonical_id)
        .outerjoin(CabinetSpecs, CabinetSpecs.canonical_id == CanonicalPart.canonical_id)
        .order_by(listings.c.n.desc(), CanonicalPart.canonical_id)
    )
    if not recheck:
        stmt = stmt.where(CabinetSpecs.radiator_sizes.is_(None))
    rows = session.execute(stmt).all()
    if not recheck:
        rows = [r for r in rows if not ((r[2].raw_response or {}) if r[2] else {}).get(CHECKED_KEY)]
    return [(SimpleNamespace(canonical_id=cp.canonical_id, key_fields=cp.key_fields), n) for cp, n, _ in rows]


def _row(session, cp) -> CabinetSpecs:
    row = session.scalar(select(CabinetSpecs).where(CabinetSpecs.canonical_id == cp.canonical_id))
    if row is None:
        row = CabinetSpecs(canonical_id=cp.canonical_id, brand=(cp.key_fields or {}).get("brand"), status="ok")
        session.add(row)
    return row


def _mark(row, info: dict) -> None:
    # Reassign rather than mutate: JSONB changes in place are not tracked.
    row.raw_response = {**(row.raw_response or {}), **info}


def main(limit, pages, apply, recheck, sleep_s, batch_size):
    with SessionLocal() as session, HttpClient() as client, default_service() as llm:
        models = live_case_models(session, recheck)
        if limit:
            models = models[:limit]
        print("=" * 78)
        print(f"CABINET RADIATOR SUPPORT FROM PRODUCT PAGES {'(APPLY)' if apply else '(DRY RUN)'}")
        print(f"  models to check: {len(models)}")
        print("=" * 78)
        stats = dict(filled=0, changed=0, no_statement=0, ungrounded=0, failed=0)

        for i in range(0, len(models), batch_size):
            batch = models[i:i + batch_size]
            jobs, inputs = [], []
            for cp, _n in batch:
                for product, text, snippet in fetch_pages(session, client, cp.canonical_id, pages, sleep_s,
                                                          terms=RADIATOR_TERMS):
                    jobs.append((cp, product, text))
                    inputs.append(f"TITLE: {product.name} | EXCERPT: {snippet}")

            found: dict[str, dict] = {}
            if inputs:
                try:
                    results = llm.extract_batch(PROMPT, inputs)
                except GroqExtractionError as e:
                    print(f"  batch @ {i} failed: {e}")
                    stats["failed"] += len(batch)
                    continue
                for (cp, product, text), res in zip(jobs, results):
                    f = found.setdefault(cp.canonical_id, {"sizes": set(), "src": []})
                    for item in (res["parsed"].get("radiators") or []):
                        size, quote = item.get("size_mm"), item.get("quote")
                        if size in RADIATOR_SIZES_MM and is_grounded(size, quote, text, (120, 480)):
                            f["sizes"].add(size)
                            f["src"].append(f"{product.product_url} \"{quote}\"")
                        else:
                            stats["ungrounded"] += 1

            today = date.today().isoformat()
            for cp, _n in batch:
                f = found.get(cp.canonical_id)
                value = format_radiator_sizes(f["sizes"]) if f else None
                if value is None:
                    stats["no_statement"] += 1
                    if apply:
                        _mark(_row(session, cp), {CHECKED_KEY: today})
                    continue
                row = session.scalar(select(CabinetSpecs).where(CabinetSpecs.canonical_id == cp.canonical_id))
                old = row.radiator_sizes if row else None
                if old == value:
                    continue
                if old is not None:
                    stats["changed"] += 1
                    print(f"  CHANGE {cp.canonical_id}: {old} -> {value}")
                else:
                    stats["filled"] += 1
                    print(f"  {cp.canonical_id[:56]:58} radiators={value}")
                if apply:
                    row = _row(session, cp)
                    row.radiator_sizes = value
                    _mark(row, {CHECKED_KEY: today, "radiator_sources": f["src"][:6]})
            if apply:
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()  # a group in this batch was deleted mid-run
                    stats["failed"] += len(batch)
            print(f"  [{min(i + batch_size, len(models))}/{len(models)}] {stats}")

        print("=" * 78)
        for k, val in stats.items():
            print(f"  {k:14} {val}")
        print("=" * 78)


def fill_cabinet_radiators(limit: int | None = 20) -> None:
    """Scheduled entry point: new or unchecked cabinets only, most-listed first."""
    main(limit, pages=2, apply=True, recheck=False, sleep_s=0.3, batch_size=4)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--recheck", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--batch-size", type=int, default=4)
    a = ap.parse_args()
    main(a.limit, a.pages, a.apply, a.recheck, a.sleep, a.batch_size)
