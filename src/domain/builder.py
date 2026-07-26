from decimal import Decimal
from pydantic import BaseModel, ConfigDict


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
    level: str         # "error", "warning", "info"
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
