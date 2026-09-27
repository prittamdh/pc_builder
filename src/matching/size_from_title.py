"""The size a listing's title states, per category: VRAM, capacity, wattage, screen.

Used by the builder picker's size chips and by the daily identity audit (a model whose
listings state different sizes is a wrong merge). Titles are the source because they
are what every store publishes; a title with no size gives None, never a guess.
"""
from __future__ import annotations

import re

from matching.gpu_identity import memory_gb_from_title

_STORAGE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s?(TB|GB)\b", re.I)
_WATTS = re.compile(r"(?<![\d.])(\d{3,4})\s?(?:W|Watts?)\b", re.I)
_RAM_KIT = re.compile(r"(?<![\d.])(\d)\s?[xX*]\s?(\d{1,3})\s?GB\b", re.I)
_RAM_TOTAL = re.compile(r"(?<![\d.xX*])(\d{1,3})\s?GB\b", re.I)
_SCREEN = re.compile(r"(?<![\d.])(\d{2}(?:\.\d)?)\s?(?:\"|”|''|-?\s?inch(?:es)?\b|in\b)", re.I)


def storage_gb_from_title(title: str) -> int | None:
    m = _STORAGE.search(title or "")
    if not m:
        return None
    value = float(m.group(1)) * (1000 if m.group(2).upper() == "TB" else 1)
    return int(round(value))


def psu_watts_from_title(title: str) -> int | None:
    m = _WATTS.search(title or "")
    return int(m.group(1)) if m else None


def ram_gb_from_title(title: str) -> int | None:
    """Total kit capacity: "32GB (2x16GB)" and "2x16GB" are both 32."""
    t = title or ""
    total = _RAM_TOTAL.search(t)
    if total:
        return int(total.group(1))
    kit = _RAM_KIT.search(t)
    return int(kit.group(1)) * int(kit.group(2)) if kit else None


def screen_inches_from_title(title: str) -> float | None:
    m = _SCREEN.search(title or "")
    if not m:
        return None
    inches = float(m.group(1))
    return inches if 15 <= inches <= 57 else None


def _gb(n) -> str:
    return f"{n // 1000:g}TB" if n >= 1000 and n % 1000 == 0 else f"{n}GB"


# p_category -> (reader, label for a value). The label is what the chip shows and what
# the picker sends back, so it is the value compared on filtering.
SIZE_READERS = {
    "GPU": (memory_gb_from_title, lambda v: f"{v}GB"),
    "RAM": (ram_gb_from_title, lambda v: f"{v}GB"),
    "Storage": (storage_gb_from_title, _gb),
    "Power Supply": (psu_watts_from_title, lambda v: f"{v}W"),
    "Monitor": (screen_inches_from_title, lambda v: f'{v:g}"'),
}


def size_label(p_category: str | None, title: str) -> str | None:
    reader = SIZE_READERS.get(p_category or "")
    if reader is None:
        return None
    value = reader[0](title)
    return None if value is None else reader[1](value)


def size_sort_key(label: str) -> float:
    m = re.match(r"([\d.]+)\s*(TB|GB|W|\")?", label)
    if not m:
        return 0.0
    return float(m.group(1)) * (1000 if m.group(2) == "TB" else 1)
