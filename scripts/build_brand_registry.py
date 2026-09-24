"""
Rebuild data/brand_registry.json from the brands Stage 1 has already named confidently.

Run this after an identity-extraction pass. Every brand the model managed to name on a
clear title becomes a hint on the terse ones, so recognition of India-market makes
improves with each cycle instead of staying flat.

Cheap and deterministic - one grouped query, no API calls - so it is safe to run from
the DAG on every cycle.

Dry-run by default. Pass --apply to write the file.
"""
import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.session import SessionLocal
from matching.brand_registry import (
    REGISTRY_PATH, SEED_BRANDS, build_registry, load_registry, save_registry,
)


def main(apply: bool = False, min_listings: int = 2):
    with SessionLocal() as session:
        print("=" * 80)
        print(f"BRAND REGISTRY BUILD ({'APPLY' if apply else 'DRY RUN'})")
        print("=" * 80)

        registry = build_registry(session, min_listings=min_listings)
        previous = load_registry()

        total = sum(len(v) for v in registry.values())
        print(f"  categories: {len(registry)}")
        print(f"  brand hints total: {total}  (min {min_listings} canonical models each)")

        for category in sorted(registry):
            names = registry[category]
            was = set(previous.get(category, []))
            added = [n for n in names if n not in was]
            seeded = [n for n in names if n in SEED_BRANDS.get(category, [])]
            print(f"\n  {category:12} {len(names):3} hints  (+{len(added)} new, {len(seeded)} seeded)")
            if added:
                print(f"       new: {', '.join(added[:12])}{' ...' if len(added) > 12 else ''}")

        if not apply:
            print(f"\nDry run - {REGISTRY_PATH} not written. Re-run with --apply.")
            return

        path = save_registry(registry)
        print(f"\nWrote {path}")
        print("Next: re-run the Stage 1 extractors; prompts pick the hints up automatically.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the registry (default is a dry run).")
    parser.add_argument("--min-listings", type=int, default=2,
                        help="Canonical models a brand must appear on to become a hint (default 2).")
    args = parser.parse_args()
    main(apply=args.apply, min_listings=args.min_listings)
