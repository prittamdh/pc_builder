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
        "cooler", "radiator_size_mm", "le", "case", "max_cooler_height_mm", "warning",
        lambda a, b: f"Cooler Clearance Check: cooler size ({a}mm) vs Cabinet max clearance ({b}mm) - verify radiator/tower mount fits.",
    ),
    Rule(
        "motherboard", "form_factor", "form_factor_fits", "case", "form_factor", "error",
        lambda a, b: f"Case Fit Error: Motherboard form factor ({a}) does not fit inside Cabinet ({b}).",
    ),
]

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
