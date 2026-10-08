import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from matching.board_memory import (  # noqa: E402
    base_chipset, board_slots, platform_max_memory_gb,
)


@pytest.mark.parametrize("raw,base", [
    ("B760M", "B760"), ("X870E", "X870E"), ("B650EM", "B650E"), ("X870I", "X870"),
    ("X870-A", "X870"), ("B650M-P", "B650"), ("Z790D", "Z790"), ("B860G", "B860"),
    ("h610m", "H610"), (" H81M ", "H81"), ("TRX50", "TRX50"), ("WRX90E", "WRX90"),
    (None, None), ("", None), ("SP5", None),
])
def test_base_chipset(raw, base):
    assert base_chipset(raw) == base


@pytest.mark.parametrize("slots,form_factor,expected", [
    (4, "ATX", 4), (2, "ATX", 2), (None, "ITX", 2), (None, "Mini-ITX", 2),
    (None, "ATX", None), (None, "MATX", None), (None, None, None), (4, "ITX", 4),
])
def test_board_slots(slots, form_factor, expected):
    assert board_slots(slots, form_factor) == expected


@pytest.mark.parametrize("chipset,memory_type,slots,expected", [
    # DDR4: 64GB with 2 slots, 128GB with 4.
    ("B550M", "DDR4", 4, 128), ("B550M", "DDR4", 2, 64), ("H610M", "DDR4", 2, 64),
    ("B760M", "DDR4", 4, 128), ("A520M", "DDR4", 2, 64),
    # DDR5: the lower published figure - 96GB with 2 slots, 192GB with 4.
    ("Z890", "DDR5", 4, 192), ("B650M", "DDR5", 2, 96), ("X870E", "DDR5", 4, 192),
    ("H610M", "DDR5", 2, 96), ("B840M", "DDR5", 2, 96),
    # Old Intel H61/H81/B85 era: 16GB with 2 slots, 32GB with 4.
    ("H81M", "DDR3", 2, 16), ("B85", "DDR3", 4, 32), ("H61", "DDR3", 2, 16),
    # Intel 100-300 series DDR4: 32GB with 2, 64GB with 4.
    ("H310M", "DDR4", 2, 32), ("H110M", "DDR4", 4, 64), ("Q270", "DDR4", 4, 64),
])
def test_known_platforms(chipset, memory_type, slots, expected):
    assert platform_max_memory_gb(chipset, memory_type, slots) == expected


def test_unknown_slot_count_uses_the_two_slot_figure():
    """Be conservative: when the slot count is unknown, take the lower value."""
    assert platform_max_memory_gb("B760M", "DDR5", None) == 96
    assert platform_max_memory_gb("B550", "DDR4", None) == 64


@pytest.mark.parametrize("chipset,memory_type", [
    ("TRX50", "DDR5"), ("WRX90", "DDR5"), ("W790", "DDR5"), ("X299", "DDR4"),  # HEDT/workstation
    ("Z890", "DDR4"), ("H81", "DDR4"), ("B550", "DDR5"),  # chipset never shipped with that memory
    (None, "DDR5"), ("B760", None), ("XYZ1", "DDR5"),
])
def test_unknown_platform_gives_none(chipset, memory_type):
    assert platform_max_memory_gb(chipset, memory_type, 4) is None
