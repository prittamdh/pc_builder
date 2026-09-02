"""Canonical forms for extracted spec values.

Values come from free-text retailer titles via an LLM, so the same fact arrives spelled
several ways. Left alone the filters become unusable: 255 brand options across the
catalog for 183 actual brands, 42 monitor "resolutions" for about 8 real ones, and 72
motherboard chipsets where the form factor had been baked into the chipset name.

Two rules throughout:

- **Only collapse things that are genuinely the same.** Case and spacing variants merge;
  distinct products never do. Sub-brands (XPG, AORUS) stay separate from their parents
  because shoppers search for them by name.
- **A value that says nothing becomes NULL.** "Unknown" as a filter option wastes a
  click and tells the shopper nothing; the facets endpoint omits NULLs entirely.
"""

import re

# --------------------------------------------------------------------- brands

# Display spellings for brands that appear in more than one form. The key is the
# normalized form (lowercase, alphanumeric only), the value is how it should read.
# Sub-brands are deliberately absent: XPG is ADATA's memory line and AORUS is
# Gigabyte's, but people shop for "XPG", so folding them into the parent would lose
# a search term without making any filter meaningfully shorter.
BRAND_CANONICAL: dict[str, str] = {
    "asus": "ASUS", "asrock": "ASRock", "gigabyte": "Gigabyte", "msi": "MSI",
    "zotac": "ZOTAC", "colorful": "Colorful", "sapphire": "Sapphire",
    "powercolor": "PowerColor", "inno3d": "Inno3D", "galax": "GALAX",
    "pny": "PNY", "nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel",
    "nextron": "NEXTRON", "foxin": "Foxin",

    "corsair": "Corsair", "gskill": "G.Skill", "teamgroup": "TeamGroup",
    "kingston": "Kingston", "crucial": "Crucial", "adata": "ADATA",
    "patriot": "Patriot", "patriotmemory": "Patriot", "samsung": "Samsung",
    "micron": "Micron", "lexar": "Lexar", "transcend": "Transcend",
    "hynix": "SK Hynix", "skhynix": "SK Hynix", "siliconpower": "Silicon Power",
    "vcolor": "V-COLOR", "zion": "ZION", "evm": "EVM", "acer": "Acer",

    "westerndigital": "Western Digital", "wd": "Western Digital",
    "seagate": "Seagate", "toshiba": "Toshiba", "kioxia": "Kioxia",
    "sandisk": "SanDisk", "addlink": "Addlink", "sabrent": "Sabrent",
    "synology": "Synology", "hikvision": "Hikvision", "biwin": "Biwin",
    "verbatim": "Verbatim", "orico": "ORICO", "geonix": "GEONIX",

    "coolermaster": "Cooler Master", "thermaltake": "Thermaltake",
    # Real typo in the catalog, not another brand.
    "thermaltek": "Thermaltake",
    "deepcool": "DeepCool", "antec": "Antec", "antesports": "Ant Esports",
    "ant": "Ant Esports", "superflower": "Super Flower", "fsp": "FSP",
    "evga": "EVGA", "nzxt": "NZXT", "silverstone": "SilverStone",
    "gamdias": "GAMDIAS", "circle": "Circle", "zebronics": "Zebronics",
    "prolabdesign": "ProLab Design", "prolab": "ProLab Design",
    "fractaldesign": "Fractal Design", "syrotech": "Syrotech",
    "gamerstorm": "Gamer Storm",

    "noctua": "Noctua", "arctic": "ARCTIC", "lianli": "Lian Li",
    "alseye": "ALSEYE", "montech": "Montech", "cougar": "COUGAR",
    "xigmatek": "Xigmatek", "aerocool": "AeroCool", "hyte": "HYTE",
    "phanteks": "Phanteks", "inwin": "InWin", "razer": "Razer",
    "cocosports": "COCO Sports", "coconut": "Coconut", "dawg": "DAWG",
    "taggamerz": "TAG Gamerz", "consistent": "Consistent",
    "iball": "iBall", "lapcare": "Lapcare", "icemaster": "IceMaster",

    "lg": "LG", "dell": "Dell", "benq": "BenQ", "viewsonic": "ViewSonic",
    "aoc": "AOC", "philips": "Philips", "lenovo": "Lenovo", "hp": "HP",
}


def normalize_brand(value: str | None) -> str | None:
    """Canonical brand spelling, or None when the value names nothing."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    key = re.sub(r"[^a-z0-9]", "", text.lower())
    if not key or key in {"unknown", "na", "none", "generic", "brand"}:
        return None
    return BRAND_CANONICAL.get(key, text)


# ------------------------------------------------------------------- sockets

def normalize_socket(value: str | None) -> str | None:
    """`LGA 1851` and `LGA1851` are one socket; server sockets keep their own names."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().upper().replace(" ", "")
    if not text or text in {"UNKNOWN", "NA", "NONE"}:
        return None
    if text.startswith("LGA"):
        return "LGA" + text[3:]
    return value.strip()


# ------------------------------------------------------------------ chipsets

# `M` = micro-ATX and `I` = ITX are form factors, and form factor is already its own
# filter, so carrying them in the chipset name split B850 across B850 / B850M / B850I
# and inflated the list to 72 entries. `E` is NOT a form factor (B650E and X870E are
# genuinely different chipsets) and neither are the A/F/G/P model-line letters, so only
# a trailing M or I is removed.
_CHIPSET_FORM_SUFFIX = re.compile(r"^([A-Z]{1,2}\d{3,4})[MI]$")

# Sockets that extraction sometimes writes into the chipset column. They are not
# chipsets and already have their own filter.
_NOT_CHIPSETS = {"SP5", "SP6", "SP3", "TR4"}


def normalize_chipset(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().upper().replace(" ", "")
    if not text or text in {"UNKNOWN", "NA", "NONE"} or text in _NOT_CHIPSETS:
        return None
    text = text.replace("−", "-")
    match = _CHIPSET_FORM_SUFFIX.match(text)
    return match.group(1) if match else text


# ------------------------------------------------------------- GPU chipsets

_GPU_FIXES = {
    # "GTX 710" and "GTX 730" were never products - both are GT cards.
    "GTX710": "GT 710",
    "GTX730": "GT 730",
    # Quadro was retired as a prefix; the same dies are listed both ways.
    "QUADRORTXA1000": "RTX A1000",
    "QUADRORTX2000ADAGENERATION": "RTX 2000 Ada Generation",
    "QUADROT1000": "T1000",
    "QUADROT400": "T400",
    # AMD's workstation card, three spellings of one part.
    "R9700": "Radeon R9700",
    "RADEONR9700": "Radeon R9700",
    "RX9700": "Radeon R9700",
}


def normalize_gpu_chipset(value: str | None) -> str | None:
    """Fix spacing and legacy prefixes so one die is one filter option.

    "RX 9060 XT" and "RX 9060XT" were separate options for the same card, which split
    its offer counts in two and made both look rarer than the part actually is.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.upper() in {"UNKNOWN", "NA", "NONE"}:
        return None

    key = re.sub(r"[^A-Z0-9]", "", text.upper())
    if key in _GPU_FIXES:
        return _GPU_FIXES[key]

    # Re-space a missing gap before a trailing XT/XTX/GRE/TI suffix.
    text = re.sub(r"(\d)(XTX|XT|GRE|TI)\b", r"\1 \2", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------- GPU memory type

# GDDR is graphics memory; plain DDR6/DDR7 do not exist as GPU memory at all and are
# extraction errors. DDR3 does appear on genuinely old cards, so it stays.
_VALID_GPU_MEMORY = {"GDDR7", "GDDR6X", "GDDR6", "GDDR5X", "GDDR5", "GDDR3", "DDR3", "HBM2E", "HBM3"}


def normalize_gpu_memory_type(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().upper().replace(" ", "")
    return text if text in _VALID_GPU_MEMORY else None


# ----------------------------------------------------------- monitor display

# One label per real resolution. The catalog held 42 variants across four naming
# systems at once - labels (QHD), pixel pairs (2560x1440), marketing names (Full HD,
# 1440p) and a mojibake entry where the x had been mangled in transit.
_RESOLUTION_CANONICAL = {
    "1366X768": "HD", "1280X720": "HD", "HD": "HD", "HD+": "HD+", "HDPLUS": "HD+",
    "1600X900": "HD+", "1440X900": "WXGA+",
    "1920X1080": "FHD", "FHD": "FHD", "FULLHD": "FHD", "FULL-HD": "FHD", "1080P": "FHD",
    "1920X1200": "WUXGA", "WUXGA": "WUXGA",
    "2560X1080": "WFHD", "WFHD": "WFHD",
    "2560X1440": "QHD", "QHD": "QHD", "2K": "QHD", "2KQHD": "QHD",
    "1440P": "QHD", "WQHD": "QHD", "1280X1024": "SXGA", "SXGA": "SXGA",
    "1680X1050": "WSXGA+", "WSXGA": "WSXGA+",
    "3440X1440": "UWQHD", "UWQHD": "UWQHD", "WQHD+": "UWQHD", "45WQHD": "UWQHD",
    "3840X1080": "DFHD",
    "5120X1440": "DQHD", "DQHD": "DQHD", "DUALQHD": "DQHD", "5K2K": "5K2K",
    "3840X2160": "4K UHD", "4K": "4K UHD", "UHD": "4K UHD", "4KUHD": "4K UHD",
    "4K+": "4K UHD", "DUALUHD": "Dual UHD",
    "5120X2880": "5K", "5K": "5K", "6K": "6K", "7680X4320": "8K", "8K": "8K",
    "1024X768": "XGA",
}

# Curved and ultrawide describe the panel's shape, not its technology, and LED is a
# backlight. Keeping them here made "panel type" answer two questions at once.
_PANEL_CANONICAL = {
    "IPS": "IPS", "NANOIPS": "Nano IPS", "IPSBLACK": "IPS Black",
    "VA": "VA", "TN": "TN", "OLED": "OLED",
    "QDOLED": "QD-OLED", "QD-OLED": "QD-OLED",
    "MINILED": "Mini LED", "MICROLED": "Micro LED",
}


def normalize_resolution(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    # The mojibake case: "3440�1440" - the separator was corrupted upstream.
    text = re.sub(r"[^\x20-\x7e]", "x", value).strip()
    key = re.sub(r"[\s_]", "", text.upper()).replace("*", "X").replace("×", "X")
    key = re.sub(r"XX+", "X", key)
    return _RESOLUTION_CANONICAL.get(key, text if len(text) <= 12 else None)


def normalize_panel_type(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    key = re.sub(r"[^A-Z0-9]", "", value.upper())
    return _PANEL_CANONICAL.get(key)


# --------------------------------------------------------- PSU efficiency

# 80 PLUS and Cybenetics are separate certification schemes with different test
# regimes, so mixing them in one filter compares things that aren't comparable. A bare
# "80+" claims a tier without naming one, which is not a rating.
_EFFICIENCY_CANONICAL = {
    "80+TITANIUM": "80+ Titanium", "80+PLATINUM": "80+ Platinum",
    "80+GOLD": "80+ Gold", "80+SILVER": "80+ Silver",
    "80+BRONZE": "80+ Bronze", "80+WHITE": "80+ White",
    "80PLUSTITANIUM": "80+ Titanium", "80PLUSPLATINUM": "80+ Platinum",
    "80PLUSGOLD": "80+ Gold", "80PLUSSILVER": "80+ Silver",
    "80PLUSBRONZE": "80+ Bronze", "80PLUSWHITE": "80+ White",
}


def normalize_efficiency(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    key = re.sub(r"[\s_-]", "", value.upper())
    return _EFFICIENCY_CANONICAL.get(key)


# ----------------------------------------------------------------- interface

# "SSD" answers "what kind of drive", not "how does it connect" - it was sitting in the
# interface filter telling the shopper nothing they hadn't already chosen.
_INTERFACE_CANONICAL = {
    "SATA": "SATA", "SATAIII": "SATA", "SATA3": "SATA", "SATA6GBS": "SATA",
    "NVME": "NVMe",
    "NVMEGEN3": "NVMe Gen3", "NVMEGEN30": "NVMe Gen3", "PCIEGEN3": "NVMe Gen3",
    "NVMEPCIE30": "NVMe Gen3",
    "NVMEGEN4": "NVMe Gen4", "NVMEGEN40": "NVMe Gen4", "PCIEGEN4": "NVMe Gen4",
    "NVMEPCIE40": "NVMe Gen4",
    "NVMEGEN5": "NVMe Gen5", "NVMEGEN50": "NVMe Gen5", "PCIEGEN5": "NVMe Gen5",
    "NVMEPCIE50": "NVMe Gen5",
    "HDD": "HDD", "SAS": "SAS", "USB": "USB",
}


def normalize_interface(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    key = re.sub(r"[^A-Z0-9]", "", value.upper())
    return _INTERFACE_CANONICAL.get(key)


# ---------------------------------------------------------------- modularity

# "Modular" on its own doesn't distinguish fully from semi, but every product in the
# catalog spelled that way turned out to be fully modular, and the vendor phrasing
# ("Fully Modular") confirms it.
_MODULARITY_CANONICAL = {
    "FULL": "Full", "FULLY": "Full", "FULLMODULAR": "Full", "FULLYMODULAR": "Full",
    "MODULAR": "Full",
    "SEMI": "Semi", "SEMIMODULAR": "Semi",
    "NON": "Non", "NONMODULAR": "Non", "NONE": "Non", "FIXED": "Non",
}


def normalize_modularity(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    key = re.sub(r"[^A-Z]", "", value.upper())
    return _MODULARITY_CANONICAL.get(key)


# ------------------------------------------------------------------ dispatch

# Values that name nothing. Stored, they become a filter option that costs a click and
# tells the shopper nothing; as NULL the facets endpoint omits them entirely.
PLACEHOLDERS = {
    "", "unknown", "na", "n/a", "none", "-", "--", "generic", "other", "misc",
    "notspecified", "nospecified", "tbd",
    # Not an interface: it says what the drive is, not how it connects.
    "ssd",
}


def _is_placeholder(text: str) -> bool:
    return re.sub(r"[^a-z0-9/]", "", text.lower()) in PLACEHOLDERS

# spec column -> normalizer. Anything not listed is passed through unchanged.
NORMALIZERS = {
    "brand": normalize_brand,
    "socket": normalize_socket,
    "chipset": normalize_chipset,
    "resolution": normalize_resolution,
    "panel_type": normalize_panel_type,
    "efficiency_rating": normalize_efficiency,
    "interface": normalize_interface,
    "modularity": normalize_modularity,
}

# GPU shares column names with other categories but needs different rules for them.
CATEGORY_NORMALIZERS = {
    "GPU": {"chipset": normalize_gpu_chipset, "memory_type": normalize_gpu_memory_type},
}


def normalize_spec_value(column: str, value, category: str | None = None):
    """Canonical form of `value` for `column`, or None if it carries no information."""
    if not isinstance(value, str):
        return value

    # Applies to every column, including those with no dedicated normalizer - it is
    # how "Unknown" stays out of every filter rather than being handled per field and
    # forgotten in the one category nobody checked.
    if _is_placeholder(value):
        return None

    per_category = CATEGORY_NORMALIZERS.get(category or "", {})
    fn = per_category.get(column) or NORMALIZERS.get(column)
    return fn(value) if fn else (value.strip() or None)
