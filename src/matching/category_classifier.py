"""
Category Classifier for PC Hardware.
Classifies raw store/target category strings into canonical p_category values via direct dictionary mapping.
"""

PRODUCTION_CATEGORIES = [
    "CPU",
    "Motherboard",
    "GPU",
    "RAM",
    "Storage",
    "Cabinet",
    "Power Supply",
    "CPU Cooler",
    "Monitor",
    "Accessories",
]

# Direct 1-to-1 Exact Category Mapping Dictionary (No Title Regex Normalization)
CATEGORY_MAPPING = {
    # CPUs
    "CPU": "CPU",
    "Processor": "CPU",
    "Desktop Processors": "CPU",
    "Intel Processor": "CPU",
    "AMD Processor": "CPU",
    "Threadripper Processor": "CPU",
    
    # GPUs
    "GPU": "GPU",
    "Graphics Card": "GPU",
    "Graphics Card (NVIDIA)": "GPU",
    "Graphics Card (AMD)": "GPU",
    "AMD Graphics Card": "GPU",
    "NVIDIA RTX 50 Series": "GPU",
    "NVIDIA RTX 30 Series": "GPU",
    
    # Motherboards
    "Motherboard": "Motherboard",
    "Motherboards": "Motherboard",
    "Intel Motherboard": "Motherboard",
    "AMD Motherboard": "Motherboard",
    
    # RAM
    "RAM": "RAM",
    "Desktop RAM": "RAM",
    "Laptop RAM": "RAM",
    "Desktop RAM (DDR4)": "RAM",
    "Desktop RAM (DDR5)": "RAM",
    "Laptop RAM (DDR4)": "RAM",
    "Laptop RAM (DDR5)": "RAM",
    
    # Storage
    "Storage": "Storage",
    "SSD": "Storage",
    "HDD": "Storage",
    "Internal HDD": "Storage",
    "External HDD": "Storage",
    "Internal SSD": "Storage",
    "External SSD": "Storage",
    "NVMe SSD": "Storage",
    "M.2 NVMe SSD": "Storage",
    "M.2 SSD": "Storage",
    "Gen3 NVMe SSD": "Storage",
    "Gen4 NVMe SSD": "Storage",
    "Gen5 NVMe SSD": "Storage",
    "Laptop SSD": "Storage",
    "External Portable HDD": "Storage",
    "External Portable SSD": "Storage",
    "External Hard Disk": "Storage",
    "Hard Drive": "Storage",
    "SATA SSD": "Storage",
    '2.5" SATA SSD': "Storage",
    
    # Cabinets
    "Cabinet": "Cabinet",
    "Cabinet Case": "Cabinet",
    
    # Power Supply
    "PSU": "Power Supply",
    "Power Supply": "Power Supply",
    "Power Supply / SMPS": "Power Supply",
    
    # CPU Coolers
    "CPU Cooler": "CPU Cooler",
    "CPU Air Cooler": "CPU Cooler",
    "CPU Liquid Cooler": "CPU Cooler",
    "Cooling System": "CPU Cooler",
    "Cooling Systems": "CPU Cooler",
    
    # Monitors
    "Monitor": "Monitor",
    
    # Accessories & Peripherals
    "Gaming Headset": "Accessories",
    "Wireless Router": "Accessories",
    "Accessories": "Accessories",
}

# Discrete-GPU title indicators. Deliberately excludes bare "radeon" since AMD Ryzen
# CPUs legitimately advertise integrated "Radeon Graphics" (e.g. "Ryzen 5 8500G
# Processor with Radeon Graphics") - only phrases specific to standalone graphics
# cards are used here.
GPU_TITLE_INDICATORS = (
    "graphics card", "geforce", " rtx ", " gtx ", "radeon rx", "radeon pro", "radeon vii",
)

# CPU brand/family markers. Presence of one of these alongside a GPU_TITLE_INDICATORS
# match (e.g. "Ryzen ... with Radeon RX Vega Graphics") means the title is describing
# a CPU's integrated graphics, not a discrete card - so the CPU classification stands.
CPU_BRAND_INDICATORS = (
    "ryzen", "core i", "core ultra", "threadripper", "pentium",
    "celeron", "athlon", "epyc", "xeon",
)


# Audio gear that some stores file under Power Supply, presumably because it plugs in.
# A Sennheiser soundbar reached the PSU spec pipeline and had an efficiency rating
# scraped onto it before this guard existed.
AUDIO_INDICATORS = (
    "soundbar", "speaker", "headphone", "headset", "earbud", "earphone",
    "microphone", "subwoofer",
)


# Thermal interface material sold alongside coolers. It ships under the cooler
# category at several stores, but it is a consumable, not a mountable cooler - and a
# builder offering "Noctua NT-H2 AM5 Edition" as a CPU cooler is plainly wrong.
THERMAL_MATERIAL_INDICATORS = (
    "thermal paste", "thermal grease", "thermal compound", "thermal pad",
    "thermal putty", "nt-h1", "nt-h2",
)


def _title_indicates_discrete_gpu(title: str | None) -> bool:
    t = f" {(title or '').lower()} "
    if not any(marker in t for marker in GPU_TITLE_INDICATORS):
        return False
    return not any(marker in t for marker in CPU_BRAND_INDICATORS)


def _title_indicates_thermal_material(title: str | None) -> bool:
    t = f" {(title or '').lower()} "
    return any(marker in t for marker in THERMAL_MATERIAL_INDICATORS)


def _title_indicates_audio(title: str | None) -> bool:
    t = f" {(title or '').lower()} "
    return any(marker in t for marker in AUDIO_INDICATORS)


# Removable flash media that stores sometimes file under Graphics Card. A SanDisk
# 128GB memory card was the cheapest "GPU" in the catalog and would have led a
# price-ascending browse of graphics cards.
REMOVABLE_MEDIA_INDICATORS = (
    " memory card ", " sd card ", " microsd ", " micro sd ", " sdhc ", " sdxc ",
    " pen drive ", " pendrive ", " flash drive ", " compactflash ",
)


def _title_indicates_removable_media(title: str | None) -> bool:
    t = f" {(title or '').lower()} "
    return any(marker in t for marker in REMOVABLE_MEDIA_INDICATORS)


# High-confidence title markers, used only when the store gave us no usable category.
# Order matters: the first match wins, so the more specific phrases come first.
# Everything here has to be unambiguous on its own, because there is no raw category
# to cross-check against - anything doubtful is better left as Accessories.
TITLE_ONLY_CATEGORY_MARKERS = (
    ("Power Supply", ("power supply", "smps", "psu ", " psu")),
    ("CPU Cooler", ("cpu cooler", "air cooler", "liquid cooler", "aio cooler",
                    "cpu air cooler", "cpu liquid cooler")),
    ("Motherboard", ("motherboard", "mainboard")),
    ("Cabinet", ("cabinet", "pc case", "computer case", "mid tower", "full tower")),
    ("Monitor", ("monitor", "gaming monitor")),
    ("Storage", ("ssd", "nvme", "hard disk", "hard drive", " hdd")),
    ("RAM", ("ram ", " ram", "dimm", "memory module")),
)


def _classify_from_title(title: str | None) -> str | None:
    """Best-effort category from the title alone, or None if nothing is certain.

    Only consulted when the store supplied no category or one we don't recognise.
    Previously those products were filed as Accessories regardless of what they were,
    which hid real parts from the builder - an AMD Radeon Pro W7700 sat in Accessories
    because its listing carried no category at all.
    """
    if not title:
        return None

    # A discrete card is checked first: its detector already rules out CPUs
    # advertising integrated graphics, which the coarse markers below would not.
    if _title_indicates_discrete_gpu(title):
        return "GPU"
    if _title_indicates_removable_media(title) or _title_indicates_audio(title):
        return "Accessories"
    if _title_indicates_thermal_material(title):
        return "Accessories"

    t = f" {title.lower()} "
    if any(marker in t for marker in CPU_BRAND_INDICATORS):
        return "CPU"
    for category, markers in TITLE_ONLY_CATEGORY_MARKERS:
        if any(marker in t for marker in markers):
            return category
    return None


class CategoryClassifier:
    @staticmethod
    def get_p_category(raw_category: str | None = None, title: str | None = None) -> str:
        if not raw_category:
            return _classify_from_title(title) or "Accessories"

        cleaned_cat = raw_category.strip()

        # Direct Exact Match
        if cleaned_cat in CATEGORY_MAPPING:
            p_cat = CATEGORY_MAPPING[cleaned_cat]
        else:
            # Case-Insensitive Lookup Fallback
            c_low = cleaned_cat.lower()
            p_cat = next((v for k, v in CATEGORY_MAPPING.items() if k.lower() == c_low), None)

        if p_cat is None:
            return _classify_from_title(title) or "Accessories"

        # Store-side raw categories are sometimes wrong (e.g. a discrete GPU listed
        # under "Processor"). If the raw category maps to CPU but the title clearly
        # describes a standalone graphics card, trust the title instead.
        if p_cat == "CPU" and _title_indicates_discrete_gpu(title):
            return "GPU"

        # Thermal paste and pads ship under the cooler category but are consumables,
        # not coolers, and must never be offered to fill a build's cooler slot.
        if p_cat == "CPU Cooler" and _title_indicates_thermal_material(title):
            return "Accessories"

        # Audio devices are not power supplies, whatever the store filed them under.
        if p_cat == "Power Supply" and _title_indicates_audio(title):
            return "Accessories"

        # A memory card is not a graphics card. Removable media has no build slot, so
        # it belongs in Accessories rather than Storage, which feeds the drive slot.
        if p_cat == "GPU" and _title_indicates_removable_media(title):
            return "Accessories"

        return p_cat

