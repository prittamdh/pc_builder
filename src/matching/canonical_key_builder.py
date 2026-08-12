"""
Canonical Key Builder Module.
Implements category-specific canonical key extraction rules as specified in docs/canonical_part_resolution_spec.md.

Canonical Key Rules Per Category:
- CPU: brand + model_number
- PSU: brand + model_number + wattage
- Cooler: brand + model_number
- Case: brand + model_number
- Storage: brand + series + capacity + interface
- RAM: brand + series + capacity + speed_mhz + cl_timing
- Motherboard: brand + chipset + model_number
- GPU: aib_brand + variant_model + chipset
"""
import re


def normalize_category(category: str) -> str:
    """Standardizes category input string to canonical category key."""
    cat = (category or "").lower().strip()
    if cat in ("cpu", "processor"):
        return "cpu"
    elif cat in ("gpu", "graphics card"):
        return "gpu"
    elif cat in ("ram", "desktop ram", "laptop ram", "memory"):
        return "ram"
    elif cat in ("storage", "ssd", "hdd", "nvme ssd", "m.2 nvme ssd", "sata ssd"):
        return "storage"
    elif cat in ("power supply", "psu", "smps"):
        return "psu"
    elif cat in ("cpu cooler", "cooler"):
        return "cooler"
    elif cat in ("cabinet", "case", "pc cabinet"):
        return "case"
    elif cat in ("motherboard", "mobo"):
        return "motherboard"
    return cat


def extract_brand(title: str) -> str:
    """Extracts known brand name from title."""
    title_lower = title.lower()
    
    # Explicit brand inference for CPUs
    if "ryzen" in title_lower or "threadripper" in title_lower:
        return "AMD"
    if "intel" in title_lower or "core i" in title_lower or "xeon" in title_lower:
        return "Intel"

    known_brands = [
        "ant esports", "cooler master", "western digital", "deepcool", "thermalright",
        "lii auto", "g.skill", "gskill", "kingston", "corsair", "crucial", "adata",
        "samsung", "kioxia", "teamgroup", "montech", "arctic", "noctua", "be quiet!",
        "inno3d", "zotac", "gigabyte", "asus", "msi", "galax", "sapphire", "powercolor",
        "xfx", "asrock", "amd", "intel", "lenovo", "tps", "nzxt", "silverstone"
    ]
    for brand in known_brands:
        if brand in title_lower:
            return brand.upper() if len(brand) <= 4 else brand.title()
    # Fallback to first word
    words = title.split()
    return words[0].title() if words else "Unknown"


def build_canonical_key(title: str, category: str, specs: dict | None = None) -> dict:
    """
    Builds the category-specific canonical key dictionary from normalized title and optional specs.
    Returns minimal field set defining uniqueness for that category.
    """
    cat = normalize_category(category)
    t_lower = title.lower()
    
    # Normalize spaces/hyphens and word order for CPU model numbers
    t_clean = re.sub(r"(\d{4}[a-z0-9]*)\s*ryzen\s*(\d)", r"ryzen \2 \1", t_lower)
    t_clean = re.sub(r"ryzen\s*(\d)\s*[\-_\s]*(\d{4}[a-z0-9]*)", r"ryzen \1 \2", t_clean)
    t_clean = re.sub(r"core\s*i\s*([3579])\s*[\-_\s]*(\d{4,5}[a-z]*)", r"core i\1-\2", t_clean)

    brand = extract_brand(title)
    specs = specs or {}

    key_dict = {"category": cat, "brand": brand}

    if cat == "cpu":
        # CPU: brand + model_number
        match = re.search(r"(ryzen\s+[3579]\s+\d{4}[a-z0-9]*|core\s+i[3579]-\d{4,5}[a-z]*|\b\d{4,5}[a-z]{1,2}\b)", t_clean)
        model_num = match.group(0) if match else t_clean
        key_dict["model_number"] = model_num.strip()

    elif cat == "psu":
        # PSU: brand + model_number + wattage
        watt_match = re.search(r"(\d{3,4})\s*w(att)?", t_lower)
        wattage = f"{watt_match.group(1)}W" if watt_match else "Unknown"

        # Model series
        model_match = re.search(r"(cx\d{3}m?|cv\d{3}|rm\d{3}[x|e]?|pylon\s*\d{3}|vs\d{3}l?|mwe\s*\d{3}|toughpower\s*\d{3})", t_lower)
        model_num = model_match.group(0) if model_match else title.split()[1] if len(title.split()) > 1 else title

        key_dict["model_number"] = model_num.strip()
        key_dict["wattage"] = wattage

    elif cat in ("cooler", "case"):
        # Cooler & Case: brand + model_number
        # Strip marketing fluff
        clean_name = re.sub(r"(cpu air cooler|liquid cooler|argb|rgb|mid tower cabinet|atx|matx)", "", t_lower).strip()
        words = clean_name.split()
        model_num = " ".join(words[:4]) if words else clean_name
        key_dict["model_number"] = model_num

    elif cat == "storage":
        # Storage: brand + series + capacity + interface
        cap_match = re.search(r"(\d+(\.\d+)?\s*(tb|gb))", t_lower)
        capacity = cap_match.group(1).replace(" ", "") if cap_match else "Unknown"

        interface = "sata"
        if "nvme" in t_lower or "pcie" in t_lower or "m.2" in t_lower:
            if "gen5" in t_lower or "pcie 5" in t_lower:
                interface = "nvme_gen5"
            elif "gen4" in t_lower or "pcie 4" in t_lower:
                interface = "nvme_gen4"
            else:
                interface = "nvme"
        elif "hdd" in t_lower or "hard drive" in t_lower:
            interface = "hdd_sata"

        # Series (e.g. 990 pro, legend 860, exceria plus)
        series_match = re.search(r"(990\s*pro|980\s*pro|990\s*evo|legend\s*\d+|exceria\s*\w+|sn850x|sn770|p3\s*plus)", t_lower)
        series = series_match.group(0) if series_match else "generic"

        key_dict["series"] = series
        key_dict["capacity"] = capacity
        key_dict["interface"] = interface

    elif cat == "ram":
        # RAM: brand + series + capacity + speed_mhz + cl_timing
        cap_match = re.search(r"(\d+\s*gb(\s*x\s*\d+)?)", t_lower)
        capacity = cap_match.group(1).replace(" ", "") if cap_match else "Unknown"

        speed_match = re.search(r"(\d{4})\s*mhz", t_lower)
        speed = f"{speed_match.group(1)}MHz" if speed_match else "Unknown"

        cl_match = re.search(r"cl\s*(\d{2})", t_lower)
        cl_timing = f"CL{cl_match.group(1)}" if cl_match else "Unknown"

        series_match = re.search(r"(fury\s*beast|trident\s*z5?|vengeance|lancer|ripjaws)", t_lower)
        series = series_match.group(0) if series_match else "generic"

        key_dict["series"] = series
        key_dict["capacity"] = capacity
        key_dict["speed_mhz"] = speed
        key_dict["cl_timing"] = cl_timing

    elif cat == "motherboard":
        # Motherboard: brand + chipset + model_number
        chipset_match = re.search(r"(b650m?|b760m?|z790m?|x670e?|b550m?|a620m?)", t_lower)
        chipset = chipset_match.group(0).upper() if chipset_match else "Unknown"

        model_match = re.search(r"(tuf\s*gaming|rog\s*strix|prime|aorus|tomahawk|mortar|pro\s*rs|steel\s*legend)", t_lower)
        model_num = model_match.group(0) if model_match else title

        key_dict["chipset"] = chipset
        key_dict["model_number"] = model_num

    elif cat == "gpu":
        # GPU: aib_brand + variant_model + chipset
        chipset_match = re.search(r"(rtx\s*\d{4}\s*(ti)?\s*(super)?|rx\s*\d{4}\s*(xt)?(x)?)", t_lower)
        chipset = chipset_match.group(0).upper() if chipset_match else "Unknown"

        variant_match = re.search(r"(ventus|gaming\s*x|tuf|strix|aorus|eagle|windforce|solid|twin\s*edge|shadow|inspire)", t_lower)
        raw_variant = variant_match.group(0) if variant_match else "base"
        
        # Strip brand token if present in variant_model to avoid duplication
        brand_lower = brand.lower()
        if raw_variant.lower().startswith(brand_lower):
            raw_variant = raw_variant[len(brand_lower):].strip()
        variant = raw_variant if raw_variant else "base"

        key_dict["aib_brand"] = brand
        key_dict["variant_model"] = variant
        key_dict["chipset"] = chipset

    else:
        key_dict["model_number"] = title

    return key_dict


def make_canonical_key_string(category: str, key_dict: dict) -> str:
    """Generates deterministic string representation of the canonical key dict."""
    cat = normalize_category(category)
    parts = [cat]
    seen_vals = set()
    for k in sorted(key_dict.keys()):
        if k != "category":
            val = str(key_dict[k]).lower().strip().replace(" ", "_")
            if val and val not in seen_vals:
                parts.append(val)
                seen_vals.add(val)
    return ":".join(parts)
