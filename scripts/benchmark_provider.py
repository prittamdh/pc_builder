"""
Score a PSU-title-extraction provider against a fixed, independently-verified answer
key (AI-01), so the provider chain (and, in Phase 8, a locally-hosted model on the
same machine) can be compared on the same terms.

WRITES NOTHING TO THE DATABASE. This script never imports db.session (directly or
indirectly) and never calls the DB-hint prompt builder that appends live catalogue
brand names to the prompt - only the bare PSU_IDENTITY_BATCH_PROMPT constant. This
is the same Stage 1 identity prompt production uses (services.groq_extraction_
service.identity_prompt('psu')), minus only the brand-hint block that prompt appends
from live DB data - the benchmark deliberately measures the Stage 1 identity call's
efficiency_rating field (the tier as read off the retailer title), never Stage 2's
PSU_SPEC_BATCH_PROMPT (which extracts modularity from a clean model name + listing
pair, a different call entirely). Dropping the brand-hint block keeps a run fully
reproducible and needing no database at all (useful for the Phase 8 desktop trial,
which has none).

How the case list was built: the original 2026-09-20 benchmark's 8 titles/answers
were never committed anywhere (see .planning/phases/01-launch-hardening/01-RESEARCH.md,
"Reconstructing the AI-01 benchmark") - only the aggregate "8/8" scores survive in
PROGRESS.md prose. This list was rebuilt from scratch on 2026-09-25 from real,
currently-catalogued product titles (read from the live `products` table, read-only).
Every case's expected answer is independently verified against either the 80 PLUS
official registry export (data/raw/All_certified_psus.xlsx, via
scripts.import_80plus_efficiency's loader) or the manufacturer's own product page -
never from this project's own LLM extractions, which would be circular (see Pitfall 9
in 01-RESEARCH.md). Evidence quotes the registry's Manufacturer/Model #/Voltage/
Wattage/Certified Date/Rating fields verbatim, cell by cell - not the brand aliases
scripts.import_80plus_efficiency.norm_brand() maps them to for matching purposes.
See each case's "evidence" field for its specific source.

One candidate was dropped as pure redundancy, and one deliberately excluded case
type was considered and rejected:
  - MSI MAG A850GL PCIE5 (850W): dropped because it repeats the exact same trap as
    the locked MSI MAG A750GL PCIE5 case (the "GL" suffix, same brand, same model
    line, only the wattage differs) - kept out to make room for MSI MAG A650BN
    below without exceeding 8.
  - An untiered (expected-None) case: no catalogued PSU title could be confirmed
    absent from *both* the registry and a manufacturer page (search results were
    inconclusive), so per the owner's rule ("if absence can't be confirmed from both
    sources, don't include an untiered case"), none is included.

Final case count: 8 (all independently verified; see CASE_COUNT below).

Usage:
    python scripts/benchmark_provider.py --provider mistral
    python scripts/benchmark_provider.py --provider google --runs 2
    python scripts/benchmark_provider.py --url http://localhost:1234/v1/chat/completions \\
        --model local-model --key-env-optional

Read-only, makes provider API calls, prints results, exits. No --apply, no DB access.
"""
import argparse
import os
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from services.groq_extraction_service import (  # noqa: E402
    GroqExtractionError, GroqExtractionService, PSU_IDENTITY_BATCH_PROMPT,
    ProviderExhausted, provider_chain,
)

# --- Answer key ---------------------------------------------------------------------
#
# Every "evidence" string names its source verbatim (registry row or manufacturer
# URL + quote) and the date it was checked, per the owner's rule that a locked case
# must never be verified from memory or from this project's own extraction tables.

CASES = [
    {
        "title": "Super Flower LEADEX III GOLD UP ATX 3.1 750W Cybenetics Platinum Certified Gold SMPS Power Supply",
        "expected": "80+ Gold",
        "trap": "Title states both a Cybenetics tier (Platinum) and an 80 PLUS tier "
                "(Gold) - the model must report the 80 PLUS tier and not let the "
                "Cybenetics rating (a different certification body) override it.",
        "evidence": (
            "Manufacturer page https://www.super-flower.com.tw/products-detail/LIII-G/ "
            "(checked 2026-09-25): 750W variant listed with 'model no.: SF-750F14GE' and "
            "'80 PLUS Gold Certified'. Cross-checked in data/raw/All_certified_psus.xlsx "
            "(verbatim row): Manufacturer 'Super Flower', Model # 'SF-750F14GE', "
            "Voltage '115V Internal', Wattage 750, Certified Date '10/28/2016', "
            "Rating 'Gold' - both sources agree on Gold, independent of this project's "
            "own extraction tables."
        ),
    },
    {
        "title": "MSI MAG A750GL PCIE5 ATX 3.1 Fully Modular SMPS MAG-A750GL-PCIE5",
        "expected": "80+ Gold",
        "trap": "MSI's 'GL' model-name suffix means Gold; the title never spells out "
                "a tier word at all, so the model must infer it from the suffix.",
        "evidence": (
            "80 PLUS registry (data/raw/All_certified_psus.xlsx, checked 2026-09-25) "
            "has two verbatim rows for this model line, both agreeing on Gold: "
            "Manufacturer 'Micro-Star International Co., Ltd.', Model # 'MAG A750GL', "
            "Voltage '115V Internal', Wattage 750, Certified Date '12/19/2019', Rating "
            "'Gold'; and Manufacturer 'Micro-Star International Co., Ltd.', Model # "
            "'MAG A750GL PCIE5' (same certified date, same voltage/wattage), Rating "
            "'Gold' - exact model+wattage match, unambiguous."
        ),
    },
    {
        "title": "Corsair RM750E 750 Watt Cybenetics Gold Fully Modular ATX 3.1 Power Supply (CP-9020295-IN)",
        "expected": None,
        "trap": "Cybenetics-only title: the true 80 PLUS tier (Gold, registry) must "
                "NOT be reported because the title does not state it; an answer of "
                "Gold means Cybenetics leakage or recall.",
        "evidence": (
            "The product's real 80 PLUS certification IS Gold - 80 PLUS registry "
            "(data/raw/All_certified_psus.xlsx, checked 2026-09-25), two verbatim rows: "
            "Manufacturer 'Corsair', Model # 'RPS0177 (CP-9020262) (RM750e)', Voltage "
            "'115V Internal', Wattage 750, Certified Date '08/29/2023', Rating 'Gold'; "
            "and Manufacturer 'Corsair', Model # 'RPS0147 (CP-9020248) (RM750e)', "
            "same voltage/wattage, Certified Date '04/19/2021', Rating 'Gold'. But the "
            "catalog title names only a Cybenetics rating ('Cybenetics Gold') and no "
            "80 PLUS tier at all, and PSU_IDENTITY_BATCH_PROMPT (groq_extraction_"
            "service.py:275) instructs the model to ignore Cybenetics and return null "
            "when no 80 PLUS tier is determinable from the title. Per the grounding "
            "rule, the model must not recall the tier from memory just because it "
            "happens to be true - so the correct extraction from THIS title is null, "
            "even though the product itself is Gold."
        ),
    },
    {
        "title": "Cooler Master MWE Gold 850 V3 850 Watt 80 Plus Gold ATX 3.1 Full Modular PSU",
        "expected": "80+ Gold",
        "trap": "The tier word ('Gold') is the manufacturer's own model-name marker, "
                "not just marketing copy elsewhere in the title - the documented "
                "'manufacturer's own marker' case.",
        "evidence": (
            "Manufacturer page https://www.coolermaster.com/en-global/products/"
            "mwe-gold-850-v3-atx-3-1.html (checked 2026-09-25): spec table shows "
            "'80 PLUS Rating' / '80 PLUS Gold'. (Not independently locatable in the "
            "registry export: Cooler Master's registry rows are keyed by internal SKU "
            "codes such as 'RS-850-AFBA-G1', not the 'MWE' marketing name, so the "
            "manufacturer's own page is used per the plan's fallback rule.)"
        ),
    },
    {
        "title": "Gigabyte P550SS 550 Watt 80 Plus Silver Power Supply (GP-P550SS)",
        "expected": "80+ Silver",
        "trap": "Silver-tier diversity case, and a different wattage/SKU from the "
                "'80 PLUS Silver' few-shot example already in the prompt (GIGABYTE "
                "P650SS) so it is not a memorized answer.",
        "evidence": (
            "80 PLUS registry (data/raw/All_certified_psus.xlsx, checked 2026-09-25), "
            "verbatim row: Manufacturer 'Gigabyte', Model # 'GP-P550SS', Voltage "
            "'230V EU Internal', Wattage 550, Certified Date '03/22/2024', Rating "
            "'Silver' - exact model+wattage match. The registry row is a 230V EU "
            "certification rather than a 115V one, but the catalog title's own text "
            "already states '80 Plus Silver' directly, so the title itself grounds "
            "the answer regardless of which regional certification the registry row "
            "reflects."
        ),
    },
    {
        "title": "MSI MAG A650BN 650 Watt 80 Plus Bronze Power Supply",
        "expected": "80+ Bronze",
        "trap": "MSI's 'BN' model-name suffix means Bronze (also stated directly in "
                "production's PSU_IDENTITY_BATCH_PROMPT, groq_extraction_service.py:275, "
                "as manufacturer-marker evidence); the registry also carries a later, "
                "higher-tier '230V EU Internal' Silver certification for the same "
                "model number, which is a documented EU-market re-certification "
                "uplift, not the retail box tier this title (and the 115V US "
                "certification) reflect.",
        "evidence": (
            "80 PLUS registry (data/raw/All_certified_psus.xlsx, checked 2026-09-25), "
            "verbatim row: Manufacturer 'Micro-Star International Co., Ltd.', Model # "
            "'MAG A650BN', Voltage '115V Internal', Wattage 650, Certified Date "
            "'04/10/2013', Rating 'Bronze' - matches the retail tier this title states. "
            "A second row for the identical model number, Voltage '230V EU Internal', "
            "Certified Date '03/31/2023', Rating 'Silver', exists in the same registry "
            "- PROGRESS.md's 2026-09-24 audit ('Revisited 2026-09-24 - keep gap-fill-"
            "only') documents this exact pattern generally: 'the registry also lists "
            "230V EU internal certifications a tier above the retail box rating' - so "
            "the 115V Bronze row, not the later 230V Silver row, is the correct answer "
            "for this retail-market title."
        ),
    },
    {
        "title": "SilverStone Strider Platinum SST ST1200 PTS 1200W Fully Modular 80 Plus ATX Power Supply",
        "expected": "80+ Platinum",
        "trap": "Platinum-tier diversity case at a high wattage; title states the "
                "tier explicitly, testing plain extraction rather than inference.",
        "evidence": (
            "80 PLUS registry (data/raw/All_certified_psus.xlsx, checked 2026-09-25), "
            "verbatim row: Manufacturer 'SilverStone Technology Inc.', Model # "
            "'SST-1200-PTS', Voltage '115V Internal', Wattage 1200, Certified Date "
            "'12/07/2018', Rating 'Platinum' - exact model+wattage match (a second row "
            "'SST-ST1200-PTS', same date/voltage/wattage, also agrees on Platinum)."
        ),
    },
    {
        "title": "CORSAIR AX1600i 1600W 80+ Titanium Fully Modular Power Supply",
        "expected": "80+ Titanium",
        "trap": "Titanium-tier diversity case (the highest 80 PLUS tier) at a very "
                "high wattage - checks the model doesn't cap out at Platinum for "
                "flagship units.",
        "evidence": (
            "80 PLUS registry (data/raw/All_certified_psus.xlsx, checked 2026-09-25), "
            "verbatim row: Manufacturer 'Corsair', Model # 'RPS0036 (CP-9020087) "
            "(AX1600i)', Voltage '115V Internal', Wattage 1600, Certified Date "
            "'01/03/2018', Rating 'Titanium' - exact model+wattage match, single row."
        ),
    },
]

CASE_COUNT = len(CASES)

# --- Rating normalization -------------------------------------------------------

_TIER_PREFIX_RE = re.compile(r"^80\s*(?:\+|plus)\s*", re.IGNORECASE)


def normalize_rating(value):
    """
    Normalizes an efficiency-rating string for comparison. "80 PLUS Gold", "80+ gold",
    " 80Plus  GOLD " all normalize to the same value. None, "", and "null" (any case)
    all normalize to None ("no tier").
    """
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text or text.lower() == "null":
        return None
    text = _TIER_PREFIX_RE.sub("80+ ", text)
    return text.lower()


# --- Scoring ---------------------------------------------------------------------

def score_results(cases, results) -> tuple[int, int]:
    """
    Compares results (extract_batch's return shape) against cases by the parsed
    "index" field (1-based), not array position. A missing or unparseable entry for
    a case's index counts as wrong and as one JSON failure. Returns (correct, json_failures).
    """
    by_index = {}
    for entry in results or []:
        parsed = entry.get("parsed") if isinstance(entry, dict) else None
        idx = parsed.get("index") if isinstance(parsed, dict) else None
        if isinstance(idx, int) and idx not in by_index:
            by_index[idx] = parsed

    correct = 0
    json_failures = 0
    for i, case in enumerate(cases, start=1):
        parsed = by_index.get(i)
        if parsed is None:
            json_failures += 1
            continue
        got = normalize_rating(parsed.get("efficiency_rating"))
        want = normalize_rating(case["expected"])
        if got == want:
            correct += 1
    return correct, json_failures


def run_benchmark(service, cases) -> dict:
    """
    Runs one extract_batch call with all case titles, timed with time.monotonic
    (elapsed covers only the provider call). Returns score/n/json_failures/titles_per_min.
    """
    titles = [c["title"] for c in cases]
    start = time.monotonic()
    results = service.extract_batch(PSU_IDENTITY_BATCH_PROMPT, titles)
    elapsed = time.monotonic() - start
    correct, json_failures = score_results(cases, results)
    titles_per_min = (len(titles) / elapsed * 60) if elapsed > 0 else float("inf")
    return {
        "score": correct,
        "n": len(cases),
        "json_failures": json_failures,
        "titles_per_min": titles_per_min,
        "elapsed": elapsed,
    }


# --- CLI ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.strip().splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--provider", default=None,
                     help="a name from provider_chain(), e.g. mistral, google, groq, cerebras")
    ap.add_argument("--url", default=None, help="OpenAI-compatible chat/completions URL")
    ap.add_argument("--model", default=None, help="model name for --url")
    ap.add_argument("--key-env", default=None,
                     help="environment variable name holding the API key for --url")
    ap.add_argument("--key-env-optional", action="store_true",
                     help="for keyless local servers: send a dummy placeholder key")
    ap.add_argument("--runs", type=int, default=1, help="number of benchmark runs (default 1)")
    args = ap.parse_args(argv)

    if args.runs < 1:
        print(f"benchmark_provider: --runs must be >= 1, got {args.runs}", file=sys.stderr)
        return 2

    if args.provider:
        chain = provider_chain()
        by_name = {c[0]: c for c in chain}
        entry = by_name.get(args.provider)
        if entry is None:
            names = sorted(by_name.keys())
            print(
                f"benchmark_provider: unknown or unavailable provider {args.provider!r}. "
                f"Available: {names}",
                file=sys.stderr,
            )
            return 2
        name, api_url, model, api_key = entry
    elif args.url and args.model and (args.key_env or args.key_env_optional):
        name = f"custom:{args.model}"
        api_url = args.url
        model = args.model
        api_key = None
        if args.key_env:
            api_key = os.environ.get(args.key_env)
        if not api_key:
            if args.key_env_optional:
                api_key = "local-placeholder-key"
            else:
                print(
                    f"benchmark_provider: environment variable {args.key_env} is not set",
                    file=sys.stderr,
                )
                return 2
    else:
        ap.print_usage(sys.stderr)
        print(
            "benchmark_provider: specify --provider NAME, or --url/--model plus "
            "--key-env/--key-env-optional",
            file=sys.stderr,
        )
        return 2

    try:
        service = GroqExtractionService(api_key=api_key, model=model, api_url=api_url)
    except GroqExtractionError as e:
        print(f"benchmark_provider: {e}", file=sys.stderr)
        return 1

    # Never let this run silently switch providers mid-benchmark - a benchmark must
    # fail loudly for the specific provider under test, not fall back to another one.
    service._fallbacks = []

    print(f"Provider: {name} ({model})")
    exit_code = 0
    try:
        for _ in range(args.runs):
            result = run_benchmark(service, CASES)
            print(f"Score: {result['score']}/{result['n']}")
            print(f"Titles/min: {result['titles_per_min']:.1f}")
            print(f"JSON failures: {result['json_failures']}")
    except (ProviderExhausted, GroqExtractionError) as e:
        print(f"benchmark_provider: {e}", file=sys.stderr)
        exit_code = 1
    finally:
        service.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
