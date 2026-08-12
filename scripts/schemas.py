"""
schemas.py
Category-specific attribute extractors. Each function takes a RAW title
(and optionally a spec-table dict, if your scraper captures one) and returns
a dict of structured attributes. These attributes are what you use as a HARD
GATE before/after fuzzy or embedding matching: two listings should never be
merged if their category-critical attributes disagree, no matter how similar
the titles look.

Design notes:
- Every extractor returns None for a field it can't find — never guess.
- `critical_fields` per category lists the attributes that MUST match exactly
  (after normalization) for two listings to be considered the same product.
  Everything else is supporting evidence, not a gate.
- Extend patterns as you encounter real store data; these cover the common
  Indian retailer naming conventions for each category.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from normalize import standardize_units, squeeze_number_unit


def _prep(title: str) -> str:
    """Lowercase + unit standardization/squeezing only — keep all words (brand,
    model tokens) intact, unlike normalize_title() which strips marketing noise.
    Every extractor should run its regexes against this, not raw title.lower(),
    so '6000 MHz' and '6000MHz' both hit the same pattern."""
    return squeeze_number_unit(standardize_units(title.lower()))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

BRAND_ALIASES = {
    # canonical: [aliases as they appear in titles]
    "wd": ["western digital", "wd"],
    "seagate": ["seagate"],
    "corsair": ["corsair"],
    "gskill": ["g.skill", "g skill", "gskill"],
    "crucial": ["crucial"],
    "kingston": ["kingston"],
    "asus": ["asus"],
    "msi": ["msi"],
    "gigabyte": ["gigabyte", "aorus"],
    "zotac": ["zotac"],
    "sapphire": ["sapphire"],
    "intel": ["intel"],
    "amd": ["amd"],
    "nvidia": ["nvidia"],
    "cooler_master": ["cooler master", "coolermaster"],
    "deepcool": ["deepcool"],
    "nzxt": ["nzxt"],
    "antec": ["antec"],
}


def find_brand(text: str) -> Optional[str]:
    text = text.lower()
    for canonical, aliases in BRAND_ALIASES.items():
        for alias in aliases:
            if alias in text:
                return canonical
    return None


def _search(pattern: str, text: str, group: int = 1, flags=re.IGNORECASE) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(group) if m else None


# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------

def extract_cpu(title: str, specs: dict | None = None) -> dict:
    specs = specs or {}
    t = _prep(title)

    brand = "intel" if "intel" in t or re.search(r"\bi[3579]-\d{4,5}", t) else \
            "amd" if "amd" in t or re.search(r"\bryzen\b", t) else None

    # Intel: i5-14600K, i9 13900KS, Core i7 12700
    model = _search(r"\b(i[3579]-\d{4,5}[a-z]{0,3})\b", t)
    if not model:
        model = _search(r"\b(i[3579])\s?-?\s?(\d{4,5}[a-z]{0,3})\b", t)
        if model:
            model = f"{_search(r'(i[3579])', t)}-{_search(r'i[3579]s?-?(?:\s)?(\d{4,5}[a-z]{0,3})', t)}"

    # AMD: Ryzen 5 7600X, Ryzen 9 7950X3D
    if not model and "ryzen" in t:
        ryzen_match = re.search(r"ryzen\s?(\d)\s?(\d{4}[a-z0-9]{0,3})", t)
        if ryzen_match:
            model = f"ryzen{ryzen_match.group(1)}-{ryzen_match.group(2)}"

    socket = _search(r"\b(lga\s?\d{4}|am4|am5)\b", t)
    cores = _search(r"\b(\d{1,2})\s?core", t)

    return {
        "category": "cpu",
        "brand": brand,
        "model": model,
        "socket": socket.replace(" ", "") if socket else None,
        "cores": int(cores) if cores else None,
    }


CPU_CRITICAL_FIELDS = ["brand", "model"]


# ---------------------------------------------------------------------------
# GPU
# ---------------------------------------------------------------------------

def extract_gpu(title: str, specs: dict | None = None) -> dict:
    specs = specs or {}
    t = _prep(title)

    chipset = _search(r"\b(rtx\s?\d{4}\s?ti\s?super|rtx\s?\d{4}\s?super|rtx\s?\d{4}\s?ti|rtx\s?\d{4}|"
                       r"gtx\s?\d{4}\s?ti|gtx\s?\d{4}|rx\s?\d{4}\s?xt|rx\s?\d{4})\b", t)
    if chipset:
        chipset = re.sub(r"\s+", "", chipset)

    vram = _search(r"\b(\d{1,2})\s?gb\b", t)
    aib_partner = find_brand(t)  # asus/msi/gigabyte/zotac/sapphire

    # Variant / SKU tier — matters a lot for price, doesn't gate identity match
    variant = None
    for kw in ["gaming oc", "gaming x", "tuf", "strix", "eagle", "ventus", "nitro+", "pulse", "vision", "windforce"]:
        if kw in t:
            variant = kw.replace(" ", "_")
            break

    return {
        "category": "gpu",
        "chipset": chipset,
        "vram_gb": int(vram) if vram else None,
        "aib_partner": aib_partner,
        "variant": variant,
    }


GPU_CRITICAL_FIELDS = ["chipset", "aib_partner"]  # variant differences = different SKU, handle separately downstream


# ---------------------------------------------------------------------------
# RAM
# ---------------------------------------------------------------------------

def extract_ram(title: str, specs: dict | None = None) -> dict:
    specs = specs or {}
    t = _prep(title)

    ddr_gen = _search(r"\b(ddr[345])\b", t)
    # Total kit capacity like "32gb" — exclude the per-stick number inside "(2x16gb)"
    capacity = _search(r"(?<!x)\b(\d{1,3})gb\b", t)
    kit_config = _search(r"\((\d)\s?x\s?(\d{1,2})gb\)", t, group=0)
    speed = _search(r"\b(\d{4,5})mhz\b", t)
    cl = _search(r"\bcl\s?(\d{2})\b", t)

    return {
        "category": "ram",
        "brand": find_brand(t) or _search(r"\b(gskill|corsair|kingston|crucial|adata|teamgroup)\b", t),
        "ddr_gen": ddr_gen,
        "capacity_gb": int(capacity) if capacity else None,
        "kit_config": kit_config,
        "speed_mhz": int(speed) if speed else None,
        "cas_latency": int(cl) if cl else None,
    }


RAM_CRITICAL_FIELDS = ["brand", "ddr_gen", "capacity_gb", "speed_mhz"]


# ---------------------------------------------------------------------------
# Storage (SSD/HDD)
# ---------------------------------------------------------------------------

def extract_storage(title: str, specs: dict | None = None) -> dict:
    specs = specs or {}
    t = _prep(title)

    capacity_tb = _search(r"\b(\d(?:\.\d)?)tb\b", t)
    capacity_gb = _search(r"\b(\d{2,4})gb\b", t)
    interface = "nvme" if "nvme" in t else "sata" if "sata" in t else None
    form_factor = _search(r"\b(m\.2|2\.5in|3\.5in)\b", t)
    gen = _search(r"\b(gen\s?[345])\b", t)

    total_gb = None
    if capacity_tb:
        total_gb = float(capacity_tb) * 1024
    elif capacity_gb:
        total_gb = float(capacity_gb)

    return {
        "category": "storage",
        "brand": find_brand(t) or _search(r"\b(wd|seagate|crucial|kingston|samsung|adata|sandisk)\b", t),
        "capacity_gb": total_gb,
        "interface": interface,
        "form_factor": form_factor.replace(" ", "") if form_factor else None,
        "pcie_gen": gen.replace(" ", "") if gen else None,
    }


STORAGE_CRITICAL_FIELDS = ["brand", "capacity_gb", "interface"]


# ---------------------------------------------------------------------------
# PSU
# ---------------------------------------------------------------------------

def extract_psu(title: str, specs: dict | None = None) -> dict:
    specs = specs or {}
    t = _prep(title)

    wattage = _search(r"\b(\d{3,4})w\b", t)
    efficiency = _search(r"\b(80\s?plus\s?(?:bronze|silver|gold|platinum|titanium)|80\+\s?(?:bronze|gold|platinum))\b", t)
    modularity = "full" if "fully modular" in t or "full modular" in t else \
                 "semi" if "semi modular" in t else \
                 "non" if "non modular" in t or "non-modular" in t else None

    return {
        "category": "psu",
        "brand": find_brand(t),
        "wattage": int(wattage) if wattage else None,
        "efficiency_rating": re.sub(r"\s+", "_", efficiency) if efficiency else None,
        "modularity": modularity,
    }


PSU_CRITICAL_FIELDS = ["brand", "wattage", "efficiency_rating"]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

EXTRACTORS = {
    "cpu": (extract_cpu, CPU_CRITICAL_FIELDS),
    "gpu": (extract_gpu, GPU_CRITICAL_FIELDS),
    "ram": (extract_ram, RAM_CRITICAL_FIELDS),
    "storage": (extract_storage, STORAGE_CRITICAL_FIELDS),
    "psu": (extract_psu, PSU_CRITICAL_FIELDS),
}


def extract_attributes(category: str, title: str, specs: dict | None = None) -> dict:
    """Main entry point: category + raw title -> structured attribute dict."""
    if category not in EXTRACTORS:
        raise ValueError(f"No extractor registered for category '{category}'. "
                          f"Available: {list(EXTRACTORS)}")
    extractor_fn, critical_fields = EXTRACTORS[category]
    attrs = extractor_fn(title, specs)
    attrs["_critical_fields"] = critical_fields
    attrs["_complete"] = all(attrs.get(f) is not None for f in critical_fields)
    return attrs


if __name__ == "__main__":
    tests = [
        ("cpu", "Intel Core i5-14600K (Box) Desktop Processor - LGA1700, 14 Core"),
        ("gpu", "ASUS TUF Gaming RTX 4070 Ti Super 16GB GDDR6X Graphics Card"),
        ("gpu", "MSI GeForce RTX 4070 Ti SUPER 16G VENTUS 3X"),
        ("ram", "Corsair Vengeance RGB 32GB (2x16GB) DDR5 6000MHz CL30 RAM Kit"),
        ("storage", "WD Blue SN580 1TB NVMe M.2 Gen4 SSD"),
        ("psu", "Corsair RM850x 850W 80 Plus Gold Fully Modular PSU"),
    ]
    for cat, title in tests:
        print(f"[{cat}] {title}")
        print(f"  -> {extract_attributes(cat, title)}\n")
