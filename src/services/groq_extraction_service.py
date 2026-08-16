"""
Groq LLM Title Extraction Service.
Calls Groq's OpenAI-compatible chat completions API to extract structured
brand/series/model_number identity from noisy, human-errored product titles.
Starts with the CPU category; designed to extend to other categories later.
"""
import json
import time

import httpx

from common.logger import get_logger
from configs.settings import GROQ_API_KEY, MISTRAL_API_KEY

logger = get_logger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

# LLMs intermittently emit the STRING "null" (or "N/A"/"unknown"/"") instead of a real
# JSON null, even under response_format=json_object. Postgres rejects those outright for
# typed columns - an unguarded pass-through crashed a full motherboard spec run mid-batch
# with `invalid input syntax for type integer: "null"`. Every extraction script writing
# LLM output into typed columns should route values through these.
_NULLISH = {"null", "none", "n/a", "na", "nan", "unknown", "unspecified", "-", ""}


def nullify(value):
    """Normalize LLM stand-ins for missing data ("null", "N/A", "unknown", ...) to real None."""
    if isinstance(value, str) and value.strip().lower() in _NULLISH:
        return None
    return value


def as_int(value) -> int | None:
    """Coerce an LLM value to int, or None if it isn't a usable number."""
    value = nullify(value)
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def as_float(value) -> float | None:
    """Coerce an LLM value to float, or None if it isn't a usable number."""
    value = nullify(value)
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_str(value) -> str | None:
    """Coerce an LLM value to a non-empty string, or None."""
    value = nullify(value)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def as_bool(value) -> bool | None:
    """Coerce an LLM value to bool, or None if not clearly true/false."""
    value = nullify(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "yes", "1"}:
            return True
        if low in {"false", "no", "0"}:
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    return None

# Mistral's free tier (50,000 TPM / 50 RPM) is far more generous than Groq's free
# llama-3.1-8b-instant tier turned out to be in practice - same OpenAI-compatible
# chat completions shape, so it's a drop-in swap via GroqExtractionService(api_url=...).
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-small-latest"

# Kept compact deliberately: this system prompt is resent on every call and free-tier
# Groq plans are TPM-bound (llama-3.1-8b-instant: 6000 TPM), so trimming tokens here
# directly multiplies achievable throughput.
#
# CPU extraction is split into two stages because physical specs (TDP/cores/clocks/
# socket) are a property of the MODEL, not the listing - re-deriving them once per
# listing wastes API budget (~5x more calls than needed) and risks inconsistent
# answers for the same real chip across duplicate listings.
CPU_IDENTITY_BATCH_PROMPT = """Extract CPU identity from messy Indian retailer titles (typos like "Prosser"=Processor, truncation "...", OEM/Tray noise). Some titles leak from other categories (e.g. cabinets) - for those return brand "Unknown", null fields, confidence "low".
Return STRICT JSON only: {"results": [{"index": number, "brand": "Intel"|"AMD"|"Unknown", "series": string, "model_number": string, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input title's number (1-based). Titles are often near-duplicates - re-read each title's own digits carefully, don't let neighbors bleed into each other's result. One result per input title, exact count, any order (index is authoritative, not array position).
series = product line+tier, exact casing: "Core i3/i5/i7/i9", "Core Ultra 5/7/9", "Ryzen 3/5/7/9", "Ryzen Threadripper", "Ryzen Threadripper PRO", "Pentium", "Celeron", "Athlon", "Xeon".
model_number = alphanumeric code only, e.g. 14600K, 13700KF, 225F, 265K, 7800X3D, 9950X3D2, 7985WX. Exclude series/brand and marketing words (Processor/Desktop/OEM/Tray/Box/Plus). Ignore SKU codes in parentheses unless it's the only identifier.
confidence: high=clear, medium=inferred (e.g. truncated but obvious), low=guessing or non-CPU title. notes: short reason if not high, else null. Never refuse; always give best guess.

Titles (2 total, respond with exactly 2 results, each carrying its own index):
1. "Intel Core Ultra 5 225F 10 Core 10 Threads LGA 1851 Desktop Prosser"
2. "Amd Ryzen Threadripper Pro 7985WX Oem Op..."
{"results": [{"index": 1, "brand": "Intel", "series": "Core Ultra 5", "model_number": "225F", "confidence": "high", "notes": null}, {"index": 2, "brand": "AMD", "series": "Ryzen Threadripper PRO", "model_number": "7985WX", "confidence": "medium", "notes": "title truncated"}]}
"""

# Stage 2 input is a clean model name PLUS 1-2 real scraped listing titles for that
# model (grounding) - runs once per unique canonical model, not once per listing.
# Grounding in real text matters: an earlier ungrounded version of this prompt (pure
# "recall from training knowledge") confidently returned wrong specs for AMD
# Threadripper parts (e.g. 7980X as socket sTRX4/Zen 3 - the real answer is sTR5/Zen 4;
# 5965WX as 32c/64t - the real answer is 24c/48t) while flagging them "high confidence".
# Grounding + a hard extract-before-recall rule is the fix, not just prompt wording.
CPU_SPEC_BATCH_PROMPT = """For each CPU model, you get its clean name plus 1-2 real scraped retailer listing titles for that exact model. Extract physical specs.
Return STRICT JSON only: {"results": [{"index": number, "socket": string|null, "cores": number|null, "threads": number|null, "base_clock": number|null, "boost_clock": number|null, "tdp": number|null, "integrated_graphics": boolean|null, "architecture": string|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input model's number (1-based). One result per input model, exact count, any order (index is authoritative, not array position).
PRIORITY ORDER (follow strictly):
1. If a field's value is explicitly stated in the listing titles (e.g. "8 Cores 16 Threads", "5.3 GHz", "65W"), use that value - this is the most reliable source, mark confidence "high" for that model.
2. Only if a field is NOT present in any listing title, fill it from your own trained knowledge of that EXACT SKU - ONLY if you are genuinely certain of the real published spec. Otherwise leave it null. Mark confidence "medium" if some fields came from recall.
3. NEVER guess a plausible-sounding number for a field you're not sure about, whether from title or memory - null is always the correct answer when uncertain. Confidently-stated wrong numbers are worse than missing data. If you don't recognize the model at all and nothing is in the titles, return all nulls with confidence "low".
socket: e.g. "AM5", "AM4", "LGA1700", "LGA1851", "sTR5", "SP6" (not older/newer look-alikes - e.g. Threadripper 7000/9000 non-PRO uses sTR5, NOT sTRX4 which was the prior generation; Threadripper PRO uses sWRX8/sTR5 depending on generation - don't guess between them without certainty).
cores/threads: integers. base_clock/boost_clock: GHz as a number. tdp: Watts as a number.
integrated_graphics: false for Intel "F"/"KF" suffix or Threadripper/Xeon workstation parts; true for AMD "G"-suffix APUs; else your best-knowledge guess.
architecture: e.g. "Raptor Lake", "Arrow Lake", "Zen 4", "Zen 5".
notes: short reason if not high confidence, else null.

Models (2 total, respond with exactly 2 results, each carrying its own index):
1. Model: "Intel Core i5 14600K" | Listings: ["Intel Core i5-14600K Processor 14 Cores 20 Threads Up to 5.3GHz"]
2. Model: "AMD Ryzen Threadripper 9970X" | Listings: ["AMD Ryzen Threadripper 9970X Workstation Processor Tray"]
{"results": [{"index": 1, "socket": "LGA1700", "cores": 14, "threads": 20, "base_clock": null, "boost_clock": 5.3, "tdp": null, "integrated_graphics": true, "architecture": "Raptor Lake", "confidence": "high", "notes": "cores/threads/clock from listing; tdp/socket from recall"}, {"index": 2, "socket": null, "cores": null, "threads": null, "base_clock": null, "boost_clock": null, "tdp": null, "integrated_graphics": false, "architecture": null, "confidence": "low", "notes": "not stated in listing, not certain enough of exact specs to recall reliably"}]}
"""

MONITOR_IDENTITY_BATCH_PROMPT = """Extract monitor identity from messy Indian retailer titles. Some titles leak from other categories - for those return brand "Unknown", null fields, confidence "low".
Return STRICT JSON only: {"results": [{"index": number, "brand": string, "model_number": string|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input title's number (1-based). Titles are often near-duplicates (same model, different size/panel variant) - re-read each title's own text carefully. One result per input title, exact count, any order (index is authoritative, not array position).
brand: manufacturer (Samsung, LG, BenQ, Dell, ASUS, Acer, ViewSonic, MSI, Lenovo, AOC, etc), title-cased.
model_number: the specific model code, e.g. "AW3225QF", "XG27ACMES", "VA3208-4K-MHD", "LC32R500FHWXXL", "PD2506Q", "SE2725HG". This is usually a distinct alphanumeric code separate from marketing names like "Odyssey G8" or "ROG Strix" - include the marketing line as a prefix only if no separate code exists (e.g. "Odyssey G8" alone). Null if truly no identifying code/name exists.
confidence: high=clear model code present, medium=inferred/marketing-name-only, low=guessing or non-monitor title. notes: short reason if not high, else null. Never refuse; always give best guess.

Titles (2 total, respond with exactly 2 results, each carrying its own index):
1. "Dell Alienware AW3225QF 32\" 4K 240HZ QD-OLED Curved Gaming Monitor"
2. "Samsung Odyssey G8 34 Inch Gaming Monito..."
{"results": [{"index": 1, "brand": "Dell", "model_number": "AW3225QF", "confidence": "high", "notes": null}, {"index": 2, "brand": "Samsung", "model_number": "Odyssey G8", "confidence": "medium", "notes": "marketing name used as model, no separate code stated"}]}
"""

GPU_IDENTITY_BATCH_PROMPT = """Extract GPU identity from messy Indian retailer titles. Some titles leak from other categories - for those return brand "Unknown", null fields, confidence "low".
Return STRICT JSON only: {"results": [{"index": number, "brand": string, "chipset": string|null, "variant": string|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input title's number (1-based). Titles are often near-duplicates (same chipset, different AIB edition) - re-read each title's own text carefully. One result per input title, exact count, any order (index is authoritative, not array position).
brand: the AIB manufacturer (Asus, MSI, Gigabyte, Zotac, Sapphire, PowerColor, XFX, Galax, Inno3D, PNY, etc), title-cased - NOT Nvidia/AMD.
chipset: the GPU chip, normalized e.g. "RTX 5070 Ti", "RTX 4070 Ti SUPER", "RX 7800 XT", "RTX 3050". Keep Ti/Super/XT/XTX suffixes, uppercase RTX/RX/GTX prefix.
variant: the AIB's specific product line/edition, e.g. "TUF Gaming OC", "Eagle OC Ice", "Windforce Max OC", "Twin Edge OC", "ROG Strix". This is a REAL distinguishing SKU detail, not noise - two different variants of the same chipset are different products. Null only if truly no edition name is given (bare reference/founders-style card).
confidence: high=clear chipset+variant, medium=chipset clear but variant ambiguous/inferred, low=guessing or non-GPU title. notes: short reason if not high, else null. Never refuse; always give best guess.

Titles (2 total, respond with exactly 2 results, each carrying its own index):
1. "MSI RTX 5070 World of Warcraft Midnight Void Edition OC 12GB GDDR7 Graphics Card"
2. "ASUS GeForce RTX 3050 6GB GDDR6 Low Profile Graphics Card"
{"results": [{"index": 1, "brand": "MSI", "chipset": "RTX 5070", "variant": "World of Warcraft Midnight Void Edition OC", "confidence": "high", "notes": null}, {"index": 2, "brand": "Asus", "chipset": "RTX 3050", "variant": "Low Profile", "confidence": "medium", "notes": "no edition name beyond form factor"}]}
"""

STORAGE_IDENTITY_BATCH_PROMPT = """Extract storage drive identity from messy Indian retailer titles. Some titles leak from other categories - for those return brand "Unknown", null fields, confidence "low".
Return STRICT JSON only: {"results": [{"index": number, "brand": string, "model_number": string|null, "capacity_gb": number|null, "interface": string|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input title's number (1-based). Titles are often near-duplicates (same series, different capacity) - re-read each title's own digits carefully. One result per input title, exact count, any order (index is authoritative, not array position).
brand: manufacturer (WD/Western Digital, Samsung, Crucial, Kingston, Seagate, ADATA, XPG, Kioxia, TeamGroup, etc), title-cased.
model_number: the series/model name, e.g. "Blue SN5100", "980 Pro", "KC600", "Mars 980 Blade", "IronWolf Pro". Null if truly generic/no series name.
capacity_gb: total capacity as a number in GB (e.g. "2TB" -> 2000, "500GB" -> 500, "1TB" -> 1000).
interface: one of "NVMe Gen3", "NVMe Gen4", "NVMe Gen5", "SATA", "HDD" - infer generation from title if stated (Gen3/Gen4/Gen5/PCIe 3.0 etc), else just "NVMe" if PCIe/M.2 mentioned without a stated gen.
confidence: high=clear series+capacity+interface, medium=some inferred, low=guessing or non-storage title. notes: short reason if not high, else null. Never refuse; always give best guess.

Titles (2 total, respond with exactly 2 results, each carrying its own index):
1. "WD Blue SN5100 500GB NVMe Gen4 SSD (WDS500G1B0E)"
2. "Western Digital Blue 2TB 7200 RPM Desktop HDD"
{"results": [{"index": 1, "brand": "WD", "model_number": "Blue SN5100", "capacity_gb": 500, "interface": "NVMe Gen4", "confidence": "high", "notes": null}, {"index": 2, "brand": "Western Digital", "model_number": "Blue", "capacity_gb": 2000, "interface": "HDD", "confidence": "high", "notes": null}]}
"""

COOLER_IDENTITY_BATCH_PROMPT = """Extract CPU cooler identity from messy Indian retailer titles. Some titles leak from other categories - for those return brand "Unknown", null fields, confidence "low".
Return STRICT JSON only: {"results": [{"index": number, "brand": string, "model_number": string|null, "cooler_type": "Air"|"AIO Liquid"|"Unknown", "size_mm": number|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input title's number (1-based). Titles are often near-duplicates (same series, different radiator size) - re-read each title's own digits carefully. One result per input title, exact count, any order (index is authoritative, not array position).
brand: manufacturer (Corsair, Cooler Master, Deepcool, Thermaltake, NZXT, Ant Esports, Arctic, Noctua, be quiet!, etc), title-cased.
model_number: the series/model name, e.g. "Nautilus 360 RS", "Poseidon Elite", "ICEStorm 360", "Toughair 710". Null if truly generic.
cooler_type: "AIO Liquid" if "liquid"/"AIO"/radiator size in mm is mentioned with fans, "Air" if "air cooler"/heatsink+fan tower, else "Unknown".
size_mm: radiator size for AIO (120/240/280/360/420) or fan size for air coolers (92/120/140), from title. Null if not stated.
confidence: high=clear series+type, medium=some inferred, low=guessing or non-cooler title. notes: short reason if not high, else null. Never refuse; always give best guess.

Titles (2 total, respond with exactly 2 results, each carrying its own index):
1. "Corsair Nautilus 360 RS ARGB Liquid CPU Cooler"
2. "Thermaltake Toughair 710 140mm CPU Air Cooler"
{"results": [{"index": 1, "brand": "Corsair", "model_number": "Nautilus 360 RS", "cooler_type": "AIO Liquid", "size_mm": 360, "confidence": "high", "notes": null}, {"index": 2, "brand": "Thermaltake", "model_number": "Toughair 710", "cooler_type": "Air", "size_mm": 140, "confidence": "high", "notes": null}]}
"""

CABINET_IDENTITY_BATCH_PROMPT = """Extract PC cabinet/case identity from messy Indian retailer titles. Some titles leak from other categories - for those return brand "Unknown", null fields, confidence "low".
Return STRICT JSON only: {"results": [{"index": number, "brand": string, "model_number": string|null, "color": string|null, "form_factor": string|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input title's number (1-based). Titles are often near-duplicates (same model, different color) - re-read each title's own text carefully; color is a REAL distinguishing detail here, not noise - two colorways of the same model are different SKUs. One result per input title, exact count, any order (index is authoritative, not array position).
brand: manufacturer (Corsair, Cooler Master, Deepcool, Antec, Lian Li, NZXT, Zebronics, Ant Esports, Montech, etc), title-cased.
model_number: the model/series name only, WITHOUT color words, e.g. "Xtender VG ARGB", "VX310 ARGB", "CH690 Digital", "Elite 690 Wood", "3000D Airflow". Null if truly generic.
color: e.g. "Black", "White", "Black/White", null if not stated.
form_factor: "ATX"|"mATX"|"ITX"|"E-ATX"|"SFF" if stated, else null.
confidence: high=clear model+color, medium=some inferred, low=guessing or non-cabinet title. notes: short reason if not high, else null. Never refuse; always give best guess.

Titles (2 total, respond with exactly 2 results, each carrying its own index):
1. "Antec VX310 ARGB with 4 Fans ATX Cabinet (Black)"
2. "Deepcool CH690 Digital WH ATX Cabinet Wh..."
{"results": [{"index": 1, "brand": "Antec", "model_number": "VX310 ARGB", "color": "Black", "form_factor": "ATX", "confidence": "high", "notes": null}, {"index": 2, "brand": "Deepcool", "model_number": "CH690 Digital", "color": "White", "form_factor": "ATX", "confidence": "high", "notes": null}]}
"""

PSU_IDENTITY_BATCH_PROMPT = """Extract power supply (PSU) identity from messy Indian retailer titles. Some titles leak from other categories - for those return brand "Unknown", null fields, confidence "low".
Return STRICT JSON only: {"results": [{"index": number, "brand": string, "model_number": string|null, "wattage": number|null, "efficiency_rating": string|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input title's number (1-based). Titles are often near-duplicates (same series, different wattage) - re-read each title's own digits carefully. One result per input title, exact count, any order (index is authoritative, not array position).
brand: manufacturer (Corsair, Cooler Master, Thermaltake, GIGABYTE, MSI, Seasonic, Antec, Ant Esports, Deepcool, etc), title-cased.
model_number: the series/model name, e.g. "Toughpower GF A3", "V SFX", "P650SS", "Smart BM3". Null if truly generic.
wattage: number only, e.g. "1050 Watt" -> 1050, "650W" -> 650.
efficiency_rating: normalize to "80+ White"|"80+ Bronze"|"80+ Silver"|"80+ Gold"|"80+ Platinum"|"80+ Titanium" if stated, else null.
confidence: high=clear series+wattage, medium=some inferred, low=guessing or non-PSU title. notes: short reason if not high, else null. Never refuse; always give best guess.

Titles (2 total, respond with exactly 2 results, each carrying its own index):
1. "Thermaltake Toughpower GF A3 1050 Watt 80 Plus Gold ATX 3.0 SMPS"
2. "GIGABYTE P650SS 80+ Silver ATX 3.1 Non Modular Power Supply (Black) (650W)"
{"results": [{"index": 1, "brand": "Thermaltake", "model_number": "Toughpower GF A3", "wattage": 1050, "efficiency_rating": "80+ Gold", "confidence": "high", "notes": null}, {"index": 2, "brand": "GIGABYTE", "model_number": "P650SS", "wattage": 650, "efficiency_rating": "80+ Silver", "confidence": "high", "notes": null}]}
"""

MOTHERBOARD_IDENTITY_BATCH_PROMPT = """Extract motherboard identity AND compatibility fields from messy Indian retailer titles. Some titles leak from other categories - for those return brand "Unknown", null fields, confidence "low".
Return STRICT JSON only: {"results": [{"index": number, "brand": string, "chipset": string|null, "model_number": string|null, "socket": string|null, "memory_type": "DDR4"|"DDR5"|null, "form_factor": "ITX"|"MATX"|"ATX"|"EATX"|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input title's number (1-based). Titles are often near-duplicates (same model line, different chipset tier) - re-read each title's own text carefully. One result per input title, exact count, any order (index is authoritative, not array position).
brand: manufacturer (Asus, MSI, Gigabyte, ASRock, Colorful, Biostar, etc), title-cased.
chipset: copy the chipset code EXACTLY as the title spells it, uppercase, KEEPING any trailing variant letter - "B850I" stays "B850I", "B650M" stays "B650M", never shorten to "B850"/"B650". That letter marks a physically different board (I=mini-ITX, M=micro-ATX) with a different DIMM count, so dropping it merges two different products. E.g. "B850", "B850I", "B650M", "X870E", "Z890", "B760", "TRX50", "SP6". Null if not identifiable.
model_number: the model line WITHOUT brand/chipset, e.g. "MPG EDGE TI WIFI", "AORUS PRO WIFI7", "CVN GAMING FROZEN V14", "PRO-P WiFi". Keep any short "-X" model suffix that distinguishes board variants ("ROG STRIX-A" vs "-F" vs "-G" vs "-I"). Null if truly generic.
socket: prefer what's explicitly stated in the title (e.g. "AM5", "LGA1700", "LGA1851", "sTR5"). If not stated, infer from the chipset using well-known chipset-to-socket mappings (AMD: A620/B650/B850/X670/X870 series -> AM5; A520/B550/X570 -> AM4; TRX40/TRX50/WRX90 -> sTR5; Intel: B760/Z790/H610/12th-14th gen chipsets -> LGA1700; B860/Z890 -> LGA1851). Null only if you truly can't tell.
memory_type: from title if stated ("DDR5"/"DDR4"); if not stated, infer from socket/chipset generation only if very confident (e.g. AM5/LGA1851 boards are DDR5-only; older AM4/most LGA1700 boards are DDR4 unless "DDR5" variant stated) - else null.
form_factor: ITX/MATX/ATX/EATX, from the chipset variant letter (I->ITX, M->MATX) or stated literally in the title ("Micro-ATX"->MATX, "Mini-ITX"->ITX, "E-ATX"->EATX). Null if neither - do NOT infer it from the model line or from what you know of the board.
confidence: high=clear chipset+model, medium=some inferred, low=guessing or non-motherboard title. notes: short reason if not high, else null. Never refuse; always give best guess.

Titles (3 total, respond with exactly 3 results, each carrying its own index):
1. "MSI MPG B850 EDGE TI WIFI ATX Motherboard"
2. "Gigabyte B860M AORUS PRO WIFI7 Motherboard"
3. "MSI MPG B850I Edge TI WiFi Motherboard"
{"results": [{"index": 1, "brand": "MSI", "chipset": "B850", "model_number": "MPG EDGE TI WIFI", "socket": "AM5", "memory_type": "DDR5", "form_factor": "ATX", "confidence": "high", "notes": null}, {"index": 2, "brand": "Gigabyte", "chipset": "B860M", "model_number": "AORUS PRO WIFI7", "socket": "LGA1851", "memory_type": "DDR5", "form_factor": "MATX", "confidence": "high", "notes": "form factor from M suffix in chipset code"}, {"index": 3, "brand": "MSI", "chipset": "B850I", "model_number": "MPG EDGE TI WIFI", "socket": "AM5", "memory_type": "DDR5", "form_factor": "ITX", "confidence": "high", "notes": "B850I kept intact - different board from the B850"}]}
"""

# Stage 2 input is a clean model name plus 1-2 real scraped listing titles for that
# model - screen_size/resolution/refresh_rate/panel_type/response_time are almost
# always stated explicitly in retail titles, so this is mostly text extraction, not
# memory recall, and carries much lower hallucination risk than CPU physical specs.
MONITOR_SPEC_BATCH_PROMPT = """For each monitor model, you get its clean identity plus 1-2 real scraped retailer listing titles for that exact model. Extract display specs.
Return STRICT JSON only: {"results": [{"index": number, "screen_size_inch": number|null, "resolution": string|null, "refresh_rate_hz": number|null, "panel_type": string|null, "response_time_ms": number|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input model's number (1-based). One result per input model, exact count, any order (index is authoritative, not array position).
PRIORITY ORDER: 1) use values explicitly stated in the listing titles (this is almost always where these specs come from - mark confidence "high"). 2) Only if truly absent from every listing, and you're genuinely certain of that exact model's real spec, fill from knowledge (confidence "medium"). 3) NEVER guess a plausible number - null is correct when uncertain.
screen_size_inch: number (e.g. 27, 32, 21.5). resolution: normalize to one of "FHD"|"QHD"|"2K"|"4K"|"UHD"|"5K"|"8K"|exact pixel dims like "2560x1440" if that's all that's given. refresh_rate_hz: integer (e.g. 60, 144, 240). panel_type: "IPS"|"VA"|"OLED"|"QD-OLED"|"TN"|"Mini LED" etc, from title. response_time_ms: number (e.g. 1, 0.5, 5).
notes: short reason if not high confidence, else null.

Models (2 total, respond with exactly 2 results, each carrying its own index):
1. Identity: "BenQ PD2506Q" | Listings: ["BENQ PD2506Q 25 Inch 2K QHD 60Hz IPS Panel 100% SRGB 5MS AMD Freesync Gaming Monitor"]
2. Identity: "Samsung Odyssey G8" | Listings: ["Samsung Odyssey G8 34 Inch Gaming Monito..."]
{"results": [{"index": 1, "screen_size_inch": 25, "resolution": "2K", "refresh_rate_hz": 60, "panel_type": "IPS", "response_time_ms": 5, "confidence": "high", "notes": null}, {"index": 2, "screen_size_inch": 34, "resolution": null, "refresh_rate_hz": null, "panel_type": null, "response_time_ms": null, "confidence": "low", "notes": "listing truncated, only size stated"}]}
"""

# Physical-spec Stage 2 prompts for the remaining canonical_id-keyed *_specs tables
# (re-keyed from per-listing to per-unique-model 2026-08-16, matching the CPU/Monitor
# pattern). Same grounding discipline as CPU/Monitor Stage 2: extract from the real
# listing text first, only fall back to trained-knowledge recall when genuinely
# certain, null beats a confidently-wrong guess.

GPU_SPEC_BATCH_PROMPT = """For each GPU model, you get its clean identity (AIB brand + chipset + variant) plus 1-2 real scraped retailer listing titles for that exact model. Extract physical/electrical specs.
Return STRICT JSON only: {"results": [{"index": number, "memory_size_gb": number|null, "memory_type": string|null, "length_mm": number|null, "tdp": number|null, "recommended_psu": number|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input model's number (1-based). One result per input model, exact count, any order (index is authoritative, not array position).
PRIORITY ORDER: 1) use values stated in the listing titles (memory size/type is almost always there, e.g. "12GB GDDR6X" - mark high). 2) length_mm/tdp/recommended_psu are rarely in retailer titles - only fill from trained knowledge if you are genuinely certain of that EXACT AIB variant's real spec (different AIB editions of the same chipset can have meaningfully different card lengths - don't average/guess). 3) Null beats a plausible-sounding wrong number, especially for length_mm which varies a lot by AIB cooler design.
memory_type: "GDDR6"|"GDDR6X"|"GDDR7"|"HBM2" etc. length_mm: physical card length in mm. tdp: rated board power in Watts. recommended_psu: manufacturer's minimum recommended PSU wattage if known, else null.
notes: short reason if not high confidence, else null.

Models (2 total, respond with exactly 2 results, each carrying its own index):
1. Identity: "Asus RTX 4070 Ti SUPER TUF Gaming OC" | Listings: ["ASUS TUF Gaming RTX 4070 Ti SUPER OC Edition 16GB GDDR6X Graphics Card"]
2. Identity: "MSI RX 7600 Gaming X" | Listings: ["MSI Gaming X RX 7600 8GB Graphics Card"]
{"results": [{"index": 1, "memory_size_gb": 16, "memory_type": "GDDR6X", "length_mm": null, "tdp": null, "recommended_psu": 750, "confidence": "medium", "notes": "memory stated in title; length/tdp not stated, not certain enough of this exact AIB edition's dimensions"}, {"index": 2, "memory_size_gb": 8, "memory_type": null, "length_mm": null, "tdp": null, "recommended_psu": null, "confidence": "low", "notes": "only memory size stated"}]}
"""

MOTHERBOARD_SPEC_BATCH_PROMPT = """For each motherboard model, you get its clean identity (brand + chipset + model) plus 1-2 real scraped retailer listing titles for that exact model. Extract memory-slot capacity specs (socket/memory_type/form_factor are handled elsewhere - do NOT include them).
Return STRICT JSON only: {"results": [{"index": number, "memory_slots": number|null, "max_memory_gb": number|null, "m2_slots": number|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input model's number (1-based). One result per input model, exact count, any order (index is authoritative, not array position).
PRIORITY ORDER: 1) use values stated in the listing titles (e.g. "4 DIMM", "Dual M.2", "128GB Max Memory" - mark high). 2) Only fall back to trained knowledge of that exact board model if genuinely certain - board memory slot counts vary a lot even within the same chipset family, don't infer from chipset alone. 3) Null beats a guess.
memory_slots: integer DIMM slot count (e.g. mini-ITX boards are usually 2, most ATX are 4). max_memory_gb: total supported RAM in GB. m2_slots: integer M.2 slot count if stated.
notes: short reason if not high confidence, else null.

Models (2 total, respond with exactly 2 results, each carrying its own index):
1. Identity: "MSI MPG B850 Edge Ti WiFi" | Listings: ["MSI MPG B850 EDGE TI WIFI AM5 ATX Motherboard, 4x DDR5 Slots, 2x M.2"]
2. Identity: "Asus ROG Strix Z890-I Gaming" | Listings: ["Asus ROG Strix Z890-I Gaming WiFi Mini-ITX Motherboard"]
{"results": [{"index": 1, "memory_slots": 4, "max_memory_gb": null, "m2_slots": 2, "confidence": "medium", "notes": "slot counts stated, max capacity not stated"}, {"index": 2, "memory_slots": null, "max_memory_gb": null, "m2_slots": null, "confidence": "low", "notes": "Mini-ITX board, typically 2 DIMM slots, but not stated in title and not certain enough of this exact model"}]}
"""

PSU_SPEC_BATCH_PROMPT = """For each PSU model, you get its clean identity (brand + model + wattage) plus 1-2 real scraped retailer listing titles for that exact model. Extract efficiency/modularity specs (wattage/form_factor are handled elsewhere - do NOT include them).
Return STRICT JSON only: {"results": [{"index": number, "efficiency_rating": string|null, "modularity": string|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input model's number (1-based). One result per input model, exact count, any order (index is authoritative, not array position).
These specs are almost always stated directly in PSU retail titles - if not present in the title, mark low confidence rather than guessing from trained knowledge (efficiency tier and modularity are marketing-critical, retailers virtually never omit them, so their absence usually means the LISTING is ambiguous, not that you should recall it).
efficiency_rating: normalize to "80+ White"|"80+ Bronze"|"80+ Silver"|"80+ Gold"|"80+ Platinum"|"80+ Titanium", null if not stated. modularity: "Full"|"Semi"|"Non", null if not stated.
notes: short reason if not high confidence, else null.

Models (2 total, respond with exactly 2 results, each carrying its own index):
1. Identity: "Corsair RM850x 850W" | Listings: ["Corsair RM850x 850W 80+ Gold Fully Modular ATX Power Supply"]
2. Identity: "Ant Esports VS500L 500W" | Listings: ["Ant Esports VS500L 500W Power Supply"]
{"results": [{"index": 1, "efficiency_rating": "80+ Gold", "modularity": "Full", "confidence": "high", "notes": null}, {"index": 2, "efficiency_rating": null, "modularity": null, "confidence": "low", "notes": "not stated in title"}]}
"""

CABINET_SPEC_BATCH_PROMPT = """For each PC cabinet/case model, you get its clean identity (brand + model) plus 1-2 real scraped retailer listing titles for that exact model. Extract maximum clearance dimensions (form_factor is handled elsewhere - do NOT include it).
Return STRICT JSON only: {"results": [{"index": number, "max_gpu_length_mm": number|null, "max_cooler_height_mm": number|null, "max_psu_length_mm": number|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input model's number (1-based). One result per input model, exact count, any order (index is authoritative, not array position).
These are deep spec-sheet numbers that retailer titles almost never state - only fill a value if it is EXPLICITLY present in the listing text (e.g. "supports GPU up to 400mm"), or if you are genuinely certain of that exact case model's published clearance spec from trained knowledge. Do NOT estimate from case size/form-factor category (e.g. "it's a mid-tower so probably ~350mm") - that is exactly the kind of plausible-sounding guess that must stay null instead. Expect most results to be null - that is the correct, honest outcome for this field.
notes: short reason if not high confidence, else null.

Models (2 total, respond with exactly 2 results, each carrying its own index):
1. Identity: "Lian Li O11 Dynamic EVO" | Listings: ["Lian Li O11 Dynamic EVO ATX Mid Tower Case, Supports up to 422mm GPU, 167mm CPU Cooler"]
2. Identity: "Ant Esports ICE-130TG" | Listings: ["Ant Esports ICE-130TG Mid Tower Cabinet"]
{"results": [{"index": 1, "max_gpu_length_mm": 422, "max_cooler_height_mm": 167, "max_psu_length_mm": null, "confidence": "high", "notes": "GPU/cooler clearance explicitly stated"}, {"index": 2, "max_gpu_length_mm": null, "max_cooler_height_mm": null, "max_psu_length_mm": null, "confidence": "low", "notes": "no dimensions stated, not a well-known enough model to recall exact spec"}]}
"""

COOLER_SPEC_BATCH_PROMPT = """For each CPU cooler model, you get its clean identity (brand + model) plus 1-2 real scraped retailer listing titles for that exact model. Extract compatibility/rating specs (cooler_type/radiator_size_mm are handled elsewhere - do NOT include them).
Return STRICT JSON only: {"results": [{"index": number, "fan_size_mm": number|null, "supported_sockets": string|null, "tdp_rating": number|null, "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input model's number (1-based). One result per input model, exact count, any order (index is authoritative, not array position).
PRIORITY ORDER: 1) use values stated in the listing titles (e.g. "120mm Fan", "Supports LGA1700/AM5", "250W TDP" - mark high). 2) Only fall back to trained knowledge if genuinely certain of that exact model's published spec. 3) Null beats a guess - especially supported_sockets, since guessing wrong here could tell a user an incompatible cooler will fit.
fan_size_mm: integer (e.g. 120, 140). supported_sockets: comma-separated list as stated, e.g. "LGA1700,LGA1851,AM5,AM4", null if not stated/uncertain. tdp_rating: Watts the cooler is rated to dissipate, null if not stated.
notes: short reason if not high confidence, else null.

Models (2 total, respond with exactly 2 results, each carrying its own index):
1. Identity: "Deepcool AK620" | Listings: ["Deepcool AK620 Dual Tower CPU Air Cooler, 260W TDP, Compatible with LGA1700/1851/AM5/AM4, Dual 120mm Fans"]
2. Identity: "Cooler Master Hyper 212" | Listings: ["Cooler Master Hyper 212 Black Edition CPU Cooler"]
{"results": [{"index": 1, "fan_size_mm": 120, "supported_sockets": "LGA1700,LGA1851,AM5,AM4", "tdp_rating": 260, "confidence": "high", "notes": null}, {"index": 2, "fan_size_mm": null, "supported_sockets": null, "tdp_rating": null, "confidence": "low", "notes": "no specs stated in title"}]}
"""

RAM_BATCH_SYSTEM_PROMPT = """Extract RAM identity from messy Indian retailer titles. Some titles are not RAM at all (leaked from other categories, e.g. cabinets) - for those return brand "Unknown" and null fields with confidence "low".
Return STRICT JSON only: {"results": [{"index": number, "brand": string, "series": string|null, "memory_type": "DDR3"|"DDR4"|"DDR5"|"Unknown", "modules": number|null, "capacity_per_module_gb": number|null, "capacity_gb": number|null, "speed_mhz": number|null, "cl_timing": string|null, "form_factor": "Desktop"|"Laptop"|"Unknown", "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
CRITICAL: "index" MUST equal the input title's number (1-based). Titles are often near-duplicates of each other (same series, differing only in color/capacity/speed) - re-read each title's own digits carefully and do not let neighboring similar titles bleed into each other's result. One result per input title, exact count, any order (index is authoritative, not array position).
brand: manufacturer (Corsair, Kingston, G.Skill, Crucial, ADATA, TeamGroup, HP, Zebronics, etc), title-cased.
series: product line only if named (e.g. "Vengeance", "Fury Beast", "T-Force Vulcan Z", "XPG Lancer Blade", "Trident Z5", "Premier"), else null.
memory_type: from title; if absent infer from speed_mhz (DDR3 <=2400, DDR4 2133-3600ish, DDR5 4800+), else "Unknown".
KIT FIELDS - many listings are kits of multiple identical sticks, e.g. "16GB (8GBx2)" or "32GB (16GBX2)":
  modules = stick count (e.g. "8GBx2" -> 2; "16GB" alone with no "x" multiplier -> 1).
  capacity_per_module_gb = size of ONE stick (e.g. "8GBx2" -> 8; "16GB" alone -> 16).
  capacity_gb = TOTAL kit capacity = modules * capacity_per_module_gb (e.g. "8GBx2" -> 16; "16GB" alone -> 16).
  If title gives only a total with no per-stick breakdown, assume modules=1 and capacity_per_module_gb=capacity_gb.
speed_mhz: number only. cl_timing: e.g. "CL16" (keep the CL prefix), null if absent.
form_factor: "Laptop"/"SODIMM" mentions -> "Laptop", else "Desktop" unless clearly unknown.
confidence/notes: same convention as elsewhere - high=clear, medium=inferred, low=guessing or non-RAM title. Never refuse.

Titles (3 total, respond with exactly 3 results, each carrying its own index):
1. "HP V10 16GB (8GBx2) RGB DDR4 RAM 3600MHz CL16 Gaming Desktop Memory"
2. "Crucial 8GB DDR4 RAM 2666MHz CL19 Laptop Memory"
3. "COOLER MASTER MASTER FRAME 600 Mesh ARGB EATX Mid Tower Cabinet"
{"results": [{"index": 1, "brand": "HP", "series": "V10", "memory_type": "DDR4", "modules": 2, "capacity_per_module_gb": 8, "capacity_gb": 16, "speed_mhz": 3600, "cl_timing": "CL16", "form_factor": "Desktop", "confidence": "high", "notes": null}, {"index": 2, "brand": "Crucial", "series": null, "memory_type": "DDR4", "modules": 1, "capacity_per_module_gb": 8, "capacity_gb": 8, "speed_mhz": 2666, "cl_timing": "CL19", "form_factor": "Laptop", "confidence": "high", "notes": null}, {"index": 3, "brand": "Unknown", "series": null, "memory_type": "Unknown", "modules": null, "capacity_per_module_gb": null, "capacity_gb": null, "speed_mhz": null, "cl_timing": null, "form_factor": "Unknown", "confidence": "low", "notes": "not a RAM listing, appears to be a cabinet"}]}
"""


class GroqExtractionError(Exception):
    pass


class GroqExtractionService:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = GROQ_MODEL,
        api_url: str = GROQ_API_URL,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or GROQ_API_KEY
        if not self.api_key:
            raise GroqExtractionError("No API key configured for this provider.")
        self.model = model
        self.api_url = api_url
        self.client = httpx.Client(timeout=timeout)

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _call(self, system_prompt: str, user_content: str, max_retries: int = 4) -> dict:
        """
        Low-level Groq chat completion call with retry/backoff on rate limits and
        server errors. Returns {"parsed": dict, "raw_response": dict, "model": str}.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = None
        for attempt in range(max_retries):
            try:
                resp = self.client.post(self.api_url, headers=headers, json=payload)
            except httpx.HTTPError as e:
                last_error = e
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("retry-after", 2 ** attempt))
                logger.warning(f"Groq rate limited, retrying in {retry_after}s (attempt {attempt + 1})")
                time.sleep(retry_after)
                continue

            if resp.status_code >= 500:
                last_error = GroqExtractionError(f"Groq server error {resp.status_code}: {resp.text[:300]}")
                time.sleep(2 ** attempt)
                continue

            if resp.status_code != 200:
                raise GroqExtractionError(f"Groq API error {resp.status_code}: {resp.text[:500]}")

            body = resp.json()
            content = body["choices"][0]["message"]["content"]
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                raise GroqExtractionError(f"Groq returned non-JSON content: {content[:300]}") from e

            return {
                "parsed": parsed,
                "raw_response": body,
                "model": self.model,
            }

        raise GroqExtractionError(f"Groq API failed after {max_retries} attempts: {last_error}")

    def extract_batch(self, system_prompt: str, titles: list[str], max_retries: int = 4) -> list[dict]:
        """
        Extracts structured fields for multiple titles in a single Groq call, amortizing
        the fixed system-prompt token cost across the batch (important under TPM-bound
        free-tier rate limits). system_prompt must instruct the model to return
        {"results": [ {...}, ... ]} with exactly len(titles) objects in input order.

        Falls back to a recursive bisection (and eventually single-item calls) if the
        model returns a mismatched result count, to avoid ever misaligning a result
        with the wrong title.
        """
        if not titles:
            return []

        numbered = "\n".join(f'{i + 1}. "{t}"' for i, t in enumerate(titles))
        user_content = f"Titles ({len(titles)} total, respond with exactly {len(titles)} results in order):\n{numbered}"

        try:
            result = self._call(system_prompt, user_content, max_retries=max_retries)
            items = result["parsed"].get("results")
            if not isinstance(items, list) or len(items) != len(titles):
                raise GroqExtractionError(
                    f"Batch size mismatch: expected {len(titles)}, got "
                    f"{len(items) if isinstance(items, list) else type(items)}"
                )

            by_index = {}
            for item in items:
                idx = item.get("index")
                if not isinstance(idx, int) or idx in by_index:
                    raise GroqExtractionError(f"Batch index invalid or duplicated: {idx}")
                by_index[idx] = item
            if set(by_index.keys()) != set(range(1, len(titles) + 1)):
                raise GroqExtractionError(f"Batch indices don't cover 1..{len(titles)}: got {sorted(by_index.keys())}")

            return [
                {"parsed": by_index[i], "raw_response": result["raw_response"], "model": result["model"]}
                for i in range(1, len(titles) + 1)
            ]
        except GroqExtractionError as e:
            if len(titles) == 1:
                raise
            logger.warning(f"Batch of {len(titles)} failed ({e}), bisecting and retrying.")
            mid = len(titles) // 2
            return self.extract_batch(system_prompt, titles[:mid], max_retries=max_retries) + \
                self.extract_batch(system_prompt, titles[mid:], max_retries=max_retries)
