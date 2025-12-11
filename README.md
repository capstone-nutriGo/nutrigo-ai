# NutriGo AI

배달앱 링크나 장바구니 캡처 이미지를 입력받아 메뉴별 영양성분을 분석하는 FastAPI 서비스입니다. 두 가지 엔드포인트(`/internal/api/v1/nutrition/store-link`, `/internal/api/v1/nutrition/cart-image`)를 통해 가게 링크 크롤링 또는 OCR 파이프라인을 거친 뒤 LLM 분석 결과를 반환합니다.

## 준비물
- Python 3.10 이상
- 가상환경 권장 (예: `python -m venv .venv` 후 `source .venv/bin/activate`)

## 설치
```bash
pip install -e .
# 크롤링·OCR까지 사용하려면 선택적으로 ingest 익스트라 설치
pip install -e .[ingest]
# playwright를 처음 설치했다면 브라우저 바이너리도 준비
python -m playwright install chromium
```
- `pytesseract`를 활용하려면 OS에 Tesseract OCR 바이너리가 설치되어 있어야 합니다.

## 환경 변수
- `OPENAI_API_KEY`: 기본 LLM 호출 시 사용. 없으면 `MOCK_LLM=true`로 모의 응답을 사용할 수 있습니다.
- `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`: DeepSeek 호환 엔드포인트를 쓸 경우 설정(기본은 OpenAI와 동일 키/`deepseek-chat`).
- `OPENAI_MODEL`: 기본 `gpt-4.1-nano`.
- `PORT`: FastAPI 실행 포트(기본 8000).

루트 디렉터리의 `.env`에 위 값을 적어두면 자동으로 불러옵니다.

## 실행 (FastAPI)
```bash
uvicorn nutrigo_ai.api.main:app --host 0.0.0.0 --port 8000 --reload
```
- 헬스체크: `GET /health`
- 자동 문서: `http://localhost:8000/docs`

## 주요 API
- `POST /internal/api/v1/nutrition/store-link`
  - 바디 예시: `{ "store_url": "https://...", "user_goal": "다이어트" }`
  - 요기요 링크를 우선 크롤링하고 실패 시 더미 메뉴를 사용해 영양 분석을 수행합니다.
- `POST /internal/api/v1/nutrition/cart-image`
  - 바디 예시: `{ "image_url": "https://.../cart.png", "user_goal": "단백질 증량" }`
  - 이미지를 내려받아 OCR → 메뉴 후보를 추출한 뒤 영양 분석을 진행합니다.

두 엔드포인트 모두 응답 스키마는 `src/nutrigo_ai/api/schemas.py`의 `NutritionAnalysisResponse`를 따릅니다.

## 테스트
```bash
python -m pytest
```