import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from matching.legacy_policy import (
    intel_core_generation,
    amd_ryzen_generation,
    is_cpu_legacy,
    is_motherboard_legacy,
    is_ram_legacy,
)


class TestIntelGeneration:
    def test_four_digit_uses_one_leading_digit(self):
        assert intel_core_generation("3220") == 3
        assert intel_core_generation("9350KF") == 9
        assert intel_core_generation("8100") == 8

    def test_five_digit_uses_two_leading_digits(self):
        assert intel_core_generation("10105") == 10
        assert intel_core_generation("12100F") == 12
        assert intel_core_generation("14600K") == 14

    def test_strips_model_prefix(self):
        assert intel_core_generation("i3-6100") == 6

    def test_worded_generation(self):
        # Retailers sometimes state the generation instead of the SKU. Without this
        # these parse to a bare leading digit and obsolete parts slip through.
        assert intel_core_generation("8th Gen") == 8
        assert intel_core_generation("3rd Gen 4 Cores 8 Threads 3.9GHz 8MB Cache") == 3
        assert intel_core_generation("4th Gen 4 Cores 8 Threads 3.4GHz 8MB Cache") == 4
        assert intel_core_generation("12th Gen") == 12

    def test_unparseable(self):
        assert intel_core_generation(None) is None
        assert intel_core_generation("") is None


class TestAmdGeneration:
    def test_leading_digit_is_series(self):
        assert amd_ryzen_generation("5600X") == 5
        assert amd_ryzen_generation("9800X3D") == 9
        assert amd_ryzen_generation("7995WX") == 7

    def test_unparseable(self):
        assert amd_ryzen_generation(None) is None
        assert amd_ryzen_generation("") is None


class TestCpuPolicy:
    def test_intel_10th_gen_and_newer_kept(self):
        assert is_cpu_legacy("Core i5", "10400F", "LGA1200") is False
        assert is_cpu_legacy("Core i9", "14900K", "LGA1700") is False

    def test_intel_9th_gen_and_older_dropped(self):
        assert is_cpu_legacy("Core i7", "9700", "LGA1151") is True
        assert is_cpu_legacy("Core i3", "3220", "LGA1155") is True
        assert is_cpu_legacy("Core i5", "6400", "LGA1151") is True

    def test_core_ultra_always_kept(self):
        assert is_cpu_legacy("Core Ultra 9", "285K", "LGA1851") is False
        assert is_cpu_legacy("Core Ultra 5", "225F", "LGA1851") is False

    def test_amd_3000_and_newer_kept(self):
        assert is_cpu_legacy("Ryzen 5", "3600", "AM4") is False
        assert is_cpu_legacy("Ryzen 7", "9800X3D", "AM5") is False
        assert is_cpu_legacy("Ryzen Threadripper PRO", "5955WX", "sWRX8") is False

    def test_amd_pre_3000_dropped(self):
        assert is_cpu_legacy("Ryzen 5", "2600", "AM4") is True
        assert is_cpu_legacy("Ryzen 7", "1700", "AM4") is True

    def test_entry_level_lines_dropped(self):
        assert is_cpu_legacy("Pentium", "G4560", "LGA1151") is True
        assert is_cpu_legacy("Athlon", "3000G", "AM4") is True

    def test_retired_socket_overrides(self):
        # LGA2066 is a dead HEDT platform regardless of the model number.
        assert is_cpu_legacy("Core i9", "10940X", "LGA2066") is True

    def test_unknown_identity_is_kept_not_hidden(self):
        assert is_cpu_legacy(None, None, None) is False
        assert is_cpu_legacy("", "5700X", None) is False


class TestMotherboardPolicy:
    def test_current_sockets_kept(self):
        for socket in ["AM4", "AM5", "LGA1200", "LGA1700", "LGA1851", "sTR5", "sWRX8"]:
            assert is_motherboard_legacy(socket) is False, socket

    def test_retired_sockets_dropped(self):
        for socket in ["LGA1151", "LGA1155", "LGA1150", "LGA2066", "2066"]:
            assert is_motherboard_legacy(socket) is True, socket

    def test_socket_spacing_normalized(self):
        assert is_motherboard_legacy("LGA 1851") is False
        assert is_motherboard_legacy("LGA 1155") is True

    def test_unknown_socket_is_kept(self):
        assert is_motherboard_legacy(None) is False


class TestRamPolicy:
    def test_ddr4_and_ddr5_kept(self):
        assert is_ram_legacy("DDR4") is False
        assert is_ram_legacy("DDR5") is False

    def test_ddr3_and_older_dropped(self):
        assert is_ram_legacy("DDR3") is True
        assert is_ram_legacy("DDR3L") is True
        assert is_ram_legacy("DDR2") is True

    def test_unknown_is_kept(self):
        assert is_ram_legacy(None) is False
        assert is_ram_legacy("Unknown") is False
