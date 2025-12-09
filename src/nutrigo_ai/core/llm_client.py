import os
import json
from typing import Dict, Any

from dotenv import load_dotenv
from fastapi import HTTPException

# .env 로부터 키 로드 (이미 다른 데서 load_dotenv 쓰고 있으면 생략해도 OK)
load_dotenv()

MOCK_LLM = os.getenv("MOCK_LLM", "false").lower() == "true"

if not MOCK_LLM:
    from openai import OpenAI

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")

def call_openai_json(system_prompt: str, user_payload: Dict[str, Any]) -> Dict[str, Any]:
    # 1) MOCK 모드: 진짜 OpenAI 안 쓰고 가짜 응답 리턴
    if MOCK_LLM:
        # nutrition API에서 호출한 경우와 nutribot에서 호출한 경우를 대충 분기
        if "menus" in user_payload:
            # 영양 분석용 더미
            menus = user_payload.get("menus", [])
            items = []
            for m in menus:
                mid = m.get("id")
                items.append(
                    {
                        "menu_id": mid,
                        "nutrition": {
                            "kcal": 800.0,
                            "carb_g": 90.0,
                            "protein_g": 30.0,
                            "fat_g": 25.0,
                            "sodium_mg": 1800.0,
                            "confidence": 0.3,
                        },
                        "score": 50.0,
                        "badges": ["테스트용", "모의데이터"],
                        "coach_sentence": f"[MOCK] {m.get('name', '메뉴')}에 대한 테스트 코멘트입니다.",
                    }
                )
            return {
                "items": items,
                "summary": "[MOCK] 여기는 영양 분석 요약 문장입니다.",
                "recommended_menu_ids": [m.get("id") for m in menus],
            }
        else:
            # nutribot 코칭용 더미
            return {
                "reply": "[MOCK] 오늘은 테스트 모드라 실제 LLM 대신 모의 응답을 보여드려요.",
                "tone": "gentle",
                "recommended_actions": [
                    "테스트 상태에서 API 호출이 잘 되는지 확인해 보세요.",
                    "나중에 쿼터가 생기면 MOCK_LLM=false 로 바꾸세요.",
                ],
            }


    # --------------------------
    # 2) 실제 OpenAI API 호출
    # --------------------------
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 가 설정되어 있지 않습니다.")

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)

        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
        )
        raw = completion.choices[0].message.content
        return json.loads(raw)

    except Exception as e:
        # 여기서 발생하는 에러는 FastAPI 쪽에서 500으로 내려감
        raise HTTPException(status_code=500, detail=f"LLM 호출 중 오류: {e}")