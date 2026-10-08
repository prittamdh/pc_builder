"""Cooler socket lists in the spellings CPUs use (cpu_specs.socket: LGA1700, AM5, sTR5...).

Cooler sockets arrive as free text: "LGA1851/1700/1200/115X, AMD AM5/AM4", "115x,1200",
"TR4-SP3". normalize_sockets turns that into one sorted comma list, expanding the
LGA115x family, so the build check can match whole sockets instead of substrings
(as a substring, "LGA1151" is not in "LGA115X" and the check wrongly warned).
"""
from __future__ import annotations

import re

_LGA_115X = ("LGA1150", "LGA1151", "LGA1155", "LGA1156")
_LGA_NUMBERS = {"775", "1150", "1151", "1155", "1156", "1200", "1700", "1851", "2011", "2066",
                "3647", "4189", "4677", "4710"}
_NAMED = {
    "AM2": "AM2", "AM2+": "AM2+", "AM3": "AM3", "AM3+": "AM3+", "AM4": "AM4", "AM5": "AM5",
    "FM1": "FM1", "FM2": "FM2", "FM2+": "FM2+",
    "TR4": "sTR4", "STR4": "sTR4", "STRX4": "sTRX4", "TR5": "sTR5", "STR5": "sTR5",
    "SWRX8": "sWRX8", "WRX8": "sWRX8", "SWRX9": "sWRX9",
    "SP3": "SP3", "SP5": "SP5", "SP6": "SP6",
}


def _tokens(text: str) -> list[str]:
    text = text.upper().replace("INTEL", " ").replace("AMD", " ")
    text = re.sub(r"\bLGA\s+", "LGA", text)
    # "LGA2011-v3" is LGA2011; "TR4-SP3" is two sockets.
    text = re.sub(r"(LGA\d{3,4})-V\d", r"\1", text)
    return [t for t in re.split(r"[\s,/;|&-]+|\bAND\b", text) if t]


def normalize_sockets(text: str | None) -> str | None:
    if not text:
        return None
    found: set[str] = set()
    for tok in _tokens(text):
        tok = tok.strip()
        bare = tok[3:] if tok.startswith("LGA") else tok
        if bare in ("115X", "115"):
            found.update(_LGA_115X)
        elif bare in _LGA_NUMBERS:
            found.add("LGA" + bare)
        elif tok in _NAMED:
            found.add(_NAMED[tok])
    if not found:
        return None
    lga = sorted((s for s in found if s.startswith("LGA")), key=lambda s: int(s[3:]))
    rest = sorted((s for s in found if not s.startswith("LGA")), key=str.lower)
    return ",".join(lga + rest)


# A newer socket that kept the older one's cooler mounting: LGA1851 has LGA1700's hole
# spacing and keep-out (Intel), AM5 keeps AM4's (AMD). A cooler listing only the older
# socket, typically because it predates the newer one, mounts on both.
SAME_MOUNT = {"LGA1700": "LGA1851", "AM4": "AM5"}

# Sockets almost every cooler sold new today mounts on (owner decision 2026-10-08).
# Coolers differ on older sockets, so only these make an unknown list a mere note.
CURRENT_SOCKETS = ("AM4", "AM5", "LGA1700", "LGA1851")


def socket_supported(cpu_socket: str | None, cooler_sockets: str | None) -> bool | None:
    """True/False when both are known, None when either is unknown."""
    if not cpu_socket or not cooler_sockets:
        return None
    have = set((normalize_sockets(cooler_sockets) or "").split(","))
    have |= {SAME_MOUNT[s] for s in have if s in SAME_MOUNT}
    want = normalize_sockets(cpu_socket) or cpu_socket.strip()
    return want in have
