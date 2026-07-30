"""
normalize.py
Generic title/text normalization used as a pre-pass before category-specific
attribute extraction. Store-agnostic: strips marketing fluff, standardizes
units and casing, collapses whitespace/punctuation noise.
"""

import re

# Words that carry zero identifying signal but pollute fuzzy/embedding matching.
MARKETING_NOISE = {
    "new", "genuine", "original", "brand", "sealed", "sale", "offer",
    "best", "price", "in", "india", "gaming", "rgb", "argb", "premium",
    "latest", "official", "warranty", "with", "free", "shipping",
    "cod", "available", "hot", "deal", "combo", "set", "pack", "piece",
    "pcs", "1x", "buy", "online", "for", "pc", "computer", "desktop",
}

# Unit normalization: map every variant spelling to one canonical token.
# Order matters — longer/more specific patterns first.
UNIT_PATTERNS = [
    (r"\bgb/?s\b", "gbps"),
    (r"\bmb/?s\b", "mbps"),
    (r"\bmega\s?hertz\b", "mhz"),
    (r"\bmhz\b", "mhz"),
    (r"\bmt/?s\b", "mhz"),          # RAM speed often listed as MT/s ~ treat same axis as MHz for matching
    (r"\bgiga\s?bytes?\b", "gb"),
    (r"\bgb\b", "gb"),
    (r"\btera\s?bytes?\b", "tb"),
    (r"\btb\b", "tb"),
    (r"\bwatts?\b", "w"),
    (r"\b(\d+)\s?w\b", r"\1w"),
    (r"\bmillimet(er|re)s?\b", "mm"),
    (r"\bmm\b", "mm"),
    (r"\binches?\b", "in"),
    (r"\b(\d+)\s?in\b", r"\1in"),
]

_whitespace_re = re.compile(r"\s+")
_punct_re = re.compile(r"[^\w\s.+/-]")  # keep +, /, -, . (relevant in model numbers e.g. i5-14600K, RTX 4070 Ti)


def basic_clean(text: str) -> str:
    """Lowercase, strip punctuation noise, collapse whitespace."""
    text = text.lower().strip()
    text = _punct_re.sub(" ", text)
    text = _whitespace_re.sub(" ", text).strip()
    return text


def standardize_units(text: str) -> str:
    for pattern, repl in UNIT_PATTERNS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


def strip_marketing_noise(text: str) -> str:
    tokens = text.split()
    kept = [t for t in tokens if t not in MARKETING_NOISE]
    return " ".join(kept)


def squeeze_number_unit(text: str) -> str:
    """'16 gb' -> '16gb', '6000 mhz' -> '6000mhz' so tokens match cleanly."""
    return re.sub(r"(\d+)\s+(gb|tb|mhz|w|mm|in|mbps|gbps)\b", r"\1\2", text)


def strip_dangling_symbols(text: str) -> str:
    """Remove standalone leftover punctuation tokens (e.g. a lone '-' after noise strip)."""
    tokens = [t for t in text.split() if t.strip("-./+")]
    return " ".join(tokens)


def normalize_title(raw_title: str) -> str:
    """
    Full normalization pipeline. Use this output for fuzzy matching / embeddings.
    NOTE: this is intentionally lossy for matching purposes — keep the raw_title
    column untouched in your DB for display; normalized_title is match-only.
    """
    t = basic_clean(raw_title)
    t = standardize_units(t)
    t = squeeze_number_unit(t)
    t = strip_marketing_noise(t)
    t = strip_dangling_symbols(t)
    return t


if __name__ == "__main__":
    samples = [
        "Intel Core i5-14600K (Box) Desktop Processor - New Sealed",
        "Corsair Vengeance RGB 16 GB (2x8GB) DDR5 6000 MHz RAM Kit - Best Price in India",
        "WD Blue 1 Tera Bytes SATA Internal Hard Disk Drive",
    ]
    for s in samples:
        print(f"{s!r}\n  -> {normalize_title(s)!r}\n")
