"""The catalog stages the scheduler runs after prices come in (moved from
dags/scheduled_scraper_dag.py in plan 02-03; the Airflow DAG and the worker both call
these).

Strictly ordered when run together: identities key the spec tables, and the catalog
policy reads the spec fields.
"""
import sys
from pathlib import Path

from db.session import SessionLocal
from pipeline.checks import backlog_snapshot, check_extraction_progress, count_extraction_progress, state_of

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def execute_canonical_extraction(limit_per_category: int = 15):
    """Runs incremental LLM-based canonical identity extraction (Mistral) for newly-scraped
    products across all 9 tracked categories. Each extractor already defaults to processing
    only products missing a canonical_id, so this is safe to run every DAG cycle without
    reprocessing existing work or overrunning the free-tier rate limit (~9 categories x a
    couple of small batches per run, well under Mistral's 50 RPM)."""
    scripts_path = SCRIPTS_DIR
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))

    from extract_cpu_titles_groq import extract_cpu_identity
    from extract_motherboard_titles_groq import extract_motherboard_identity
    from extract_gpu_titles_groq import extract_gpu_identity
    from extract_storage_titles_groq import extract_storage_identity
    from extract_psu_titles_groq import extract_psu_identity
    from extract_cooler_titles_groq import extract_cooler_identity
    from extract_cabinet_titles_groq import extract_cabinet_identity
    from extract_monitor_titles_groq import extract_monitor_identity
    from extract_ram_titles_groq import extract_ram_titles
    from wire_ram_canonical import wire_ram_canonical

    runners = [
        ("CPU", extract_cpu_identity),
        ("Motherboard", extract_motherboard_identity),
        ("GPU", extract_gpu_identity),
        ("Storage", extract_storage_identity),
        ("Power Supply", extract_psu_identity),
        ("CPU Cooler", extract_cooler_identity),
        ("Cabinet", extract_cabinet_identity),
        ("Monitor", extract_monitor_identity),
    ]

    for label, fn in runners:
        try:
            fn(limit=limit_per_category)
        except Exception as e:
            print(f"[Canonical Extraction] {label} failed: {e}")

    try:
        extract_ram_titles(limit=limit_per_category)
        wire_ram_canonical()
    except Exception as e:
        print(f"[Canonical Extraction] RAM failed: {e}")


def execute_physical_spec_extraction(limit_per_category: int = 10):
    """Stage 2: fill physical specs for canonical models that don't have them yet.

    Runs after identity extraction, since every one of these keys off canonical_id.
    Each extractor skips models that already have a spec row, so a steady-state cycle
    does almost nothing; the small per-category limit keeps a burst of newly-scraped
    products from overrunning Mistral's free tier.

    RAM and Storage need no API calls at all - their identity extraction already
    captures everything their spec tables hold - so they run unlimited.
    """
    scripts_path = SCRIPTS_DIR
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))

    from extract_cpu_specs_groq import extract_cpu_specs
    from extract_monitor_specs_groq import extract_monitor_specs
    from extract_gpu_specs_groq import extract_gpu_specs
    from extract_motherboard_specs_groq import extract_motherboard_specs
    from extract_psu_specs_groq import extract_psu_specs
    from extract_cooler_specs_groq import extract_cooler_specs
    from extract_cabinet_specs_groq import extract_cabinet_specs
    from populate_ram_specs_from_extractions import populate_ram_specs
    from populate_ssd_specs_from_extractions import populate_ssd_specs

    llm_runners = [
        ("CPU", extract_cpu_specs),
        ("Monitor", extract_monitor_specs),
        ("GPU", extract_gpu_specs),
        ("Motherboard", extract_motherboard_specs),
        ("Power Supply", extract_psu_specs),
        ("CPU Cooler", extract_cooler_specs),
        ("Cabinet", extract_cabinet_specs),
    ]
    for label, fn in llm_runners:
        try:
            fn(limit=limit_per_category)
        except Exception as e:
            print(f"[Spec Extraction] {label} failed: {e}")

    for label, fn in (("RAM", populate_ram_specs), ("Storage", populate_ssd_specs)):
        try:
            fn()
        except Exception as e:
            print(f"[Spec Extraction] {label} failed: {e}")

    # Cabinet clearances come from retailer product pages, not titles. Runs after the
    # title-based cabinet pass so any clearance a title states explicitly is already in.
    try:
        from scrape_cabinet_clearance import fill_cabinet_clearance
        fill_cabinet_clearance(limit=limit_per_category)
    except Exception as e:
        print(f"[Spec Extraction] Cabinet clearance failed: {e}")

    # Air-cooler heights, likewise from product pages - what the cooler clearance rule reads.
    try:
        from scrape_cooler_height import fill_cooler_height
        fill_cooler_height(limit=limit_per_category)
    except Exception as e:
        print(f"[Spec Extraction] Cooler height failed: {e}")

    # Cabinet radiator support, for the AIO radiator-fit rule.
    try:
        from scrape_cabinet_radiators import fill_cabinet_radiators
        fill_cabinet_radiators(limit=limit_per_category)
    except Exception as e:
        print(f"[Spec Extraction] Cabinet radiators failed: {e}")


def execute_catalog_policy():
    """Re-apply the supported-platform policy and the catalog data-quality fixes.

    Without this the cleanup decays: every scrape can introduce a pre-10th-gen CPU, a
    DDR3 kit, an external USB drive or a cabinet whose form factor reads "Mid Tower",
    and each would be offered in the builder until someone re-ran these by hand. Both
    scripts are idempotent and make no API calls, so running them every cycle is cheap.

    Runs last because it reads the spec fields the two stages above populate.
    """
    scripts_path = SCRIPTS_DIR
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))

    from classify_legacy_products import classify
    from fix_catalog_data_quality import main as fix_data_quality
    from build_brand_registry import main as build_brand_registry

    try:
        classify(dry_run=False)
    except Exception as e:
        print(f"[Catalog Policy] legacy classification failed: {e}")

    try:
        fix_data_quality(dry_run=False)
    except Exception as e:
        print(f"[Catalog Policy] data-quality fixes failed: {e}")

    # Refresh the brand hints Stage 1 reads. Rebuilt after extraction, not before, so
    # every brand named confidently this cycle becomes a hint on the terse listings of
    # the same make next cycle - recognition of India-market brands improves instead of
    # staying flat. One grouped query, no API calls.
    try:
        build_brand_registry(apply=True)
    except Exception as e:
        print(f"[Catalog Policy] brand registry rebuild failed: {e}")


def execute_canonical_extraction_checked(limit_per_category: int | None = None):
    """Runs execute_canonical_extraction, then fails loudly if it made no progress on a
    non-empty backlog (OPS-06). Snapshot and re-read use separate sessions so the check
    survives rows deleted mid-run.

    limit_per_category defaults to None so the DAG's no-argument call passes through to
    execute_canonical_extraction's own default (15) instead of silently overriding it
    with a smaller number; pass an explicit value to override.
    """
    with SessionLocal() as session:
        before = backlog_snapshot(session)

    effective_limit = limit_per_category if limit_per_category is not None else 15
    execute_canonical_extraction(limit_per_category=effective_limit)

    with SessionLocal() as session:
        after = state_of(session, before.keys())

    progress = count_extraction_progress(before, after)
    print(f"[Canonical Extraction] backlog_before={len(before)} progress={progress}")
    check_extraction_progress(len(before), progress)
