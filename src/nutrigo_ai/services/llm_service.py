from typing import List, Any, Dict

from nutrigo_ai.api.schemas import (
    NutritionAnalysisRequest,
    NutritionAnalysisResponse,
    MenuAnalysis,
    NutritionEstimate,
    NutriBotCoachRequest,
    NutriBotCoachResponse,
)
from nutrigo_ai.core.llm_client import call_openai_json


def _to_dict(model: Any) -> Dict[str, Any]:
    """Pydantic v1 / v2 양쪽 호환용"""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


# -----------------------------
# 1) 영양 분석 + 메뉴 추천
# -----------------------------
def analyze_menus_with_llm(req: NutritionAnalysisRequest) -> NutritionAnalysisResponse:
    system_prompt = """
너는 한국 배달 음식을 잘 아는 전문 영양 코치이자 데이터 분석가 AI다.
입력으로 사용자 기본 정보(user_info: 성별, 생년월일)와 여러 메뉴 정보를 받는다.

해야 할 일:
1. 각 메뉴에 대해 대략적인 영양 성분을 추정한다.
   - kcal (열량)
   - 탄수화물(g), 단백질(g), 지방(g), 나트륨(mg)
   - confidence (0~1, 추정 신뢰도)

2. 사용자 성별·연령대를 고려해서, 각 메뉴가
   일반적인 건강 관점에서 얼마나 무난한 선택인지 0~100 점으로 score를 준다.
   (칼로리 과다/나트륨 과다/단백질 부족 등을 종합적으로 판단)

3. 각 메뉴에 대해 1~2문장 정도의 코멘트(coach_sentence)를 한국어로 작성한다.
4. 각 메뉴에 대해 특징적인 badge 목록을 만든다.
   - 예: ["고단백", "저열량", "저나트륨", "고열량주의"] 등 0~3개.

5. 전체 메뉴 리스트에 대해 요약(summary) 문단을 한국어로 작성한다.
6. score 상위 메뉴를 중심으로 recommended_menu_ids 를 구성한다 (3~5개).

출력은 반드시 아래 JSON 스키마를 따르는 단일 JSON 객체여야 한다.

{
  "items": [
    {
      "menu_id": "메뉴ID",
      "nutrition": {
        "kcal": float,
        "carb_g": float,
        "protein_g": float,
        "fat_g": float,
        "sodium_mg": float,
        "confidence": float
      },
      "score": float,
      "badges": ["문자열", ...],
      "coach_sentence": "문자열"
    }
  ],
  "summary": "문자열",
  "recommended_menu_ids": ["메뉴ID1", "메뉴ID2", ...]
}
"""

    payload = {
        "user_info": _to_dict(req.user_info) if req.user_info is not None else None,
        "menus": [_to_dict(m) for m in req.menus],
        "source_type": req.source_type,
    }

    data = call_openai_json(system_prompt, payload)

    id_to_menu = {m.id: m for m in req.menus}
    analyses: List[MenuAnalysis] = []

    for item in data.get("items", []):
        mid = item.get("menu_id")
        if mid not in id_to_menu:
            continue

        nutr_raw = item["nutrition"]
        nutrition = NutritionEstimate(
            kcal=nutr_raw["kcal"],
            carb_g=nutr_raw["carb_g"],
            protein_g=nutr_raw["protein_g"],
            fat_g=nutr_raw["fat_g"],
            sodium_mg=nutr_raw["sodium_mg"],
            confidence=nutr_raw.get("confidence", 0.5),
        )

        analysis = MenuAnalysis(
            menu=id_to_menu[mid],
            nutrition=nutrition,
            score=item["score"],
            badges=item.get("badges", []),
            coach_sentence=item["coach_sentence"],
        )
        analyses.append(analysis)

    analyses.sort(key=lambda a: a.score, reverse=True)

    return NutritionAnalysisResponse(
        analyses=analyses,
        summary=data.get("summary", ""),
        recommended_menu_ids=data.get(
            "recommended_menu_ids", [a.menu.id for a in analyses[:5]]
        ),
    )


# -----------------------------
# 2) NutriBot 코칭
# -----------------------------
def coach_with_llm(req: NutriBotCoachRequest) -> NutriBotCoachResponse:
    system_prompt = """
너는 'NutriBot'이라는 이름의 영양 코치 챗봇이다.
상대는 배달 음식을 자주 먹지만, 완벽한 식단관리는 어렵고
'지금 상황에서 덜 후회되는 선택'을 찾고 싶어 한다.

원칙:
- 말투는 친근하고 부드러운 존댓말.
- 죄책감을 과하게 느끼지 않도록, 잘하고 있는 점을 최소 1개 이상 짚어줄 것.
- 오늘 당장 실천 가능한 2~3가지 행동에 집중할 것.
- 의학적 진단/병명 언급은 하지 말 것.
"""

    if req.mode == "today":
        user_instruction = """
mode: today

오늘과 최근 며칠간의 섭취 패턴, 사용자 목표, 최근에 먹은 대표 메뉴 목록이 주어진다.
오늘 기준으로 짧은 코칭 메시지를 만들어라.

반드시 JSON 형식으로 응답해야 합니다:
{
  "reply": "한국어 코칭 문단 (2~5문장)",
  "tone": "gentle | strict | motivational 중 하나",
  "recommended_actions": ["오늘 실천하면 좋은 간단한 행동", ...]
}
"""
    else:  # chat
        user_instruction = """
mode: chat

사용자의 질문/메시지와 기본적인 영양 목표,
최근 며칠간의 섭취 패턴, 최근 먹은 메뉴 목록이 주어진다.

질문에 대해 성의 있게 답변하되,
오늘 당장 적용 가능한 2~3가지 액션을 제시하라.

반드시 JSON 형식으로 응답해야 합니다:
{
  "reply": "한국어 코칭 문단 (2~6문장)",
  "tone": "gentle | strict | motivational 중 하나",
  "recommended_actions": ["오늘 실천하면 좋은 간단한 행동", ...]
}
"""

    payload = {
        "mode": req.mode,
        "user_goal": _to_dict(req.user_goal),
        "daily_summaries": [_to_dict(d) for d in req.daily_summaries],
        "recent_menus": [_to_dict(m) for m in req.recent_menus],
        "user_message": req.user_message,
        "instruction": user_instruction,
    }

    data = call_openai_json(system_prompt, payload)

    return NutriBotCoachResponse(
        reply=data.get(
            "reply",
            "오늘 식단도 너무 걱정하지 마시고, 천천히 한 걸음씩 같이 조정해 봐요.",
        ),
        tone=data.get("tone", "gentle"),
        recommended_actions=data.get("recommended_actions", []),
    )
