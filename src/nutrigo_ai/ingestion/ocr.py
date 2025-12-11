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

    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    with Image.open(io.BytesIO(img_bytes)) as image:
        image = image.convert("RGB")
        try:
            return pytesseract.image_to_string(image, lang="kor+eng")
        except Exception:
            return pytesseract.image_to_string(image)


def _extract_menu_lines(text: str) -> List[str]:
    lines: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        # 한 글자짜리 노이즈(내, 포 등) 제거
        if len(re.sub(r"\s+", "", line)) <= 1:
            continue

        lines.append(line)
    return lines

def _looks_like_price(line: str) -> bool:
    # 숫자 + '원' 이 들어가면 가격으로 본다
    return "원" in line and re.search(r"\d", line) is not None


def _parse_price(line: str) -> Optional[int]:
    m = re.search(r"([\d.,]+)\s*원", line)
    if not m:
        return None
    num = m.group(1).replace(",", "").replace(".", "")
    try:
        return int(num)
    except ValueError:
        return None


def _looks_like_menu_name(line: str) -> bool:
    """버거 세트 이름처럼 보이는지 대략 판별."""
    clean = re.sub(r"\s+", "", line)
    # 이번 스크린샷은 전부 '버거 라지세트' 형태라 이 정도 규칙이면 충분
    return ("세트" in clean) and ("버거" in clean) and re.search(r"[가-힣]", clean)


def _lines_to_menus(lines: Iterable[str]) -> List[MenuText]:
    menus: List[MenuText] = []
    lines = list(lines)
    i = 0
    idx = 1

    while i < len(lines):
        line = lines[i]

        # 메뉴명처럼 안 보이면 건너뜀
        if not _looks_like_menu_name(line):
            i += 1
            continue

        name = line
        desc_parts: List[str] = []
        price: Optional[int] = None
        j = i + 1

        # 다음 메뉴명 or 가격이 나오기 전까지를 설명으로 모으고,
        # 가격 줄을 만나면 price 로 파싱
        while j < len(lines):
            l2 = lines[j]

            if _looks_like_price(l2):
                price = _parse_price(l2)
                j += 1
                break

            if _looks_like_menu_name(l2):
                break

            desc_parts.append(l2)
            j += 1

        description = " ".join(desc_parts).strip() or ""

        menus.append(
            MenuText(
                id=f"ocr-{idx}",
                name=name,
                description=description,
                price=price,
                category_hint=None,
                option_text=None,
            )
        )
        idx += 1
        i = j

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

