"""
Stage 1 - Groq LLM CPU Identity Extraction (per listing, batched).
Extracts brand/series/model_number from each raw CPU listing title, computes a
canonical key, upserts a thin canonical_parts row, and stamps products.canonical_id.
Cheap and per-listing since titles genuinely vary (typos, truncation, word order).
Physical specs (TDP/cores/etc) are NOT extracted here - see extract_cpu_specs_groq.py
(Stage 2), which runs once per unique canonical_id instead of once per listing.
Re-runnable: skips products that already have a canonical_id unless --all.
"""
import argparse
import sys
import time

from sqlalchemy import select

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart
from db.models.cpu_title_extraction import CPUTitleExtraction
from matching.canonical_key_builder import make_canonical_key_string, disambiguate_failed_key
from services.groq_extraction_service import GroqExtractionService, GroqExtractionError, CPU_IDENTITY_BATCH_PROMPT


def extract_cpu_identity(reprocess_all: bool = False, limit: int | None = None, batch_size: int = 6, sleep_s: float = 0.0):
    with SessionLocal() as session, GroqExtractionService() as groq:
        print("=" * 80)
        print("GROQ LLM CPU IDENTITY EXTRACTION - Stage 1 (per listing, batched)")
        print("=" * 80)

        stmt = select(Product).where(Product.p_category == "CPU")
        if not reprocess_all:
            stmt = stmt.where(Product.canonical_id.is_(None))
        if limit:
            stmt = stmt.limit(limit)

        products = session.scalars(stmt).all()
        total = len(products)
        print(f"Found {total} CPU products needing identity extraction (reprocess_all={reprocess_all}).")

        ok_count = 0
        fail_count = 0
        confidence_counts = {"high": 0, "medium": 0, "low": 0}
        processed = 0
        canonical_cache: dict[str, CanonicalPart] = {}

        for batch_start in range(0, total, batch_size):
            batch = products[batch_start:batch_start + batch_size]
            titles = [p.name for p in batch]

            try:
                results = groq.extract_batch(CPU_IDENTITY_BATCH_PROMPT, titles)
            except GroqExtractionError as e:
                print(f"[batch @ {batch_start}] FAILED entire batch of {len(batch)}: {e}")
                for product in batch:
                    product.spec_status = "failed"
                    extraction = session.scalar(select(CPUTitleExtraction).where(CPUTitleExtraction.product_id == product.id))
                    if extraction is None:
                        extraction = CPUTitleExtraction(product_id=product.id, raw_title=product.name)
                        session.add(extraction)
                    extraction.status = "failed"
                    extraction.error = str(e)[:2000]
                    fail_count += 1
                session.commit()
                processed += len(batch)
                continue

            for product, result in zip(batch, results):
                parsed = result["parsed"]
                conf = parsed.get("confidence")

                key_dict = {
                    "category": "cpu",
                    "brand": parsed.get("brand") or "Unknown",
                    "series": parsed.get("series") or "",
                    "model_number": parsed.get("model_number") or "",
                }
                key_dict = disambiguate_failed_key(key_dict, product.id)
                canonical_id = make_canonical_key_string("cpu", key_dict)

                cp = canonical_cache.get(canonical_id)
                if cp is None:
                    cp = session.scalar(select(CanonicalPart).where(CanonicalPart.canonical_id == canonical_id))
                if cp is None:
                    cp = CanonicalPart(
                        canonical_id=canonical_id,
                        category="cpu",
                        brand=key_dict["brand"],
                        key_fields=key_dict,
                        from_title=[product.name],
                        status="NEEDS_REVIEW" if conf == "low" else "OK",
                    )
                    session.add(cp)
                    session.flush()
                canonical_cache[canonical_id] = cp

                product.canonical_id = canonical_id
                product.spec_status = "needs_review" if conf == "low" else "extracted"

                extraction = session.scalar(select(CPUTitleExtraction).where(CPUTitleExtraction.product_id == product.id))
                if extraction is None:
                    extraction = CPUTitleExtraction(product_id=product.id, raw_title=product.name)
                    session.add(extraction)
                extraction.raw_title = product.name
                extraction.canonical_id = canonical_id
                extraction.brand = parsed.get("brand")
                extraction.series = parsed.get("series")
                extraction.model_number = parsed.get("model_number")
                extraction.confidence = conf
                extraction.notes = parsed.get("notes")
                extraction.llm_model = result["model"]
                extraction.raw_response = result["raw_response"]
                extraction.status = "ok"
                extraction.error = None

                ok_count += 1
                if conf in confidence_counts:
                    confidence_counts[conf] += 1

            session.commit()
            processed += len(batch)

            print(f"[{processed}/{total}] ok={ok_count} fail={fail_count} | last: '{batch[-1].name[:55]}' -> "
                  f"{results[-1]['parsed'].get('brand')} / {results[-1]['parsed'].get('series')} / "
                  f"{results[-1]['parsed'].get('model_number')} ({results[-1]['parsed'].get('confidence')})")

            if sleep_s:
                time.sleep(sleep_s)

        print("=" * 80)
        print("STAGE 1 COMPLETE")
        print(f"  Total processed:      {processed}")
        print(f"  Succeeded:            {ok_count}")
        print(f"  Failed:               {fail_count}")
        print(f"  Confidence breakdown: {confidence_counts}")
        print(f"  Unique canonical IDs seen this run: {len(canonical_cache)}")
        print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 1: extract CPU identity (brand/series/model_number) via Groq LLM (batched).")
    parser.add_argument("--all", action="store_true", help="Reprocess all CPU products, including ones with a canonical_id already.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of products processed (for testing).")
    parser.add_argument("--batch-size", type=int, default=6, help="Titles per Groq API call.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between batch API calls.")
    args = parser.parse_args()

    extract_cpu_identity(reprocess_all=args.all, limit=args.limit, batch_size=args.batch_size, sleep_s=args.sleep)
