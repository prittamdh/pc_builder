"""
Motherboard Identity Extraction (per listing, batched, Groq LLM).
Extracts brand/chipset/model_number from each raw Motherboard listing title.
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
from db.models.motherboard_title_extraction import MotherboardTitleExtraction
from matching.canonical_key_builder import (
    make_canonical_key_string, disambiguate_failed_key, build_motherboard_key_dict,
    resolve_motherboard_form_factor,
)
from matching.motherboard_identity import reconcile_group_form_factors
from services.groq_extraction_service import (
    GroqExtractionService, GroqExtractionError, MOTHERBOARD_IDENTITY_BATCH_PROMPT,
    MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL,
)


def extract_motherboard_identity(reprocess_all: bool = False, limit: int | None = None, batch_size: int = 6, sleep_s: float = 0.0):
    with SessionLocal() as session, GroqExtractionService(api_key=MISTRAL_API_KEY, model=MISTRAL_MODEL, api_url=MISTRAL_API_URL) as groq:
        print("=" * 80)
        print("GROQ LLM MOTHERBOARD IDENTITY EXTRACTION (per listing, batched)")
        print("=" * 80)

        stmt = select(Product).where(Product.p_category == "Motherboard")
        if not reprocess_all:
            stmt = stmt.where(Product.canonical_id.is_(None))
        if limit:
            stmt = stmt.limit(limit)

        products = session.scalars(stmt).all()
        total = len(products)
        print(f"Found {total} Motherboard products needing identity extraction (reprocess_all={reprocess_all}).")

        ok_count = 0
        fail_count = 0
        confidence_counts = {"high": 0, "medium": 0, "low": 0}
        processed = 0
        canonical_cache: dict[str, CanonicalPart] = {}

        for batch_start in range(0, total, batch_size):
            batch = products[batch_start:batch_start + batch_size]
            titles = [p.name for p in batch]

            try:
                results = groq.extract_batch(MOTHERBOARD_IDENTITY_BATCH_PROMPT, titles)
            except GroqExtractionError as e:
                print(f"[batch @ {batch_start}] FAILED entire batch of {len(batch)}: {e}")
                for product in batch:
                    product.spec_status = "failed"
                    extraction = session.scalar(select(MotherboardTitleExtraction).where(MotherboardTitleExtraction.product_id == product.id))
                    if extraction is None:
                        extraction = MotherboardTitleExtraction(product_id=product.id, raw_title=product.name)
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

                # The designation is recovered from the title rather than taken from the
                # model, so B850 / B850I / B850M-P stay distinct canonical models even
                # when the model normalizes the variant letter away.
                key_dict = build_motherboard_key_dict(
                    parsed.get("brand"), parsed.get("chipset"),
                    parsed.get("model_number"), product.name,
                )
                key_dict = disambiguate_failed_key(key_dict, product.id)
                canonical_id = make_canonical_key_string("motherboard", key_dict)

                cp = canonical_cache.get(canonical_id)
                if cp is None:
                    cp = session.scalar(select(CanonicalPart).where(CanonicalPart.canonical_id == canonical_id))
                if cp is None:
                    cp = CanonicalPart(
                        canonical_id=canonical_id,
                        category="motherboard",
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

                extraction = session.scalar(select(MotherboardTitleExtraction).where(MotherboardTitleExtraction.product_id == product.id))
                if extraction is None:
                    extraction = MotherboardTitleExtraction(product_id=product.id, raw_title=product.name)
                    session.add(extraction)
                extraction.raw_title = product.name
                extraction.canonical_id = canonical_id
                extraction.brand = parsed.get("brand")
                # Store the recovered designation, not the model's normalized chipset, so
                # this column agrees with the canonical key (raw value stays in raw_response).
                extraction.chipset = key_dict["chipset"] or parsed.get("chipset")
                extraction.model_number = parsed.get("model_number")
                extraction.socket = parsed.get("socket")
                extraction.memory_type = parsed.get("memory_type")
                # Prefer evidence (variant letter / literal title text) over the model's
                # guess; reconcile_group_form_factors() then makes the group agree.
                extraction.form_factor = (
                    resolve_motherboard_form_factor(key_dict["chipset"], product.name)
                    or parsed.get("form_factor")
                )
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
                  f"{results[-1]['parsed'].get('brand')} / {results[-1]['parsed'].get('chipset')} / "
                  f"{results[-1]['parsed'].get('socket')} / {results[-1]['parsed'].get('memory_type')} / "
                  f"{results[-1]['parsed'].get('form_factor')} ({results[-1]['parsed'].get('confidence')})")

            if sleep_s:
                time.sleep(sleep_s)

        # A canonical group is one physical SKU, so it must carry one form factor.
        stats = reconcile_group_form_factors(session, list(canonical_cache.keys()) or None)
        session.commit()
        print(f"Form-factor reconciliation: {stats}")

        print("=" * 80)
        print("EXTRACTION COMPLETE")
        print(f"  Total processed:      {processed}")
        print(f"  Succeeded:            {ok_count}")
        print(f"  Failed:               {fail_count}")
        print(f"  Confidence breakdown: {confidence_counts}")
        print(f"  Unique canonical IDs seen this run: {len(canonical_cache)}")
        print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract Motherboard identity via Groq LLM (batched).")
    parser.add_argument("--all", action="store_true", help="Reprocess all Motherboard products, including ones with a canonical_id already.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of products processed (for testing).")
    parser.add_argument("--batch-size", type=int, default=6, help="Titles per Groq API call.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between batch API calls.")
    args = parser.parse_args()

    extract_motherboard_identity(reprocess_all=args.all, limit=args.limit, batch_size=args.batch_size, sleep_s=args.sleep)
