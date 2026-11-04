from fastapi import APIRouter, Depends

from app.auth.deps import get_current_owner
from app.models import Owner
from app.schemas.api import OwnerOut

router = APIRouter(prefix="/api", tags=["owner"])


@router.get("/me", response_model=OwnerOut)
def me(owner: Owner = Depends(get_current_owner)):
    return owner
