from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from db.models.product import Product
from domain.builder import BuildSelection, BuildSummary, ComponentSlot
from services.builder_service import BuilderService
from services.compatibility_engine import CompatibilityEngine

router = APIRouter(prefix="/builder", tags=["PC Builder"])

# Builder slot -> normalized p_category used to pull candidates.
SLOT_CATEGORY = {
    "cpu": "CPU",
    "motherboard": "Motherboard",
    "gpu": "GPU",
    "ram": "RAM",
    "storage": "Storage",
    "psu": "Power Supply",
    "case": "Cabinet",
    "cooler": "CPU Cooler",
}


class CandidateRequest(BaseModel):
    slot: str
    selected_product_ids: list[int] = []
    q: str | None = None
    compatible_only: bool = True


@router.get("/slots", response_model=list[ComponentSlot])
def list_component_slots():
    """Retrieve PC component slots required for building a system."""
    return BuilderService.get_slots()


@router.post("/validate", response_model=BuildSummary)
def validate_build(
    selection: BuildSelection,
    db: Session = Depends(get_db),
):
    """Validate hardware compatibility and calculate multi-store price summary."""
    service = BuilderService(db)
    return service.validate_and_calculate_build(selection.selected_product_ids)


@router.post("/candidates")
def list_slot_candidates(
    req: CandidateRequest,
    limit: int = Query(60, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """In-stock, on-policy parts for a slot, optionally narrowed to those compatible
    with the current selection.

    Surfacing incompatible parts and only complaining afterwards makes the builder a
    tool that reports mistakes rather than one that prevents them - so this applies
    CompatibilityEngine.filter_candidates (error-level rules only; warnings stay
    informational and never hide a part)."""
    category = SLOT_CATEGORY.get(req.slot)
    if category is None:
        return {"items": [], "total": 0, "filtered_out": 0, "error": f"unknown slot '{req.slot}'"}

    stmt = (
        select(Product)
        .where(
            Product.p_category == category,
            Product.in_stock.is_(True),
            Product.is_legacy.is_(False),
        )
    )
    if req.q:
        stmt = stmt.where(Product.name.ilike(f"%{req.q}%"))

    # Pull a wider pool than we return, since compatibility filtering thins it.
    candidates = list(db.scalars(stmt.limit(limit * 5)))
    total_before = len(candidates)

    if req.compatible_only and req.selected_product_ids:
        engine = CompatibilityEngine(db)
        others = [pid for pid in req.selected_product_ids if pid not in {c.id for c in candidates}]
        candidates = engine.filter_candidates(req.slot, others, candidates)

    kept = candidates[:limit]
    return {
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "current_price": float(p.current_price) if p.current_price is not None else None,
                "p_category": p.p_category,
            }
            for p in kept
        ],
        "total": len(kept),
        "filtered_out": total_before - len(candidates),
    }
