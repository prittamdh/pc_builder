"""
Groq LLM RAM Title Extraction Batch Script.
Runs GroqExtractionService in batched mode over all RAM category products' raw titles,
upserting brand/series/capacity/speed/CL results into ram_title_extractions.
Re-runnable: skips products already extracted unless --all is passed.
"""
import argparse
import sys
import time

from sqlalchemy import select

# Windows console (cp1252) can't encode characters like the double-prime symbol
# that sometimes appears in scraped titles (e.g. inch marks) - degrade gracefully
# instead of crashing mid-batch.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.session import SessionLocal
from db.models.product import Product
from db.models.ram_title_extraction import RAMTitleExtraction
from services.groq_extraction_service import (
    GroqExtractionService, GroqExtractionError, RAM_BATCH_SYSTEM_PROMPT,
    MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL,
)


def extract_ram_titles(reprocess_all: bool = False, limit: int | None = None, batch_size: int = 8, sleep_s: float = 0.0):
    with SessionLocal() as session, GroqExtractionService(api_key=MISTRAL_API_KEY, model=MISTRAL_MODEL, api_url=MISTRAL_API_URL) as groq:
        print("=" * 80)
        print("GROQ LLM RAM TITLE EXTRACTION (batched)")
        print("=" * 80)

        stmt = select(Product).where(Product.p_category == "RAM")
        if not reprocess_all:
            already_done = select(RAMTitleExtraction.product_id).where(RAMTitleExtraction.status == "ok")
            stmt = stmt.where(Product.id.notin_(already_done))
        if limit:
            stmt = stmt.limit(limit)

        products = session.scalars(stmt).all()
        total = len(products)
        print(f"Found {total} RAM products to process in batches of {batch_size} (reprocess_all={reprocess_all}).")

        ok_count = 0
        fail_count = 0
        confidence_counts = {"high": 0, "medium": 0, "low": 0}
        processed = 0

        for batch_start in range(0, total, batch_size):
            batch = products[batch_start:batch_start + batch_size]
            titles = [p.name for p in batch]

            try:
                results = groq.extract_batch(RAM_BATCH_SYSTEM_PROMPT, titles)
            except GroqExtractionError as e:
                print(f"[batch @ {batch_start}] FAILED entire batch of {len(batch)}: {e}")
                for product in batch:
                    existing = session.scalar(select(RAMTitleExtraction).where(RAMTitleExtraction.product_id == product.id))
                    if existing is None:
                        existing = RAMTitleExtraction(product_id=product.id, raw_title=product.name, status="pending")
                        session.add(existing)
                    existing.raw_title = product.name
                    existing.status = "failed"
                    existing.error = str(e)[:2000]
                    product.spec_status = "failed"
                    fail_count += 1
                session.commit()
                processed += len(batch)
                continue

            for product, result in zip(batch, results):
                existing = session.scalar(select(RAMTitleExtraction).where(RAMTitleExtraction.product_id == product.id))
                if existing is None:
                    existing = RAMTitleExtraction(product_id=product.id, raw_title=product.name, status="pending")
                    session.add(existing)

                parsed = result["parsed"]
                existing.raw_title = product.name
                existing.brand = parsed.get("brand")
                existing.series = parsed.get("series")
                existing.memory_type = parsed.get("memory_type")
                existing.modules = parsed.get("modules")
                existing.capacity_per_module_gb = parsed.get("capacity_per_module_gb")
                existing.capacity_gb = parsed.get("capacity_gb")
                existing.speed_mhz = parsed.get("speed_mhz")
                existing.cl_timing = parsed.get("cl_timing")
                existing.form_factor = parsed.get("form_factor")
                existing.confidence = parsed.get("confidence")
                existing.notes = parsed.get("notes")
                existing.llm_model = result["model"]
                existing.raw_response = result["raw_response"]
                existing.status = "ok"
                existing.error = None

                conf = parsed.get("confidence")
                product.spec_status = "needs_review" if conf == "low" else "extracted"

                ok_count += 1
                if conf in confidence_counts:
                    confidence_counts[conf] += 1

            session.commit()
            processed += len(batch)

            print(f"[{processed}/{total}] ok={ok_count} fail={fail_count} | last: '{batch[-1].name[:55]}' -> "
                  f"{results[-1]['parsed'].get('brand')} / {results[-1]['parsed'].get('capacity_gb')}GB / "
                  f"{results[-1]['parsed'].get('speed_mhz')}MHz ({results[-1]['parsed'].get('confidence')})")

            if sleep_s:
                time.sleep(sleep_s)

        print("=" * 80)
        print("EXTRACTION COMPLETE")
        print(f"  Total processed:  {processed}")
        print(f"  Succeeded:        {ok_count}")
        print(f"  Failed:           {fail_count}")
        print(f"  Confidence breakdown: {confidence_counts}")
        print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract RAM title identity fields via Groq LLM (batched).")
    parser.add_argument("--all", action="store_true", help="Reprocess all RAM products, including already-extracted ones.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of products processed (for testing).")
    parser.add_argument("--batch-size", type=int, default=8, help="Titles per Groq API call.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between batch API calls.")
    args = parser.parse_args()

    extract_ram_titles(reprocess_all=args.all, limit=args.limit, batch_size=args.batch_size, sleep_s=args.sleep)
