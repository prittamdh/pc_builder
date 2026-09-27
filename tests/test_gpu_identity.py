"""GPU identity keys: never merge different memory sizes, and stop spelling differences
from splitting one card into many models (found 2026-09-27 in the builder's picker:
"Asus Dual RX 9060 XT 16GB" carried four 8GB listings, so its "lowest" price was the
8GB card's; and "RX 9060XT" listings from Clarion never joined their "RX 9060 XT" twins).
"""
import pytest

from matching.gpu_identity import gpu_key, memory_gb_from_title, normalize_chipset, normalize_variant


@pytest.mark.parametrize("title, gb", [
    ("ASUS Dual RX 9060 XT 8GB GDDR6 Graphics Card", 8),
    ("Asus Dual RX 9060 XT 16GB", 16),
    ("ASUS Radeon RX 9060 XT Prime OC 16G Graphic Card PRIME-RX9060XT-O16G", 16),
    ("Asus Dual RX 9060 XT 16GB GDDR6 Graphics Card DUAL-RX9060XT-16G", 16),
    ("Zotac Gaming GeForce RTX 5060 Ti 16 GB AMP", 16),
    ("MSI GeForce RTX 3050 Ventus 2X 6G OC", 6),
    ("Gigabyte GeForce RTX 5070 Windforce OC SFF", None),
])
def test_memory_from_title(title, gb):
    assert memory_gb_from_title(title) == gb


def test_memory_ignores_numbers_that_are_not_memory():
    assert memory_gb_from_title("RTX 5070 12GB 192-bit 2560 cores") == 12
    assert memory_gb_from_title("PNY RTX 4000 Ada 20GB 130W") == 20


@pytest.mark.parametrize("raw, norm", [
    ("RX 9060XT", "RX 9060 XT"),
    ("RX 9060 XT", "RX 9060 XT"),
    ("RX 9070XT", "RX 9070 XT"),
    ("Intel Arc A380", "ARC A380"),
    ("Arc A380", "ARC A380"),
    ("RTX Pro 4500 Blackwell", "RTX PRO 4500 BLACKWELL"),
    ("RTX 6000 Ada Generation", "RTX 6000 ADA"),
    ("Quadro RTX A1000", "RTX A1000"),
    ("RTX 4070 Ti SUPER", "RTX 4070 TI SUPER"),
    ("Radeon R9700", "R9700"),
])
def test_chipset_spellings_collapse(raw, norm):
    assert normalize_chipset(raw) == norm


@pytest.mark.parametrize("brand, a, b", [
    ("Sapphire", "Nitro+", "Nitro Plus OC"),
    ("Sapphire", "Pulse", "Pulse Gaming OC"),
    ("Sapphire", "Pulse OC", "PULSE"),
    ("Sapphire", "Pure OC", "Pure"),
    ("Asus", "Prime OC Edition", "Prime OC"),
    ("MSI", "Ventus 2X OC", "Ventus 2X OC Graphics Card"),
    ("Asus", "Dual 16G", "Dual"),
])
def test_same_card_different_wording(brand, a, b):
    assert normalize_variant(brand, a) == normalize_variant(brand, b)


@pytest.mark.parametrize("brand, a, b", [
    # Real, separately sold SKUs that must stay apart.
    ("Gigabyte", "Gaming", "Gaming OC"),
    ("Asus", "Dual", "Dual OC"),
    ("Gigabyte", "Gaming OC", "Gaming OC Ice"),
    ("MSI", "Ventus 2X", "Ventus 3X"),
    ("Sapphire", "Pulse", "Pure"),
])
def test_different_cards_stay_apart(brand, a, b):
    assert normalize_variant(brand, a) != normalize_variant(brand, b)


def test_8gb_and_16gb_never_share_a_key():
    k8 = gpu_key("Asus", "RX 9060 XT", "Dual", "ASUS Dual RX 9060 XT 8GB GDDR6 Graphics Card")
    k16 = gpu_key("Asus", "RX 9060 XT", "Dual", "Asus Dual RX 9060 XT 16GB GDDR6 Graphics Card")
    assert k8 != k16


def test_spelling_variants_share_a_key():
    a = gpu_key("AsRock", "RX 9060XT", "Challenger OC", "AsRock RX 9060XT Challenger OC 16GB OC Graphics Card")
    b = gpu_key("ASRock", "RX 9060 XT", "Challenger OC", "ASRock RX 9060 XT Challenger OC 16GB GDDR6 Graphics Card")
    assert a == b
    assert a == "gpu:asrock:rx_9060_xt:16gb:challenger_oc"


def test_unknown_memory_stays_out_of_known_groups():
    known = gpu_key("MSI", "RTX 5070", "Ventus 2X OC", "MSI RTX 5070 Ventus 2X OC 12GB")
    unknown = gpu_key("MSI", "RTX 5070", "Ventus 2X OC", "MSI RTX 5070 Ventus 2X OC")
    assert known != unknown


def test_memory_alone_does_not_identify_a_card():
    # A failed extraction with only "16GB" readable must not join every other such
    # listing in one fake "gpu:unknown:16gb" model.
    from matching.canonical_key_builder import disambiguate_failed_key, make_canonical_key_string
    from matching.gpu_identity import gpu_key_fields

    a = disambiguate_failed_key(gpu_key_fields(None, None, None, "Some card 16GB"), 1)
    b = disambiguate_failed_key(gpu_key_fields(None, None, None, "Other card 16GB"), 2)
    assert make_canonical_key_string("gpu", a) != make_canonical_key_string("gpu", b)
