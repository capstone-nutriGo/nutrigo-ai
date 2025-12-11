from fastapi import APIRouter

from nutrigo_ai.api.schemas import (
    CartImageAnalysisRequest,
    NutritionAnalysisRequest,
    NutritionAnalysisResponse,
    StoreLinkAnalysisRequest,
    MealLogCandidate,
    OrderImageMealLogResponse,
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
def analyze_from_store_link(req: StoreLinkAnalysisRequest):
    """배달앱 가게 페이지 링크 기반 분석"""

    menus = build_menus_from_store_link(req)
    analysis_req = NutritionAnalysisRequest(
        source_type="store_link",
        source_id=req.store_url,
        user_goal=req.user_goal,
        menus=menus,
    )
    return analyze_menus_with_llm(analysis_req)


@router.post("/cart-image", response_model=NutritionAnalysisResponse)
def analyze_from_cart_image(req: CartImageAnalysisRequest):
    """장바구니 캡처(OCR) 기반 분석"""

    menus = build_menus_from_cart_image(req)
    analysis_req = NutritionAnalysisRequest(
        source_type="cart_image",
        source_id=req.capture_id or req.image_url,
        user_goal=req.user_goal,
        menus=menus,
    )
    return analyze_menus_with_llm(analysis_req)

@router.post("/order-image", response_model=OrderImageMealLogResponse)
def analyze_from_order_image(req: CartImageAnalysisRequest):
    """
    주문 내역 캡처(OCR) 기반 *식사 기록용* 분석.

    1) 장바구니/주문 내역 캡처에서 메뉴 텍스트를 OCR로 뽑고
    2) LLM으로 대략적인 영양 성분/점수를 추정한 뒤
    3) MealLog에 바로 저장할 수 있는 형태로 리턴한다.
    """

    # 1) OCR 기반으로 메뉴 후보 추출 (CartImage와 동일 파이프라인 재사용)
    menus = build_menus_from_cart_image(req)

    # 2) LLM 영양 분석 (source_type만 order_image로 지정)
    analysis_req = NutritionAnalysisRequest(
        source_type="order_image",
        source_id=req.capture_id or req.image_url,
        user_goal=req.user_goal,
        menus=menus,
    )
    nutri_res: NutritionAnalysisResponse = analyze_menus_with_llm(analysis_req)

    # 3) MenuAnalysis -> MealLogCandidate 로 매핑
    items: list[MealLogCandidate] = []
    for a in nutri_res.analyses:
        items.append(
            MealLogCandidate(
                menu=a.menu.name,
                category=a.menu.category_hint,
                kcal=a.nutrition.kcal,
                sodium_mg=a.nutrition.sodium_mg,
                protein_g=a.nutrition.protein_g,
                carb_g=a.nutrition.carb_g,
                total_score=a.score,
            )
        )

    return OrderImageMealLogResponse(
        capture_id=req.capture_id or req.image_url,
        items=items,
        # raw_ocr_text는 필요하면 ocr.py에서 텍스트도 같이 리턴하도록 확장
        raw_ocr_text=None,
    )