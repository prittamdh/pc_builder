"""A GPU's board power from its chip, for listings with no TDP of their own.

On 2026-10-08, 95 of 556 listed GPUs had no TDP, so the PSU estimate fell back to a
flat 250 W. The chip sets the reference board power (NVIDIA "Total Graphics Power",
AMD "Total Board Power", Intel "TBP"), so a missing value is filled from the chip
named in the canonical id (gpu:<brand>:<chip>[:<memory>][:<variant>]). Only missing
values are filled; a listed TDP always wins.

Values are the makers' published reference figures. Where variants of one chip
differ, the key "<chip>:<qualifier>" (a memory size or "sff") holds the variant and
the bare chip holds the common card; for a chip sold in several memory types with
no qualifier (GT 730), the higher figure is used, since this sizes a PSU.

Not covered on purpose: the RX 9050, whose board power isn't confirmed from a
primary source yet.
"""
from __future__ import annotations

GPU_BOARD_POWER_W = {
    # NVIDIA GeForce RTX 50
    "rtx_5090": 575, "rtx_5080": 360, "rtx_5070_ti": 300, "rtx_5070": 250,
    "rtx_5060_ti": 180, "rtx_5060": 145, "rtx_5050": 130,
    # NVIDIA GeForce RTX 40 / 30
    "rtx_4090": 450, "rtx_4080_super": 320, "rtx_4080": 320, "rtx_4070_ti_super": 285,
    "rtx_4070_ti": 285, "rtx_4070_super": 220, "rtx_4070": 200, "rtx_4060_ti": 165,
    "rtx_4060": 115, "rtx_3080": 320, "rtx_3080:12gb": 350, "rtx_3070_ti": 290,
    "rtx_3070": 220, "rtx_3060_ti": 200, "rtx_3060": 170, "rtx_3050": 130, "rtx_3050:6gb": 70,
    # NVIDIA GeForce GTX / GT
    "gtx_1660_super": 125, "gtx_1650": 75, "gtx_1050_ti": 75, "gt_1030": 30, "gt_740": 64,
    "gt_730": 49, "gt_710": 19, "gt_610": 29,
    # NVIDIA workstation / data centre
    "rtx_pro_6000_blackwell": 600, "rtx_pro_5000_blackwell": 300, "rtx_5000_blackwell": 300,
    "rtx_pro_4500_blackwell": 200, "rtx_pro_4000_blackwell": 140,
    "rtx_pro_4000_blackwell:sff": 70, "rtx_pro_2000_blackwell": 70,
    "rtx_5000_ada": 250, "rtx_4000_ada": 130, "rtx_4000_sff_ada": 70, "rtx_2000_ada": 70,
    "rtx_2000e_ada": 50, "rtx_a2000": 70, "rtx_a1000": 50, "rtx_a400": 50,
    "t1000": 50, "t400": 30, "a800": 240, "l40": 300,
    # AMD Radeon RX
    "rx_9070_xt": 304, "rx_9070": 220, "rx_9070_gre": 220, "rx_9060_xt": 160,
    "rx_9060_xt:8gb": 150, "rx_7900_xtx": 355, "rx_7900_xt": 315, "rx_7900_gre": 260,
    "rx_7800_xt": 263, "rx_7700_xt": 245, "rx_7600_xt": 190, "rx_7600": 165,
    "rx_6600": 132, "rx_6500_xt": 107, "rx_580": 185, "rx_550": 50,
    # AMD Radeon PRO
    "r9700": 300, "pro_w7900": 295, "pro_w7800": 260, "pro_w7800:48gb": 281,
    "pro_w7700": 190, "pro_w7600": 130, "pro_w7500": 70, "pro_w6600": 100, "pro_w5700": 205,
    # Intel Arc
    "arc_b580": 190, "arc_b570": 150, "arc_a380": 75, "arc_a310": 75,
}


def gpu_board_power(canonical_id: str | None) -> int | None:
    """Reference board power in watts for the chip in a GPU canonical id, or None."""
    parts = (canonical_id or "").split(":")
    if len(parts) < 3 or parts[0] != "gpu":
        return None
    chip = parts[2]
    for qualifier in parts[3:]:
        if f"{chip}:{qualifier}" in GPU_BOARD_POWER_W:
            return GPU_BOARD_POWER_W[f"{chip}:{qualifier}"]
    return GPU_BOARD_POWER_W.get(chip)
