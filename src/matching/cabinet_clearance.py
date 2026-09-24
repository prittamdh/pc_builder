"""
Pure helpers for reading cabinet clearances off retailer product pages.

Clearances (max GPU length, max CPU cooler height) are almost never in listing titles,
but retailer pages usually carry the manufacturer's spec table. The LLM reads them;
these helpers decide what it sees and whether its answer is trusted:

- snippets_for_llm() cuts the page down to the text around clearance terms, so the
  model reads a spec table and not a whole page of cross-sell carousels.
- is_grounded() rejects any value whose quote is not verbatim on the page or does not
  contain the number - the check that stops a recalled or invented figure landing.
- resolve_votes() combines several pages for one model. Pages agreeing within
  tolerance give the SMALLEST value (a spec sheet's "with front radiator" figure is
  what a real build must satisfy); pages disagreeing beyond it give nothing, since
  one of them has mis-read and a wrong clearance green-lights a card that won't fit.
"""
import re

CLEARANCE_TERMS = re.compile(
    r"\b(?:GPU|VGA|graphics\s*card|video\s*card|CPU\s*cooler|cooler\s*height|CPU\s*heat\s*sink|heatsink)\b",
    re.IGNORECASE,
)

# Physically plausible ranges. Outside these the value is a mis-read (a radiator size,
# a case dimension) regardless of how grounded its quote is.
GPU_RANGE_MM = (120, 500)
COOLER_RANGE_MM = (40, 200)

AGREEMENT_TOLERANCE = 0.10


def snippets_for_llm(text: str, radius: int = 160, max_chars: int = 1500) -> str:
    """Windows of page text around clearance terms, overlapping windows merged."""
    spans: list[list[int]] = []
    for m in CLEARANCE_TERMS.finditer(text):
        start, end = max(0, m.start() - radius), min(len(text), m.end() + radius)
        if spans and start <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    out = " ... ".join(text[s:e].strip() for s, e in spans)
    return out[:max_chars]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def is_grounded(value, quote: str | None, page_text: str, valid_range: tuple[int, int]) -> bool:
    """True only if the value is in range and its quote is verbatim on the page and names it."""
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    lo, hi = valid_range
    if not lo <= value <= hi:
        return False
    q = _norm(quote)
    if len(q) < 6 or q not in _norm(page_text):
        return False
    return re.search(rf"(?<!\d){value}(?!\d)", q) is not None


def resolve_votes(values: list[int]) -> tuple[int | None, bool]:
    """(value, conflict). Agreeing pages give the smallest value; disagreeing give None."""
    if not values:
        return None, False
    lo, hi = min(values), max(values)
    if (hi - lo) / lo > AGREEMENT_TOLERANCE:
        return None, True
    return lo, False
