"""
Stage 2 - Groq LLM Monitor Display Spec Extraction (per UNIQUE model, batched).
Runs once per distinct canonical_id (not once per listing). Screen size/resolution/
refresh rate/panel type/response time are almost always stated explicitly in retail
titles, so this is grounded text extraction, not memory recall - much lower
hallucination risk than CPU physical specs.
Re-runnable: only processes canonical_ids that don't have a monitor_specs row yet, unless --all.
"""
import argparse
import sys
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart
from db.models.category_specs import MonitorSpecs
from services.groq_extraction_service import (
    GroqExtractionService, GroqExtractionError, MONITOR_SPEC_BATCH_PROMPT,
    MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL,
    as_int, as_float, as_str,
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


def extract_monitor_specs(reprocess_all: bool = False, limit: int | None = None, batch_size: int = 6, sleep_s: float = 0.0):
    with SessionLocal() as session, GroqExtractionService(api_key=MISTRAL_API_KEY, model=MISTRAL_MODEL, api_url=MISTRAL_API_URL) as groq:
        print("=" * 80)
        print("GROQ LLM MONITOR SPEC EXTRACTION - Stage 2 (per unique model, batched)")
        print("=" * 80)

        stmt = select(CanonicalPart).where(CanonicalPart.category == "monitor")
        if not reprocess_all:
            already_done = select(MonitorSpecs.canonical_id)
            stmt = stmt.where(CanonicalPart.canonical_id.notin_(already_done))
        if limit:
            stmt = stmt.limit(limit)

        canonical_parts = session.scalars(stmt).all()
        total = len(canonical_parts)
        print(f"Found {total} unique Monitor models needing spec extraction (reprocess_all={reprocess_all}).")

        ok_count = 0
        fail_count = 0
        confidence_counts = {"high": 0, "medium": 0, "low": 0}
        processed = 0

        for batch_start in range(0, total, batch_size):
            batch = canonical_parts[batch_start:batch_start + batch_size]
            inputs = [grounded_input(session, cp) for cp in batch]

            try:
                results = groq.extract_batch(MONITOR_SPEC_BATCH_PROMPT, inputs)
            except GroqExtractionError as e:
                print(f"[batch @ {batch_start}] FAILED entire batch of {len(batch)}: {e}")
                for cp in batch:
                    existing = session.scalar(select(MonitorSpecs).where(MonitorSpecs.canonical_id == cp.canonical_id))
                    if existing is None:
                        existing = MonitorSpecs(canonical_id=cp.canonical_id, status="pending")
                        session.add(existing)
                    existing.status = "failed"
                    existing.error = str(e)[:2000]
                    fail_count += 1
                session.commit()
                processed += len(batch)
                continue

            for cp, result in zip(batch, results):
                existing = session.scalar(select(MonitorSpecs).where(MonitorSpecs.canonical_id == cp.canonical_id))
                if existing is None:
                    existing = MonitorSpecs(canonical_id=cp.canonical_id, status="pending")
                    session.add(existing)

                parsed = result["parsed"]
                existing.brand = cp.key_fields.get("brand") if cp.key_fields else None
                existing.model_number = cp.key_fields.get("model_number") if cp.key_fields else None
                existing.screen_size_inch = as_float(parsed.get("screen_size_inch"))
                existing.resolution = as_str(parsed.get("resolution"))
                existing.refresh_rate_hz = as_int(parsed.get("refresh_rate_hz"))
                existing.panel_type = as_str(parsed.get("panel_type"))
                existing.response_time_ms = as_float(parsed.get("response_time_ms"))
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
                  f"{results[-1]['parsed'].get('screen_size_inch')}in {results[-1]['parsed'].get('resolution')} "
                  f"{results[-1]['parsed'].get('refresh_rate_hz')}Hz ({results[-1]['parsed'].get('confidence')})")

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
    parser = argparse.ArgumentParser(description="Stage 2: extract Monitor display specs per unique model via Groq LLM (batched).")
    parser.add_argument("--all", action="store_true", help="Reprocess all canonical Monitor models, including ones already extracted.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of unique models processed (for testing).")
    parser.add_argument("--batch-size", type=int, default=6, help="Models per Groq API call.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between batch API calls.")
    args = parser.parse_args()

    extract_monitor_specs(reprocess_all=args.all, limit=args.limit, batch_size=args.batch_size, sleep_s=args.sleep)
