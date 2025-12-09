
from datetime import date
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


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
    """store-link / cart-image 공통 요청 바디"""
    source_type: Literal["store_link", "cart_image"]
    source_id: Optional[str] = Field(
        None, description="storeId 또는 cartCaptureId 등"
    )
    user_goal: UserGoal
    menus: List[MenuText]


class NutritionAnalysisResponse(BaseModel):
    analyses: List[MenuAnalysis]
    summary: str
    recommended_menu_ids: List[str]


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
