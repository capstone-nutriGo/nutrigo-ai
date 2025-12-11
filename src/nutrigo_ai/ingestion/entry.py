"""인입 오케스트레이션.

배달앱 가게 링크 크롤링, 장바구니 캡처 OCR 파이프라인을 묶어
LLM 영양 분석에 필요한 MenuText 리스트를 만든다. 외부 의존성(브라우저,
Tesseract)이 없거나 실패해도 기본 더미 메뉴를 반환해 API가 깨지지 않도록
설계했다.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Iterable, List

from nutrigo_ai.api.schemas import CartImageAnalysisRequest, MenuText, StoreLinkAnalysisRequest
from nutrigo_ai.ingestion.ocr import menus_from_cart_image
from nutrigo_ai.ingestion.store_link import menus_from_store_link


def _ensure_menu_ids(menus: Iterable[MenuText], prefix: str = "item") -> List[MenuText]:
    """MenuText.id 가 비어 있으면 prefix 기반으로 채워 넣는다."""

    normalized: List[MenuText] = []
    for idx, menu in enumerate(menus, start=1):
        menu_id = menu.id if getattr(menu, "id", None) else f"{prefix}-{idx}"
        normalized.append(
            MenuText(
                id=menu_id,
                name=menu.name,
                description=menu.description,
                price=menu.price,
                category_hint=menu.category_hint,
                option_text=menu.option_text,
            )
        )
    return normalized


def _fallback_menus(base_key: str) -> List[MenuText]:
    """크롤링/ OCR 결과가 없을 때 기본적으로 제공할 더미 메뉴."""

    digest = hashlib.sha256(base_key.encode("utf-8", errors="ignore")).hexdigest()[:6]
    return _ensure_menu_ids(
        [
            MenuText(id=f"{digest}-1", name="시그니처 메뉴", description="추천 인기 메뉴"),
            MenuText(id=f"{digest}-2", name="가벼운 식사 세트", description="부담 없는 한 끼"),
            MenuText(id=f"{digest}-3", name="든든한 단백질 플레이트", description="단백질 보충용"),
        ]
    )


def build_menus_from_store_link(req: StoreLinkAnalysisRequest) -> List[MenuText]:
    """
    가게 링크 기반으로 메뉴 목록을 확보한다.

    1) 배달앱 크롤러(yogiyo) 실행을 시도한다.
    2) 모두 실패하면 URL 해시 기반의 더미 메뉴를 반환한다.
    """

    crawled = menus_from_store_link(req)
    if crawled:
        return _ensure_menu_ids(crawled, prefix="store")

    return _fallback_menus(req.store_url)


def build_menus_from_cart_image(req: CartImageAnalysisRequest) -> List[MenuText]:
    """
    장바구니 캡처 기반으로 메뉴 목록을 확보한다.

    - OCR 파이프라인을 통해 텍스트를 추출 후 메뉴 후보를 만든다.
    - 실패 시 기본 메뉴를 반환한다.
    """

    import sys
    print(f"[Entry] build_menus_from_cart_image 시작: capture_id={req.capture_id}, image_url={'있음' if req.image_url else '없음'}", file=sys.stderr)
    
    # 항상 OCR을 통해 메뉴를 추출한다.
    ocr_menus = menus_from_cart_image(req)
    if ocr_menus:
        print(f"[Entry] OCR 성공: {len(ocr_menus)}개 메뉴 추출", file=sys.stderr)
        return _ensure_menu_ids(ocr_menus, prefix=req.capture_id or "cart")

    print("[Entry] OCR 실패 또는 빈 결과 → fallback 메뉴 사용", file=sys.stderr)
    base_key = req.capture_id or req.image_url or "cart-image"

    # image_base64 가 들어왔다면 해시를 안정적으로 만들기 위해 디코드만 시도한다.
    if req.image_base64:
        try:
            decoded = base64.b64decode(req.image_base64.split(",")[-1], validate=False)
            base_key = f"{base_key}-{hashlib.sha256(decoded).hexdigest()[:6]}"
        except Exception:
            pass

    return _fallback_menus(base_key)

