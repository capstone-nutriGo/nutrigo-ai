from nutrigo_ai.api.schemas import (
    UserGoal,
    NutritionAnalysisRequest,
    NutritionAnalysisResponse,
)
from nutrigo_ai.services.llm_service import analyze_menus_with_llm
from nutrigo_ai.ingestion.sources.yogiyo import (
    fetch_store_info,
    menu_json_to_menu_texts,
)


def analyze_yogiyo_store(
    *,
    store_id: str,
    address_text: str,
    lat: float,
    lng: float,
    user_goal: UserGoal,
) -> NutritionAnalysisResponse:
    """
    1) 요기요에서 메뉴 크롤링
    2) menu_json → MenuText[]
    3) LLM에 NutritionAnalysisRequest 던져서 결과 반환
    """
    # 1) 크롤링
    result = fetch_store_info(
        store_id=store_id,
        address_text=address_text,
        lat=lat,
        lng=lng,
        order_serving_type="delivery",
        headless=True,
        pause_on_finish=False,
    )
    if result is None:
        raise RuntimeError("요기요 메뉴 크롤링 실패")

    # 2) menu_json → MenuText[]
    menus = menu_json_to_menu_texts(result["menu_json"])

    # 3) LLM 요청 만들기
    req = NutritionAnalysisRequest(
        source_type="store_link",
        source_id=store_id,
        user_goal=user_goal,
        menus=menus,
    )

    # 4) LLM 호출
    return analyze_menus_with_llm(req)
