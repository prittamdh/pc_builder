"""
Resolve missing PSU efficiency ratings by reading the retailer product pages.

Titles frequently omit the rating even though the product page states it plainly, and
neither certification database covers everything: Cybenetics doesn't test the budget
Indian brands, and rebrands like Ant Esports hold their 80 PLUS certificate under the
ODM's name in the official registry. The page itself is the remaining source.

Extraction is regex-first because "80 Plus Bronze" is a distinctive, unambiguous
string - no model is needed to read it, and a deterministic match can't hallucinate.
The LLM is only consulted when the page mentions 80 PLUS but the regex can't pin the
tier, which is rare. A page that simply doesn't state a rating yields nothing, since
the unit may genuinely be uncertified.

Multiple listings usually back one canonical model; they're tried in turn until one
page answers, and a disagreement between pages is reported rather than silently
resolved.
"""
import argparse
import re
import sys
import time
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart
from db.models.category_specs import PSUSpecs
from scrapers.http_client import HttpClient

TIERS = ("TITANIUM", "PLATINUM", "GOLD", "SILVER", "BRONZE", "WHITE", "STANDARD")
TIER_LABEL = {
    "TITANIUM": "80+ Titanium", "PLATINUM": "80+ Platinum", "GOLD": "80+ Gold",
    "SILVER": "80+ Silver", "BRONZE": "80+ Bronze",
    "WHITE": "80+ White", "STANDARD": "80+ White",
}

# "80 Plus Gold", "80+ Gold", "80PLUS Gold", "Gold 80 Plus", "80 PLUS® Gold Certified"
_NEAR = r"80\s*[-+]?\s*PLUS|80\s*\+"
RATING_PATTERNS = [
    re.compile(rf"(?:{_NEAR})[^A-Za-z0-9]{{0,12}}({'|'.join(TIERS)})", re.IGNORECASE),
    re.compile(rf"({'|'.join(TIERS)})[^A-Za-z0-9]{{0,12}}(?:{_NEAR})", re.IGNORECASE),
]
MENTIONS_80PLUS = re.compile(_NEAR, re.IGNORECASE)

MODULARITY_PATTERNS = [
    (re.compile(r"\bfully[\s-]*modular\b|\bfull[\s-]*modular\b", re.I), "Full"),
    (re.compile(r"\bsemi[\s-]*modular\b", re.I), "Semi"),
    (re.compile(r"\bnon[\s-]*modular\b", re.I), "Non"),
]


def strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def parse_rating(text: str, model_token: str | None = None) -> str | None:
    """Find the tier, but only when it plainly belongs to *this* product.

    Retailer pages carry related-product carousels, "customers also bought" strips and
    cross-sell blocks, all full of other PSUs and their ratings. A whole-page regex
    happily reads those: a first pass had an Ant Esports "Value Series" unit come back
    as 80+ Gold from a neighbouring listing. So when the page repeats the product's own
    model number, the tier is only accepted if it sits near one of those mentions.
    """
    # An anchor is mandatory. Falling back to a whole-page match produced real damage:
    # entries whose identity extraction had failed (no model number) picked up a tier
    # from a cross-sell strip, and two of them weren't power supplies at all - a
    # Sennheiser soundbar and a Marshall speaker, mis-categorised into Power Supply,
    # both landed a confident rating off a page carrying three different tiers.
    if not model_token or len(model_token) < 4:
        return None

    positions = [m.start() for m in re.finditer(re.escape(model_token), text, re.IGNORECASE)]
    if not positions:
        return None

    # Take the tier physically CLOSEST to the model mention, not merely the first one
    # inside the window. Taking the first match read "Corsair RM850x 80 Plus Gold" from
    # a related-products line that preceded the product's own "VS700L 700W 80+ Bronze".
    best: tuple[int, str] | None = None
    for pos in positions:
        start, end = max(0, pos - 220), pos + 220
        window = text[start:end]
        anchor_in_window = pos - start
        for pattern in RATING_PATTERNS:
            for m in pattern.finditer(window):
                distance = abs(m.start() - anchor_in_window)
                label = TIER_LABEL.get(m.group(1).upper())
                if label and (best is None or distance < best[0]):
                    best = (distance, label)
    return best[1] if best else None


def parse_modularity(text: str) -> str | None:
    for pattern, label in MODULARITY_PATTERNS:
        if pattern.search(text):
            return label
    return None


def ask_llm(title: str, snippet: str) -> str | None:
    """Only used when a page mentions 80 PLUS but the tier can't be matched."""
    try:
        from services.groq_extraction_service import (
            GroqExtractionService, GroqExtractionError,
            MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL,
        )
    except Exception:
        return None

    prompt = (
        'Read the power-supply page text and report its 80 PLUS efficiency tier.\n'
        'Return STRICT JSON only: {"results": [{"index": 1, "efficiency_rating": '
        '"80+ Titanium"|"80+ Platinum"|"80+ Gold"|"80+ Silver"|"80+ Bronze"|"80+ White"|null}]}\n'
        'Use only what the text states. If it does not clearly state a tier, return null - '
        'the unit may genuinely be uncertified, and a guess here is worse than no answer.\n'
    )
    try:
        with GroqExtractionService(api_key=MISTRAL_API_KEY, model=MISTRAL_MODEL, api_url=MISTRAL_API_URL) as svc:
            out = svc.extract_batch(prompt, [f'"{title}" | PAGE: {snippet[:1500]}'])
        value = (out[0]["parsed"] or {}).get("efficiency_rating")
        return value if value in TIER_LABEL.values() else None
    except Exception:
        return None


def main(limit: int | None, dry_run: bool, sleep_s: float, use_llm: bool) -> None:
    with SessionLocal() as session, HttpClient() as client:
        specs = session.scalars(select(PSUSpecs).where(PSUSpecs.efficiency_rating.is_(None))).all()
        if limit:
            specs = specs[:limit]
        print("=" * 78)
        print(f"SCRAPE PSU EFFICIENCY FROM PRODUCT PAGES {'(DRY RUN)' if dry_run else ''}")
        print(f"  models missing a rating: {len(specs)}")
        print("=" * 78)

        resolved = unresolved = conflicts = llm_used = 0

        for spec in specs:
            products = session.scalars(
                select(Product).where(Product.canonical_id == spec.canonical_id)
            ).all()

            # The canonical model number anchors extraction to this product's own
            # section of the page rather than a neighbouring cross-sell block.
            spec_key_model = None
            cp_row = session.scalar(
                select(CanonicalPart).where(CanonicalPart.canonical_id == spec.canonical_id)
            )
            if cp_row and cp_row.key_fields:
                spec_key_model = cp_row.key_fields.get("model_number")

            votes: Counter = Counter()
            modularity_votes: Counter = Counter()
            sources: dict[str, str] = {}

            for product in products:
                if not product.product_url:
                    continue
                try:
                    resp = client.get(product.product_url)
                    html = getattr(resp, "text", "") or ""
                except Exception:
                    continue
                if not html:
                    continue

                text = strip_html(html)
                model_token = (spec_key_model or "").strip()
                rating = parse_rating(text, model_token)
                if rating is None and use_llm and MENTIONS_80PLUS.search(text):
                    rating = ask_llm(product.name, text)
                    if rating:
                        llm_used += 1

                if rating:
                    votes[rating] += 1
                    sources.setdefault(rating, product.product_url)
                mod = parse_modularity(text)
                if mod:
                    modularity_votes[mod] += 1

                if sleep_s:
                    time.sleep(sleep_s)

            if not votes:
                unresolved += 1
                continue

            if len(votes) > 1:
                conflicts += 1
                print(f"  CONFLICT {spec.canonical_id}: {dict(votes)} - taking the majority")

            rating, _ = votes.most_common(1)[0]
            resolved += 1
            print(f"  {spec.canonical_id[:46]:48} -> {rating}")

            if not dry_run:
                spec.efficiency_rating = rating
                if modularity_votes and not spec.modularity:
                    spec.modularity = modularity_votes.most_common(1)[0][0]
                spec.confidence = "high" if len(votes) == 1 else "medium"
                spec.notes = f"Read from retailer product page ({sources.get(rating, '')})."
                spec.status = "ok"

        if not dry_run:
            session.commit()

        print("=" * 78)
        print(f"  resolved:   {resolved}")
        print(f"  unresolved: {unresolved} (page states no rating - may be genuinely uncertified)")
        print(f"  conflicts:  {conflicts}")
        print(f"  llm assists:{llm_used}")
        print("=" * 78)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Scrape PSU efficiency ratings from retailer product pages.")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.4, help="Delay between page fetches.")
    ap.add_argument("--no-llm", action="store_true", help="Regex only.")
    args = ap.parse_args()
    main(args.limit, args.dry_run, args.sleep, use_llm=not args.no_llm)
