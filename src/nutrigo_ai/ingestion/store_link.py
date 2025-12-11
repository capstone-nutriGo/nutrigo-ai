from __future__ import annotations

import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse
from typing import TYPE_CHECKING

from nutrigo_ai.api.schemas import MenuText, StoreLinkAnalysisRequest

# 요기요 호출에 쓸 기본 위치(대충 서울 시청 근처)
DEFAULT_LAT = 37.5665
DEFAULT_LNG = 126.978
DEFAULT_ADDRESS = "서울특별시 중구 세종대로"


def _is_yogiyo(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return "yogiyo" in hostname


def _extract_yogiyo_id(url: str) -> Optional[str]:
    """
    https://www.yogiyo.co.kr/mobile/#/1383754/ 이런 URL에서 1383754 뽑기.

    - path 에 있을 수도 있고
    - fragment( #/1383754/ ) 에 있을 수도 있어서 둘 다 검사
    """
    parsed = urlparse(url)

    for text in (parsed.path, parsed.fragment):
        if not text:
            continue

        # 1) / 로 잘라서 순수 숫자인 토큰 먼저 찾기
        for token in text.split("/"):
            if token.isdigit():
                return token

        # 2) 그래도 못 찾으면 정규식으로 아무 숫자 덩어리나 하나
        m = re.search(r"(\d+)", text)
        if m:
            return m.group(1)

    return None


def _yogiyo_helpers():
    """
    런타임 의존성(playwright 등) 문제로 import 가 실패할 수 있어서
    try/except 로 감싸고, 실패하면 콘솔에 이유를 찍어준다.
    """
    if TYPE_CHECKING:
        from nutrigo_ai.ingestion.sources.yogiyo import (
            fetch_store_info,
            menu_json_to_menu_texts,
        )

    try:
        from nutrigo_ai.ingestion.sources.yogiyo import (
            fetch_store_info,
            menu_json_to_menu_texts,
        )
        print("[store-link] yogiyo helpers import OK")
        return fetch_store_info, menu_json_to_menu_texts
    except Exception as e:
        # 여기서 playwright ModuleNotFoundError 같은 게 터지면 디버깅용으로 확인 가능
        print("[store-link] yogiyo helpers import FAILED:", repr(e))
        return None, None


def menus_from_store_link(req: StoreLinkAnalysisRequest) -> List[MenuText]:
    """스토어 링크를 실제 크롤링해 MenuText 리스트를 만든다."""

    print(f"[store-link] start, url={req.store_url!r}")

    if not req.store_url:
        print("[store-link] empty store_url")
        return []

    # 1) 요기요가 아니면 현재는 지원 X
    if not _is_yogiyo(req.store_url):
        print("[store-link] not a yogiyo URL → skip")
        return []

    # 2) 요기요 크롤러 함수 가져오기
    fetch_store_info, menu_json_to_menu_texts = _yogiyo_helpers()
    if not (fetch_store_info and menu_json_to_menu_texts):
        print("[store-link] yogiyo helpers unavailable")
        return []

    # 3) URL 에서 가게 ID 뽑기
    store_id = _extract_yogiyo_id(req.store_url)
    print(f"[store-link] extracted store_id={store_id!r}")
    if not store_id:
        print("[store-link] FAILED to extract store_id from URL")
        return []

    # 4) 실제 크롤링 호출
    try:
        result = fetch_store_info(
            store_id=store_id,
            address_text=DEFAULT_ADDRESS,
            lat=DEFAULT_LAT,
            lng=DEFAULT_LNG,
            order_serving_type="delivery",
            headless=True,
            pause_on_finish=False,
        )
        print("[store-link] fetch_store_info result:", bool(result))
    except Exception as e:
        # 여기서 timeout, playwright 에러 등이 찍힘
        print("[store-link] fetch_store_info ERROR:", repr(e))
        return []

    if not result:
        print("[store-link] fetch_store_info returned None/empty")
        return []

    menu_json = result.get("menu_json")
    if not isinstance(menu_json, dict):
        print("[store-link] invalid menu_json:", type(menu_json))
        return []

    print(
        "[store-link] menu_json schema:",
        menu_json.get("schema"),
        "keys:",
        list(menu_json.keys()),
    )

    try:
        menus = menu_json_to_menu_texts(menu_json)
        print(f"[store-link] parsed MenuText count={len(menus)}")
        return menus
    except Exception as e:
        print("[store-link] menu_json_to_menu_texts ERROR:", repr(e))
        return []
