"""Canonical-form tests for extracted spec values.

Every case below is a real value from the catalog on 2026-08-17. Before normalization
the filters offered 255 brand options for 183 actual brands, 42 monitor "resolutions"
for about 8 real ones, and 72 motherboard chipsets - most of them the same chipset with
a form-factor letter appended, which `form_factor` already covers as its own filter.
"""
import pytest

from matching.spec_value_normalizer import normalize_spec_value as norm


class TestBrands:
    @pytest.mark.parametrize("value, expected", [
        ("AsRock", "ASRock"), ("Asrock", "ASRock"), ("ASRock", "ASRock"),
        ("TEAMGROUP", "TeamGroup"), ("Teamgroup", "TeamGroup"),
        ("Team Group", "TeamGroup"),
        ("G.SKILL", "G.Skill"), ("G Skill", "G.Skill"), ("Gskill", "G.Skill"),
        ("WD", "Western Digital"), ("Western Digital", "Western Digital"),
        ("Patriot Memory", "Patriot"),
        ("Hynix", "SK Hynix"), ("SK Hynix", "SK Hynix"),
        ("PROLAB DESIGN", "ProLab Design"), ("Prolab", "ProLab Design"),
        ("Ant", "Ant Esports"),
        # A genuine typo in the catalog, not a different manufacturer.
        ("Thermaltek", "Thermaltake"),
    ])
    def test_spelling_variants_collapse(self, value, expected):
        assert norm("brand", value) == expected

    @pytest.mark.parametrize("value", ["XPG", "AORUS", "Gamer Storm"])
    def test_sub_brands_stay_separate_from_their_parent(self, value):
        """XPG is ADATA's line and AORUS is Gigabyte's, but shoppers search the
        sub-brand by name, so folding them in would lose a search term without making
        any filter meaningfully shorter."""
        assert norm("brand", value) not in (None, "ADATA", "Gigabyte", "DeepCool")

    @pytest.mark.parametrize("value", ["Unknown", "unknown", "N/A", "", "  ", "Other"])
    def test_placeholders_become_null(self, value):
        assert norm("brand", value) is None

    def test_an_unlisted_brand_is_kept_as_written(self):
        assert norm("brand", "Some New Brand") == "Some New Brand"


class TestChipsets:
    @pytest.mark.parametrize("value, expected", [
        # M is micro-ATX and I is ITX - form factor, which is its own filter, so
        # carrying it here split B850 across three options.
        ("B850M", "B850"), ("B850I", "B850"), ("B760M", "B760"), ("X870I", "X870"),
        ("Z890M", "Z890"),
    ])
    def test_form_factor_suffix_is_stripped(self, value, expected):
        assert norm("chipset", value) == expected

    @pytest.mark.parametrize("value", ["B650E", "X670E", "X870E", "WRX90E"])
    def test_e_is_not_a_form_factor_and_survives(self, value):
        """B650E and B650 are genuinely different chipsets with different PCIe
        provisioning; collapsing them would merge distinct products."""
        assert norm("chipset", value) == value

    @pytest.mark.parametrize("value", ["SP5", "SP6"])
    def test_sockets_filed_as_chipsets_are_dropped(self, value):
        assert norm("chipset", value) is None


class TestGpuFields:
    @pytest.mark.parametrize("value, expected", [
        ("RX 9060XT", "RX 9060 XT"), ("RX 9070XT", "RX 9070 XT"),
        ("RX 9060 XT", "RX 9060 XT"),
    ])
    def test_missing_space_before_suffix_is_restored(self, value, expected):
        """"RX 9060 XT" and "RX 9060XT" were separate filter options for one card,
        splitting its offer count and making both look rarer than the part is."""
        assert norm("chipset", value, "GPU") == expected

    @pytest.mark.parametrize("value, expected", [
        ("GTX 710", "GT 710"), ("GTX 730", "GT 730"),
        ("Quadro RTX A1000", "RTX A1000"),
        ("R9700", "Radeon R9700"), ("RX 9700", "Radeon R9700"),
    ])
    def test_wrong_or_legacy_names_are_corrected(self, value, expected):
        assert norm("chipset", value, "GPU") == expected

    @pytest.mark.parametrize("value", ["DDR7", "DDR6", "SDR"])
    def test_impossible_gpu_memory_becomes_null(self, value):
        """No GPU ships plain DDR6/DDR7; these are extraction errors."""
        assert norm("memory_type", value, "GPU") is None

    @pytest.mark.parametrize("value", ["GDDR7", "GDDR6X", "GDDR6", "DDR3"])
    def test_real_gpu_memory_survives(self, value):
        assert norm("memory_type", value, "GPU") == value


class TestMonitorFields:
    @pytest.mark.parametrize("value, expected", [
        ("1920x1080", "FHD"), ("Full HD", "FHD"), ("Full-HD", "FHD"), ("1080p", "FHD"),
        ("2560x1440", "QHD"), ("2K", "QHD"), ("1440p", "QHD"), ("WQHD", "QHD"),
        ("3840x2160", "4K UHD"), ("4K", "4K UHD"), ("UHD", "4K UHD"),
        ("3440x1440", "UWQHD"), ("5120x1440", "DQHD"), ("Dual QHD", "DQHD"),
    ])
    def test_four_naming_systems_collapse_to_one_label(self, value, expected):
        assert norm("resolution", value) == expected

    def test_the_mojibake_resolution_is_recovered(self):
        """One row's separator was corrupted upstream, so it read 3440<junk>1440 and
        became its own filter option."""
        assert norm("resolution", "3440�1440") == "UWQHD"

    @pytest.mark.parametrize("value, expected", [
        ("QD OLED", "QD-OLED"), ("QD-OLED", "QD-OLED"),
        ("Nano IPS", "Nano IPS"), ("IPS", "IPS"),
    ])
    def test_panel_variants_collapse(self, value, expected):
        assert norm("panel_type", value) == expected

    @pytest.mark.parametrize("value", ["Curved", "Ultrawide Curved", "LED"])
    def test_non_panel_types_are_dropped(self, value):
        """Curved is a shape and LED is a backlight; keeping them made "panel type"
        answer two questions at once."""
        assert norm("panel_type", value) is None


class TestStorageAndPsu:
    @pytest.mark.parametrize("value, expected", [
        ("SATA III", "SATA"), ("SATA", "SATA"),
        ("NVMe Gen 4.0", "NVMe Gen4"), ("NVMe PCIe 4.0", "NVMe Gen4"),
        ("PCIe Gen5", "NVMe Gen5"),
    ])
    def test_interface_variants_collapse(self, value, expected):
        assert norm("interface", value) == expected

    def test_ssd_is_not_an_interface(self):
        """It says what the drive is, not how it connects."""
        assert norm("interface", "SSD") is None

    @pytest.mark.parametrize("value, expected", [
        ("Fully Modular", "Full"), ("Modular", "Full"), ("Full", "Full"),
        ("Semi Modular", "Semi"), ("Non Modular", "Non"),
    ])
    def test_modularity_variants_collapse(self, value, expected):
        assert norm("modularity", value) == expected

    @pytest.mark.parametrize("value, expected", [
        ("80+ Gold", "80+ Gold"), ("80 PLUS Gold", "80+ Gold"),
        ("80+ Titanium", "80+ Titanium"),
    ])
    def test_efficiency_tiers_are_canonical(self, value, expected):
        assert norm("efficiency_rating", value) == expected

    @pytest.mark.parametrize("value", ["80+", "Cybenetics Bronze"])
    def test_non_80plus_ratings_are_dropped(self, value):
        """Cybenetics is a different test regime, and a bare "80+" claims a tier
        without naming one - neither belongs in an 80 PLUS filter."""
        assert norm("efficiency_rating", value) is None


class TestSockets:
    @pytest.mark.parametrize("value, expected", [
        ("LGA 1851", "LGA1851"), ("LGA1851", "LGA1851"), ("lga 1700", "LGA1700"),
    ])
    def test_spacing_variants_collapse(self, value, expected):
        assert norm("socket", value) == expected

    @pytest.mark.parametrize("value", ["AM5", "AM4", "sTR5", "sWRX8"])
    def test_amd_sockets_keep_their_own_casing(self, value):
        assert norm("socket", value) == value


def test_non_string_values_pass_through_untouched():
    """Numeric columns share this dispatch; they must not be stringified."""
    assert norm("wattage", 750) == 750
    assert norm("capacity_gb", None) is None
