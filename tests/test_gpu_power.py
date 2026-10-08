import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from matching.gpu_power import gpu_board_power  # noqa: E402


@pytest.mark.parametrize("canonical_id,watts", [
    ("gpu:pny:rtx_5070:oc_triple_fan", 250),
    ("gpu:zotac:rtx_5060:8gb:gaming_amp_core", 145),
    ("gpu:asus:rx_9070_xt:16gb:prime_oc", 304),
    ("gpu:asus:rx_9060_xt:16gb:tuf_gaming_oc", 160),
    ("gpu:powercolor:rx_9060_xt:8gb:reaper", 150),
    ("gpu:asus:rtx_3080:10gb:tuf_gaming_v2", 320),
    ("gpu:pny:rtx_pro_4000_blackwell", 140),
    ("gpu:pny:rtx_pro_4000_blackwell:24gb:sff", 70),
    ("gpu:pny:rtx_pro_4000_blackwell:sff", 70),
    ("gpu:evm:gt_610", 29),
    ("gpu:sapphire:pro_w7800:48gb", 281),
    ("gpu:amd:pro_w7800", 260),
])
def test_known_chips(canonical_id, watts):
    assert gpu_board_power(canonical_id) == watts


@pytest.mark.parametrize("canonical_id", [
    None, "", "gpu", "gpu:asus", "gpu:asus:unknown_chip:8gb", "cpu:intel:14500",
])
def test_unknown_gives_none(canonical_id):
    assert gpu_board_power(canonical_id) is None


def test_covers_every_chip_in_the_gap_list():
    """Every chip missing a TDP in the 2026-10-08 gap list has a value, except the
    RX 9050, whose board power isn't confirmed (see module docstring)."""
    import json
    gaps = Path(__file__).resolve().parents[1] / ".planning" / "spec-gaps" / "spec_gaps_2026-10-08.json"
    if not gaps.exists():  # .planning is local-only in some checkouts
        pytest.skip("gap list not present")
    models = json.loads(gaps.read_text(encoding="utf-8"))["GPU"]["models"]
    uncovered = sorted(cid for cid, m in models.items()
                       if "tdp" in m["missing"] and gpu_board_power(cid) is None)
    assert uncovered == ["gpu:powercolor:rx_9050:8gb:reaper"]
