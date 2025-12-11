"""장바구니 캡처 OCR 파이프라인."""

from __future__ import annotations

import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

import base64
import io
import importlib.util
import re
from typing import Iterable, List, Optional

from nutrigo_ai.api.schemas import CartImageAnalysisRequest, MenuText
from nutrigo_ai.core import config


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


def _boto3_client():
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        session = boto3.session.Session(region_name=config.S3_REGION)
        cfg = BotoConfig(
            s3={
                "addressing_style": "path" if config.S3_FORCE_PATH_STYLE else "virtual",
            }
        )
        return session.client(
            "s3",
            endpoint_url=config.S3_ENDPOINT,
            config=cfg,
        )
    except Exception:
        return None


def _load_image_from_url(url: str):
    httpx = _httpx_client()
    if httpx is None:
        return None

    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.content


def _load_image_from_s3(url: str) -> Optional[bytes]:
    """
    지원 형태:
      - s3://bucket/key
      - 키만 전달된 경우(default bucket 필요)
    """
    client = _boto3_client()
    if client is None:
        return None

    bucket = None
    key = None

    if url.startswith("s3://"):
        # s3://bucket/key...
        without_scheme = url[len("s3://") :]
        parts = without_scheme.split("/", 1)
        if len(parts) == 2:
            bucket, key = parts[0], parts[1]
    else:
        # http/https 아닌 경우 키로 취급
        if not url.startswith("http"):
            bucket = config.S3_BUCKET
            key = url

    if not bucket or not key:
        return None

    try:
        obj = client.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()
    except Exception:
        return None


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
        # 먼저 S3 시도 -> 실패 시 일반 URL GET
        s3_bytes = _load_image_from_s3(req.image_url)
        if s3_bytes:
            return s3_bytes
        try:
            return _load_image_from_url(req.image_url)
        except Exception:
            return None
    return None


def _preprocess_image_conservative(image: Image.Image) -> Image.Image:
    """보수적인 이미지 전처리 - 텍스트 손상 최소화."""
    from PIL import ImageEnhance
    
    # 1. RGB로 변환
    if image.mode != "RGB":
        image = image.convert("RGB")
    
    # 2. 그레이스케일로 변환
    image = image.convert("L")
    
    # 3. 이미지 크기 조정 (너무 작으면 확대)
    width, height = image.size
    min_size = 600  # 최소 크기 증가 (더 높은 해상도로 한글 인식 향상)
    
    if width < min_size or height < min_size:
        scale = max(min_size / width, min_size / height)
        new_width = int(width * scale)
        new_height = int(height * scale)
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # 4. 약한 대비 향상만 (과도한 처리는 피함)
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.2)  # 대비 1.2배만 증가
    
    return image


def _preprocess_image_aggressive(image: Image.Image) -> Image.Image:
    """공격적인 이미지 전처리 - 대비가 낮은 이미지용."""
    from PIL import ImageEnhance, ImageFilter
    import statistics
    
    # 1. RGB로 변환
    if image.mode != "RGB":
        image = image.convert("RGB")
    
    # 2. 그레이스케일로 변환
    image = image.convert("L")
    
    # 3. 이미지 크기 조정
    width, height = image.size
    min_size = 600
    
    if width < min_size or height < min_size:
        scale = max(min_size / width, min_size / height)
        new_width = int(width * scale)
        new_height = int(height * scale)
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # 4. 대비 향상
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.5)
    
    # 5. 밝기 조정
    enhancer = ImageEnhance.Brightness(image)
    pixels = list(image.getdata())
    if len(pixels) > 0:
        avg_brightness = statistics.mean(pixels)
        if avg_brightness < 100:
            image = enhancer.enhance(1.2)
        elif avg_brightness > 180:
            image = enhancer.enhance(0.9)
    
    # 6. 선명도 향상
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(1.3)
    
    return image


def _image_to_text_with_size(img_bytes: bytes) -> tuple[str, dict]:
    """OCR 텍스트와 폰트 크기 정보를 함께 반환."""
    if not (_pillow_available() and _pytesseract_available()):
        return "", {}
    
    from PIL import Image
    import pytesseract
    import sys
    
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    
    with Image.open(io.BytesIO(img_bytes)) as original_image:
        best_text = ""
        best_data = {}
        best_score = 0
        
        # 여러 전처리 방법 시도
        preprocessing_methods = [
            ("conservative", _preprocess_image_conservative),
            ("aggressive", _preprocess_image_aggressive),
        ]
        
        # 여러 OCR 설정 시도
        ocr_configs = [
            ("PSM6_KOR+ENG", "6", "kor+eng"),
            ("PSM11_KOR+ENG", "11", "kor+eng"),
            ("PSM6_KOR", "6", "kor"),
            ("PSM11_KOR", "11", "kor"),
        ]
        
        for preprocess_name, preprocess_func in preprocessing_methods:
            try:
                processed_image = preprocess_func(original_image.copy())
                
                for config_name, psm_mode, lang in ocr_configs:
                    try:
                        if lang:
                            custom_config = f'--oem 3 --psm {psm_mode} -l {lang}'
                        else:
                            custom_config = f'--oem 3 --psm {psm_mode}'
                        
                        # 텍스트 추출
                        text = pytesseract.image_to_string(processed_image, config=custom_config)
                        
                        # 데이터 추출 (폰트 크기 정보 포함)
                        try:
                            data = pytesseract.image_to_data(processed_image, config=custom_config, output_type=pytesseract.Output.DICT)
                        except Exception:
                            data = {}
                        
                        if not text:
                            continue
                        
                        has_korean = bool(re.search(r"[가-힣]", text))
                        text_length = len(text.strip())
                        meaningful_words = len([w for w in text.split() if len(w) > 2 or re.search(r"[가-힣]", w)])
                        
                        score = text_length
                        if has_korean:
                            score *= 3
                        score += meaningful_words * 10
                        
                        if score > best_score:
                            best_score = score
                            best_text = text
                            best_data = data
                            
                    except Exception:
                        continue
                        
            except Exception:
                continue
        
        if best_text:
            return best_text, best_data
        
        # 폴백
        try:
            text = pytesseract.image_to_string(original_image, lang="kor+eng")
            try:
                data = pytesseract.image_to_data(original_image, lang="kor+eng", output_type=pytesseract.Output.DICT)
            except Exception:
                data = {}
            return text, data
        except Exception:
            return pytesseract.image_to_string(original_image), {}


def _image_to_text(img_bytes: bytes) -> str:
    """여러 OCR 설정을 시도하여 최적의 결과 반환."""
    if not (_pillow_available() and _pytesseract_available()):
        return ""

    from PIL import Image
    import pytesseract
    import sys

    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    with Image.open(io.BytesIO(img_bytes)) as original_image:
        best_text = ""
        best_score = 0
        
        # 여러 전처리 방법 시도
        preprocessing_methods = [
            ("conservative", _preprocess_image_conservative),
            ("aggressive", _preprocess_image_aggressive),
        ]
        
        # 여러 OCR 설정 시도
        ocr_configs = [
            # (설명, PSM 모드, 언어)
            ("PSM6_KOR+ENG", "6", "kor+eng"),
            ("PSM11_KOR+ENG", "11", "kor+eng"),
            ("PSM6_KOR", "6", "kor"),
            ("PSM11_KOR", "11", "kor"),
            ("PSM6_ENG", "6", "eng"),
            ("PSM11_ENG", "11", "eng"),
            ("PSM6_NONE", "6", None),
            ("PSM11_NONE", "11", None),
        ]
        
        for preprocess_name, preprocess_func in preprocessing_methods:
            try:
                processed_image = preprocess_func(original_image.copy())
                
                for config_name, psm_mode, lang in ocr_configs:
                    try:
                        # 언어 설정 구성
                        if lang:
                            custom_config = f'--oem 3 --psm {psm_mode} -l {lang}'
                        else:
                            custom_config = f'--oem 3 --psm {psm_mode}'
                        
                        # OCR 실행
                        text = pytesseract.image_to_string(processed_image, config=custom_config)
                        
                        if not text:
                            continue
                        
                        # 한글 포함 여부 확인
                        has_korean = bool(re.search(r"[가-힣]", text))
                        # 텍스트 길이 확인
                        text_length = len(text.strip())
                        # 의미 있는 단어 확인 (한글 또는 긴 영어 단어)
                        meaningful_words = len([w for w in text.split() if len(w) > 2 or re.search(r"[가-힣]", w)])
                        
                        # 점수 계산 (한글이 있으면 높은 점수)
                        score = text_length
                        if has_korean:
                            score *= 3  # 한글이 있으면 3배 가중치
                        score += meaningful_words * 10
                        
                        print(f"[OCR] 시도: {preprocess_name} + {config_name} -> 점수: {score}, 길이: {text_length}, 한글: {has_korean}", file=sys.stderr)
                        
                        # 최고 점수 업데이트
                        if score > best_score:
                            best_score = score
                            best_text = text
                            
                    except Exception as e:
                        # 특정 설정 실패 시 계속 진행
                        continue
                        
            except Exception as e:
                # 전처리 실패 시 계속 진행
                continue
        
        # 최고 결과 반환
        if best_text:
            print(f"[OCR] 최종 선택: 점수 {best_score}, 길이 {len(best_text.strip())}", file=sys.stderr)
            return best_text
        
        # 모든 시도 실패 시 원본 이미지로 기본 OCR 시도
        try:
            return pytesseract.image_to_string(original_image, lang="kor+eng")
        except Exception:
            try:
                return pytesseract.image_to_string(original_image, lang="kor")
            except Exception:
                return pytesseract.image_to_string(original_image)


def _extract_menu_lines(text: str, large_font_lines: set[str] = None) -> List[str]:
    if large_font_lines is None:
        large_font_lines = set()
    
    lines: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        # 한 글자짜리 노이즈(내, 포 등) 제거
        if len(re.sub(r"\s+", "", line)) <= 1:
            continue
        
        # 큰 글씨로 인식된 라인은 우선적으로 메뉴명으로 간주
        is_large_font = line in large_font_lines or any(large_line in line or line in large_line for large_line in large_font_lines)
        if is_large_font:
            # 큰 글씨 라인이라도 설명 문구 키워드가 많으면 제외
            description_keywords = ["제공됩니다", "조리되며", "기준으로", "생각나는", "구현", "특제소스", "요청사항", "수정", "선택 가능", "단계", "매운맛", "선택", "싱싱한", "해물과", "불맛의", "풍미까지", "더해진"]
            description_count = sum(1 for keyword in description_keywords if keyword in line)
            
            # 설명 키워드가 2개 이상이거나 너무 긴 줄(50자 이상)이면 설명 문구로 간주하고 건너뛰기
            if description_count >= 2 or len(line) > 50:
                continue
            
            # 큰 글씨 라인은 필터링을 완화하여 추가
            lines.append(line)
            continue
        
        # 숫자로 시작하는 설명 문구 제거 (예: "2. 목살은...")
        if re.match(r"^\d+[\.\)]\s*", line):
            continue
        
        # 너무 긴 줄은 설명일 가능성이 높음 (50자 이상)
        # 하지만 메뉴 키워드가 포함되어 있으면 유지
        menu_keywords_in_filter = ["지존", "짬뽕", "수제비", "순두부", "쌀국수", "면", "밥", "국", "찜", "찌개", "탕"]
        has_menu_keyword = any(keyword in line for keyword in menu_keywords_in_filter)
        if len(line) > 50 and not has_menu_keyword:
            continue
        
        # "제공됩니다", "조리되며", "기준으로" 같은 설명 문구 제거
        # 하지만 메뉴 키워드가 포함되어 있으면 유지
        description_keywords = ["제공됩니다", "조리되며", "기준으로", "생각나는", "구현", "특제소스", "요청사항", "수정", "선택 가능", "단계"]
        if any(keyword in line for keyword in description_keywords) and not has_menu_keyword:
            continue
        
        # "소(", "중(", "대(" 같은 사이즈 정보만 있는 줄 제거
        if re.match(r"^[소중대특]\s*[\(\(]", line) and len(line) < 20:
            continue
        
        # 사이드 메뉴 패턴 제거 (예: "치킨무 + 계란찜")
        if re.search(r"\+", line) and not re.search(r"품은|찜|국|밥|면", line):
            continue
        
        # 영어만 있는 짧은 줄 제거 (예: "rz", "aS", "BA", "ola")
        if re.match(r"^[A-Za-z\s]{1,4}$", line):
            continue
        
        # "없음", "단계" 같은 단일 단어 제거
        if line in ["없음", "단계", "더", "선택", "가능", "매", "운맛", "맛"]:
            continue
        
        # 숫자와 특수문자만 있는 줄 제거 (예: "~4", "000-2!")
        if re.match(r"^[\d~\-!()\s]+$", line):
            continue
        
        # 영어와 숫자만 있는 줄 제거 (예: "rz", "aS", "BA", "ola", "KI")
        if re.match(r"^[A-Za-z0-9\s]+$", line) and len(line) <= 5:
            continue

        lines.append(line)
    return lines

def _looks_like_price(line: str) -> bool:
    # 숫자 + '원' 이 들어가면 가격으로 본다
    if "원" in line and re.search(r"\d", line) is not None:
        return True
    # "원"이 없어도 숫자와 쉼표 패턴이 있으면 가격으로 간주 (예: "13,0002" -> "13,000원")
    if re.search(r"[\d,]{4,}", line):  # 4자리 이상의 숫자+쉼표 패턴
        return True
    return False


def _parse_price(line: str) -> Optional[int]:
    # "원"이 포함된 경우
    m = re.search(r"([\d.,]+)\s*원", line)
    if m:
        num = m.group(1).replace(",", "").replace(".", "")
        try:
            return int(num)
        except ValueError:
            pass
    
    # "원"이 없지만 숫자 패턴이 있는 경우 (예: "13,0002")
    m = re.search(r"([\d,]+)", line)
    if m:
        num_str = m.group(1).replace(",", "")
        # 마지막 숫자가 잘못 인식된 경우 제거 (예: "130002" -> "13000")
        # 4자리 이상의 숫자에서 마지막 1-2자리가 이상하면 제거
        if len(num_str) >= 5:
            # 마지막 1-2자리가 0-9 사이의 작은 숫자면 제거
            if num_str[-1] in "0123456789" and int(num_str[-1]) < 5:
                num_str = num_str[:-1]
        try:
            price = int(num_str)
            # 가격이 합리적인 범위인지 확인 (1,000원 ~ 1,000,000원)
            if 1000 <= price <= 1000000:
                return price
        except ValueError:
            pass
    
    return None


def _looks_like_menu_name(line: str) -> bool:
    """메뉴 이름처럼 보이는지 대략 판별."""
    clean = line.strip()
    if not clean or len(clean) < 2:
        return False
    
    # 너무 긴 줄은 메뉴 이름이 아닐 가능성이 높음 (40자 이상)
    # 하지만 강한 메뉴 키워드가 포함되어 있으면 유지
    strong_menu_keywords_for_length = [
        "지존", "짬뽕", "수제비", "순두부", "쌀국수", "일품", "깐풍", "투움바", "나폴리", "윙콤보"
    ]
    has_strong_keyword = any(keyword in clean for keyword in strong_menu_keywords_for_length)
    if len(clean) > 40 and not has_strong_keyword:
        return False
    
    # 숫자만 있는 줄은 제외
    if re.match(r"^[\d.,\s]+$", clean):
        return False
    
    # 태그 제거 (예: [[위생등급매우우수]], [[줍고배고플땐]])
    clean = re.sub(r"\[\[.*?\]\]", "", clean).strip()
    
    # "메뉴 :" 같은 패턴 제거 (옵션 설명)
    if re.search(r"메뉴\s*[:：]", clean):
        return False
    
    # "소(", "중(", "대(" 같은 사이즈 정보만 있는 줄 제거
    if re.match(r"^[소중대특]\s*[\(\(]", clean):
        return False
    
    # 한글이 포함되어 있어야 함
    has_korean = bool(re.search(r"[가-힣]", clean))
    if not has_korean:
        return False
    
    # 메뉴 관련 키워드가 있는 경우 (더 많은 키워드 추가)
    menu_keywords = [
        "찜", "국", "밥", "면", "튀김", "치킨", "피자", "스테이크", "샐러드", "파스타", "리조또", "돈까스", 
        "우동", "라면", "떡볶이", "김치", "비빔밥", "덮밥", "볶음밥", "세트", "버거", "품은", "스팸", 
        "삼겹", "목살", "수제비", "순두부", "된장", "김치찌개", "부대찌개", "해물", "삼계탕", "갈비", 
        "불고기", "제육", "닭갈비", "족발", "보쌈", "냉면", "물냉면", "비빔냉면", "막국수", "칼국수",
        "짜장면", "간짜장", "쌈붕", "짬뽕", "볶음밥", "짜장밥", "짬뽕밥", "탕수육", "깐풍기", "깐풍", "양장피", "마파두부",
        "마라탕", "마라샹궈", "훠궈", "샤브샤브", "초밥", "회", "사시미", "연어", "참치", "장어",
        "지존", "쌀국수",  # 짬뽕 관련 키워드
        "일품", "윙", "콤보", "윙콤보", "투움바", "나폴리", "순", "다리", "살",  # 치킨 메뉴 키워드
        "프리미엄", "스타일",  # 프리미엄 메뉴 키워드
        "담다", "연덮", "세트", "연덮세트", "담다연덮세트"  # 초밥/연어 관련 키워드
    ]
    has_menu_keyword = any(keyword in clean for keyword in menu_keywords)
    
    # 사이드 메뉴 패턴 제외 (예: "치킨무 + 계란찜")
    # 단, "+"로 시작하는 메뉴명은 허용 (예: "+연어초밥")
    if re.search(r"\+", clean) and not (clean.strip().startswith("+") or re.search(r"품은|찜|국|밥|면|초밥", clean)):
        return False
    
    # 설명 문구 키워드가 있으면 제외 (하지만 메뉴 키워드가 강하면 예외)
    description_keywords = [
        "제공", "조리", "기준", "생각", "구현", "소스", "요청", "수정", "특별", "즐기", "끌어안", "묵은지", "호수", "선택 가능", "단계",
        "스타일", "프리미엄", "100%", "국내산", "즐겨보세요", "만나보세요", "더해진", "터치", "완벽해진", "족촉한", "촉촉한",
        "셰프", "기술", "탄생", "매콤한", "향취고추", "볶음땅콩", "알러지", "주의", "땅콩"
    ]
    has_description_keyword = any(keyword in clean for keyword in description_keywords)
    
    # 가격 패턴이 포함된 경우 제외 (가격은 별도로 처리)
    has_price_pattern = bool(re.search(r"[\d.,]+\s*원", clean))
    
    # 너무 짧은 단어만 있는 경우 제외 (2자 이하)
    if len(re.sub(r"\s+", "", clean)) <= 2:
        return False
    
    # 영어만 있는 경우 제외 (메뉴는 한글이 있어야 함)
    if not has_korean and re.match(r"^[A-Za-z\s]+$", clean):
        return False
    
    # 메뉴 키워드가 강하면 설명 키워드가 있어도 인식 (예: "부드러운 순두부")
    strong_menu_keywords = [
        "순두부", "수제비", "면", "국", "밥", "찜", "찌개", "탕", "짬뽕", "지존", "쌀국수", 
        "짜장면", "간짜장", "쌈붕", "볶음밥", "깐풍", "깐풍기", "일품", "윙콤보", "투움바", 
        "나폴리", "치킨", "순", "다리", "살",
        "담다", "연덮", "연덮세트", "담다연덮세트", "연어초밥", "초밥"  # 초밥/연어 관련 키워드
    ]
    has_strong_menu_keyword = any(keyword in clean for keyword in strong_menu_keywords)
    
    # 여러 메뉴 키워드가 포함된 경우 (예: "짜장면            간짜장           쌈붕             볶음밥")
    # 이 경우는 한 줄에 여러 메뉴명이 있는 것으로 간주하고, _split_multiple_menus에서 처리
    menu_keyword_count = sum(1 for keyword in menu_keywords if keyword in clean)
    
    # 설명 키워드가 많으면 (3개 이상) 메뉴가 아닌 설명 문구로 간주
    # 단, 강한 메뉴 키워드가 있으면 2개까지 허용
    description_keyword_count = sum(1 for keyword in description_keywords if keyword in clean)
    if description_keyword_count >= 3:
        return False
    if description_keyword_count >= 2 and not has_strong_menu_keyword:
        return False
    
    # 메뉴 키워드가 있고, (설명 키워드가 없거나 강한 메뉴 키워드가 있고), 가격 패턴이 없는 경우 메뉴로 간주
    # 또는 여러 메뉴 키워드가 있는 경우도 메뉴로 간주 (한 줄에 여러 메뉴명이 있을 수 있음)
    return (has_menu_keyword and (not has_description_keyword or has_strong_menu_keyword) and not has_price_pattern) or (menu_keyword_count >= 2)


def _split_multiple_menus(line: str) -> List[str]:
    """한 줄에 여러 메뉴명이 있는 경우 분리 (예: "짜장면            간짜장           쌈붕             볶음밥")"""
    # 여러 메뉴명이 공백으로 구분되어 있는 경우 분리
    # 메뉴 키워드가 포함된 단어들을 찾아서 분리
    menu_keywords = [
        "짜장면", "간짜장", "쌈붕", "볶음밥", "짬뽕", "수제비", "순두부", "쌀국수",
        "면", "밥", "국", "찜", "탕", "찌개", "튀김", "치킨", "피자", "스테이크",
        "샐러드", "파스타", "리조또", "돈까스", "우동", "라면", "떡볶이", "김치",
        "비빔밥", "덮밥", "세트", "버거", "냉면", "물냉면", "비빔냉면", "막국수",
        "칼국수", "탕수육", "깐풍기", "깐풍", "양장피", "마파두부", "지존",
        "일품", "윙", "콤보", "윙콤보", "투움바", "나폴리", "순", "다리", "살",
        "담다", "연덮", "연덮세트", "담다연덮세트", "연어초밥"  # 초밥/연어 관련 키워드
    ]
    
    # 공백이 3개 이상 연속으로 있는 경우를 기준으로 분리
    parts = re.split(r"\s{3,}", line.strip())
    menu_parts = []
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 메뉴 키워드가 포함되어 있으면 메뉴로 간주
        if any(keyword in part for keyword in menu_keywords):
            # 한글과 숫자, 기본 특수문자만 남기고 정리
            cleaned = re.sub(r"[^\w\s가-힣]", "", part).strip()
            # 설명 문구 필터링 (설명 키워드가 많으면 제외)
            description_keywords = [
                "스타일", "프리미엄", "100%", "국내산", "즐겨보세요", "만나보세요", "더해진", "터치", "완벽해진", "족촉한", "촉촉한",
                "셰프", "기술", "탄생", "매콤한", "향취고추", "볶음땅콩", "알러지", "주의", "땅콩"
            ]
            description_count = sum(1 for keyword in description_keywords if keyword in cleaned)
            if description_count >= 2:
                continue
            if len(cleaned) >= 2:
                menu_parts.append(cleaned)
    
    return menu_parts if menu_parts else [line]


def _lines_to_menus(lines: Iterable[str]) -> List[MenuText]:
    """병합된 라인들을 MenuText로 변환. 병합은 이미 완료된 상태여야 함."""
    menus: List[MenuText] = []
    lines = list(lines)
    i = 0
    idx = 1

    while i < len(lines):
        line = lines[i]
        
        # 먼저 메뉴명 정리 (OCR 오타 보정, 불필요한 문자 제거 등)
        cleaned_line = line.strip()
        # 한글 뒤의 긴 공백과 영어/특수문자 제거 (예: "일품깐풍                                 pai" → "일품깐풍")
        if re.search(r"[가-힣]", cleaned_line):
            cleaned_line = re.sub(r"([가-힣]+)\s{3,}[a-zA-Z\s]*$", r"\1", cleaned_line)
            cleaned_line = re.sub(r"([가-힣]+)\s+[a-zA-Z]+$", r"\1", cleaned_line)
        cleaned_line = cleaned_line.strip()

        # 한 줄에 여러 메뉴명이 있는 경우 분리
        menu_parts = _split_multiple_menus(cleaned_line)
        
        # 분리된 메뉴명이 여러 개인 경우 각각 처리
        if len(menu_parts) > 1:
            for menu_part in menu_parts:
                if _looks_like_menu_name(menu_part):
                    # 세트 메뉴명 정리 (예: "1정식 짜장짱  탕수육" → "1정식")
                    cleaned_name = menu_part
                    set_menu_match = re.search(r"(\d+)\s*정식", cleaned_name)
                    if set_menu_match:
                        set_number = set_menu_match.group(1)
                        cleaned_name = f"{set_number}정식"
                    
                    # 가격 찾기 (원래 라인 주변에서, 세트 메뉴는 더 넓은 범위)
                    is_set_menu = bool(re.search(r"\d+정식", cleaned_name))
                    price: Optional[int] = None
                    for j in range(i, min(i + (5 if is_set_menu else 3), len(lines))):
                        if _looks_like_price(lines[j]):
                            price = _parse_price(lines[j])
                            break
                    
                    menus.append(
                        MenuText(
                            id=f"ocr-{idx}",
                            name=cleaned_name,
                            description="",
                            price=price,
                            category_hint=None,
                            option_text=None,
                        )
                    )
                    idx += 1
            i += 1
            continue

        # 메뉴명처럼 안 보이면 건너뜀 (정리된 라인으로 체크)
        if not _looks_like_menu_name(cleaned_line):
            # 긴 설명 문구에서 메뉴명 추출 시도
            if len(cleaned_line) > 30:
                extracted_menu = _extract_menu_from_description(cleaned_line)
                if extracted_menu:
                    # 추출된 메뉴명으로 메뉴 생성
                    price: Optional[int] = None
                    # 다음 몇 줄에서 가격 찾기
                    for j in range(i + 1, min(i + 6, len(lines))):
                        if _looks_like_price(lines[j]):
                            price = _parse_price(lines[j])
                            break
                    
                    menus.append(
                        MenuText(
                            id=f"ocr-{idx}",
                            name=extracted_menu,
                            description="",
                            price=price,
                            category_hint=None,
                            option_text=None,
                        )
                    )
                    idx += 1
                    i += 1
                    continue
            
            i += 1
            continue

        # 태그 제거 (예: [[위생등급매우우수]])
        # 정리된 라인 사용 (이미 정리되었으므로 line 대신 cleaned_line 사용)
        name = re.sub(r"\[\[.*?\]\]", "", cleaned_line).strip()
        
        # OCR 오타 보정
        name = re.sub(r"짱봉", "짬뽕", name)  # "짱봉" → "짬뽕"
        name = re.sub(r"짱\s*봉", "짬뽕", name)  # "짱 봉" → "짬뽕"
        
        # "+"로 시작하는 메뉴명 처리 (예: "+연어초밥4ㅁ" → "연어초밥")
        name = re.sub(r"^\+\s*", "", name)  # "+연어초밥" → "연어초밥"
        
        # 괄호 앞뒤 공백 정리 (예: "순(다리)살" → "순(다리)살" 유지)
        # 또는 "담다연덮세트 (연덮" → "담다연덮세트"
        # 괄호가 포함된 메뉴명은 괄호를 유지하되, 불필요한 공백만 제거
        # 괄호 뒤에 가격이나 추가 설명이 있으면 괄호 부분 제거
        name = re.sub(r"\s*\([^)]*$", "", name)  # "담다연덮세트 (연덮" → "담다연덮세트"
        name = re.sub(r"\s*\(\s*", "(", name)  # "순 (다리)" → "순(다리)"
        name = re.sub(r"\s*\)\s*", ")", name)  # "순(다리 )" → "순(다리)"
        
        # 끝의 숫자와 특수문자 제거 (예: "연어초밥4ㅁ" → "연어초밥")
        name = re.sub(r"[\dㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ]+$", "", name)
        
        # 메뉴명 끝의 불필요한 영어나 특수문자 제거 (예: "일품깐풍                                 pai" → "일품깐풍")
        # 또는 "순(다리)살 나폴리 투움바                                                 oe" → "순(다리)살 나폴리 투움바"
        # 한글이 포함된 경우, 한글 뒤의 긴 공백과 영어/특수문자 제거
        if re.search(r"[가-힣]", name):
            # 한글 뒤의 긴 공백(3개 이상)과 영어/특수문자 제거
            name = re.sub(r"([가-힣]+)\s{3,}[a-zA-Z\s]*$", r"\1", name)
            name = re.sub(r"([가-힣]+)\s+[a-zA-Z]+$", r"\1", name)  # "일품깐풍 pai" → "일품깐풍"
            # "나폴리 투움바                                                 oe" 같은 경우 처리
            name = re.sub(r"([가-힣]+)\s{3,}[a-zA-Z\s]*$", r"\1", name)
            # 숫자와 특수문자만 있는 끝 부분 제거 (예: "0000.")
            name = re.sub(r"\s+[\d.,]+\s*\.?\s*$", "", name)
            # 끝의 숫자와 한글 자음 제거 (예: "연어초밥4ㅁ" → "연어초밥")
            name = re.sub(r"[\dㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ]+$", "", name)
        
        # 세트 메뉴명 정리 (예: "1정식 (짜장 +짱봉 + 깐풍기 )" → "1정식")
        # 또는 "4정식 ( 짜장 +짱봉 + 깐풍기 )" → "4정식"
        # 또는 "1정식 짜장짱  탕수육" → "1정식"
        # 또는 "3 2정식" → "2정식" (OCR 오류로 앞에 숫자가 붙은 경우)
        set_menu_match = re.search(r"(\d+)\s*정식", name)
        if set_menu_match:
            # 세트 메뉴명은 "N정식" 형태로 정리
            set_number = set_menu_match.group(1)
            # "1정식" 뒤에 다른 텍스트가 있으면 제거
            name = f"{set_number}정식"
        else:
            # 앞뒤 이상한 문자 제거 (예: "(HCE SENS4", "x" 등)
            name = re.sub(r"^[\(\)\[\]xX\s]+", "", name)  # 앞의 괄호, 대괄호, x 제거
            name = re.sub(r"[\(\)\[\]xX\s]+$", "", name)  # 뒤의 괄호, 대괄호, x 제거
            # 영어나 숫자로 시작하는 이상한 문자 제거 (예: "HCE SENS4")
            name = re.sub(r"^[A-Z0-9\s]+\s+", "", name)  # 앞의 영어/숫자 제거
            name = name.strip()
        
        # 메뉴명이 너무 짧거나 비어있으면 제외
        if len(name) < 2:
            i += 1
            continue
        
        # 사이드 메뉴 패턴 제거 (예: "치킨무 + 계란찜")
        if re.search(r"\+", name) and not re.search(r"품은|찜|국|밥|면", name):
            i += 1
            continue
        
        desc_parts: List[str] = []
        price: Optional[int] = None
        j = i + 1

        # 다음 메뉴명 or 가격이 나오기 전까지를 설명으로 모으고,
        # 가격 줄을 만나면 price 로 파싱
        # 세트 메뉴의 경우 가격을 더 넓은 범위에서 찾기 (1-5줄)
        is_set_menu = bool(re.search(r"\d+정식", name))
        max_price_search = min(j + (5 if is_set_menu else 3), len(lines))
        while j < max_price_search:
            l2 = lines[j]

            if _looks_like_price(l2):
                price = _parse_price(l2)
                j += 1
                break

            if _looks_like_menu_name(l2):
                break

            desc_parts.append(l2)
            j += 1
        
        # 가격을 찾지 못했으면 현재 메뉴명에서도 찾아보기
        if price is None:
            if _looks_like_price(line):
                price = _parse_price(line)
        
        # 가격을 찾지 못했으면 뒤에서 가격 찾기 (최대 5줄 뒤까지)
        if price is None:
            for k in range(i + 1, min(i + 6, len(lines))):
                if _looks_like_price(lines[k]):
                    price = _parse_price(lines[k])
                    break

        description = " ".join(desc_parts).strip() or ""
        
        # 설명에서 불필요한 부분 제거
        if description:
            # "부드러운", "들어있는" 같은 형용사 제거하고 메뉴명만 남기기
            description = re.sub(r"^(부드러운|들어있는|맛있는|신선한|따뜻한|차가운)\s+", "", description)

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


def _extract_menu_from_description(description: str) -> Optional[str]:
    """긴 설명 문구에서 실제 메뉴명 추출 (키워드 기반 생성이 아닌 실제 텍스트에서 추출)."""
    # 실제 텍스트에서 메뉴명 패턴 찾기 (예: "지존짬뽕", "지존짬뽕밥" 등)
    # 완전한 메뉴명 패턴 우선 매칭
    complete_menu_patterns = [
        r"지존\s*짬뽕\s*밥",
        r"지존\s*짬뽕\s*면",
        r"지존\s*짬뽕",
        r"수제비\s*짬뽕",
        r"순두부\s*짬뽕\s*밥",
        r"순두부\s*짬뽕\s*면",
        r"순두부\s*짬뽕",
        r"쌀국수\s*짬뽕",
    ]
    
    for pattern in complete_menu_patterns:
        match = re.search(pattern, description)
        if match:
            # 실제 텍스트에서 찾은 부분을 정리하여 반환
            found_text = match.group(0).strip()
            # 공백 제거하여 메뉴명 생성
            menu_name = re.sub(r"\s+", "", found_text)
            return menu_name
    
    # 완전한 패턴이 없으면 키워드만 찾기 (하지만 기본 형태로만)
    # "지존"만 있으면 "지존짬뽕"으로 추정하지 않고 None 반환
    # 실제로 OCR 텍스트에 "지존짬뽕" 같은 완전한 형태가 있어야 함
    
    return None


def _merge_broken_menu_lines(lines: List[str]) -> List[str]:
    """OCR로 인해 분리된 메뉴명을 합치는 함수."""
    if not lines:
        return lines
    
    merged: List[str] = []
    i = 0
    
    menu_keywords = ["수제비", "순두부", "면", "국", "밥", "찜", "찌개", "탕", "품은", "짬뽕", "지존", "쌀국수"]
    skip_words = ["매", "운맛", "맛", "단계", "선택", "가능", "없음", "~4", "~4단계"]
    
    while i < len(lines):
        current = lines[i]
        
        # "들어있는 부드" 같은 특수 케이스 처리
        if ("부드" in current or "들어있는" in current) and i + 1 < len(lines):
            next_line = lines[i + 1]
            if "러운" in next_line and "순두부" in next_line:
                # 두 라인을 병합
                combined = f"{current} {next_line}".strip()
                combined = re.sub(r"들어있는\s+부드\s+러운", "부드러운", combined)
                combined = re.sub(r"부드\s+러운", "부드러운", combined)
                merged.append(combined)
                i += 2
                continue
        
        # 현재 라인이 메뉴 키워드를 포함하고 있으면
        has_keyword = any(keyword in current for keyword in menu_keywords)
        
        if has_keyword:
            parts = [current]
            j = i + 1
            skip_count = 0  # 건너뛴 횟수 추적
            
            # 다음 몇 줄을 확인해서 메뉴명의 일부인지 확인 (최대 5줄)
            while j < len(lines) and j < i + 6:
                next_line = lines[j]
                
                # 가격이면 중단
                if _looks_like_price(next_line):
                    break
                
                # 건너뛸 단어면 건너뛰기
                if next_line in skip_words or any(skip in next_line for skip in skip_words):
                    skip_count += 1
                    j += 1
                    continue
                
                # 영어만 있거나 숫자/특수문자만 있으면 건너뛰기
                if re.match(r"^[A-Za-z\s]+$", next_line) or re.match(r"^[\d~\-!()\s]+$", next_line):
                    j += 1
                    continue
                
                # 한 글자짜리 노이즈 제거
                if len(re.sub(r"\s+", "", next_line)) <= 1:
                    j += 1
                    continue
                
                # 메뉴 키워드를 포함하는 경우만 병합
                if any(keyword in next_line for keyword in menu_keywords):
                    parts.append(next_line)
                    j += 1
                    skip_count = 0  # 병합했으므로 skip_count 리셋
                # 짧은 한글 단어인 경우 (2-3자), 현재 메뉴와 관련이 있어 보이면 병합
                # 단, "면"만 단독으로 있으면 병합하지 않음 (잘못된 병합 방지)
                elif len(next_line) <= 3 and re.search(r"[가-힣]", next_line) and skip_count <= 1:
                    # "밥", "국", "탕", "찜", "찌개" 같은 짧은 메뉴 관련 단어만 병합
                    # "면"은 제외 (예: "지존" + "면" → "지존짬뽕면" 같은 잘못된 병합 방지)
                    if any(kw in next_line for kw in ["밥", "국", "탕", "찜", "찌개"]):
                        parts.append(next_line)
                        j += 1
                        skip_count = 0
                    else:
                        break
                else:
                    break
            
            # 병합된 메뉴명 생성
            merged_name = " ".join(parts).strip()
            # "부드" + "러운 순두부" → "부드러운 순두부"로 정리
            merged_name = re.sub(r"부드\s+러운", "부드러운", merged_name)
            merged_name = re.sub(r"들어있는\s+부드", "부드러운", merged_name)
            # "수제비 매 면" → "수제비짬뽕"으로 정리 (OCR 오류 보정)
            merged_name = re.sub(r"수제비\s+매\s+면", "수제비짬뽕", merged_name)
            # "지존" + "짬뽕" → "지존짬뽕" (명확히 "짬뽕"이 함께 있는 경우만)
            merged_name = re.sub(r"지존\s+짬뽕", "지존짬뽕", merged_name)
            # "순두부" + "짬뽕" → "순두부짬뽕" (명확히 "짬뽕"이 함께 있는 경우만)
            merged_name = re.sub(r"순두부\s+짬뽕", "순두부짬뽕", merged_name)
            # "쌀국수" + "짬뽕" → "쌀국수짬뽕" (명확히 "짬뽕"이 함께 있는 경우만)
            merged_name = re.sub(r"쌀국수\s+짬뽕", "쌀국수짬뽕", merged_name)
            # "면"만 단독으로 있으면 병합하지 않음 (잘못된 병합 방지)
            
            merged.append(merged_name)
            i = j
        else:
            merged.append(current)
            i += 1
    
    # 추가 정리: "들어있는 부드" + "러운 순두부" 같은 분리된 패턴 병합
    final_merged: List[str] = []
    i = 0
    while i < len(merged):
        current = merged[i]
        
        # "들어있는 부드" 또는 "부드"로 끝나는 라인
        if ("부드" in current or "들어있는" in current) and i + 1 < len(merged):
            next_line = merged[i + 1]
            # 다음 라인이 "러운 순두부" 또는 "순두부"를 포함하면 병합
            if "러운" in next_line and "순두부" in next_line:
                combined = f"{current} {next_line}".strip()
                combined = re.sub(r"들어있는\s+부드\s+러운", "부드러운", combined)
                combined = re.sub(r"부드\s+러운", "부드러운", combined)
                final_merged.append(combined)
                i += 2
                continue
        
        final_merged.append(current)
        i += 1
    
    return final_merged


def menus_from_cart_image(req: CartImageAnalysisRequest) -> List[MenuText]:
    """OCR을 통해 CartImageAnalysisRequest → MenuText[]."""

    import sys
    print(f"[OCR] 이미지 다운로드 시작: image_url={req.image_url[:100] if req.image_url else None}, image_base64={'있음' if req.image_base64 else '없음'}", file=sys.stderr)
    
    image_bytes = _read_image_bytes(req)
    if not image_bytes:
        print("[OCR] 이미지 다운로드 실패 또는 이미지 바이트가 없음", file=sys.stderr)
        return []
    
    print(f"[OCR] 이미지 다운로드 성공: 크기={len(image_bytes)} bytes", file=sys.stderr)

    # 폰트 크기 정보와 함께 OCR 수행
    text, font_data = _image_to_text_with_size(image_bytes)
    print(f"[OCR] OCR 텍스트 추출: 길이={len(text)} 문자, 내용={text[:200] if text else '(비어있음)'}", file=sys.stderr)
    
    # 폰트 크기 정보를 활용하여 큰 글씨를 메뉴명으로 우선 인식
    large_font_lines = set()
    if font_data and 'height' in font_data and len(font_data['height']) > 0:
        # 높이 값들의 중간값 계산
        heights = [h for h in font_data['height'] if h > 0]
        if heights:
            median_height = sorted(heights)[len(heights) // 2]
            large_font_threshold = median_height * 1.3  # 중간값의 1.3배 이상이면 큰 글씨
            print(f"[OCR] 폰트 크기 분석: 중간값={median_height}, 큰 글씨 기준={large_font_threshold:.1f}", file=sys.stderr)
            
            # 큰 글씨 단어들을 추출하여 라인별로 그룹화
            large_font_words = []
            for i, word in enumerate(font_data.get('text', [])):
                if word and word.strip() and i < len(font_data['height']):
                    height = font_data['height'][i]
                    if height >= large_font_threshold:
                        large_font_words.append(word.strip())
            
            # 큰 글씨 단어들을 텍스트 라인과 매칭
            text_lines = text.splitlines()
            for line in text_lines:
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                # 라인에 큰 글씨 단어가 포함되어 있으면 큰 글씨 라인으로 간주
                for word in large_font_words:
                    if word in line_stripped:
                        large_font_lines.add(line_stripped)
                        break
            
            if large_font_lines:
                print(f"[OCR] 큰 글씨로 인식된 라인: {list(large_font_lines)[:5]}", file=sys.stderr)
    
    lines = _extract_menu_lines(text, large_font_lines)
    print(f"[OCR] 메뉴 라인 추출: {len(lines)}개", file=sys.stderr)
    if lines:
        print(f"[OCR] 첫 5개 라인: {lines[:5]}", file=sys.stderr)
    
    # 분리된 메뉴명 합치기
    lines = _merge_broken_menu_lines(lines)
    print(f"[OCR] 메뉴명 병합 후: {len(lines)}개", file=sys.stderr)
    
    menus = _lines_to_menus(lines)
    
    # OCR 텍스트 전체에서 실제 메뉴명 패턴 찾기
    if len(menus) == 0:
        print(f"[OCR] 라인 기반 파싱 실패, 텍스트 전체에서 메뉴명 패턴 검색 시도", file=sys.stderr)
        
        # 1단계: 완전한 메뉴명 패턴 찾기 (가장 정확함)
        complete_menu_patterns = [
            (r"지존\s*짬뽕\s*밥", "지존짬뽕밥"),
            (r"지존\s*짬뽕\s*면", "지존짬뽕면"),
            (r"지존\s*짬뽕", "지존짬뽕"),
            (r"수제비\s*짬뽕", "수제비짬뽕"),
            (r"순두부\s*짬뽕\s*밥", "순두부짬뽕밥"),
            (r"순두부\s*짬뽕\s*면", "순두부짬뽕면"),
            (r"순두부\s*짬뽕", "순두부짬뽕"),
            (r"쌀국수\s*짬뽕", "쌀국수짬뽕"),
        ]
        
        found_menus = set()
        for pattern, menu_name in complete_menu_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                if menu_name not in found_menus:
                    found_menus.add(menu_name)
                    # 가격 찾기
                    price: Optional[int] = None
                    price_match = re.search(r"([\d,]+)\s*원", text)
                    if price_match:
                        price = _parse_price(price_match.group(0))
                    else:
                        price_match = re.search(r"([\d,]{4,})", text)
                        if price_match:
                            price = _parse_price(price_match.group(1))
                    
                    menus.append(
                        MenuText(
                            id=f"ocr-{len(menus) + 1}",
                            name=menu_name,
                            description="",
                            price=price,
                            category_hint=None,
                            option_text=None,
                        )
                    )
                    print(f"[OCR] 완전한 패턴으로 메뉴 발견: {menu_name} (가격: {price})", file=sys.stderr)
        
        # 2단계: 완전한 패턴이 없으면 키워드 주변 텍스트 분석으로 메뉴명 추출
        if len(menus) == 0:
            print(f"[OCR] 완전한 패턴 없음, 키워드 주변 텍스트 분석 시도", file=sys.stderr)
            
            # 강한 메뉴 키워드와 그 주변 텍스트 분석
            menu_keywords_with_context = [
                ("지존", ["짬뽕", "면", "밥"]),  # "지존" + 주변에 "짬뽕", "면", "밥"이 있으면 조합
                ("수제비", ["짬뽕", "면"]),
                ("순두부", ["짬뽕", "면", "밥"]),
                ("쌀국수", ["짬뽕"]),
            ]
            
            for keyword, context_words in menu_keywords_with_context:
                keyword_match = re.search(rf"\b{re.escape(keyword)}\b", text)
                if keyword_match:
                    keyword_pos = keyword_match.start()
                    # 키워드 주변 50자 내에서 컨텍스트 단어 찾기
                    context_start = max(0, keyword_pos - 25)
                    context_end = min(len(text), keyword_pos + len(keyword) + 25)
                    context_text = text[context_start:context_end]
                    
                    # 컨텍스트 단어가 있는지 확인
                    found_context = None
                    for ctx_word in context_words:
                        if re.search(rf"\b{re.escape(ctx_word)}\b", context_text):
                            found_context = ctx_word
                            break
                    
                    # 메뉴명 구성: 키워드 + 컨텍스트 (실제 텍스트에 둘 다 있어야 함)
                    if found_context:
                        menu_name = f"{keyword}{found_context}"
                        if menu_name not in found_menus:
                            found_menus.add(menu_name)
                            # 가격 찾기
                            price: Optional[int] = None
                            price_match = re.search(r"([\d,]+)\s*원", text)
                            if price_match:
                                price = _parse_price(price_match.group(0))
                            else:
                                price_match = re.search(r"([\d,]{4,})", text)
                                if price_match:
                                    price = _parse_price(price_match.group(1))
                            
                            menus.append(
                                MenuText(
                                    id=f"ocr-{len(menus) + 1}",
                                    name=menu_name,
                                    description="",
                                    price=price,
                                    category_hint=None,
                                    option_text=None,
                                )
                            )
                            print(f"[OCR] 키워드+컨텍스트 분석으로 메뉴 발견: {menu_name} (가격: {price})", file=sys.stderr)
    
    print(f"[OCR] 최종 메뉴 개수: {len(menus)}개", file=sys.stderr)
    if menus:
        for i, menu in enumerate(menus, 1):
            print(f"[OCR] 메뉴 {i}: {menu.name} (가격: {menu.price})", file=sys.stderr)
    else:
        print(f"[OCR] 메뉴 파싱 실패 - _looks_like_menu_name이 모든 라인을 거부했을 수 있음", file=sys.stderr)
        # 디버깅: 각 라인이 메뉴로 인식되는지 확인
        for i, line in enumerate(lines[:10], 1):
            is_menu = _looks_like_menu_name(line)
            print(f"[OCR] 라인 {i}: '{line[:50]}' -> 메뉴로 인식: {is_menu}", file=sys.stderr)

    return menus

