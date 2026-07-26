from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_db
from domain.builder import BuildSelection, BuildSummary, ComponentSlot
from services.builder_service import BuilderService

router = APIRouter(prefix="/builder", tags=["PC Builder"])


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
