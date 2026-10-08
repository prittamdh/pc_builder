"""Cooler socket lists, normalized to the spellings CPUs use (cpu_specs.socket), so the
"cooler supports the CPU's socket" check compares like with like (owner, 2026-10-08:
only 21 of 564 coolers had sockets, so the check was unverified on almost every build).
"""
import pytest

from matching.cooler_sockets import normalize_sockets, socket_supported


@pytest.mark.parametrize("raw, norm", [
    ("LGA1700,LGA1851,AM5,AM4", "LGA1700,LGA1851,AM4,AM5"),
    ("AM5", "AM5"),
    ("LGA 1700 / AM5", "LGA1700,AM5"),
    ("Intel LGA1851/1700/1200/115X, AMD AM5/AM4", "LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5"),
    ("115x,1200", "LGA1150,LGA1151,LGA1155,LGA1156,LGA1200"),
    ("775,115x,1200", "LGA775,LGA1150,LGA1151,LGA1155,LGA1156,LGA1200"),
    ("LGA1700,LGA1200,LGA115X,AM4,AM5", "LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,AM4,AM5"),
    ("TR4", "sTR4"),
    ("TR4-SP3", "SP3,sTR4"),
    ("TR5-SP6", "SP6,sTR5"),
    ("sTR5, sWRX8", "sTR5,sWRX8"),
    ("LGA2066 and LGA2011-v3", "LGA2011,LGA2066"),
    ("AM3+, FM2+", "AM3+,FM2+"),
    ("LGA4677", "LGA4677"),
])
def test_normalize(raw, norm):
    assert normalize_sockets(raw) == norm


@pytest.mark.parametrize("raw", [None, "", "unknown", "Universal", "not stated"])
def test_nothing_known_is_none(raw):
    assert normalize_sockets(raw) is None


def test_socket_supported_matches_whole_sockets_not_substrings():
    assert socket_supported("LGA1700", "LGA1200,LGA1700,AM5") is True
    assert socket_supported("AM4", "LGA1700,AM5") is False
    # LGA115X on the cooler side covers the 115x family.
    assert socket_supported("LGA1151", "LGA115X,LGA1200") is True
    # A substring is not a match: AM5 is not "AM5+" and LGA115 is not LGA1151.
    assert socket_supported("LGA1151", "LGA1150") is False
    # Unknown either way is not a verdict.
    assert socket_supported(None, "AM5") is None
    assert socket_supported("AM5", None) is None


def test_newer_sockets_share_older_mounting():
    assert socket_supported("LGA1851", "LGA1700") is True
    assert socket_supported("AM5", "AM4") is True
    # Not the other way round, and not across vendors.
    assert socket_supported("LGA1700", "LGA1851") is False
    assert socket_supported("AM4", "AM5") is False
