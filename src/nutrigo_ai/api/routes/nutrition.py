from fastapi import APIRouter

from nutrigo_ai.api.schemas import (
    CartImageAnalysisRequest,
    NutritionAnalysisRequest,
    NutritionAnalysisResponse,
    StoreLinkAnalysisRequest,
    MealLogCandidate,
    OrderImageMealLogResponse,
    OrderImageAnalysisRequest, 
)
from nutrigo_ai.ingestion.entry import (
    build_menus_from_cart_image,
    build_menus_from_store_link,
)
from nutrigo_ai.services.llm_service import analyze_menus_with_llm

router = APIRouter(prefix="/internal/api/v1/nutrition", tags=["nutrition"])


@router.post("/store-link", response_model=NutritionAnalysisResponse)
def analyze_from_store_link(req: StoreLinkAnalysisRequest) -> NutritionAnalysisResponse:
    menus = build_menus_from_store_link(req)

    analysis_req = NutritionAnalysisRequest(
        source_type="store_link",
        source_id=req.store_url,
        user_info=req.user_info,
        menus=menus,
    )
    return analyze_menus_with_llm(analysis_req)


@router.post("/cart-image", response_model=NutritionAnalysisResponse)
def analyze_from_cart_image(req: CartImageAnalysisRequest) -> NutritionAnalysisResponse:
    menus = build_menus_from_cart_image(req)

    analysis_req = NutritionAnalysisRequest(
        source_type="cart_image",
        source_id=req.capture_id or req.image_url,
        user_info=req.user_info,
        menus=menus,
    )
    return analyze_menus_with_llm(analysis_req)


@router.post("/order-image", response_model=OrderImageMealLogResponse)
def analyze_from_order_image(req: OrderImageAnalysisRequest) -> OrderImageMealLogResponse:
    """
    주문내역 캡처 → OCR → 메뉴 인식 → LLM 영양 추정 → MealLog 후보 리스트

    👉 여기서는 user_info 를 전혀 받지 않는다.
       order_date / meal_time 은 요청으로만 받고, LLM 쪽에는 넘기지 않는다.
    """

    # 1) cart-image 와 동일한 OCR 파이프라인 재사용
    menus = build_menus_from_cart_image(req)

    # 2) 영양 분석은 user_info 없이 수행
    analysis_req = NutritionAnalysisRequest(
        source_type="order_image",
        source_id=req.capture_id or req.image_url,
        user_info=None,   # ★ order-image 는 user_info 안 씀
        menus=menus,
    )
    nutri_res = analyze_menus_with_llm(analysis_req)

    # 3) NutritionAnalysisResponse -> OrderImageMealLogResponse 변환
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
        raw_ocr_text=None,
    )
