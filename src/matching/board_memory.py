"""A motherboard's memory slots and maximum memory when the listing doesn't say.

On 2026-10-08 only 34 of 903 listed boards had a slot count and none had a maximum,
so RAM vs motherboard read "Unverified" on nearly every build. Two facts fill most of it:

- Every desktop board has at least 2 DIMM slots, and Mini-ITX boards have exactly 2.
- The maximum memory is set by the platform (chipset + memory type) times the slots.
  Values below are the published platform limits, taking the LOWER figure where
  boards of one platform differ (owner rule: be conservative):
    * DDR5 (Intel 600/700/800, AMD AM5): 48GB per slot -> 96GB with 2, 192GB with 4.
    * DDR4 (Intel 400-700, AMD AM4): 32GB per slot -> 64GB with 2, 128GB with 4.
    * DDR4 (Intel 100-300, Skylake to Coffee Lake): 16GB per slot -> 32 / 64GB.
    * DDR3 (Intel 6-9 series, H61/B75/H81/B85 era): 8GB per slot -> 16 / 32GB.
  HEDT and workstation platforms (TRX50, WRX90, W790, X299...) vary too much by board
  and are left unknown.

The build summary says when a maximum is a platform estimate. Since it is a floor, RAM
above it is "unverified", never an error - the real board may take more.
"""
from __future__ import annotations

import re

from matching.form_factor import normalize_form_factor

MIN_DESKTOP_DIMM_SLOTS = 2

_DDR3_INTEL = {"H61", "H67", "P67", "Z68", "B65", "Q65", "Q67", "B75", "H77", "Z75", "Z77",
               "Q75", "Q77", "H81", "B85", "H87", "Z87", "Q85", "Q87", "H97", "Z97"}
_DDR4_INTEL_OLD = {"H110", "B150", "H170", "Z170", "Q150", "Q170", "B250", "H270", "Z270",
                   "Q250", "Q270", "H310", "B360", "B365", "H370", "Z370", "Z390", "Q370"}
_DDR4_NEW = {"H410", "B460", "H470", "Z490", "Q470", "H510", "B560", "H570", "Z590", "Q570",
             "H610", "B660", "H670", "Z690", "Q670", "B760", "H770", "Z790",
             "A320", "B350", "X370", "B450", "X470", "A520", "B550", "X570"}
_DDR5 = {"H610", "B660", "H670", "Z690", "Q670", "B760", "H770", "Z790", "H810", "B860", "Z890",
         "A620", "B650", "B650E", "X670", "X670E", "B840", "B850", "X870", "X870E"}

# (memory type, chipset set) -> GB per DIMM slot.
_GB_PER_SLOT = [
    ("DDR5", _DDR5, 48),
    ("DDR4", _DDR4_NEW, 32),
    ("DDR4", _DDR4_INTEL_OLD, 16),
    ("DDR3", _DDR3_INTEL, 8),
]

# Letter-prefixed chipset name, keeping AMD's "E" (X870E, B650E). Anything after it -
# a form-factor letter (B760M, X870I), "-A", "-P", "D", "G" - is the board's, not the chipset's.
_CHIPSET_RE = re.compile(r"^(TRX\d{2}|WRX\d{2}|[ABHPQWXZ]\d{2,3}E?)")


def base_chipset(chipset: str | None) -> str | None:
    m = _CHIPSET_RE.match((chipset or "").strip().upper())
    return m.group(1) if m else None


def board_slots(memory_slots: int | None, form_factor: str | None) -> int | None:
    """The slot count if listed, 2 for a Mini-ITX board, else None."""
    if memory_slots:
        return memory_slots
    if normalize_form_factor(form_factor) == "ITX":
        return 2
    return None


def platform_max_memory_gb(chipset: str | None, memory_type: str | None,
                           slots: int | None) -> int | None:
    """Platform limit for a board, or None when the platform isn't in the table.
    An unknown slot count counts as 2, the lower figure."""
    base = base_chipset(chipset)
    mem = (memory_type or "").strip().upper()
    for table_mem, chipsets, per_slot in _GB_PER_SLOT:
        if mem == table_mem and base in chipsets:
            return per_slot * (slots or MIN_DESKTOP_DIMM_SLOTS)
    return None
