from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select

from db.models.product import Product
from db.models.store import Store
from domain.builder import (
    BuildSummary,
    ComponentSlot,
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
    ComponentSlot(key="cooler", name="CPU Cooler", required=False),
    # A monitor carries no compatibility constraints against the other parts, but it
    # belongs in the build's cost and store breakdown - people buy one with the machine.
    ComponentSlot(key="monitor", name="Monitor", required=False),
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

        total_min_cost = Decimal("0.00")
        for p in products:
            if p.current_price:
                total_min_cost += Decimal(p.current_price)

        # Compatibility is entirely delegated to CompatibilityEngine, which is
        # order-independent (works regardless of which slots the user filled first)
        # and reads from real extracted/spec data rather than regexing raw titles.
        from services.compatibility_engine import CompatibilityEngine
        engine = CompatibilityEngine(self.session)
        compatible, warnings, estimated_wattage = engine.validate_build(product_ids)

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
