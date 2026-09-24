"""
Fill air-cooler heights (cooler_specs.height_mm) from retailer product pages.

Same approach and safeguards as scrape_cabinet_clearance.py: the LLM reads only the page
text around "height"/"dimensions", must quote the exact span each number came from, and
a value whose quote is not on the page is discarded. Up to --pages pages per model must
agree within 10%, otherwise nothing is written.

Only air coolers are read. An AIO's fit is a radiator-mount question, not a height one.
A model whose pages yield nothing is marked "Pages checked <date>" so the scheduled run
does not re-fetch it every cycle; --recheck ignores the marker.

Dry-run by default. Pass --apply to write.
"""
import argparse
import sys
from datetime import date
from types import SimpleNamespace

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart
from db.models.category_specs import CoolerSpecs
from db.models.cooler_title_extraction import CoolerTitleExtraction
from matching.cabinet_clearance import COOLER_HEIGHT_RANGE_MM, COOLER_HEIGHT_TERMS, is_grounded, resolve_votes
from scrapers.http_client import HttpClient
from services.groq_extraction_service import GroqExtractionError, default_service

sys.path.insert(0, "scripts")
from scrape_cabinet_clearance import fetch_pages  # noqa: E402

CHECKED_MARKER = "Height pages checked"

PROMPT = """Each input is a CPU air cooler's listing title plus text excerpts from its retailer product page.
Report the cooler's total height in millimetres, measured from the CPU surface to the top of the heatsink.
Return STRICT JSON only: {"results": [{"index": number, "height_mm": number|null, "quote": string|null}, ...]}
CRITICAL: "index" MUST equal the input's number (1-based). One result per input.
Rules:
- Use ONLY what the excerpt states. Never use your own knowledge of the cooler. No statement -> null.
- The quote must be copied VERBATIM from the excerpt (a short span, 5-80 characters) and must contain the number.
- A dimensions line gives several numbers. Take the one labelled H / height. If the line has no labels, return null.
- If heights with and without the fan are both given, report the height with the included fan fitted.
- Ignore fan dimensions (e.g. 120 x 120 x 25 mm), heatpipe counts, and any other product's specs.
- Convert cm to mm."""


def air_cooler_models(session, recheck: bool):
    listings = (
        select(Product.canonical_id, func.count().label("n"))
        .where(Product.canonical_id.like("cooler:%"))
        .group_by(Product.canonical_id)
        .subquery()
    )
    air_by_extraction = (
        select(CoolerTitleExtraction.canonical_id)
        .where(CoolerTitleExtraction.cooler_type == "Air")
    )
    stmt = (
        select(CanonicalPart, listings.c.n)
        .join(listings, listings.c.canonical_id == CanonicalPart.canonical_id)
        .outerjoin(CoolerSpecs, CoolerSpecs.canonical_id == CanonicalPart.canonical_id)
        .where(or_(CoolerSpecs.cooler_type == "Air", CanonicalPart.canonical_id.in_(air_by_extraction)))
        .order_by(listings.c.n.desc(), CanonicalPart.canonical_id)
    )
    if not recheck:
        stmt = stmt.where(
            CoolerSpecs.height_mm.is_(None),
            func.coalesce(CoolerSpecs.notes, "").notlike(f"{CHECKED_MARKER}%"),
        )
    return session.execute(stmt).all()


def _row(session, cp) -> CoolerSpecs:
    row = session.scalar(select(CoolerSpecs).where(CoolerSpecs.canonical_id == cp.canonical_id))
    if row is None:
        row = CoolerSpecs(canonical_id=cp.canonical_id, brand=(cp.key_fields or {}).get("brand"),
                          cooler_type="Air", status="ok")
        session.add(row)
    return row


def main(limit, pages, apply, recheck, sleep_s, batch_size):
    with SessionLocal() as session, HttpClient() as client, default_service() as llm:
        # Plain snapshots: the DAG's catalog clean-up can delete a canonical_parts row
        # mid-run (see scrape_cabinet_clearance.main).
        models = [(SimpleNamespace(canonical_id=cp.canonical_id, key_fields=cp.key_fields), n)
                  for cp, n in air_cooler_models(session, recheck)]
        if limit:
            models = models[:limit]
        print("=" * 78)
        print(f"AIR COOLER HEIGHT FROM PRODUCT PAGES {'(APPLY)' if apply else '(DRY RUN)'}")
        print(f"  models to check: {len(models)}")
        print("=" * 78)
        stats = dict(filled=0, changed=0, no_statement=0, conflicts=0, ungrounded=0, failed=0)

        for i in range(0, len(models), batch_size):
            batch = models[i:i + batch_size]
            jobs, inputs = [], []
            for cp, _n in batch:
                for product, text, snippet in fetch_pages(session, client, cp.canonical_id, pages, sleep_s,
                                                          terms=COOLER_HEIGHT_TERMS):
                    jobs.append((cp, product, text))
                    inputs.append(f"TITLE: {product.name} | EXCERPT: {snippet}")

            votes: dict[str, dict] = {}
            if inputs:
                try:
                    results = llm.extract_batch(PROMPT, inputs)
                except GroqExtractionError as e:
                    print(f"  batch @ {i} failed: {e}")
                    stats["failed"] += len(batch)
                    continue
                for (cp, product, text), res in zip(jobs, results):
                    p = res["parsed"]
                    v = votes.setdefault(cp.canonical_id, {"h": [], "src": [], "model": res["model"]})
                    h = p.get("height_mm")
                    if h is None:
                        continue
                    if is_grounded(h, p.get("quote"), text, COOLER_HEIGHT_RANGE_MM):
                        v["h"].append(h)
                        v["src"].append(f"{product.product_url} \"{p.get('quote')}\"")
                    else:
                        stats["ungrounded"] += 1

            for cp, _n in batch:
                v = votes.get(cp.canonical_id)
                height, conflict = resolve_votes(v["h"]) if v else (None, False)
                if height is None:
                    stats["conflicts" if conflict else "no_statement"] += 1
                    if conflict:
                        print(f"  CONFLICT {cp.canonical_id}: {v['h']}")
                    if apply:
                        row = _row(session, cp)
                        if row.height_mm is None:
                            reason = f"pages disagree ({v['h']})" if conflict else "no height stated"
                            row.notes = f"{CHECKED_MARKER} {date.today().isoformat()}: {reason}."
                    continue

                row = session.scalar(select(CoolerSpecs).where(CoolerSpecs.canonical_id == cp.canonical_id))
                old = row.height_mm if row else None
                if old == height:
                    continue
                if old is not None:
                    stats["changed"] += 1
                    print(f"  CHANGE {cp.canonical_id}: {old} -> {height}")
                else:
                    stats["filled"] += 1
                    print(f"  {cp.canonical_id[:56]:58} height={height}")
                if apply:
                    row = _row(session, cp)
                    row.height_mm = height
                    row.notes = ("Height read from retailer product page: " + "; ".join(v["src"]))[:2000]
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


def fill_cooler_height(limit: int | None = 20) -> None:
    """Scheduled entry point: new or unchecked air coolers only, most-listed first."""
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
