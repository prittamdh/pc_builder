"""A CPU's maximum power draw, for the build's PSU estimate.

The estimate used the TDP, which is the BASE power: an i5-14500 is sold as 65 W but
draws up to 154 W under load. Owner decision 2026-10-06: size the PSU on the maximum.

- Intel publishes "Maximum Turbo Power" per model. Values below are Intel's, as
  reproduced in Wikipedia's Alder Lake, Raptor Lake and Arrow Lake tables (checked
  2026-10-06). Where the two disagree the higher is used, since this sizes a PSU.
- AMD socketed desktop CPUs (AM4, AM5) are limited by PPT = 1.35 x TDP, AMD's own rule
  (65 -> 88, 105 -> 142, 120 -> 162, 170 -> 230). Threadripper's PPT equals its TDP.
- Anything else is a cautious estimate of 2 x TDP, capped at 253 W, and the build
  summary says it was estimated.
"""
from __future__ import annotations

INTEL_MAX_TURBO_W = {
    # 12th gen (Alder Lake)
    "12100": 89, "12100f": 89, "12400": 117, "12400f": 117, "12600k": 150, "12600kf": 150,
    "12700": 180, "12700f": 180, "12700k": 190, "12700kf": 190, "12900": 202, "12900f": 202,
    "12900k": 241, "12900kf": 241, "12900ks": 241,
    # 13th gen (Raptor Lake)
    "13100": 110, "13100f": 110, "13400": 148, "13400f": 148, "13600": 154, "13600k": 181,
    "13600kf": 181, "13700": 219, "13700f": 219, "13700k": 253, "13700kf": 253,
    "13900": 219, "13900f": 219, "13900k": 253, "13900kf": 253, "13900ks": 253,
    # 14th gen (Raptor Lake Refresh)
    "14100": 110, "14100f": 110, "14400": 148, "14400f": 148, "14500": 154, "14600": 154,
    "14600k": 181, "14600kf": 181, "14700": 219, "14700f": 219, "14700k": 253, "14700kf": 253,
    "14900": 219, "14900f": 219, "14900k": 253, "14900kf": 253, "14900ks": 253,
    # Core Ultra 200S (Arrow Lake)
    "225": 121, "225f": 121, "235": 121, "245": 121, "245k": 159, "245kf": 159,
    "265": 182, "265f": 182, "265k": 250, "265kf": 250, "285": 182, "285k": 250,
    "270k": 250,
}

_AMD_DESKTOP_SOCKETS = {"AM4", "AM5"}
_AMD_PPT = {65: 88, 105: 142, 120: 162, 170: 230}


def cpu_max_power(canonical_id: str | None, socket: str | None, tdp: int | None):
    """(watts, source) with source "intel", "amd_ppt" or "estimate"; (None, None)
    when nothing is known."""
    parts = (canonical_id or "").split(":")
    brand = parts[1] if len(parts) > 1 else ""
    model = parts[2] if len(parts) > 2 else ""

    if brand == "intel" and model in INTEL_MAX_TURBO_W:
        return INTEL_MAX_TURBO_W[model], "intel"
    if not tdp:
        return None, None
    tdp = int(tdp)
    if brand == "amd" and socket in _AMD_DESKTOP_SOCKETS:
        return _AMD_PPT.get(tdp, round(tdp * 1.35)), "amd_ppt"
    if brand == "amd" and socket in ("sTR5", "sWRX8", "sTRX4", "sWRX9"):
        return tdp, "amd_ppt"
    return min(tdp * 2, 253), "estimate"
