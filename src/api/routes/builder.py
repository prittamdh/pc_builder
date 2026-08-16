import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from db.models.product import Product
from db.models.saved_build import SavedBuild
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
    "monitor": "Monitor",
}


class CandidateRequest(BaseModel):
    slot: str
    selected_product_ids: list[int] = []
    q: str | None = None
    compatible_only: bool = True


class SaveBuildRequest(BaseModel):
    # slot key -> product id, e.g. {"cpu": 4089, "motherboard": 4867}
    selections: dict[str, int]
    name: str | None = None
    notes: str | None = None


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


@router.post("/builds")
def save_build(req: SaveBuildRequest, db: Session = Depends(get_db)):
    """Persist an assembled build and return a share token.

    Stores product ids rather than prices: the ten stores reprice constantly and the
    whole point of the tool is the current best price, so a saved build is re-costed
    whenever it's opened.
    """
    selections = {slot: pid for slot, pid in (req.selections or {}).items() if pid}
    if not selections:
        raise HTTPException(status_code=400, detail="Cannot save an empty build.")

    unknown_slots = set(selections) - set(SLOT_CATEGORY)
    if unknown_slots:
        raise HTTPException(status_code=400, detail=f"Unknown slots: {sorted(unknown_slots)}")

    product_ids = list(selections.values())
    found = {p.id for p in db.scalars(select(Product).where(Product.id.in_(product_ids)))}
    missing = set(product_ids) - found
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown product ids: {sorted(missing)}")

    summary = BuilderService(db).validate_and_calculate_build(product_ids)

    # token_urlsafe(16) is ~22 chars of URL-safe randomness - unguessable, so a shared
    # link can't be walked to reach anyone else's build the way a sequential id could.
    build = SavedBuild(
        share_token=secrets.token_urlsafe(16),
        name=(req.name or "").strip()[:120] or None,
        selections=selections,
        was_compatible=summary.compatible,
        notes=(req.notes or "").strip()[:2000] or None,
    )
    db.add(build)
    db.commit()
    db.refresh(build)

    return {
        "share_token": build.share_token,
        "name": build.name,
        "compatible": summary.compatible,
        "total_min_cost": str(summary.total_min_cost),
        "created_at": build.created_at.isoformat() if build.created_at else None,
    }


@router.get("/builds/{share_token}")
def load_build(share_token: str, db: Session = Depends(get_db)):
    """Re-hydrate a saved build, re-validated and re-costed against current data.

    Components can go out of stock or be repriced between save and load, so the stored
    verdict is never trusted - it's recomputed and any drift is reported explicitly.
    """
    build = db.scalar(select(SavedBuild).where(SavedBuild.share_token == share_token))
    if build is None:
        raise HTTPException(status_code=404, detail="Saved build not found.")

    selections = build.selections or {}
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(list(selections.values()))))}

    items = {}
    unavailable = []
    for slot, pid in selections.items():
        p = products.get(pid)
        if p is None:
            unavailable.append({"slot": slot, "product_id": pid, "reason": "no longer in catalog"})
            continue
        if not p.in_stock:
            unavailable.append({"slot": slot, "product_id": pid, "name": p.name, "reason": "out of stock"})
        items[slot] = {
            "id": p.id,
            "name": p.name,
            "current_price": float(p.current_price) if p.current_price is not None else None,
            "in_stock": bool(p.in_stock),
        }

    summary = BuilderService(db).validate_and_calculate_build([p.id for p in products.values()])

    return {
        "share_token": build.share_token,
        "name": build.name,
        "notes": build.notes,
        "created_at": build.created_at.isoformat() if build.created_at else None,
        "items": items,
        "unavailable": unavailable,
        "compatible": summary.compatible,
        "warnings": [w.model_dump() if hasattr(w, "model_dump") else w for w in summary.warnings],
        "estimated_wattage": summary.estimated_wattage,
        "total_min_cost": str(summary.total_min_cost),
        "store_breakdown": [
            s.model_dump() if hasattr(s, "model_dump") else s for s in summary.store_breakdown
        ],
        # Surfaced so the UI can say the verdict changed rather than silently showing
        # a different answer than the one the build was saved with.
        "compatibility_changed_since_save": (
            build.was_compatible is not None and build.was_compatible != summary.compatible
        ),
    }
