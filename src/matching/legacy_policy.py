"""
Platform-currency policy: which parts are still worth offering in a new build.

The catalog tracks whatever the 10 retailers list, which includes a long tail of
genuinely obsolete hardware (LGA1155 boards, DDR3 kits, 3rd-gen Core chips). Those
are fine to keep for price history, but offering them in the PC Builder is worse
than useless - they crowd out real options and let someone assemble a machine
nobody should build in 2026.

Policy (set by the project owner, 2026-08-16):
  * Intel Core: 10th generation and newer. Core Ultra is always current.
  * AMD Ryzen: 3000 series and newer.
  * Motherboards: only sockets that can host a CPU meeting the above.
  * Memory: DDR4 and newer.

Everything here is a pure function of already-extracted spec fields so it can be
unit-tested and re-run cheaply. Uncertainty resolves to "current", never to
"legacy" - hiding a part we merely failed to identify would silently shrink the
catalog, which is the more damaging error.
"""
import re

# Sockets that can host a CPU meeting the generation policy above.
#   LGA1200  - Intel 10th/11th gen
#   LGA1700  - Intel 12th/13th/14th gen
#   LGA1851  - Intel Core Ultra (Arrow Lake)
#   AM4      - Ryzen 1000-5000; still current because 3000/5000 chips are in policy
#   AM5      - Ryzen 7000/9000
#   sTR5     - Threadripper 7000/9000
#   sWRX8    - Threadripper PRO 5000WX
#   LGA4677  - Xeon W-2400/3400
#   SP5      - EPYC 9004/9005
CURRENT_SOCKETS = {
    "LGA1200", "LGA1700", "LGA1851",
    "AM4", "AM5",
    "STR5", "SWRX8", "STRX4",
    "LGA4677", "SP5", "SP6",
}

# Explicitly retired sockets. Anything here is legacy even if it appears elsewhere.
LEGACY_SOCKETS = {
    "LGA775", "LGA1150", "LGA1151", "LGA1155", "LGA1156", "LGA1366",
    "LGA2011", "LGA2066", "2066", "AM3", "AM3+", "FM2", "FM2+", "TR4", "STR4",
}

CURRENT_MEMORY_TYPES = {"DDR4", "DDR5", "DDR6"}
LEGACY_MEMORY_TYPES = {"DDR", "DDR2", "DDR3", "DDR3L", "LPDDR3", "SDRAM"}

MIN_INTEL_CORE_GEN = 10
MIN_AMD_RYZEN_GEN = 3


def _normalize_socket(socket: str | None) -> str | None:
    if not socket:
        return None
    return re.sub(r"[^A-Z0-9]", "", socket.upper())


def intel_core_generation(model_number: str | None) -> int | None:
    """Generation from an Intel Core model number, or None if not determinable.

    Intel encodes generation in the leading digits, but the width varies:
    4-digit SKUs use one leading digit (3220 -> 3rd gen, 9350KF -> 9th), while
    5-digit SKUs use two (10105 -> 10th, 14600K -> 14th). Some scraped values
    carry an 'i3-' style prefix, so leading non-digits are stripped first.
    """
    if not model_number:
        return None
    text = str(model_number).strip()

    # Some listings state the generation in words instead of a SKU ("Core i7 8th Gen",
    # "3rd Gen 4 Cores 8 Threads"). Those parse to a bare leading digit otherwise,
    # which reads as an unusable 1-digit model and lets obsolete parts through.
    worded = re.search(r"\b(\d{1,2})\s*(?:st|nd|rd|th)\s*gen\b", text, flags=re.IGNORECASE)
    if worded:
        return int(worded.group(1))

    # Strip an 'i3-'/'i7 ' style tier prefix first: naively removing leading letters
    # would leave "3-6100" and misread the tier digit as the generation.
    cleaned = re.sub(r"^i[3579][-\s]*", "", text, flags=re.IGNORECASE)
    if cleaned == text:
        cleaned = re.sub(r"^[a-zA-Z]+[-\s]*", "", text)
    match = re.match(r"(\d+)", cleaned)
    if not match:
        return None
    digits = match.group(1)
    if len(digits) >= 5:
        return int(digits[:2])
    if len(digits) == 4:
        return int(digits[0])
    return None


def amd_ryzen_generation(model_number: str | None) -> int | None:
    """Series number from an AMD Ryzen/Threadripper model (5600X -> 5, 9970X -> 9)."""
    if not model_number:
        return None
    match = re.match(r"(\d)", str(model_number).strip())
    return int(match.group(1)) if match else None


def is_cpu_legacy(series: str | None, model_number: str | None, socket: str | None) -> bool:
    norm_socket = _normalize_socket(socket)
    if norm_socket in LEGACY_SOCKETS:
        return True

    series_text = (series or "").strip().lower()

    # Core Ultra (Arrow Lake and later) has no generation digit in the old sense.
    if "core ultra" in series_text:
        return False

    if "core i" in series_text or re.match(r"^i[3579]\b", series_text):
        gen = intel_core_generation(model_number)
        return gen is not None and gen < MIN_INTEL_CORE_GEN

    if "threadripper" in series_text:
        gen = amd_ryzen_generation(model_number)
        return gen is not None and gen < MIN_AMD_RYZEN_GEN

    if "ryzen" in series_text:
        gen = amd_ryzen_generation(model_number)
        return gen is not None and gen < MIN_AMD_RYZEN_GEN

    # Entry-level lines that never met the policy bar on any current platform.
    if series_text in {"pentium", "celeron", "athlon"}:
        return True

    # Unrecognized series: fall back to the socket, and keep it if that's unknown too.
    return False


def is_motherboard_legacy(socket: str | None) -> bool:
    norm = _normalize_socket(socket)
    if norm is None:
        return False  # unknown socket - keep rather than silently hide
    if norm in LEGACY_SOCKETS:
        return True
    return norm not in CURRENT_SOCKETS


def is_ram_legacy(memory_type: str | None) -> bool:
    if not memory_type:
        return False
    norm = memory_type.strip().upper()
    if norm in LEGACY_MEMORY_TYPES:
        return True
    return norm not in CURRENT_MEMORY_TYPES and norm.startswith("DDR")
