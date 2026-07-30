"""
API Endpoints for Experimental Canonical Product Matching.
Enables running the matching pipeline and inspecting canonical product groups via GUI.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db.session import get_session
from services.canonical_matching_service import CanonicalMatchingService

router = APIRouter(prefix="/canonical", tags=["canonical"])


@router.post("/run")
def run_canonical_matching(session: Session = Depends(get_session)):
    """Run the experimental matching pipeline over 10-store database products."""
    service = CanonicalMatchingService(session)
    summary = service.run_experimental_matching()
    return {"status": "success", "summary": summary}


@router.get("/products")
def get_canonical_products(
    category: str | None = Query(None, description="Filter by category e.g. cpu, gpu, ram, storage, psu"),
    needs_review: bool | None = Query(None, description="Filter by review queue status"),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session)
):
    """Fetch grouped canonical products and store listings for GUI inspection."""
    service = CanonicalMatchingService(session)
    products = service.get_canonical_products(category=category, needs_review=needs_review, limit=limit)
    return {"status": "success", "count": len(products), "items": products}
