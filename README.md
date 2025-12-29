````markdown
# NutriGo AI

배달앱 **가게 링크**나 **장바구니/주문 내역 캡처 이미지**를 입력받아  
메뉴별 영양 성분을 추정하고 코칭 멘트를 만들어주는 FastAPI 기반 서비스입니다.

두 가지 주요 엔드포인트(`/internal/api/v1/nutrition/store-link`, `/internal/api/v1/nutrition/cart-image`)를 통해

- 가게 링크 크롤링 (요기요 위주)
- 장바구니/주문 내역 OCR

을 거친 뒤, LLM 분석 결과를 JSON으로 반환합니다.

---

## 준비물

- Python 3.10 이상 (권장 3.11)
- 가상환경 사용 권장
  - 예: Windows PowerShell 기준
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    ```

---

## 설치

### 1) 의존성 설치

루트 디렉터리에서 가상환경을 활성화한 뒤:

```bash
pip install -r requirements.txt
````

> 크롤링(Playwright)과 OCR(PyTesseract)을 모두 쓰려면
> `requirements.txt` 에 포함된 `playwright`, `Pillow`, `pytesseract`, `httpx` 등이 설치되어 있어야 합니다.

Playwright를 처음 쓰는 경우 한 번만 브라우저 바이너리를 설치해 주세요:

```bash
python -m playwright install chromium
```

### 2) Tesseract OCR 설치 (pytesseract용)

이미지 OCR은 `pytesseract`가 **로컬 Tesseract 바이너리**를 호출하는 구조입니다.

* Windows 기준

  1. Tesseract 설치 (예: `C:\Program Files\Tesseract-OCR\`)
  2. 설치 시 **Korean(kor)**, **English(eng)** 언어 데이터 선택
  3. Python 코드에서 다음과 같이 실행 파일 경로를 지정해 둡니다 (`ocr.py` 내부):

     ```python
     import pytesseract
     pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
     ```

* Linux (Ubuntu/Debian) 기준

  ```bash
  sudo apt-get update
  sudo apt-get install tesseract-ocr
  sudo apt-get install tesseract-ocr-kor
  ```

* macOS 기준

  ```bash
  brew install tesseract
  brew install tesseract-lang
  ```

---

## 환경 변수

`.env` 파일 또는 시스템 환경 변수에 아래 값을 설정할 수 있습니다.

* `OPENAI_API_KEY`

  * 기본 LLM 호출에 사용.
  * 없으면 `MOCK_LLM=true` 설정 시 모의 응답(LLM 없이 더미 응답) 모드로 동작.
* `OPENAI_MODEL`

  * 기본: `gpt-4.1-nano` (코드 설정에 맞춰 수정 가능).
* `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`

  * DeepSeek 호환 엔드포인트 사용 시 설정 (미사용 시 생략 가능).
* `PORT`

  * FastAPI 실행 포트 (기본 8000).

-> 노션 확인

---

## 실행 (FastAPI)

가상환경 활성화 후:

```bash
uvicorn nutrigo_ai.api.main:app --host 0.0.0.0 --port 8000 --reload
```

* 헬스체크:
  `GET http://localhost:8000/health`
* Swagger 자동 문서:
  `http://localhost:8000/docs`

---

## 주요 API

### 1. 가게 링크 기반 분석

`POST /internal/api/v1/nutrition/store-link`

* **설명**

  * 배달앱(요기요 등) **가게 상세 링크**를 크롤링해서
  * 메뉴/옵션 텍스트를 추출하고
  * 사용자의 영양 목표(`user_goal`)에 맞춰 메뉴별 영양 분석 및 추천을 반환합니다.

* **요청 바디 예시**

  ```json
  {
    "store_url": "https://www.yogiyo.co.kr/mobile/#/123456",
    "user_goal": {
      "focus": "diet",
      "calorie_min": 0,
      "calorie_max": 0,
      "protein_min": 0,
      "fat_max": 0,
      "carb_max": 0,
      "sodium_max": 0
    }
  }
  ```

* **동작 요약**

  * `store_url` 크롤링 → 메뉴 텍스트(`MenuText[]`) 추출
  * LLM에 메뉴 리스트 + user_goal 전달
  * 각 메뉴별 추정 영양값, 점수, 배지, 코칭 문장을 포함한 응답 반환
  * 크롤링 실패 시 간단한 **더미 메뉴**로 폴백하여 LLM 흐름은 깨지지 않도록 처리

---

### 2. 장바구니/주문 내역 캡처 기반 분석

`POST /internal/api/v1/nutrition/cart-image`

* **설명**

  * 배달앱 장바구니 화면 또는 주문 내역 캡처 이미지를 받아
  * **이미지 다운로드 → OCR → 메뉴 텍스트 추출 → LLM 분석**까지 한 번에 수행합니다.

* **요청 바디 예시 (S3 Object URL 사용)**

  ```json
  {
    "capture_id": "order-2025-12-09-223825",
    "image_url": "https://nutrigo-ai.s3.ap-northeast-2.amazonaws.com/스크린샷+2025-12-09+223825.png",
    "user_goal": {
      "focus": "diet",
      "calorie_min": 0,
      "calorie_max": 0,
      "protein_min": 0,
      "fat_max": 0,
      "carb_max": 0,
      "sodium_max": 0
    }
  }
  ```

* **요청 바디 예시 (base64 Data URL 사용)**

  ```json
  {
    "capture_id": "order-2025-12-09-223825",
    "image_base64": "data:image/png;base64,iVBORw0K...",
    "user_goal": {
      "focus": "diet",
      "calorie_min": 0,
      "calorie_max": 0,
      "protein_min": 0,
      "fat_max": 0,
      "carb_max": 0,
      "sodium_max": 0
    }
  }
  ```

  > `image_url`과 `image_base64` 중 **하나 이상은 필수**입니다.
  > 이미지에 접근 가능한 HTTP(S) URL이어야 하며, S3의 경우 **객체 URL 또는 presigned URL**을 사용합니다.

* **동작 요약**

  * `image_url` 또는 `image_base64`로부터 이미지 바이트 로드
  * Tesseract 기반 OCR 수행 → 메뉴 이름/설명/가격 후보 추출
  * LLM에 메뉴 리스트 + user_goal 전달
  * 각 메뉴별 영양 추정/코칭 + 전체 요약/추천 메뉴 ID 응답

---

## 응답 스키마

두 엔드포인트 모두 공통 응답 스키마를 사용합니다.
자세한 정의는 `src/nutrigo_ai/api/schemas.py`의 `NutritionAnalysisResponse`를 참고하세요.

대략적인 구조는 다음과 같습니다:

```json
{
  "analyses": [
    {
      "menu": {
        "id": "string",
        "name": "string",
        "description": "string",
        "price": 0,
        "category_hint": "string",
        "option_text": "string"
      },
      "nutrition": {
        "kcal": 0,
        "carb_g": 0,
        "protein_g": 0,
        "fat_g": 0,
        "sodium_mg": 0,
        "confidence": 0.0
      },
      "score": 80,
      "badges": ["저열량", "고단백"],
      "coach_sentence": "string"
    }
  ],
  "summary": "string",
  "recommended_menu_ids": ["string"]
}
```

---

## 디렉터리 구조

```
nutrigo-ai/
├── src/
│   └── nutrigo_ai/
│       ├── api/              # FastAPI 엔드포인트
│       │   ├── main.py       # 애플리케이션 진입점
│       │   ├── routes/       # 라우트 핸들러
│       │   └── schemas.py    # Pydantic 스키마
│       ├── core/             # 핵심 설정
│       │   ├── config.py     # 설정 관리
│       │   ├── llm_client.py # LLM 클라이언트
│       │   └── logging.py    # 로깅 설정
│       ├── ingestion/        # 데이터 수집
│       │   ├── ocr.py        # OCR 처리
│       │   ├── store_link.py # 가게 링크 크롤링
│       │   └── sources/      # 크롤링 소스별 파서
│       └── services/         # 비즈니스 로직
│           ├── llm_service.py      # LLM 서비스
│           └── prediction_service.py # 예측 서비스
├── requirements.txt
├── pyproject.toml
└── Dockerfile
```

---

## 문제 해결

### Playwright 크롤링 실패
- Playwright 브라우저가 제대로 설치되었는지 확인: `python -m playwright install chromium`
- 네트워크 연결 확인
- 크롤링 대상 사이트의 구조 변경 가능성 확인

### OCR 인식 실패
- Tesseract OCR이 설치되어 있고, 언어 데이터(kor, eng)가 포함되어 있는지 확인
- 이미지 품질이 낮은 경우 전처리가 필요할 수 있습니다
- Windows에서 경로 설정이 올바른지 확인

### LLM API 호출 실패
- `.env` 파일의 API 키가 올바른지 확인
- 인터넷 연결 확인
- `MOCK_LLM=true`로 설정하여 모의 모드로 테스트 가능

### 포트 충돌
- 다른 애플리케이션이 포트 8000을 사용 중인지 확인
- `PORT` 환경 변수로 다른 포트 지정 가능

---

## Docker를 사용한 실행

Dockerfile이 포함되어 있습니다. Docker를 사용하여 실행할 수 있습니다:

```bash
docker build -t nutrigo-ai .
docker run -p 8000:9000 --env-file .env nutrigo-ai
```

주의: Dockerfile의 기본 포트는 9000입니다.

---
