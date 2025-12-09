"""배달앱 스토어 링크 크롤링 진입점."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

from typing import TYPE_CHECKING

from nutrigo_ai.api.schemas import MenuText, StoreLinkAnalysisRequest


DEFAULT_LAT = 37.5665
DEFAULT_LNG = 126.978
DEFAULT_ADDRESS = "서울특별시 중구 세종대로"


def _is_yogiyo(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return "yogiyo" in hostname


def _extract_yogiyo_id(url: str) -> Optional[str]:
    path = urlparse(url).path
    for token in path.split("/"):
        if token.isdigit():
            return token
    match = re.search(r"/(\d+)(?:/|$)", path)
    return match.group(1) if match else None


def _yogiyo_helpers():
    if TYPE_CHECKING:
        from nutrigo_ai.ingestion.sources.yogiyo import fetch_store_info, menu_json_to_menu_texts

    try:
        from nutrigo_ai.ingestion.sources.yogiyo import fetch_store_info, menu_json_to_menu_texts
    except Exception:
        return None, None
    return fetch_store_info, menu_json_to_menu_texts


def menus_from_store_link(req: StoreLinkAnalysisRequest) -> List[MenuText]:
    """스토어 링크를 실제 크롤링해 MenuText 리스트를 만든다."""

    if not req.store_url:
        return []

    if _is_yogiyo(req.store_url):
        fetch_store_info, menu_json_to_menu_texts = _yogiyo_helpers()
        if not (fetch_store_info and menu_json_to_menu_texts):
            return []

        store_id = req.store_id or _extract_yogiyo_id(req.store_url)
        if not store_id:
            return []

        try:
            result = fetch_store_info(
                store_id=store_id,
                address_text=req.address_text or DEFAULT_ADDRESS,
                lat=req.lat if req.lat is not None else DEFAULT_LAT,
                lng=req.lng if req.lng is not None else DEFAULT_LNG,
                order_serving_type=req.order_serving_type,
                headless=True,
                pause_on_finish=False,
            )
        except Exception:
            return []

        if not result:
            return []
        try:
            return menu_json_to_menu_texts(result["menu_json"])
        except Exception:
            return []

    return []

