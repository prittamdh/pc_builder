from decimal import Decimal
from pydantic import BaseModel, ConfigDict, computed_field


class ComponentSlot(BaseModel):
    key: str           # cpu, gpu, motherboard, ram, storage, psu, case
    name: str          # Processor, Graphics Card, Motherboard, etc.
    required: bool = True


class SelectedComponent(BaseModel):
    product_id: int
    quantity: int = 1


class BuildSelection(BaseModel):
    selected_product_ids: list[int]


class CompatibilityWarning(BaseModel):
    # "error"      - a known mismatch; the build won't work as chosen.
    # "warning"    - a likely problem worth checking (retailer pages can be incomplete).
    # "unverified" - a check that could not run because a spec is missing (FIT-01).
    # "estimate"   - a figure built on a typical value, e.g. a default TDP (FIT-03).
    level: str
    message: str


class StorePriceBreakdown(BaseModel):
    store_id: int
    store_name: str
    total_price: Decimal
    available_items_count: int


class BuildSummary(BaseModel):
    compatible: bool
    warnings: list[CompatibilityWarning]
    estimated_wattage: int
    total_min_cost: Decimal
    store_breakdown: list[StorePriceBreakdown]

    # Derived from `warnings`, so builder_service keeps building this model exactly
    # as before and these still serialize in the /builder/validate response.

    @computed_field
    @property
    def unverified_count(self) -> int:
        return sum(1 for w in self.warnings if w.level == "unverified")

    @computed_field
    @property
    def verdict(self) -> str:
        """Exactly one of three states (FIT-02), in fixed precedence: problems, then
        unverified, then all passed. "All checks passed" is impossible while any
        check is unverified. Estimate notes are informational and don't count."""
        if any(w.level in ("error", "warning") for w in self.warnings):
            return "Problems found"
        n = self.unverified_count
        if n:
            return f"No problems found - {n} check{'' if n == 1 else 's'} unverified"
        return "All checks passed"

    @computed_field
    @property
    def wattage_notes(self) -> list[str]:
        return [w.message for w in self.warnings if w.level == "estimate"]
