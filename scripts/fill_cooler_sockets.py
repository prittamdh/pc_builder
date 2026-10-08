"""Propose each listed cooler model's supported sockets from the AI's knowledge.

The regular cooler spec step (COOLER_SPEC_BATCH_PROMPT) only takes sockets a title
states, and titles rarely do: 21 of 564 listed coolers had them (2026-10-08). This asks
for the manufacturer's published list per model, allows "unknown", and writes proposals
to a JSON file for the owner to review. Nothing is written to the database here; the
reviewed values ship as a migration, marked as AI-filled.

    python scripts/fill_cooler_sockets.py out.json [--limit N]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api.filters import has_usable_price, is_listed
from db.models.category_specs import CoolerSpecs
from db.models.cooler_title_extraction import CoolerTitleExtraction
from db.models.product import Product
from db.session import SessionLocal
from matching.cooler_sockets import normalize_sockets
from services.groq_extraction_service import GroqExtractionError, default_service

PROMPT = """For each CPU cooler model you get its identity and 1-2 real retailer listing titles. Give the CPU sockets the MANUFACTURER lists as supported for that exact model (its mounting kit), from the titles or from what you reliably know of the model.
Return STRICT JSON only: {"results": [{"index": number, "sockets": string|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input model's number (1-based). One result per input, exact count.
sockets: comma list like "LGA1851,LGA1700,LGA1200,LGA115X,AM5,AM4". Use null if you do not know this exact model - a wrong list would tell a shopper an incompatible cooler fits, so null beats a guess. Do not assume the newest sockets (LGA1851, AM5) for an older model unless you know it supports them.
confidence: high = stated in a title or you know the published spec; medium = you know the product line's usual kit; low = unsure (then sockets should usually be null). notes: short reason when not high.

Models (2 total, respond with exactly 2 results):
1. "Deepcool AK620" | ["Deepcool AK620 Dual Tower CPU Air Cooler, 260W TDP"]
2. "Ant Esports ICE-C612" | ["Ant Esports ICE-C612 CPU Air Cooler"]
{"results": [{"index": 1, "sockets": "LGA1700,LGA1200,LGA115X,AM5,AM4", "confidence": "high", "notes": null}, {"index": 2, "sockets": "LGA1700,LGA1200,LGA115X,AM5,AM4", "confidence": "medium", "notes": "line's standard kit"}]}
"""


def models_needing_sockets(session):
    rows = session.execute(
        select(Product.canonical_id, Product.name, CoolerTitleExtraction.brand,
               CoolerTitleExtraction.model_number, CoolerSpecs.supported_sockets)
        .outerjoin(CoolerTitleExtraction, CoolerTitleExtraction.product_id == Product.id)
        .outerjoin(CoolerSpecs, CoolerSpecs.canonical_id == Product.canonical_id)
        .where(Product.p_category == "CPU Cooler", is_listed(), has_usable_price(),
               Product.canonical_id.is_not(None))
    ).all()
    models = defaultdict(lambda: {"titles": [], "identity": None, "has": False})
    for cid, name, brand, model, sockets in rows:
        m = models[cid]
        m["titles"].append(name)
        if brand and model and not m["identity"]:
            m["identity"] = f"{brand} {model}"
        m["has"] = m["has"] or bool(sockets)
    todo = {cid: m for cid, m in models.items() if not m["has"]}
    # Most-listed first: they matter most and are best known.
    return sorted(todo.items(), key=lambda kv: -len(kv[1]["titles"]))


def main(out: Path, limit: int | None, batch_size: int = 8):
    with SessionLocal() as session, default_service() as llm:
        todo = models_needing_sockets(session)[:limit]
        print(f"{len(todo)} cooler models without sockets")
        results = {}
        for start in range(0, len(todo), batch_size):
            batch = todo[start:start + batch_size]
            inputs = [f'{m["identity"] or m["titles"][0]}" | {json.dumps(m["titles"][:2], ensure_ascii=False)}'
                      for _, m in batch]
            try:
                answers = llm.extract_batch(PROMPT, inputs)
            except GroqExtractionError as e:
                print(f"batch @{start} failed: {e}")
                continue
            for (cid, m), a in zip(batch, answers):
                p = a["parsed"]
                results[cid] = {
                    "identity": m["identity"], "titles": m["titles"], "raw": p.get("sockets"),
                    "sockets": normalize_sockets(p.get("sockets")), "confidence": p.get("confidence"),
                    "notes": p.get("notes"), "llm_model": a["model"],
                }
            out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"{min(start + batch_size, len(todo))}/{len(todo)}")
        filled = sum(1 for r in results.values() if r["sockets"])
        print(f"done: {filled} of {len(results)} got sockets")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    main(args.out, args.limit)
