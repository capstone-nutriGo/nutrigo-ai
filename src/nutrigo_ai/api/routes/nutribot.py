from fastapi import APIRouter

from nutrigo_ai.api.schemas import (
    NutriBotCoachRequest,
    NutriBotCoachResponse,
)
from nutrigo_ai.services.llm_service import coach_with_llm

router = APIRouter(
    prefix="/internal/api/v1/nutribot",
    tags=["nutribot"],
)


@router.post("/coach", response_model=NutriBotCoachResponse)
async def nutribot_coach(req: NutriBotCoachRequest):
    """
    NutriBot 코칭 엔드포인트
    - /api/v1/nutribot/today    → Spring 에서 mode=today 로 호출
    - /api/v1/nutribot/messages → Spring 에서 mode=chat  으로 호출
    """
    return coach_with_llm(req)
