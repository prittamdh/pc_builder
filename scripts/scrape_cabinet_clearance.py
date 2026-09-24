"""
Fill cabinet clearances (max GPU length, max CPU cooler height) from retailer product pages.

Titles almost never carry these numbers, but most retailer pages reproduce the
manufacturer's spec table - a 2026-09-24 probe found them on 5 of the 6 stores that
served a page (PCStudio returns 403). The LLM reads only the text around clearance terms
and must return a verbatim quote for every number; a value whose quote is not on the page
is discarded (see matching.cabinet_clearance). Up to --pages pages per model are read and
must agree, otherwise the model is reported as a conflict and left alone.

Rows marked "Web-verified" (scripts/seed_cabinet_clearance.py) are never touched. Any other
existing value - including earlier LLM recall - is replaced when a page states otherwise,
and the change is printed.

Dry-run by default. Pass --apply to write.
"""
import argparse
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select

from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart
from db.models.category_specs import CabinetSpecs
from matching.cabinet_clearance import (
    COOLER_RANGE_MM, GPU_RANGE_MM, is_grounded, resolve_votes, snippets_for_llm,
)
from scrapers.http_client import HttpClient
from services.groq_extraction_service import GroqExtractionError, default_service

sys.path.insert(0, "scripts")
from scrape_psu_efficiency import strip_html  # noqa: E402

BLOCKED_HOSTS = ("pcstudio.in",)

PROMPT = """Each input is a PC cabinet's listing title plus text excerpts from its retailer product page.
Report the cabinet's maximum supported graphics card length and maximum CPU cooler height, in millimetres.
Return STRICT JSON only: {"results": [{"index": number, "max_gpu_length_mm": number|null, "gpu_quote": string|null, "max_cooler_height_mm": number|null, "cooler_quote": string|null}, ...]}
CRITICAL: "index" MUST equal the input's number (1-based). One result per input.
Rules:
- Use ONLY what the excerpt states. Never use your own knowledge of the case. No statement -> null.
- Each quote must be copied VERBATIM from the excerpt (a short span, 5-80 characters) and must contain the number.
- If several GPU lengths are given (e.g. with and without a front radiator), report the SMALLEST.
- Ignore radiator sizes (240mm/360mm), fan sizes, and the case's own height/width/depth.
- Ignore any other product's specs that appear in the excerpt.
- Convert cm to mm (40 cm -> 400)."""


def live_case_models(session, recheck: bool):
    listings = (
        select(Product.canonical_id, func.count().label("n"))
        .where(Product.canonical_id.like("case:%"))
        .group_by(Product.canonical_id)
        .subquery()
    )
    stmt = (
        select(CanonicalPart, listings.c.n)
        .join(listings, listings.c.canonical_id == CanonicalPart.canonical_id)
        .outerjoin(CabinetSpecs, CabinetSpecs.canonical_id == CanonicalPart.canonical_id)
        .where(func.coalesce(CabinetSpecs.notes, "").notlike("Web-verified%"))
        .order_by(listings.c.n.desc())
    )
    if not recheck:
        stmt = stmt.where(CabinetSpecs.max_gpu_length_mm.is_(None))
    return session.execute(stmt).all()


def fetch_pages(session, client, cid: str, pages: int, sleep_s: float) -> list[tuple[Product, str, str]]:
    """(product, page_text, snippet) for up to `pages` listings whose page mentions clearance terms."""
    out = []
    for product in session.scalars(select(Product).where(Product.canonical_id == cid)):
        if len(out) >= pages:
            break
        url = product.product_url or ""
        if not url or any(h in url for h in BLOCKED_HOSTS):
            continue
        try:
            html = getattr(client.get(url), "text", "") or ""
        except Exception:
            continue
        finally:
            if sleep_s:
                time.sleep(sleep_s)
        text = strip_html(html)
        snippet = snippets_for_llm(text)
        if snippet:
            out.append((product, text, snippet))
    return out


def main(limit, pages, apply, recheck, sleep_s, batch_size):
    with SessionLocal() as session, HttpClient() as client, default_service() as llm:
        models = live_case_models(session, recheck)
        if limit:
            models = models[:limit]
        print("=" * 78)
        print(f"CABINET CLEARANCE FROM PRODUCT PAGES {'(APPLY)' if apply else '(DRY RUN)'}")
        print(f"  models to check: {len(models)}")
        print("=" * 78)

        stats = dict(filled_gpu=0, filled_cooler=0, changed=0, no_statement=0, conflicts=0, ungrounded=0, failed=0)

        for i in range(0, len(models), batch_size):
            batch = models[i:i + batch_size]
            jobs = []  # (canonical_part, product, page_text)
            inputs = []
            for cp, _n in batch:
                for product, text, snippet in fetch_pages(session, client, cp.canonical_id, pages, sleep_s):
                    jobs.append((cp, product, text))
                    inputs.append(f'TITLE: {product.name} | EXCERPT: {snippet}')
            if not inputs:
                stats["no_statement"] += len(batch)
                continue

            try:
                results = llm.extract_batch(PROMPT, inputs)
            except GroqExtractionError as e:
                print(f"  batch @ {i} failed: {e}")
                stats["failed"] += len(batch)
                continue

            votes: dict[str, dict] = {}
            for (cp, product, text), res in zip(jobs, results):
                p = res["parsed"]
                v = votes.setdefault(cp.canonical_id, {"cp": cp, "gpu": [], "cooler": [], "src": [], "model": res["model"]})
                gpu, cooler = p.get("max_gpu_length_mm"), p.get("max_cooler_height_mm")
                if gpu is not None:
                    if is_grounded(gpu, p.get("gpu_quote"), text, GPU_RANGE_MM):
                        v["gpu"].append(gpu)
                        v["src"].append(f"{product.product_url} \"{p.get('gpu_quote')}\"")
                    else:
                        stats["ungrounded"] += 1
                if cooler is not None:
                    if is_grounded(cooler, p.get("cooler_quote"), text, COOLER_RANGE_MM):
                        v["cooler"].append(cooler)
                    else:
                        stats["ungrounded"] += 1

            for cp, _n in batch:
                v = votes.get(cp.canonical_id)
                if not v or not (v["gpu"] or v["cooler"]):
                    stats["no_statement"] += 1
                    continue
                gpu, gpu_conflict = resolve_votes(v["gpu"])
                cooler, cooler_conflict = resolve_votes(v["cooler"])
                if gpu_conflict or cooler_conflict:
                    stats["conflicts"] += 1
                    print(f"  CONFLICT {cp.canonical_id}: gpu={v['gpu']} cooler={v['cooler']}")
                if gpu is None and cooler is None:
                    continue

                row = session.scalar(select(CabinetSpecs).where(CabinetSpecs.canonical_id == cp.canonical_id))
                old = (row.max_gpu_length_mm, row.max_cooler_height_mm) if row else (None, None)
                new = (gpu if gpu is not None else old[0], cooler if cooler is not None else old[1])
                if old == new:
                    continue
                if any(o is not None and o != n for o, n in zip(old, new)):
                    stats["changed"] += 1
                    print(f"  CHANGE {cp.canonical_id}: {old} -> {new}")
                else:
                    print(f"  {cp.canonical_id[:52]:54} gpu={new[0]} cooler={new[1]}")
                stats["filled_gpu"] += gpu is not None and old[0] is None
                stats["filled_cooler"] += cooler is not None and old[1] is None

                if apply:
                    if row is None:
                        row = CabinetSpecs(canonical_id=cp.canonical_id)
                        session.add(row)
                        row.brand = (cp.key_fields or {}).get("brand")
                    row.max_gpu_length_mm, row.max_cooler_height_mm = new
                    row.confidence = "high" if len(v["gpu"]) > 1 else "medium"
                    row.notes = ("Read from retailer product page: " + "; ".join(v["src"]))[:2000]
                    row.llm_model = v["model"]
                    row.status = "ok"
                    row.error = None
            if apply:
                session.commit()
            print(f"  [{min(i + batch_size, len(models))}/{len(models)}] {stats}")

        print("=" * 78)
        for k, val in stats.items():
            print(f"  {k:14} {val}")
        print("=" * 78)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pages", type=int, default=2, help="Pages per model to read and cross-check.")
    ap.add_argument("--recheck", action="store_true", help="Also re-read models that already have a GPU value.")
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--batch-size", type=int, default=4, help="Models per LLM call.")
    a = ap.parse_args()
    main(a.limit, a.pages, a.apply, a.recheck, a.sleep, a.batch_size)
