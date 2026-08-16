"""
Form-factor normalization shared by motherboards and cabinets.

The case-fit rule compares a board's form factor against a case's by string
identity, so "E-ATX" and "EATX" - the same thing - fail to match and the check
silently stops working. Retailer titles also mix in chassis *sizes* ("Mid Tower",
"SFF"), which say nothing about which motherboard actually fits.

Canonical values are ITX / MATX / ATX / EATX, matching FORM_FACTOR_ORDER in
compatibility_rules.py.
"""
import re

CANONICAL = ("ITX", "MATX", "ATX", "EATX")

# Order matters: check the longer/more specific spellings first, since "ATX" is a
# substring of "MATX", "EATX" and "MICRO ATX".
_PATTERNS: list[tuple[str, str]] = [
    (r"\bE[\s\-_]?ATX\b", "EATX"),
    (r"\bEXTENDED[\s\-_]?ATX\b", "EATX"),
    (r"\bCEB\b", "EATX"),                       # SSI-CEB workstation boards are EATX-class
    (r"\bSSI[\s\-_]?(EEB|CEB)\b", "EATX"),
    (r"\bM(?:ICRO)?[\s\-_]?ATX\b", "MATX"),
    (r"\bMATX\b", "MATX"),
    (r"\bU?ATX\b(?=.*\bMICRO\b)", "MATX"),
    (r"\bMINI[\s\-_]?ITX\b", "ITX"),
    (r"\bM[\s\-_]?ITX\b", "ITX"),
    (r"\bITX\b", "ITX"),
    (r"\bATX\b", "ATX"),
]

# Chassis-size marketing terms. They describe the box, not which board fits, so on
# their own they carry no form-factor information.
CHASSIS_SIZE_TERMS = {
    "MID TOWER", "MIDTOWER", "MID-TOWER",
    "FULL TOWER", "FULLTOWER", "FULL-TOWER",
    "MINI TOWER", "MINITOWER", "MINI-TOWER",
    "SFF", "SMALL FORM FACTOR", "CUBE", "DESKTOP", "TOWER",
}


def normalize_form_factor(value: str | None, fallback_text: str | None = None) -> str | None:
    """Return a canonical form factor, or None when nothing reliable is stated.

    `fallback_text` (typically the raw listing title) is consulted when `value` is a
    chassis size rather than a form factor - a case labelled "SFF" whose title reads
    "B4-mATX Wood Mesh SFF PC Case" really is MATX.

    Returns None rather than guessing: inferring "ATX" from "Mid Tower" would be right
    most of the time, but wrong for a micro-ATX-only chassis, and that error direction
    lets someone buy a board that does not physically fit.
    """
    for candidate in (value, fallback_text):
        if not candidate:
            continue
        text = str(candidate).upper()

        # A bare chassis-size label carries no form-factor meaning; fall through to
        # the next candidate (usually the full title) instead of matching on it.
        if text.strip() in CHASSIS_SIZE_TERMS:
            continue

        for pattern, canonical in _PATTERNS:
            if re.search(pattern, text):
                return canonical

    return None
