"""Copy attributes the title extractors already produced into the `*_specs` tables.

Stage 1 (title extraction) has been writing socket, form factor, memory type, wattage
and cooler type for a long time. Stage 2 (`*_specs`) is what the catalog's spec filters
and `/products/facets` read, and several of its columns were never filled from stage 1
at all - `motherboard_specs.socket` was 0% populated across 1,213 rows while
`motherboard_title_extractions.socket` had the value all along.

Nothing surfaced this because `CompatibilityEngine` reads the extraction tables
directly, so the builder worked while the catalog silently offered no motherboard
filters at all.

Fills gaps only by default; --overwrite replaces values that are already set.

    python scripts/populate_specs_from_extractions.py
    python scripts/populate_specs_from_extractions.py --only Motherboard --dry-run
"""
import argparse
import sys
from collections import Counter

from sqlalchemy import select

from db.session import SessionLocal
from db.models.cabinet_title_extraction import CabinetTitleExtraction
from db.models.category_specs import (
    CabinetSpecs,
    CoolerSpecs,
    CPUSpecs,
    GPUSpecs,
    MotherboardSpecs,
    PSUSpecs,
    RAMSpecs,
    SSDSpecs,
)
from db.models.category_specs import MonitorSpecs
from db.models.cooler_title_extraction import CoolerTitleExtraction
from db.models.monitor_title_extraction import MonitorTitleExtraction
from db.models.cpu_title_extraction import CPUTitleExtraction
from db.models.gpu_title_extraction import GPUTitleExtraction
from db.models.motherboard_title_extraction import MotherboardTitleExtraction
from db.models.psu_title_extraction import PSUTitleExtraction
from db.models.ram_title_extraction import RAMTitleExtraction
from db.models.storage_title_extraction import StorageTitleExtraction

# category -> (specs model, extraction model, {specs column: extraction column})
# Only fields present on both sides. Where the names differ the extraction name is on
# the right, e.g. the cooler's physical size is `size_mm` in stage 1.
MAPPINGS: dict[str, tuple] = {
    "Motherboard": (MotherboardSpecs, MotherboardTitleExtraction, {
        "socket": "socket",
        "form_factor": "form_factor",
        "memory_type": "memory_type",
        "chipset": "chipset",
        "brand": "brand",
    }),
    "Cabinet": (CabinetSpecs, CabinetTitleExtraction, {
        "form_factor": "form_factor",
        "brand": "brand",
    }),
    "CPU Cooler": (CoolerSpecs, CoolerTitleExtraction, {
        "cooler_type": "cooler_type",
        "fan_size_mm": "size_mm",
        "brand": "brand",
    }),
    "Power Supply": (PSUSpecs, PSUTitleExtraction, {
        "wattage": "wattage",
        "efficiency_rating": "efficiency_rating",
        "brand": "brand",
    }),
    "RAM": (RAMSpecs, RAMTitleExtraction, {
        "memory_type": "memory_type",
        "capacity_gb": "capacity_gb",
        "modules": "modules",
        "speed_mhz": "speed_mhz",
        "brand": "brand",
    }),
    "Storage": (SSDSpecs, StorageTitleExtraction, {
        "capacity_gb": "capacity_gb",
        "interface": "interface",
        "brand": "brand",
    }),
    "GPU": (GPUSpecs, GPUTitleExtraction, {
        "chipset": "chipset",
        "brand": "brand",
    }),
    "CPU": (CPUSpecs, CPUTitleExtraction, {
        "brand": "brand",
        "series": "series",
        "model_number": "model_number",
    }),
    # Monitor was missing from this map entirely, which is why it was the one category
    # still offering "Unknown" as a brand and 42 spellings of ~8 resolutions: nothing
    # ever normalized it. Its resolution and panel type have no stage-1 source, so they
    # are tidied in place via NORMALIZE_ONLY below.
    "Monitor": (MonitorSpecs, MonitorTitleExtraction, {
        "brand": "brand",
        "model_number": "model_number",
    }),
}


# Sanity bounds on numeric fields. Stage 1 occasionally reads a model-number digit as
# a measurement - an XPG Gammix D35 kit came through at "32 MHz" - and without a guard
# this script would faithfully copy that into the column the catalog filters on, undoing
# any cleanup. Values outside these ranges are skipped, leaving the column NULL, which
# is the honest answer when the only available reading is impossible.
# Columns that have no stage-1 source but still need tidying in place. Monitor
# resolution and panel type were written by an older pass and never normalized, which
# is how 42 "resolutions" and a mojibake entry ended up in a filter.
NORMALIZE_ONLY: dict[str, tuple[str, ...]] = {
    "Monitor": ("resolution", "panel_type"),
    "Motherboard": ("form_factor",),
    "GPU": ("memory_type",),
    "Storage": ("interface", "form_factor"),
    "Power Supply": ("modularity", "form_factor"),
    "CPU Cooler": ("cooler_type",),
    "Cabinet": ("form_factor",),
    "CPU": ("socket",),
}


BOUNDS: dict[str, tuple[float, float]] = {
    "speed_mhz": (400, 12000),        # no DDR generation runs below 400 MT/s
    "capacity_gb": (1, 262144),
    "wattage": (50, 3000),
    "modules": (1, 8),
    "fan_size_mm": (20, 360),
}


from matching.spec_value_normalizer import normalize_spec_value


def normalize_value(spec_col: str, value, category: str | None = None):
    """Canonical form for a spec value - see matching/spec_value_normalizer.py."""
    return normalize_spec_value(spec_col, value, category)


def is_plausible(spec_col: str, value) -> bool:
    bounds = BOUNDS.get(spec_col)
    if bounds is None:
        return True
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return bounds[0] <= number <= bounds[1]


def backfill(db, category: str, overwrite: bool, dry_run: bool) -> Counter:
    specs_model, extraction_model, field_map = MAPPINGS[category]
    stats = Counter()

    # Several listings share one canonical_id and agree on these fields by
    # construction, so the first non-null wins.
    source: dict[str, dict] = {}
    for row in db.scalars(
        select(extraction_model).where(extraction_model.canonical_id.is_not(None))
    ):
        bucket = source.setdefault(row.canonical_id, {})
        for spec_col, extraction_col in field_map.items():
            value = normalize_value(spec_col, getattr(row, extraction_col, None), category)
            if value is None or value == "" or bucket.get(spec_col) is not None:
                continue
            if not is_plausible(spec_col, value):
                continue
            bucket[spec_col] = value

    for spec in db.scalars(select(specs_model)):
        # Re-normalize what is already stored, so a run cleans up rows written before
        # an alias was added rather than only affecting new fills.
        for spec_col in (*field_map, *NORMALIZE_ONLY.get(category, ())):
            current = getattr(spec, spec_col, None)
            if isinstance(current, str):
                tidied = normalize_value(spec_col, current, category)
                if tidied != current:
                    if not dry_run:
                        setattr(spec, spec_col, tidied)
                    stats[f"{spec_col}:normalized"] += 1

        values = source.get(spec.canonical_id)
        if not values:
            stats["no_source"] += 1
            continue
        for spec_col, value in values.items():
            current = getattr(spec, spec_col, None)
            if current is not None and not overwrite:
                continue
            if current == value:
                continue
            if not dry_run:
                setattr(spec, spec_col, value)
            stats[f"{spec_col}"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="single category, e.g. Motherboard")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    categories = [args.only] if args.only else list(MAPPINGS)
    unknown = [c for c in categories if c not in MAPPINGS]
    if unknown:
        print(f"Unknown category {unknown}. Known: {', '.join(MAPPINGS)}")
        return 1

    with SessionLocal() as db:
        for category in categories:
            stats = backfill(db, category, args.overwrite, args.dry_run)
            filled = {k: v for k, v in stats.items() if k != "no_source" and v}
            print(f"{category:<14} filled={filled or '-'}  no_source={stats['no_source']}")
        if args.dry_run:
            db.rollback()
            print("(dry run - nothing written)")
        else:
            db.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
