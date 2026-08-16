"""
Power Supply (PSU) Identity Extraction (per listing, batched, Groq LLM).
Extracts brand/model_number/wattage/efficiency_rating from each raw PSU listing title.
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
from db.models.psu_title_extraction import PSUTitleExtraction
from matching.canonical_key_builder import make_canonical_key_string, disambiguate_failed_key
from services.groq_extraction_service import (
    GroqExtractionService, GroqExtractionError, PSU_IDENTITY_BATCH_PROMPT,
    MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL,
)


def extract_psu_identity(reprocess_all: bool = False, limit: int | None = None, batch_size: int = 6, sleep_s: float = 0.0):
    with SessionLocal() as session, GroqExtractionService(api_key=MISTRAL_API_KEY, model=MISTRAL_MODEL, api_url=MISTRAL_API_URL) as groq:
        print("=" * 80)
        print("GROQ LLM POWER SUPPLY IDENTITY EXTRACTION (per listing, batched)")
        print("=" * 80)

        stmt = select(Product).where(Product.p_category == "Power Supply")
        if not reprocess_all:
            stmt = stmt.where(Product.canonical_id.is_(None))
        if limit:
            stmt = stmt.limit(limit)

        products = session.scalars(stmt).all()
        total = len(products)
        print(f"Found {total} Power Supply products needing identity extraction (reprocess_all={reprocess_all}).")

        ok_count = 0
        fail_count = 0
        confidence_counts = {"high": 0, "medium": 0, "low": 0}
        processed = 0
        canonical_cache: dict[str, CanonicalPart] = {}

        for batch_start in range(0, total, batch_size):
            batch = products[batch_start:batch_start + batch_size]
            titles = [p.name for p in batch]

            try:
                results = groq.extract_batch(PSU_IDENTITY_BATCH_PROMPT, titles)
            except GroqExtractionError as e:
                print(f"[batch @ {batch_start}] FAILED entire batch of {len(batch)}: {e}")
                for product in batch:
                    product.spec_status = "failed"
                    extraction = session.scalar(select(PSUTitleExtraction).where(PSUTitleExtraction.product_id == product.id))
                    if extraction is None:
                        extraction = PSUTitleExtraction(product_id=product.id, raw_title=product.name)
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
                    "category": "psu",
                    "brand": parsed.get("brand") or "Unknown",
                    "model_number": parsed.get("model_number") or "",
                    "wattage": f"{parsed.get('wattage')}w" if parsed.get("wattage") else "",
                }
                key_dict = disambiguate_failed_key(key_dict, product.id)
                canonical_id = make_canonical_key_string("psu", key_dict)

                cp = canonical_cache.get(canonical_id)
                if cp is None:
                    cp = session.scalar(select(CanonicalPart).where(CanonicalPart.canonical_id == canonical_id))
                if cp is None:
                    cp = CanonicalPart(
                        canonical_id=canonical_id,
                        category="psu",
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

                extraction = session.scalar(select(PSUTitleExtraction).where(PSUTitleExtraction.product_id == product.id))
                if extraction is None:
                    extraction = PSUTitleExtraction(product_id=product.id, raw_title=product.name)
                    session.add(extraction)
                extraction.raw_title = product.name
                extraction.canonical_id = canonical_id
                extraction.brand = parsed.get("brand")
                extraction.model_number = parsed.get("model_number")
                extraction.wattage = parsed.get("wattage")
                extraction.efficiency_rating = parsed.get("efficiency_rating")
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
                  f"{results[-1]['parsed'].get('brand')} / {results[-1]['parsed'].get('model_number')} / "
                  f"{results[-1]['parsed'].get('wattage')}W ({results[-1]['parsed'].get('confidence')})")

            if sleep_s:
                time.sleep(sleep_s)

        print("=" * 80)
        print("EXTRACTION COMPLETE")
        print(f"  Total processed:      {processed}")
        print(f"  Succeeded:            {ok_count}")
        print(f"  Failed:               {fail_count}")
        print(f"  Confidence breakdown: {confidence_counts}")
        print(f"  Unique canonical IDs seen this run: {len(canonical_cache)}")
        print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract Power Supply identity via Groq LLM (batched).")
    parser.add_argument("--all", action="store_true", help="Reprocess all PSU products, including ones with a canonical_id already.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of products processed (for testing).")
    parser.add_argument("--batch-size", type=int, default=6, help="Titles per Groq API call.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between batch API calls.")
    args = parser.parse_args()

    extract_psu_identity(reprocess_all=args.all, limit=args.limit, batch_size=args.batch_size, sleep_s=args.sleep)
