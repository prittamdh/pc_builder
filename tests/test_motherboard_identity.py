"""
Tests for motherboard board-designation resolution and form-factor reconciliation.

Covers the failure this logic exists for: an ATX board and its mini-ITX/micro-ATX
sibling differ only by a variant letter the identity model normalizes away, so they
collapsed into one canonical_id and shared one motherboard_specs row - handing the ITX
board the ATX board's DIMM count and form factor.
"""
from types import SimpleNamespace

import pytest

from matching.canonical_key_builder import (
    build_motherboard_key_dict,
    form_factor_from_designation,
    form_factor_from_title,
    make_canonical_key_string,
    resolve_board_designation,
)
from matching.motherboard_identity import resolve_group_form_factor


def key(brand, chipset, model, title):
    return make_canonical_key_string(
        "motherboard", build_motherboard_key_dict(brand, chipset, model, title)
    )


def test_itx_variant_does_not_merge_with_atx_board():
    """The reported bug: MSI MPG B850 (ATX, 4 DIMM) vs B850I (ITX, 2 DIMM)."""
    atx = key("MSI", "B850", "MPG EDGE TI WIFI", "MSI MPG B850 EDGE TI WIFI ATX Motherboard")
    itx = key("MSI", "B850", "MPG Edge TI WiFi", "MSI MPG B850I Edge TI WiFi Motherboard")

    assert atx == "motherboard:msi:b850:mpg_edge_ti_wifi"
    assert itx == "motherboard:msi:b850i:mpg_edge_ti_wifi"
    assert atx != itx


def test_matx_variant_does_not_merge_with_atx_board():
    atx = key("Gigabyte", "B850", "Eagle Wifi6E", "Gigabyte B850 EAGLE WIFI6E AM5 ATX Motherboard")
    matx = key("Gigabyte", "B850", "Eagle Wifi6E", "GIGABYTE B850M Eagle Wifi6E DDR5 AMD Motherboard")

    assert atx != matx
    assert matx == "motherboard:gigabyte:b850m:eagle_wifi6e"


def test_same_board_merges_when_model_drops_the_variant_letter():
    """The inverse bug: the model returns B650M for some listings of a board, B650 for others."""
    a = key("Gigabyte", "B650M", "Gaming X AX Wifi", "Gigabyte B650M Gaming X Ax Wifi Am5 Matx Motherboard")
    b = key("Gigabyte", "B650", "Gaming X AX Wifi", "GIGABYTE B650M Gaming X AX Wifi DDR5 AMD Motherboard")

    assert a == b == "motherboard:gigabyte:b650m:gaming_x_ax_wifi"


def test_hyphenation_of_model_suffix_does_not_split_a_board():
    """'Gigabyte B550M K' and 'Gigabyte B550M-K' are the same product."""
    spaced = key("Gigabyte", "B550M", "K", "Gigabyte B550M K AM4 Micro ATX Motherboard")
    hyphenated = key("Gigabyte", "B550M", "K", "Gigabyte B550M-K AMD AM4 Micro-ATX Motherboard")

    assert spaced == hyphenated


def test_variant_marker_from_model_is_not_discarded():
    """ASUS writes the variant as a model suffix; the model returns it in the chipset field."""
    a = key("Asus", "B860A", "ROG STRIX GAMING WIFI", "Asus Rog Strix B860-A Gaming WiFi LGA1851")
    i = key("Asus", "B860I", "ROG STRIX GAMING WIFI", "Asus Rog Strix B860-I Gaming WiFi LGA1851")

    assert a != i


@pytest.mark.parametrize("chipset,title,expected", [
    # A bare chipset named alongside the real designation must not win.
    ("B760", "Asrock B760M Steel Legend WiFi Intel B760 Micro ATX Motherboard", "B760M"),
    ("B760M", "Asus Prime B760M-A WIFI DDR5 B760 Motherboard", "B760M"),
    # A trailing E is a chipset tier, and must survive as one.
    ("X870E", "ASUS X870 ROG CROSSHAIR X870E HERO Motherboard", "X870E"),
    ("X670E", "ASUS TUF GAMING X670E-PLUS WIFI AMD Ryzen AM5 ATX X670 Motherboard", "X670E"),
    # Nothing to add: title carries no more detail than the model gave.
    ("B850", "MSI MPG B850 EDGE TI WIFI ATX Motherboard", "B850"),
    # Stem absent from the title - fall back to what the model returned.
    ("B650", "Some Truncated Listing Title", "B650"),
    ("", "MSI MPG B850 EDGE TI WIFI", ""),
])
def test_resolve_board_designation(chipset, title, expected):
    assert resolve_board_designation(chipset, title) == expected


@pytest.mark.parametrize("designation,expected", [
    ("B850I", "ITX"),
    ("B650M", "MATX"),
    ("B860-I", "ITX"),
    ("B850", None),
    ("X870E", None),    # chipset tier, not a form factor
    ("B860A", None),
    ("", None),
])
def test_form_factor_from_designation(designation, expected):
    assert form_factor_from_designation(designation) == expected


@pytest.mark.parametrize("title,expected", [
    ("Gigabyte B850M Eagle Wifi6E M-ATX Motherboard", "MATX"),
    ("GIGABYTE B650M Aorus Micro-ATX Motherboard", "MATX"),
    ("Gigabyte Z890 Aorus Master AI TOP LGA 1851 E-ATX Motherboard", "EATX"),
    ("Msi Mpg Z890I Edge Ti WiFi LGA1851 MINI-ITX Motherboard", "ITX"),
    ("MSI MPG Z890I Edge TI WIFI M-ITX Motherboard", "ITX"),
    ("MSI PRO B850-P WIFI DDR5 AMD AM5 Full-ATX Motherboard", "ATX"),
    ("MSI MPG B850 EDGE TI WIFI Motherboard", None),
])
def test_form_factor_from_title(title, expected):
    assert form_factor_from_title(title) == expected


def row(chipset, title, form_factor=None):
    return SimpleNamespace(chipset=chipset, raw_title=title, form_factor=form_factor)


def test_group_form_factor_prefers_the_variant_letter_over_a_wrong_title():
    """'MSI PRO B850M-P AM5 ATX Motherboard' is a micro-ATX board; the retailer is wrong."""
    rows = [
        row("B850M", "MSI PRO B850M-P AM5 ATX Motherboard", "ATX"),
        row("B850M", "MSI PRO B850M-P DDR5 AMD Motherboard", "MATX"),
    ]
    assert resolve_group_form_factor(rows) == "MATX"


def test_group_form_factor_outvotes_an_unsupported_model_guess():
    """One listing tagged EATX with nothing in its title to support it loses to four ATX titles."""
    rows = [
        row("X870E", "Asus ROG Crosshair X870E Hero ATX Motherboard", "ATX"),
        row("X870E", "ASUS ROG Crosshair X870E Hero X870E AMD AM5 ATX DDR5 Motherboard", "ATX"),
        row("X870E", "ASUS ROG CROSSHAIR X870E HERO Motherboard", "EATX"),
        row("X870E", "ASUS ROG CROSSHAIR X870E HERO DDR5 AMD Motherboard", None),
    ]
    assert resolve_group_form_factor(rows) == "ATX"


def test_group_form_factor_falls_back_to_the_model_when_no_evidence_exists():
    rows = [
        row("B860", "Gigabyte B860 Gaming X WiFi6E LGA1851 AT...", "ATX"),
        row("B860", "GIGABYTE B860 Gaming X WIFI6E DDR5 Intel Motherboard", None),
    ]
    assert resolve_group_form_factor(rows) == "ATX"


def test_group_form_factor_is_none_when_nothing_is_known():
    rows = [row("B850", "MSI MPG B850 Edge Ti Wifi Motherboard", None)]
    assert resolve_group_form_factor(rows) is None
