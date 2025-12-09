from fastapi import APIRouter

from nutrigo_ai.api.schemas import (
    CartImageAnalysisRequest,
    NutritionAnalysisRequest,
    NutritionAnalysisResponse,
    StoreLinkAnalysisRequest,
)
from nutrigo_ai.ingestion.entry import (
    build_menus_from_cart_image,
    build_menus_from_store_link,
)
from nutrigo_ai.services.llm_service import analyze_menus_with_llm

router = APIRouter(
    prefix="/internal/api/v1/nutrition",
    tags=["nutrition"],
)


@router.post("/store-link", response_model=NutritionAnalysisResponse)
async def analyze_from_store_link(req: StoreLinkAnalysisRequest):
    """배달앱 가게 페이지 링크 기반 분석"""

    menus = build_menus_from_store_link(req)
    analysis_req = NutritionAnalysisRequest(
        source_type="store_link",
        source_id=req.store_id or req.store_url,
        user_goal=req.user_goal,
        menus=menus,
    )
    return analyze_menus_with_llm(analysis_req)


@router.post("/cart-image", response_model=NutritionAnalysisResponse)
async def analyze_from_cart_image(req: CartImageAnalysisRequest):
    """장바구니 캡처(OCR) 기반 분석"""

    menus = build_menus_from_cart_image(req)
    analysis_req = NutritionAnalysisRequest(
        source_type="cart_image",
        source_id=req.capture_id or req.image_url,
        user_goal=req.user_goal,
        menus=menus,
    )
    return analyze_menus_with_llm(analysis_req)
