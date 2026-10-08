"""GPU identity keys: never merge different memory sizes, and stop spelling differences
from splitting one card into many models (found 2026-09-27 in the builder's picker:
"Asus Dual RX 9060 XT 16GB" carried four 8GB listings, so its "lowest" price was the
8GB card's; and "RX 9060XT" listings from Clarion never joined their "RX 9060 XT" twins).
"""
import pytest

from matching.gpu_identity import gpu_key, gpu_key_fields, memory_gb_from_title, normalize_chipset, normalize_variant


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


# Owner review 2026-10-08: the extractor's chipset was wrong where the title is clear.
@pytest.mark.parametrize("chipset, title, chip", [
    # Workstation cards read as their gaming namesakes.
    ("RX 7900 XT", "Gigabyte Radeon PRO W7900 Dual Slot AI TOP 48G Graphic Card (W7900 AI TOP 48G)", "PRO W7900"),
    ("RX 7800 XT", "Sapphire AMD RADEON PRO W7800 48GB Graphic Card 32353-01", "PRO W7800"),
    # One card, two spellings.
    ("RX 9700", "Sapphire AMD Radeon AI Pro R9700 32GB GDDR6", "R9700"),
    ("R9700", "PowerColor AMD Radeon AI PRO R9700 32GB GDDR6 Graphics Card", "R9700"),
    # Suffix the extractor dropped.
    ("RX 9070", "Sapphire Pulse RX 9070 GRE OC 12GB GDDR6 Graphics Card", "RX 9070 GRE"),
    ("RX 9070", "ASRock AMD Radeon RX 9070 GRE Steel Legend Dark 12GB OC Graphic Card", "RX 9070 GRE"),
    ("RTX 5060", "MSI GeForce RTX 5060 Ti 16G Ventus 2X OC", "RTX 5060 TI"),
    # GT cards are not GTX.
    ("GTX 710", "Asus GT 710 2GB DDR5 Graphics Card", "GT 710"),
    ("GTX 730", "Colorful GeForce GT 730 4GB GDDR3 VRAM", "GT 730"),
    # Already right: unchanged.
    ("RX 9070", "Sapphire Nitro+ Plus AMD Radeon RX 9070 OC Graphic Card 11349-01-20G", "RX 9070"),
    ("RX 9070 XT", "Asus Prime RX 9070XT OC 16GB", "RX 9070 XT"),
    ("RTX 4070 TI SUPER", "MSI RTX 4070 Ti Super 16G", "RTX 4070 TI SUPER"),
    ("RTX 5070 TI", "Zotac RTX 5070 Ti Solid", "RTX 5070 TI"),
    ("RX 7900 XTX", "ASRock AMD Radeon RX 7900 XTX Bulk Pack 24GB GDDR6", "RX 7900 XTX"),
    ("GTX 1050 TI", "Zotac GeForce GTX 1050 Ti 4GB", "GTX 1050 TI"),
])
def test_title_corrects_the_chipset(chipset, title, chip):
    assert gpu_key_fields("Brand", chipset, "", title)["chipset"] == chip


def test_sapphire_part_number_is_not_memory():
    # 11349-01-20G is a part number; the RX 9070 has 16GB.
    assert memory_gb_from_title("Sapphire Nitro+ Plus AMD Radeon RX 9070 OC Graphic Card 11349-01-20G") is None
    assert memory_gb_from_title("Sapphire AMD Radeon AI Pro R9700 32GB Graphic Card 32358-01-20G") == 32
