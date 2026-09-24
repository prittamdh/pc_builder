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
  tolerance give the smaller value; pages disagreeing beyond it give nothing, since
  one of them has mis-read and a wrong clearance green-lights a card that won't fit.

Which figure a page's several GPU lengths reduce to is the prompt's job: the case as
sold, not with an optional radiator added. The clearance drives a blocking error, and
Deepcool's CG580 ("410mm, limited to 262mm if a 360mm radiator is mounted") read as
262 would have rejected ordinary 300mm cards in a stock build.
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


# Air-cooler pages state height on its own or inside a W x D x H dimensions line.
COOLER_HEIGHT_TERMS = re.compile(r"\b(?:height|dimensions?)\b", re.IGNORECASE)
COOLER_HEIGHT_RANGE_MM = (30, 200)


def snippets_for_llm(text: str, radius: int = 160, max_chars: int = 1500,
                     terms: re.Pattern = CLEARANCE_TERMS) -> str:
    """Windows of page text around the given terms, overlapping windows merged."""
    spans: list[list[int]] = []
    for m in terms.finditer(text):
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


_RADIATOR = re.compile(r"radiator", re.IGNORECASE)
_WITHOUT = re.compile(r"\bwithout\b|\bw/o\b|\bw/out\b|\bno\s+radiator\b", re.IGNORECASE)


def is_radiator_conditional(quote: str | None) -> bool:
    """True when a GPU-length quote describes a radiator-mounted layout.

    Cases never ship with a radiator, so such a figure is an optional-build limit, not the
    case as sold - Deepcool CG580 "limited to 262mm if a 360mm radiator is mounted", Fractal
    Epoch "345 mm (with front-mounted radiator)". The prompt says to skip these and the
    model still took them about a quarter of the time, so it is enforced here. This also
    discards some correct figures that merely share a sentence with a radiator condition;
    losing a value is the safe direction, since an absent clearance just skips the check.
    """
    q = quote or ""
    return bool(_RADIATOR.search(q)) and not _WITHOUT.search(q)


def resolve_votes(values: list[int]) -> tuple[int | None, bool]:
    """(value, conflict). Agreeing pages give the smallest value; disagreeing give None."""
    if not values:
        return None, False
    lo, hi = min(values), max(values)
    if (hi - lo) / lo > AGREEMENT_TOLERANCE:
        return None, True
    return lo, False
