"""CPU power for the PSU estimate is the MAXIMUM draw, not the base TDP (owner,
2026-10-06). An i5-14500 is sold as 65 W but draws up to 154 W."""
import pytest

from matching.cpu_power import cpu_max_power


@pytest.mark.parametrize("cid, socket, tdp, watts", [
    ("cpu:intel:14500", "LGA1700", 65, 154),
    ("cpu:intel:14700k", "LGA1700", 125, 253),
    ("cpu:intel:13400f", "LGA1700", 65, 148),
    ("cpu:intel:12400", "LGA1700", 65, 117),
    ("cpu:intel:12100f", "LGA1700", 58, 89),
    ("cpu:intel:285k", "LGA1851", 125, 250),
    ("cpu:intel:225", "LGA1851", 65, 121),
])
def test_intel_uses_published_maximum_turbo_power(cid, socket, tdp, watts):
    w, source = cpu_max_power(cid, socket, tdp)
    assert (w, source) == (watts, "intel")


@pytest.mark.parametrize("tdp, watts", [(65, 88), (105, 142), (120, 162), (170, 230)])
def test_amd_desktop_uses_ppt(tdp, watts):
    # AMD's package power tracking limit for socketed AM4/AM5 desktop parts.
    assert cpu_max_power("cpu:amd:9700x", "AM5", tdp) == (watts, "amd_ppt")
    assert cpu_max_power("cpu:amd:5600", "AM4", tdp) == (watts, "amd_ppt")


def test_threadripper_maximum_is_its_tdp():
    assert cpu_max_power("cpu:amd:9975wx", "sTR5", 350) == (350, "amd_ppt")


def test_unknown_intel_model_is_a_cautious_estimate():
    w, source = cpu_max_power("cpu:intel:10400f", "LGA1200", 65)
    assert source == "estimate" and w == 130


def test_no_tdp_gives_nothing():
    assert cpu_max_power("cpu:intel:99999", None, None) == (None, None)
