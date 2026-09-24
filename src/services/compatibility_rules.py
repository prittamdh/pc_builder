"""
Declarative PC hardware compatibility rules.

These are pairwise/aggregate relationships between component spec fields, not a pick
order - the same rule set works regardless of what order the user selects components
in (CPU-first, GPU-first, case-first, etc). See CompatibilityEngine for how they're
evaluated: a rule only fires once BOTH sides it references have a selection, and the
same rules double as candidate filters for whichever slot is still empty.

Field access uses a plain string path (e.g. "socket") looked up via getattr on the
resolved spec object for that slot - see SLOT_SPECS in compatibility_engine.py for how
each slot key resolves to its spec model and keying scheme.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Rule:
    slot_a: str
    field_a: str
    op: str  # "eq" | "le" | "ge" | "contains"
    slot_b: str
    field_b: str
    level: str  # "error" | "warning"
    message: Callable[[object, object], str]


RULES: list[Rule] = [
    Rule(
        "cpu", "socket", "eq", "motherboard", "socket", "error",
        lambda a, b: f"Socket Mismatch: CPU socket ({a}) is incompatible with Motherboard socket ({b}).",
    ),
    Rule(
        "ram", "memory_type", "eq", "motherboard", "memory_type", "error",
        lambda a, b: f"RAM Standard Mismatch: selected RAM is {a}, but Motherboard supports {b}.",
    ),
    Rule(
        "ram", "modules", "le", "motherboard", "memory_slots", "error",
        lambda a, b: f"RAM Slot Overflow: build uses {a} RAM module(s), but Motherboard only has {b} slot(s).",
    ),
    Rule(
        "ram", "capacity_gb", "le", "motherboard", "max_memory_gb", "error",
        lambda a, b: f"RAM Capacity Overflow: {a}GB selected exceeds Motherboard's max supported {b}GB.",
    ),
    Rule(
        "cpu", "socket", "contains_in", "cooler", "supported_sockets", "warning",
        lambda a, b: f"Cooler Mounting Check: verify cooler's supported sockets ({b}) include CPU socket ({a}).",
    ),
    Rule(
        "gpu", "length_mm", "le", "case", "max_gpu_length_mm", "error",
        lambda a, b: f"GPU Clearance Error: GPU length ({a}mm) exceeds Cabinet max clearance ({b}mm).",
    ),
    Rule(
        # Air coolers only: height_mm is NULL for AIOs, so the rule never fires for them.
        "cooler", "height_mm", "le", "case", "max_cooler_height_mm", "error",
        lambda a, b: f"Cooler Clearance Error: cooler height ({a}mm) exceeds Cabinet max cooler height ({b}mm).",
    ),
    Rule(
        # AIOs only (aio_radiator_mm is NULL for air coolers). A warning, not an error:
        # case pages can omit a mount, so the listed maximum may understate the case.
        "cooler", "aio_radiator_mm", "le", "case", "max_radiator_mm", "warning",
        lambda a, b: f"Radiator Fit Warning: this cooler's {a}mm radiator is larger than any radiator the Cabinet lists ({b}mm max) - check the case's mounts.",
    ),
    Rule(
        "motherboard", "form_factor", "form_factor_fits", "case", "form_factor", "error",
        lambda a, b: f"Case Fit Error: Motherboard form factor ({a}) does not fit inside Cabinet ({b}).",
    ),
]

# Plain-English name for every spec field a rule reads. Used to tell the shopper
# exactly which spec is missing when a check can't be run (FIT-01).
FIELD_LABELS: dict[str, str] = {
    "socket": "CPU socket",
    "memory_type": "memory type",
    "modules": "module count",
    "memory_slots": "memory slots",
    "capacity_gb": "memory capacity",
    "max_memory_gb": "maximum memory",
    "supported_sockets": "supported sockets",
    "length_mm": "length",
    "max_gpu_length_mm": "GPU clearance",
    "height_mm": "height",
    "max_cooler_height_mm": "CPU cooler clearance",
    "aio_radiator_mm": "radiator size",
    "max_radiator_mm": "radiator support",
    "form_factor": "form factor",
}

# Plain-English slot names for messages ("GPU/case fit could not be checked").
SLOT_LABELS: dict[str, str] = {
    "cpu": "CPU", "motherboard": "motherboard", "ram": "RAM", "gpu": "GPU",
    "case": "case", "cooler": "cooler", "psu": "PSU", "storage": "storage",
}


def _is_aio(cooler_type) -> bool:
    return str(cooler_type).strip().upper().startswith("AIO")


def rule_applies(rule: Rule, view_a, view_b) -> bool:
    """Whether a rule is meaningful for this particular pair of parts.

    A None value normally means "we don't know" (unverified). Two cooler fields are
    the exception (Pitfall 8): an AIO has no tower height, and an air cooler has no
    radiator, so for those the check simply doesn't apply. That decision rests on a
    KNOWN cooler_type - when the type itself is unknown the rule applies, so the
    shopper is honestly told it could not be checked."""
    for slot, view in ((rule.slot_a, view_a), (rule.slot_b, view_b)):
        if slot != "cooler":
            continue
        cooler_type = getattr(view, "cooler_type", None)
        if cooler_type is None or not str(cooler_type).strip():
            return True
        field = rule.field_a if slot == rule.slot_a else rule.field_b
        if field == "height_mm" and _is_aio(cooler_type):
            return False
        if field == "aio_radiator_mm" and not _is_aio(cooler_type):
            return False
    return True


# The cooler rule compares the air cooler's own height_mm. An earlier rule used
# radiator_size_mm, which holds a fan size for air coolers (120 - always passes) and a
# radiator length for AIOs (360 - always warned against a 165mm tower limit).

# Ordered smallest -> largest; a cabinet rated for a given size also fits every
# smaller form factor, not the reverse.
FORM_FACTOR_ORDER = ["ITX", "MATX", "ATX", "EATX"]


def form_factor_index(value: str | None) -> int | None:
    if not value:
        return None
    v = value.strip().upper().replace("-", "").replace(" ", "")
    for i, ff in enumerate(FORM_FACTOR_ORDER):
        if ff in v:
            return i
    return None


# Wattage is an aggregate (sum), not a pairwise rule - kept separate from RULES.
WATTAGE_HEADROOM = 150
DEFAULT_CPU_TDP = 120
DEFAULT_GPU_TDP = 250
