"""
Known-brand registry used to close Stage 1's recognition gap on regional makes.

The problem this solves: the identity model reliably names brands it has seen a lot of
(Corsair, ASUS, MSI) but is inconsistent on India-market makes - EVM, ZION, GEONIX,
Dawg, Coconut, Prolab Design, Circle, TAG Gamerz. When it cannot name the brand it
returns "Unknown", and because the canonical key is brand-led, several genuinely
different products then land in one coarse "brand unknown, same specs" group. They are
correctly flagged NEEDS_REVIEW rather than silently wrong, but they are still merged.

The registry is built from the catalogue itself rather than hand-written: any brand the
model has already named confidently somewhere becomes a hint everywhere. That makes it
self-maintaining - a brand recognised once on a clear title ("ZEBRONICS ZEB-PB750 750W")
starts being recognised on the terse listings of the same make - and it keeps the
project's existing rule that evidence beats recall.

A small seed list covers the cold-start case: brands present in the catalogue that the
model has never once named, so they could never appear in a data-derived list.

Hints are a recognition aid, never a licence to guess. The prompt fragment says so
explicitly, because the failure mode of handing a model a list of brands is that it
starts attaching one to every title.
"""
from __future__ import annotations

import json
from pathlib import Path

from matching.canonical_key_builder import normalize_category

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "brand_registry.json"

# Brands seen in the catalogue that Stage 1 has never named on its own, so they cannot
# come from the data-derived pass. Kept deliberately short: this is a cold-start seed,
# not a maintained master list, and anything the model can already recognise does not
# belong here.
SEED_BRANDS: dict[str, list[str]] = {
    "psu": ["Ant Esports", "Zebronics", "Circle", "Gamdias", "Prolab Design",
            "Chiptronex", "Foxin", "Artis", "iBall", "Frontech"],
    # Keyed "case", not "cabinet": that is what normalize_category resolves to and what
    # the extractors write to canonical_parts. Keying it "cabinet" silently produced two
    # registry entries - a seed-only one nothing read, and a derived one nothing seeded.
    "case": ["Ant Esports", "Zebronics", "Chiptronex", "TAG Gamerz", "Circle",
             "Foxin", "Artis", "Gamdias", "Frontech"],
    "cooler": ["Ant Esports", "Zebronics", "Chiptronex", "Gamdias", "Artis"],
    "ram": ["EVM", "ZION", "GEONIX", "Consistent", "Hynix", "Simmtronics", "Foxin"],
    "storage": ["EVM", "ZION", "GEONIX", "Consistent", "Dawg", "Coconut", "Foxin",
                "Simmtronics"],
    "monitor": ["Zebronics", "Frontech", "Foxin", "Consistent", "Artis"],
    "motherboard": ["Consistent", "Foxin", "Zebronics"],
    "gpu": ["Consistent", "Foxin"],
    "cpu": [],
}

# A prompt carrying hundreds of names costs tokens on every batch and, past a point,
# stops helping - the model only needs enough to recognise the makes it keeps missing.
MAX_HINTS_PER_CATEGORY = 60

_UNNAMED = {"", "unknown", "none", "null", "n/a", "generic", "no brand", "unbranded"}


def _clean(brands) -> list[str]:
    """Drops placeholders and near-duplicates, preserving the first spelling seen."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in brands:
        if not raw:
            continue
        name = " ".join(str(raw).split())
        folded = name.lower()
        if folded in _UNNAMED or folded in seen or len(name) > 40:
            continue
        seen.add(folded)
        out.append(name)
    return out


def build_registry(session, min_listings: int = 2) -> dict[str, list[str]]:
    """
    Derives per-category brand hints from canonical parts the model named confidently.

    `min_listings` exists to keep extraction noise out: a brand invented once on a single
    garbled title would otherwise be taught back to the model as though it were real.
    Requiring it to appear on at least two canonical models makes a one-off mis-read
    unable to enter the registry.
    """
    from sqlalchemy import func, select
    from db.models.canonical_part import CanonicalPart

    rows = session.execute(
        select(CanonicalPart.category, CanonicalPart.brand, func.count().label("n"))
        .where(CanonicalPart.status == "OK")
        .group_by(CanonicalPart.category, CanonicalPart.brand)
        .having(func.count() >= min_listings)
        .order_by(func.count().desc())
    ).all()

    derived: dict[str, list[str]] = {}
    for category, brand, _n in rows:
        derived.setdefault(normalize_category(category), []).append(brand)

    registry: dict[str, list[str]] = {}
    seeds = {normalize_category(k): v for k, v in SEED_BRANDS.items()}
    for category in set(derived) | set(seeds):
        # Seeds lead: they are the names the model demonstrably cannot recall unaided,
        # and truncation must never be what drops them.
        merged = _clean(seeds.get(category, []) + derived.get(category, []))
        registry[category] = merged[:MAX_HINTS_PER_CATEGORY]
    return registry


def save_registry(registry: dict[str, list[str]], path: Path = REGISTRY_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, list[str]]:
    """
    Returns the saved registry, falling back to the seed list when none has been built.

    Never raises: a missing or corrupt registry must degrade to today's behaviour rather
    than take the extraction pipeline down with it.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {normalize_category(k): _clean(v) for k, v in data.items() if isinstance(v, list)}
    except (OSError, ValueError):
        pass
    return {normalize_category(k): _clean(v) for k, v in SEED_BRANDS.items()}


def brand_hint_block(category: str, registry: dict[str, list[str]] | None = None) -> str:
    """
    Prompt fragment listing brands known to appear in this catalogue.

    Returns "" when there is nothing useful to add, so callers can concatenate
    unconditionally and an empty registry changes no prompt.

    The wording is the load-bearing part. Handing a model a list of brands invites it to
    attach one to every title, including the ones that genuinely name no brand - which
    would turn a visible "Unknown" into an invisible wrong answer. The instruction
    therefore scopes the list to recognition only and restates that Unknown is correct
    when nothing in the title matches.
    """
    registry = registry if registry is not None else load_registry()
    category = normalize_category(category)
    # Capped here, not only in build_registry: the token cost is paid at emission, and
    # the list can arrive from a JSON file written under a different cap or edited by
    # hand. Trimming only at build time lets an oversized file leak into every batch.
    hints = _clean(registry.get(category, []))[:MAX_HINTS_PER_CATEGORY]
    if not hints:
        return ""
    return (
        "\n\nBrands known to appear in this catalogue (many are India-only makes that "
        "look like noise but are real):\n"
        + ", ".join(hints)
        + "\nUse this list ONLY to recognise a brand that is actually written in the "
        "title, including in an odd case or spelling. Never pick the closest-looking "
        "name, never infer a brand from the product type, and never attach a brand to a "
        "title that names none - return \"Unknown\" for those, which is a correct answer."
    )
