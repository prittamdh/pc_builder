"""GPU identity: which listings are the same graphics card.

The key was brand + chipset + variant, straight from the LLM extraction. Two failures
came out of that, both found in the builder's picker on 2026-09-27:

- Memory size was not part of it, so the 8GB and 16GB versions of a card merged. The
  "Asus Dual RX 9060 XT 16GB" model carried four 8GB listings, and its "from" price was
  the 8GB card's.
- The same card spelled differently split into several models: "RX 9060XT" vs
  "RX 9060 XT", "Nitro+" vs "Nitro Plus OC", "Prime OC Edition" vs "Prime OC". A
  24-model picker list was really about 13 cards.

The rules here are deterministic and deliberately conservative. A split only makes a
list longer; a wrong merge shows the wrong card's price. So words are dropped only
where they never tell two real products apart.
"""
from __future__ import annotations

import re

from matching.canonical_key_builder import make_canonical_key_string

# Memory sizes GPUs are actually sold with. Anything else in a "NN GB" is not memory.
_MEMORY_SIZES = {1, 2, 3, 4, 6, 8, 10, 11, 12, 16, 20, 24, 32, 48, 64, 80, 96}

_MEMORY_GB = re.compile(r"(?<![\d.])(\d{1,2})\s?GB\b", re.I)
# Model-number spellings: "6G OC", "-16G", "PRIME-RX9060XT-O16G".
_MEMORY_G = re.compile(r"(?<![\w.])O?(\d{1,2})G\b", re.I)


def memory_gb_from_title(title: str) -> int | None:
    for pattern in (_MEMORY_GB, _MEMORY_G):
        for m in pattern.finditer(title or ""):
            gb = int(m.group(1))
            if gb in _MEMORY_SIZES:
                return gb
    return None


# Vendor and family words that some titles carry and others don't.
_CHIPSET_PREFIXES = ("INTEL", "AMD", "NVIDIA", "GEFORCE", "RADEON", "QUADRO")


def normalize_chipset(chipset: str | None) -> str:
    words = (chipset or "").upper().replace("GENERATION", " ").split()
    while words and words[0] in _CHIPSET_PREFIXES:
        words.pop(0)
    text = " ".join(words)
    # "9060XT" -> "9060 XT", "5070TI" -> "5070 TI"
    text = re.sub(r"(\d)(XTX|XT|TI|GRE|SUPER)\b", r"\1 \2", text)
    return " ".join(text.split())


# Words that describe the product type or memory, never which card it is.
_NOISE_WORDS = {
    "edition", "graphics", "graphic", "card", "gpu", "gddr6", "gddr6x", "gddr7",
    "amd", "radeon", "nvidia", "geforce",
}
# Sapphire's full names all read "<PULSE|PURE|NITRO+> ... GAMING OC", so for Sapphire
# those two words name no separate SKU; retailers keep or drop them at random. For
# other brands "Gaming" vs "Gaming OC" are different cards (Gigabyte), so this is
# per brand, not global.
_BRAND_NOISE = {"sapphire": {"gaming", "oc"}}
_MEMORY_TOKEN = re.compile(r"^o?\d{1,2}g(b)?$")


def normalize_variant(brand: str | None, variant: str | None) -> str:
    text = (variant or "").lower().replace("+", " plus ")
    text = re.sub(r"[()]", " ", text)
    drop = _NOISE_WORDS | _BRAND_NOISE.get((brand or "").strip().lower(), set())
    out: list[str] = []
    for word in re.split(r"[\s_]+", text):
        if word == "overclocked":
            word = "oc"
        if not word or word in drop or _MEMORY_TOKEN.match(word) or word in out:
            continue
        out.append(word)
    return " ".join(out)


def gpu_key_fields(brand: str | None, chipset: str | None, variant: str | None,
                   title: str) -> dict:
    """The canonical key fields for one GPU listing."""
    fields = {
        "category": "gpu",
        "aib_brand": brand or "Unknown",
        "chipset": normalize_chipset(chipset),
        "variant_model": normalize_variant(brand, variant),
    }
    gb = memory_gb_from_title(title)
    if gb is not None:
        fields["memory"] = f"{gb}gb"
    return fields


def gpu_key(brand: str | None, chipset: str | None, variant: str | None, title: str) -> str:
    return make_canonical_key_string("gpu", gpu_key_fields(brand, chipset, variant, title))
