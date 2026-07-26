from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas.store import StoreOut
from services.store_service import StoreService

router = APIRouter(prefix="/stores", tags=["Stores"])


@router.get("", response_model=list[StoreOut])
def list_stores(db: Session = Depends(get_db)):
    """Retrieve list of active retailer stores."""
    service = StoreService(db)
    return service.get_active()
