from fastapi import APIRouter, HTTPException
import logging

from nutrigo_ai.api.schemas import (
    NutriBotCoachRequest,
    NutriBotCoachResponse,
)
from nutrigo_ai.services.llm_service import coach_with_llm

logger = logging.getLogger(__name__)

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
    try:
        logger.info(f"[nutribot] 요청 받음: mode={req.mode}, user_message={req.user_message}")
        return coach_with_llm(req)
    except Exception as e:
        logger.error(f"[nutribot] 에러 발생: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"챗봇 응답 생성 실패: {str(e)}")
