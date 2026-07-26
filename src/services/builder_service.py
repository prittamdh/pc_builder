from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select

from db.models.product import Product
from db.models.store import Store
from domain.builder import (
    BuildSummary,
    ComponentSlot,
    CompatibilityWarning,
    StorePriceBreakdown,
)


SLOTS = [
    ComponentSlot(key="cpu", name="Processor (CPU)", required=True),
    ComponentSlot(key="motherboard", name="Motherboard", required=True),
    ComponentSlot(key="gpu", name="Graphics Card (GPU)", required=False),
    ComponentSlot(key="ram", name="Memory (RAM)", required=True),
    ComponentSlot(key="storage", name="Storage (SSD/HDD)", required=True),
    ComponentSlot(key="psu", name="Power Supply (PSU)", required=True),
    ComponentSlot(key="case", name="Cabinet / Case", required=False),
]


class BuilderService:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def get_slots() -> list[ComponentSlot]:
        return SLOTS

    def validate_and_calculate_build(self, product_ids: list[int]) -> BuildSummary:
        if not product_ids:
            return BuildSummary(
                compatible=True,
                warnings=[],
                estimated_wattage=0,
                total_min_cost=Decimal("0.00"),
                store_breakdown=[],
            )

        # Fetch products from database
        products = list(self.session.scalars(select(Product).where(Product.id.in_(product_ids))))
        stores = list(self.session.scalars(select(Store).where(Store.active == True)))
        store_map = {s.id: s.display_name for s in stores}

        warnings: list[CompatibilityWarning] = []
        compatible = True
        estimated_wattage = 0
        total_min_cost = Decimal("0.00")

        sockets: set[str] = set()
        ram_types: set[str] = set()
        psu_capacity = 0

        for p in products:
            if p.current_price:
                total_min_cost += Decimal(p.current_price)

            specs = p.specifications or {}
            name_lower = p.name.lower()

            # Socket detection
            for socket_key in ("lga1700", "lga1851", "am5", "am4", "lga1200"):
                if socket_key in name_lower or socket_key in str(specs).lower():
                    sockets.add(socket_key.upper())

            # RAM type detection
            if "ddr5" in name_lower or "ddr5" in str(specs).lower():
                ram_types.add("DDR5")
            elif "ddr4" in name_lower or "ddr4" in str(specs).lower():
                ram_types.add("DDR4")

            # Estimated Wattage
            if "rtx 5090" in name_lower or "rtx 4090" in name_lower:
                estimated_wattage += 450
            elif "rtx 5080" in name_lower or "rtx 4080" in name_lower:
                estimated_wattage += 320
            elif "rtx 5070" in name_lower or "rtx 4070" in name_lower:
                estimated_wattage += 250
            elif "cpu" in name_lower or "ryzen" in name_lower or "intel" in name_lower:
                estimated_wattage += 125
            else:
                estimated_wattage += 30

            # PSU wattage capacity
            if "w" in name_lower and ("power supply" in name_lower or "psu" in name_lower or "80+" in name_lower):
                for word in name_lower.split():
                    if word.endswith("w") and word[:-1].isdigit():
                        psu_capacity = max(psu_capacity, int(word[:-1]))

        # Compatibility Checks
        if len(sockets) > 1:
            compatible = False
            warnings.append(
                CompatibilityWarning(
                    level="error",
                    message=f"Socket Mismatch Detected: Selected components reference multiple incompatible sockets ({', '.join(sockets)}).",
                )
            )

        if len(ram_types) > 1:
            compatible = False
            warnings.append(
                CompatibilityWarning(
                    level="error",
                    message=f"RAM Generation Mismatch: Build mixes incompatible memory standards ({', '.join(ram_types)}).",
                )
            )

        if psu_capacity > 0 and psu_capacity < estimated_wattage + 100:
            warnings.append(
                CompatibilityWarning(
                    level="warning",
                    message=f"Power Supply Capacity Warning: Selected {psu_capacity}W PSU is close to or below recommended head-room for {estimated_wattage}W estimated build draw.",
                )
            )

        # Use Strict Compatibility Engine for Category Spec Rules
        from services.compatibility_engine import CompatibilityEngine
        engine = CompatibilityEngine(self.session)
        engine_compatible, engine_warnings, engine_wattage = engine.validate_build(product_ids)

        warnings.extend(engine_warnings)
        if not engine_compatible:
            compatible = False

        if engine_wattage > 0:
            estimated_wattage = engine_wattage

        # Multi-Store Cost Breakdown
        store_totals: dict[int, Decimal] = {s.id: Decimal("0.00") for s in stores}
        store_counts: dict[int, int] = {s.id: 0 for s in stores}

        for p in products:
            if p.sid in store_totals and p.current_price:
                store_totals[p.sid] += Decimal(p.current_price)
                store_counts[p.sid] += 1

        store_breakdown = [
            StorePriceBreakdown(
                store_id=s.id,
                store_name=s.display_name,
                total_price=store_totals[s.id],
                available_items_count=store_counts[s.id],
            )
            for s in stores
        ]

        return BuildSummary(
            compatible=compatible,
            warnings=warnings,
            estimated_wattage=estimated_wattage,
            total_min_cost=total_min_cost,
            store_breakdown=store_breakdown,
        )
