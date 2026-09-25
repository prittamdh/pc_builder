"""
Audit whether PSU efficiency tiers stored in `psu_title_extractions.efficiency_rating`
are actually grounded in the listing's OWN title, per the rules the production prompt
(PSU_IDENTITY_BATCH_PROMPT / PSU_SPEC_BATCH_PROMPT in
src/services/groq_extraction_service.py) documents.

Why this exists: scripts/benchmark_provider.py found gemini-3.1-flash-lite (second in
provider_chain()) answering "80+ Gold" for a title that states only "Cybenetics Gold" -
the prompt explicitly says to ignore Cybenetics and never let it set the tier (a
different certification body, on its own scale, that frequently disagrees with 80
PLUS). Mistral (primary) answers null correctly on the same title. So wherever
extraction fell back past Mistral, a Cybenetics-only title may have produced a tier
with no textual basis in the title at all - a value from memory, which the project's
own rules forbid (see matching/cabinet_clearance.is_grounded for the same discipline
applied to cabinet clearances).

READ-ONLY. Runs the whole audit inside SET TRANSACTION READ ONLY (as in
scripts/measure_db_growth.py) and ends with rollback, never commit. Never updates,
never deletes, never fixes a row - any fix is the data owner's call.

Grounding rules (reused verbatim from the prompt text, not invented here):
  1. The title states the 80 PLUS tier directly - "80 PLUS Gold" / "80+ Gold" /
     "80Plus Gold" (any spacing/case) with the tier word near it.
  2. A tier word inside the MODEL NAME is the manufacturer's own documented marker,
     valid evidence even with no "80" wording at all: MSI "...GL" suffix = Gold,
     "...BN" suffix = Bronze; Super Flower "Leadex III Gold"; Cooler Master "MWE
     Gold".
  3. Cybenetics wording alone ("Cybenetics Gold", "Cybenetics Platinum Certified
     Gold") is explicitly NOT grounding, even though the tier word is literally on
     the page - the prompt says to ignore Cybenetics entirely because it is a
     different certification scheme that frequently disagrees with 80 PLUS.

Three report buckets:
  a) cybenetics_leak - title mentions Cybenetics, states no 80 PLUS wording anywhere,
     and no manufacturer model-name rule applies, yet a tier is stored. This is the
     exact leak the benchmark found.
  b) no_tier_wording - the stored tier's word does not appear anywhere in the title
     at all (not even via Cybenetics) - a candidate for pure recall from memory.
  c) grounded - for scale.
  (a small residual "other_ungrounded" bucket catches ungrounded rows that fit
  neither a) nor b) - e.g. the tier word appears as ordinary text unrelated to any
  80 PLUS/Cybenetics wording - so nothing is silently dropped from the count.)

Usage:
    python scripts/audit_psu_title_tier_grounding.py
    python scripts/audit_psu_title_tier_grounding.py --limit 50
"""
import argparse
import re
import sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from db.session import SessionLocal  # noqa: E402
from db.models.psu_title_extraction import PSUTitleExtraction  # noqa: E402
from db.models.category_specs import PSUSpecs  # noqa: E402

# --- Pure grounding logic -----------------------------------------------------------

# The 80 PLUS tiers, exactly as PSU_IDENTITY_BATCH_PROMPT / PSU_SPEC_BATCH_PROMPT
# enumerate them ("80+ White"|"80+ Bronze"|"80+ Silver"|"80+ Gold"|"80+ Platinum"|
# "80+ Titanium"). Deliberately NOT matching.canonical_key_builder's
# normalize_efficiency_trim(): that tuple omits "white" (it has "standard" instead,
# which is not one of the prompt's six tiers), so reusing it here would silently
# misclassify every White-tier row in this audit as having "no recognisable tier" -
# found while building this script against live data (Ant Esports VS500L/600L/700L
# and the Gigabyte Aorus Elite P1000W all carry "80+ White"). That is a separate,
# pre-existing gap in the canonical-key normalizer, out of scope for this read-only
# audit (this script and its test are the only files touched here) - worth a look by
# whoever owns matching/canonical_key_builder.py next.
_TIER_WORDS = ("titanium", "platinum", "gold", "silver", "bronze", "white")


def _extract_tier_word(stored_tier: str | None) -> str:
    """The bare tier word (lowercase) named by a stored efficiency_rating value, or ""
    if it names none of the prompt's six recognised tiers."""
    text = (stored_tier or "").strip().lower()
    for tier in _TIER_WORDS:
        if tier in text:
            return tier
    return ""

# "80 PLUS" / "80+" / "80Plus", any spacing or case. Deliberately does NOT require the
# literal word "PLUS" - "80+ Gold" is the far more common way titles spell this. The
# trailing \b only applies to the "plus" branch: "+" is a non-word character, so a "\b"
# placed right after it never matches when the next character is also non-word (e.g.
# the space in "80+ White") - that bug silently dropped every "80+ <tier>" title from
# this marker on a first pass and must not come back.
_EIGHTY_MARKER = re.compile(r"80\s*(?:\+|plus\b)", re.IGNORECASE)

# How close (in characters) an "80 ..." marker must sit to the tier word for the two
# to be read as naming the same rating, rather than two unrelated numbers/words that
# happen to share a title. Generous enough for "80 PLUS Gold Certified" or
# "80+ ATX 3.1 Gold", tight enough not to bridge an entire multi-clause title.
_PROXIMITY_CHARS = 40

# Manufacturer model-name markers documented in PSU_IDENTITY_BATCH_PROMPT /
# PSU_SPEC_BATCH_PROMPT verbatim - not invented here. Each maps a title pattern to the
# tier it is documented evidence for.
_MANUFACTURER_RULES: tuple[tuple[re.Pattern, str], ...] = (
    # MSI's own "GL"/"BN" model-number suffix (e.g. "MAG A750GL", "MAG A650BN").
    (re.compile(r"\bmsi\b.*\b[a-z]*\d{3,4}gl\b", re.IGNORECASE), "gold"),
    (re.compile(r"\bmsi\b.*\b[a-z]*\d{3,4}bn\b", re.IGNORECASE), "bronze"),
    # Super Flower "Leadex III Gold" - the documented trap case (Cybenetics Platinum
    # sits right next to it in the same title; the model name is what actually grounds
    # the 80 PLUS Gold tier).
    (re.compile(r"leadex\s+iii\s+gold", re.IGNORECASE), "gold"),
    # Cooler Master "MWE Gold" line.
    (re.compile(r"\bmwe\s+gold\b", re.IGNORECASE), "gold"),
)


def is_tier_grounded(title: str, stored_tier: str | None) -> tuple[bool, str]:
    """True only if `stored_tier`'s tier word is grounded in `title` itself.

    Returns (grounded, reason) - reason always names the specific mechanism (or lack
    of one) so a report can say *why*, not just yes/no.
    """
    tier = _extract_tier_word(stored_tier)
    if not tier:
        return False, "stored value has no recognisable 80 PLUS tier word"

    title = title or ""

    for pattern, rule_tier in _MANUFACTURER_RULES:
        if rule_tier == tier and pattern.search(title):
            return True, f"manufacturer model-name rule ({pattern.pattern!r})"

    eighty_spans = [m.span() for m in _EIGHTY_MARKER.finditer(title)]
    if eighty_spans:
        for m in re.finditer(re.escape(tier), title.lower()):
            t_start, t_end = m.span()
            for e_start, e_end in eighty_spans:
                if abs(t_start - e_end) <= _PROXIMITY_CHARS or abs(e_start - t_end) <= _PROXIMITY_CHARS:
                    return True, "80 PLUS wording near the tier word"

    return False, "no 80 PLUS wording near the tier word and no manufacturer rule matched"


def classify_row(title: str, stored_tier: str | None) -> str:
    """Buckets a row for the audit report: 'grounded', 'cybenetics_leak',
    'no_tier_wording', or 'other_ungrounded'.
    """
    grounded, _ = is_tier_grounded(title, stored_tier)
    if grounded:
        return "grounded"

    tier = _extract_tier_word(stored_tier)
    title_l = (title or "").lower()
    has_eighty = bool(_EIGHTY_MARKER.search(title_l))
    tier_word_present = bool(tier) and tier in title_l

    if "cybenetics" in title_l and not has_eighty:
        return "cybenetics_leak"
    if not tier_word_present:
        return "no_tier_wording"
    return "other_ungrounded"


# --- Report ---------------------------------------------------------------------

_PSU_SPEC_SOURCE_REGISTRY = "80 PLUS official certification registry"
_PSU_SPEC_SOURCE_RETAILER = "Read from retailer product page"


def psu_spec_source(row: PSUSpecs) -> str:
    """Where a psu_specs.efficiency_rating value came from, for the same honesty
    check applied to the title-extraction table: LLM-derived values are exactly what
    this audit is checking for grounding; registry/retailer-page values are grounded
    elsewhere (fine, not part of this audit's concern)."""
    if row is None or row.efficiency_rating is None:
        return "no rating stored"
    if row.llm_model:
        return f"LLM-derived ({row.llm_model})"
    notes = row.notes or ""
    if _PSU_SPEC_SOURCE_REGISTRY in notes:
        return "80 PLUS registry (grounded elsewhere)"
    if _PSU_SPEC_SOURCE_RETAILER in notes:
        return "retailer product page (grounded elsewhere)"
    return "unattributed (no llm_model, no recognised notes source)"


def main(limit: int) -> None:
    with SessionLocal() as session:
        # Read-only for the whole audit: a write anywhere in this transaction would
        # error instead of silently committing.
        session.execute(_ro())
        try:
            rows = session.scalars(
                select(PSUTitleExtraction).where(
                    PSUTitleExtraction.efficiency_rating.is_not(None)
                )
            ).all()

            buckets: dict[str, list[PSUTitleExtraction]] = {
                "grounded": [], "cybenetics_leak": [], "no_tier_wording": [],
                "other_ungrounded": [],
            }
            for row in rows:
                bucket = classify_row(row.raw_title, row.efficiency_rating)
                buckets[bucket].append(row)

            provider_counts_a = Counter(r.llm_model or "unrecorded" for r in buckets["cybenetics_leak"])
            provider_counts_b = Counter(r.llm_model or "unrecorded" for r in buckets["no_tier_wording"])

            print("=" * 88)
            print("PSU TITLE TIER GROUNDING AUDIT (read-only)")
            print("=" * 88)
            print(f"Total psu_title_extractions rows with a stored tier: {len(rows)}")
            print(f"  a) cybenetics_leak   : {len(buckets['cybenetics_leak'])}")
            print(f"  b) no_tier_wording   : {len(buckets['no_tier_wording'])}")
            print(f"  c) grounded          : {len(buckets['grounded'])}")
            print(f"  (other_ungrounded)   : {len(buckets['other_ungrounded'])}")
            print()

            print("Per-provider counts, bucket a) cybenetics_leak:")
            for provider, count in provider_counts_a.most_common():
                print(f"  {provider:30s} {count}")
            print()
            print("Per-provider counts, bucket b) no_tier_wording:")
            for provider, count in provider_counts_b.most_common():
                print(f"  {provider:30s} {count}")
            print()

            for label, key in (
                ("a) CYBENETICS LEAK", "cybenetics_leak"),
                ("b) NO TIER WORDING AT ALL", "no_tier_wording"),
                ("c) GROUNDED (sample)", "grounded"),
            ):
                print("-" * 88)
                print(f"{label} - {len(buckets[key])} rows, showing up to {limit}")
                print("-" * 88)
                for row in buckets[key][:limit]:
                    print(
                        f"  product_id={row.product_id:<8} canonical_id={row.canonical_id!s:<40} "
                        f"tier={row.efficiency_rating!r:<15} llm_model={row.llm_model!r}"
                    )
                    print(f"    title: {row.raw_title}")
                print()

            # psu_specs cross-check for canonical ids touched by an ungrounded row.
            ungrounded_canonical_ids = sorted({
                r.canonical_id for r in buckets["cybenetics_leak"] + buckets["no_tier_wording"]
                if r.canonical_id
            })
            specs_by_cid = {
                r.canonical_id: r for r in session.scalars(
                    select(PSUSpecs).where(PSUSpecs.canonical_id.in_(ungrounded_canonical_ids))
                )
            } if ungrounded_canonical_ids else {}

            print("=" * 88)
            print(f"psu_specs.efficiency_rating for the {len(ungrounded_canonical_ids)} canonical ids "
                  f"touched by an ungrounded title-extraction row:")
            print("=" * 88)
            source_counts = Counter()
            for cid in ungrounded_canonical_ids:
                spec = specs_by_cid.get(cid)
                source = psu_spec_source(spec)
                source_counts[source] += 1
                print(f"  {cid:45s} rating={spec.efficiency_rating if spec else None!r:<12} source={source}")
            print()
            print("Source counts:")
            for source, count in source_counts.most_common():
                print(f"  {source:55s} {count}")
        finally:
            session.rollback()


def _ro():
    from sqlalchemy import text
    return text("SET TRANSACTION READ ONLY")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=30,
        help="Max example rows to print per bucket (default 30).",
    )
    args = parser.parse_args()
    main(args.limit)
