"""
Stage 2 - Groq LLM CPU Cooler Compatibility/Rating Spec Extraction (per UNIQUE model, batched).
cooler_type/radiator_size_mm already come from cooler_title_extractions (Stage 1,
per-listing identity) via CompatibilityEngine's merge fallback - this stage only
fills fan_size_mm/supported_sockets/tdp_rating, which are genuinely new fields.
Re-runnable: only processes canonical_ids that don't have a cooler_specs row yet, unless --all.
"""
import argparse
import sys
import time

from sqlalchemy import select

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy.orm import Session

from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart
from db.models.category_specs import CoolerSpecs
from services.groq_extraction_service import (
    GroqExtractionService, GroqExtractionError, COOLER_SPEC_BATCH_PROMPT,
    MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL,
    as_int, as_str,
)


def clean_model_name(cp: CanonicalPart) -> str:
    kf = cp.key_fields or {}
    parts = [kf.get("brand", ""), kf.get("model_number", "")]
    return " ".join(p for p in parts if p).strip()


def grounded_input(session: Session, cp: CanonicalPart, sample_count: int = 2) -> str:
    titles = session.scalars(
        select(Product.name).where(Product.canonical_id == cp.canonical_id).limit(sample_count)
    ).all()
    titles_json = ", ".join(f'"{t}"' for t in titles) if titles else ""
    return f'Identity: "{clean_model_name(cp)}" | Listings: [{titles_json}]'


def extract_cooler_specs(reprocess_all: bool = False, limit: int | None = None, batch_size: int = 6, sleep_s: float = 0.0):
    with SessionLocal() as session, GroqExtractionService(api_key=MISTRAL_API_KEY, model=MISTRAL_MODEL, api_url=MISTRAL_API_URL) as groq:
        print("=" * 80)
        print("GROQ LLM COOLER SPEC EXTRACTION - Stage 2 (per unique model, batched)")
        print("=" * 80)

        stmt = select(CanonicalPart).where(CanonicalPart.category == "cooler")
        if not reprocess_all:
            already_done = select(CoolerSpecs.canonical_id)
            stmt = stmt.where(CanonicalPart.canonical_id.notin_(already_done))
        if limit:
            stmt = stmt.limit(limit)

        canonical_parts = session.scalars(stmt).all()
        total = len(canonical_parts)
        print(f"Found {total} unique Cooler models needing spec extraction (reprocess_all={reprocess_all}).")

        ok_count = 0
        fail_count = 0
        confidence_counts = {"high": 0, "medium": 0, "low": 0}
        processed = 0

        for batch_start in range(0, total, batch_size):
            batch = canonical_parts[batch_start:batch_start + batch_size]
            inputs = [grounded_input(session, cp) for cp in batch]

            try:
                results = groq.extract_batch(COOLER_SPEC_BATCH_PROMPT, inputs)
            except GroqExtractionError as e:
                print(f"[batch @ {batch_start}] FAILED entire batch of {len(batch)}: {e}")
                for cp in batch:
                    existing = session.scalar(select(CoolerSpecs).where(CoolerSpecs.canonical_id == cp.canonical_id))
                    if existing is None:
                        existing = CoolerSpecs(canonical_id=cp.canonical_id, status="pending")
                        session.add(existing)
                    existing.status = "failed"
                    existing.error = str(e)[:2000]
                    fail_count += 1
                session.commit()
                processed += len(batch)
                continue

            for cp, result in zip(batch, results):
                existing = session.scalar(select(CoolerSpecs).where(CoolerSpecs.canonical_id == cp.canonical_id))
                if existing is None:
                    existing = CoolerSpecs(canonical_id=cp.canonical_id, status="pending")
                    session.add(existing)

                parsed = result["parsed"]
                existing.brand = cp.key_fields.get("brand") if cp.key_fields else None
                existing.fan_size_mm = as_int(parsed.get("fan_size_mm"))
                existing.supported_sockets = as_str(parsed.get("supported_sockets"))
                existing.tdp_rating = as_int(parsed.get("tdp_rating"))
                existing.confidence = as_str(parsed.get("confidence"))
                existing.notes = as_str(parsed.get("notes"))
                existing.llm_model = result["model"]
                existing.raw_response = result["raw_response"]
                existing.status = "ok"
                existing.error = None

                conf = parsed.get("confidence")
                if conf == "low":
                    session.execute(
                        Product.__table__.update()
                        .where(Product.canonical_id == cp.canonical_id)
                        .values(spec_status="needs_review")
                    )
                else:
                    session.execute(
                        Product.__table__.update()
                        .where(Product.canonical_id == cp.canonical_id, Product.spec_status == "pending")
                        .values(spec_status="extracted")
                    )

                ok_count += 1
                if conf in confidence_counts:
                    confidence_counts[conf] += 1

            session.commit()
            processed += len(batch)

            print(f"[{processed}/{total}] ok={ok_count} fail={fail_count} | last: '{clean_model_name(batch[-1])}' -> "
                  f"sockets={results[-1]['parsed'].get('supported_sockets')} tdp={results[-1]['parsed'].get('tdp_rating')}W "
                  f"({results[-1]['parsed'].get('confidence')})")

            if sleep_s:
                time.sleep(sleep_s)

        print("=" * 80)
        print("STAGE 2 COMPLETE")
        print(f"  Unique models processed: {processed}")
        print(f"  Succeeded:                {ok_count}")
        print(f"  Failed:                   {fail_count}")
        print(f"  Confidence breakdown:     {confidence_counts}")
        print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 2: extract Cooler compatibility/rating specs per unique model via Groq LLM (batched).")
    parser.add_argument("--all", action="store_true", help="Reprocess all canonical Cooler models, including ones already extracted.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of unique models processed (for testing).")
    parser.add_argument("--batch-size", type=int, default=6, help="Models per Groq API call.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between batch API calls.")
    args = parser.parse_args()

    extract_cooler_specs(reprocess_all=args.all, limit=args.limit, batch_size=args.batch_size, sleep_s=args.sleep)
