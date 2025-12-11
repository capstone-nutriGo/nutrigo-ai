from fastapi import APIRouter
from ...core.config import APP_VERSION

router = APIRouter()

@router.get("")
def health():
    return {"status": "ok", "version": APP_VERSION}
