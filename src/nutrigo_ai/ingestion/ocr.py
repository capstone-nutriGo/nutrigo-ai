"""장바구니 캡처 OCR 파이프라인."""

from __future__ import annotations

import base64
import io
import importlib.util
import re
from typing import Iterable, List, Optional

from nutrigo_ai.api.schemas import CartImageAnalysisRequest, MenuText


def _pillow_available() -> bool:
    return importlib.util.find_spec("PIL") is not None


def _pytesseract_available() -> bool:
    return importlib.util.find_spec("pytesseract") is not None


def _httpx_client():
    try:
        import httpx

        return httpx
    except Exception:
        return None


def _load_image_from_url(url: str):
    httpx = _httpx_client()
    if httpx is None:
        return None

    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.content


def _load_image_from_base64(encoded: str) -> bytes:
    body = encoded.split(",")[-1]
    return base64.b64decode(body, validate=False)


def _read_image_bytes(req: CartImageAnalysisRequest) -> Optional[bytes]:
    if req.image_base64:
        try:
            return _load_image_from_base64(req.image_base64)
        except Exception:
            return None
    if req.image_url:
        try:
            return _load_image_from_url(req.image_url)
        except Exception:
            return None
    return None


def _image_to_text(img_bytes: bytes) -> str:
    if not (_pillow_available() and _pytesseract_available()):
        return ""

    from PIL import Image
    import pytesseract

    with Image.open(io.BytesIO(img_bytes)) as image:
        image = image.convert("RGB")
        try:
            return pytesseract.image_to_string(image, lang="kor+eng")
        except Exception:
            return pytesseract.image_to_string(image)


def _extract_menu_lines(text: str) -> List[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # 가격 숫자 / 메뉴명 같이 있는 줄만 남긴다
        if re.search(r"\d", line) or re.search(r"[가-힣a-zA-Z]", line):
            lines.append(line)
    return lines


def _lines_to_menus(lines: Iterable[str]) -> List[MenuText]:
    menus: List[MenuText] = []
    for idx, line in enumerate(lines, start=1):
        price_matches = list(re.finditer(r"(\d[\d,]{2,})", line))
        price = None
        if price_matches:
            try:
                price = int(price_matches[-1].group(1).replace(",", ""))
            except Exception:
                price = None
        name = line
        if price_matches:
            name = line[: price_matches[0].start()].strip() or line
        menus.append(
            MenuText(
                id=f"ocr-{idx}",
                name=name,
                description="OCR 추출",  # 간단 설명
                price=price,
                category_hint=None,
                option_text=None,
            )
        )
    return menus


def menus_from_cart_image(req: CartImageAnalysisRequest) -> List[MenuText]:
    """OCR을 통해 CartImageAnalysisRequest → MenuText[]."""

    image_bytes = _read_image_bytes(req)
    if not image_bytes:
        return []

    text = _image_to_text(image_bytes)
    lines = _extract_menu_lines(text)
    menus = _lines_to_menus(lines)

    return menus

