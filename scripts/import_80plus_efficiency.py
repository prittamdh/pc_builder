"""
Import 80 PLUS efficiency ratings from the official CLEAResult certification export.

Source: https://www.clearesult.com/80plus/certified-psus/all-certified-psus ->
"Export Data", saved to data/raw/All_certified_psus.xlsx (14,372 certified units).
This is the authoritative registry and far broader than Cybenetics' 1,152-unit
performance database, which doesn't test the budget Indian brands this catalog is
full of.

Matching is deliberately strict. An earlier Cybenetics import matched on brand plus a
loose model substring and produced confident nonsense - a 1300W Platinum unit paired
with a 750W Bronze entry - so wattage must agree exactly and the model token must
genuinely correspond, not merely overlap.
"""
import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from db.session import SessionLocal
from db.models.canonical_part import CanonicalPart
from db.models.category_specs import PSUSpecs

DEFAULT_XLSX = Path("data/raw/All_certified_psus.xlsx")

RATING_MAP = {
    "TITANIUM": "80+ Titanium", "PLATINUM": "80+ Platinum", "GOLD": "80+ Gold",
    "SILVER": "80+ Silver", "BRONZE": "80+ Bronze",
    "STANDARD": "80+ White", "WHITE": "80+ White", "80 PLUS": "80+ White",
    "RUBY": "80+ Titanium",
}

# Registry manufacturer names are legal entities; catalogs use the consumer brand.
BRAND_ALIASES = {
    "MICRO-STAR INTERNATIONAL CO., LTD.": "MSI",
    "MICRO-STAR INTERNATIONAL": "MSI",
    "COOLER MASTER TECHNOLOGY INC.": "COOLER MASTER",
    "COOLERMASTER": "COOLER MASTER",
    "ANT ESPORTS": "ANT ESPORTS",
    "ANT": "ANT ESPORTS",
    "SEASONIC ELECTRONICS CO., LTD.": "SEASONIC",
    "SUPER FLOWER COMPUTER INC.": "SUPER FLOWER",
    "CORSAIR MEMORY, INC.": "CORSAIR",
    "GIGA-BYTE TECHNOLOGY CO., LTD.": "GIGABYTE",
    "ASUSTEK COMPUTER INC.": "ASUS",
    "THERMALTAKE TECHNOLOGY CO., LTD.": "THERMALTAKE",
    "ANTEC, INC.": "ANTEC",
    "DEEPCOOL INDUSTRIES CO., LTD.": "DEEPCOOL",
}


def norm_brand(value: str | None) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip().upper())
    if text in BRAND_ALIASES:
        return BRAND_ALIASES[text]
    # Trim common corporate suffixes so "Antec, Inc." matches "Antec".
    text = re.sub(r"\b(CO\.?|LTD\.?|INC\.?|CORP\.?|GMBH|TECHNOLOGY|TECHNOLOGIES|ELECTRONICS|INTERNATIONAL|COMPUTER)\b", "", text)
    return re.sub(r"[^A-Z0-9]+", "", text)


def norm_model(value) -> str:
    # Some registry model numbers are bare integers, so coerce before upper().
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def extract_watts(*values) -> int | None:
    for v in values:
        if v is None:
            continue
        if isinstance(v, (int, float)) and 50 <= float(v) <= 3000:
            return int(v)
        m = re.search(r"(\d{3,4})\s*W", str(v).upper())
        if m:
            return int(m.group(1))
    return None


def load_registry(path: Path) -> dict[str, list[dict]]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = [str(h or "").strip() for h in next(rows)]
    idx = {name: i for i, name in enumerate(header)}

    by_brand: dict[str, list[dict]] = {}
    for row in rows:
        if not row:
            continue
        brand = norm_brand(row[idx["Manufacturer"]])
        model = row[idx["Model #"]]
        rating = str(row[idx["Rating"]] or "").strip().upper()
        watts = extract_watts(row[idx["Wattage"]])
        if not brand or not model or rating not in RATING_MAP:
            continue
        by_brand.setdefault(brand, []).append({
            "model_norm": norm_model(model),
            "model_raw": str(model),
            "rating": RATING_MAP[rating],
            "watts": watts,
        })
    return by_brand


def match_one(entries: list[dict], model_norm: str, watts: int | None) -> dict | None:
    """Exact model match first, then a contained-token match - but only ever among
    entries whose wattage agrees, since wattage is what caught the earlier bad
    matches."""
    if not model_norm:
        return None
    pool = [e for e in entries if watts is None or e["watts"] == watts]
    if not pool:
        return None

    for e in pool:
        if e["model_norm"] == model_norm:
            return e
    # Containment needs a substantial token; short fragments match far too much.
    if len(model_norm) >= 4:
        for e in pool:
            if model_norm in e["model_norm"] or e["model_norm"] in model_norm:
                return e
    return None


def main(xlsx: Path, dry_run: bool, only_missing: bool) -> None:
    registry = load_registry(xlsx)
    total_entries = sum(len(v) for v in registry.values())
    print("=" * 78)
    print(f"80 PLUS IMPORT {'(DRY RUN)' if dry_run else ''}")
    print(f"  registry: {total_entries} certified units across {len(registry)} brands")

    with SessionLocal() as session:
        stmt = select(PSUSpecs)
        if only_missing:
            stmt = stmt.where(PSUSpecs.efficiency_rating.is_(None))
        rows = session.scalars(stmt).all()

        keys = {
            cp.canonical_id: (cp.key_fields or {})
            for cp in session.scalars(select(CanonicalPart).where(CanonicalPart.category == "psu"))
        }

        matched = unmatched = 0
        for row in rows:
            kf = keys.get(row.canonical_id, {})
            brand = norm_brand(kf.get("brand") or row.brand)
            model_norm = norm_model(kf.get("model_number"))
            watts = extract_watts(kf.get("wattage"), kf.get("model_number"))

            hit = match_one(registry.get(brand, []), model_norm, watts)
            if hit is None:
                unmatched += 1
                continue

            matched += 1
            if not dry_run:
                row.efficiency_rating = hit["rating"]
                row.confidence = "high"
                row.notes = (
                    f"80 PLUS official certification registry (CLEAResult export), "
                    f"matched to '{hit['model_raw']}'"
                    + (f" at {hit['watts']}W." if hit["watts"] else ".")
                )
                row.status = "ok"

        if not dry_run:
            session.commit()

        print(f"  scanned:  {len(rows)} psu_specs rows ({'missing-only' if only_missing else 'all'})")
        print(f"  matched:  {matched}")
        print(f"  no match: {unmatched}")
        print("=" * 78)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Import 80 PLUS ratings from the CLEAResult export.")
    ap.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true", help="Re-match every PSU, not just those missing a rating.")
    args = ap.parse_args()
    main(args.xlsx, dry_run=args.dry_run, only_missing=not args.all)
