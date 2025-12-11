
from datetime import date
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator


# -----------------------------
# LLM Nutrition / Recommendation
# -----------------------------
class UserGoal(BaseModel):
    """사용자 영양 목표"""
    focus: Literal["diet", "bulk", "maintenance", "low_sodium", "custom"] = Field(
        ..., description="주요 목표"
    )
    calorie_min: Optional[int] = Field(None, description="하루 최소 칼로리")
    calorie_max: Optional[int] = Field(None, description="하루 최대 칼로리")
    protein_min: Optional[int] = Field(None, description="하루 최소 단백질 g")
    fat_max: Optional[int] = Field(None, description="하루 최대 지방 g")
    carb_max: Optional[int] = Field(None, description="하루 최대 탄수화물 g")
    sodium_max: Optional[int] = Field(None, description="하루 최대 나트륨 mg")


class MenuText(BaseModel):
    """크롤링/OCR 결과에서 LLM에 던질 메뉴 정보"""
    id: str
    name: str
    description: Optional[str] = ""
    price: Optional[int] = None
    category_hint: Optional[str] = Field(
        None, description="예: 떡볶이, 치킨, 마라탕 등"
    )
    option_text: Optional[str] = Field(
        None, description="곱빼기/치즈추가/국물많이 등 옵션 문자열"
    )


class NutritionEstimate(BaseModel):
    """LLM이 추정한 대략적인 영양 정보"""
    kcal: float
    carb_g: float
    protein_g: float
    fat_g: float
    sodium_mg: float
    confidence: float = Field(
        0.5, description="0~1 사이 신뢰도"
    )


class MenuAnalysis(BaseModel):
    menu: MenuText
    nutrition: NutritionEstimate
    score: float = Field(..., description="0~100 점 (목표 적합도)")
    badges: List[str] = Field(
        default_factory=list,
        description="예: ['고단백', '저나트륨', '고열량주의']",
    )
    coach_sentence: str = Field(
        ..., description="이 메뉴에 대한 한 줄 코멘트"
    )


class NutritionAnalysisRequest(BaseModel):
    """store-link / cart-image / order-image 공통 요청 바디"""
    source_type: Literal["store_link", "cart_image", "order_image"]
    source_id: Optional[str] = Field(
        None, description="storeId 또는 cartCaptureId 등"
    )
    user_goal: UserGoal
    menus: List[MenuText]



class NutritionAnalysisResponse(BaseModel):
    analyses: List[MenuAnalysis]
    summary: str
    recommended_menu_ids: List[str]


class StoreLinkAnalysisRequest(BaseModel):
    """
    배달앱 가게 링크를 기반으로 메뉴 목록을 수집한 뒤 영양 분석을 수행하기 위한 요청 바디.

    - store_url: 실제 배달앱 가게 페이지 URL (배민/요기요 등)
    - user_goal: 사용자 영양 목표
    """

    store_url: str = Field(..., description="배달앱 가게 페이지 URL")
    user_goal: UserGoal


class CartImageAnalysisRequest(BaseModel):
    """
    배달앱 장바구니/주문 확인 캡처 이미지를 기반으로 OCR + 영양 분석을 수행하기 위한 요청 바디.

    - image_url 또는 image_base64 둘 중 하나는 반드시 필요
    - 메뉴 정보는 요청 바디에 포함하지 않고,
      서버가 OCR을 통해 메뉴를 추출한 뒤 응답의 analyses[*].menu 로 돌려준다.
    """

    image_url: Optional[str] = Field(None, description="장바구니 캡처 이미지 URL")
    image_base64: Optional[str] = Field(
        None, description="캡처 이미지 Base64 (데이터 URI 허용)"
    )
    capture_id: Optional[str] = Field(None, description="장바구니 캡처 식별자")
    user_goal: UserGoal

    @model_validator(mode="after")
    def validate_image_source(self):
        if not self.image_url and not self.image_base64:
            raise ValueError("image_url 또는 image_base64 중 하나는 필요합니다.")
        return self


# -----------------------------
# NutriBot 코칭 스키마
# -----------------------------
class DailySummary(BaseModel):
    date: date
    total_kcal: float
    total_sodium_mg: float
    total_protein_g: float
    total_fat_g: float
    total_carb_g: float


class NutriBotCoachRequest(BaseModel):
    """
    mode:
      - today: 오늘 기준 코칭 (/api/v1/nutribot/today)
      - chat : 자유로운 질문 (/api/v1/nutribot/messages)
    """
    mode: Literal["today", "chat"]
    user_goal: UserGoal
    daily_summaries: List[DailySummary] = Field(default_factory=list)
    recent_menus: List[MenuAnalysis] = Field(default_factory=list)
    user_message: Optional[str] = Field(
        None, description="chat 모드일 때 사용자의 질문"
    )


class NutriBotCoachResponse(BaseModel):
    reply: str
    tone: Literal["gentle", "strict", "motivational"] = "gentle"
    recommended_actions: List[str] = Field(
        default_factory=list,
        description="오늘 실천하면 좋은 간단한 액션들",
    )

class MealLogCandidate(BaseModel):
    """
    주문내역 캡처에서 인식된 한 메뉴에 대한 식사 기록 후보.
    JPA MealLog 엔티티의 대부분 필드와 1:1 매핑 가능하게 설계.
    """

    menu: str                         # MealLog.menu
    category: Optional[str] = None    # MealLog.category
    kcal: Optional[float] = None      # MealLog.kcal
    sodium_mg: Optional[float] = None # MealLog.sodiumMg
    protein_g: Optional[float] = None # MealLog.proteinG
    carb_g: Optional[float] = None    # MealLog.carbG
    total_score: Optional[float] = None  # MealLog.totalScore


class OrderImageMealLogResponse(BaseModel):
    """
    /order-image 결과를 MealLog 저장용으로 쓰기 위한 응답 스키마.
    - meal_time, meal_date 는 보통 프론트/백엔드가 알고 있으니 여기선 생략하거나 참고만.
    - created_at, id, dailyIntakeSummary 는 DB에서 채우는 필드라 응답에는 필요 X.
    """

    capture_id: Optional[str] = None          # 어떤 캡처에서 나온 결과인지
    items: List[MealLogCandidate]             # MealLog 로 저장할 후보들
    raw_ocr_text: Optional[str] = None        # (선택) 디버깅용 전체 OCR 텍스트