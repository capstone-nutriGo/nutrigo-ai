from fastapi import APIRouter

from nutrigo_ai.api.schemas import (
    NutritionAnalysisRequest,
    NutritionAnalysisResponse,
)
from nutrigo_ai.services.llm_service import analyze_menus_with_llm

router = APIRouter(
    prefix="/internal/api/v1/nutrition",
    tags=["nutrition"],
)


@router.post("/store-link", response_model=NutritionAnalysisResponse)
async def analyze_from_store_link(req: NutritionAnalysisRequest):
    """
    배달앱 가게 페이지 링크 기반 분석
    """
    req.source_type = "store_link"
    return analyze_menus_with_llm(req)


@router.post("/cart-image", response_model=NutritionAnalysisResponse)
async def analyze_from_cart_image(req: NutritionAnalysisRequest):
    """
    장바구니 캡처(OCR) 기반 분석
    """
    req.source_type = "cart_image"
    return analyze_menus_with_llm(req)
