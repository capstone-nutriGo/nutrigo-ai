import json
import os
import re
import sys
import time
from typing import Any, Dict, Optional

from playwright.sync_api import TimeoutError

from nutrigo_ai.ingestion.common.browser import (
    open_persistent_chromium,
    looks_like_json,
    wait_any_ui,
)

from nutrigo_ai.api.schemas import MenuText


# ======= 메뉴 후보 URL 키워드(느슨하게) =======
MENU_URL_RE = re.compile(
    r"(aggregation/shops/.*/menus|menu|menus|menugroup|category|categories|item|items|product|products|goods|catalog|dish)",
    re.I,
)


def menu_json_to_menu_texts(menu_json: dict) -> list[MenuText]:
    """
    fetch_store_info() 가 리턴한 result["menu_json"] 을
    LLM이 쓰는 MenuText 리스트로 변환.
    """
    menus: list[MenuText] = []
    schema = menu_json.get("schema")

    # frontyo_aggregation_v1: sections + items + options 구조
    if schema == "frontyo_aggregation_v1" and "sections" in menu_json:
        for sec in menu_json.get("sections", []):
            category = (sec.get("title") or "").strip() or None
            for item in sec.get("items", []):
                name = (item.get("name") or "").strip()
                if not name:
                    continue

                # 옵션들을 사람이 읽을 수 있는 한 줄 문자열로 합치기
                option_phrases: list[str] = []
                for og in item.get("options", []):
                    group_title = (og.get("title") or "").strip()
                    names = [
                        (opt.get("name") or "").strip()
                        for opt in og.get("items", [])
                        if (opt.get("name") or "").strip()
                    ]
                    if not names:
                        continue
                    body = ", ".join(names)
                    if group_title:
                        option_phrases.append(f"{group_title}: {body}")
                    else:
                        option_phrases.append(body)

                option_text = " / ".join(option_phrases) if option_phrases else None

                menus.append(
                    MenuText(
                        id=str(item.get("id") or len(menus)),
                        name=name,
                        description=item.get("desc") or "",
                        price=item.get("price"),
                        category_hint=category,
                        option_text=option_text,
                    )
                )

    # generic_items_v1: 납작한 items 배열만 있는 경우
    elif "items" in menu_json:
        for idx, item in enumerate(menu_json.get("items", [])):
            name = (item.get("name") or "").strip()
            if not name:
                continue
            menus.append(
                MenuText(
                    id=str(item.get("id") or idx),
                    name=name,
                    description=item.get("desc") or "",
                    price=item.get("price"),
                    category_hint=None,
                    option_text=None,
                )
            )

    return menus


# ======= 정규화 유틸 =======
def normalize_frontyo_aggregation(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    frontyo.yogiyo.co.kr/v1/aggregation/shops/{id}/menus 응답을
    섹션별 아이템 리스트로 정규화.
    """
    sections = payload.get("menu_sections") or []
    menu_map = payload.get("menu") or {}

    # 옵션 상세 맵 후보(없어도 동작)
    option_item_maps = []
    for k in [
        "option_items",
        "optionItemMap",
        "optionItems",
        "option_menu_items",
        "optionItemsMap",
    ]:
        if isinstance(payload.get(k), dict):
            option_item_maps.append(payload[k])

    def _price_from_price_obj(pobj):
        if not isinstance(pobj, dict):
            return None
        for key in [
            "final_price",
            "origin_price",
            "final_price_with_required_options",
            "origin_price_with_required_options",
        ]:
            if pobj.get(key) is not None:
                try:
                    return int(pobj[key])
                except Exception:
                    pass
        return None

    def _resolve_option_item(oid):
        for m in option_item_maps:
            if isinstance(m, dict) and oid in m:
                node = m[oid]
                name = (node.get("name") or node.get("title") or "").strip()
                price = node.get("price") or node.get("amount") or 0
                try:
                    price = int(price)
                except Exception:
                    price = 0
                soldout = bool(
                    node.get("soldout")
                    or node.get("sold_out")
                    or node.get("isSoldOut")
                )
                return {
                    "id": oid,
                    "name": name,
                    "price": price,
                    "soldout": soldout,
                }
        return {"id": oid, "name": "", "price": 0, "soldout": False}

    def _badges(badges):
        out = []
        if isinstance(badges, list):
            for b in badges:
                label = (b or {}).get("label")
                if label:
                    out.append(str(label))
        return out

    normalized_sections = []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        sec_id = str(sec.get("id", ""))
        sec_title = (sec.get("title") or "").strip()
        item_ids = sec.get("items") or []
        norm_items = []

        for iid in item_ids:
            node = menu_map.get(str(iid)) or menu_map.get(iid) or {}
            if not isinstance(node, dict):
                continue

            name = (node.get("name") or "").strip()
            desc = (node.get("description") or "").strip()
            thumb = node.get("thumbnail") or {}
            image = thumb.get("image") or ""
            price = _price_from_price_obj(node.get("price"))
            badges = _badges(node.get("badges"))

            option_groups = []
            for og in (node.get("option_sections") or []):
                if not isinstance(og, dict):
                    continue
                og_title = (og.get("title") or "").strip()
                og_required = bool(og.get("required"))
                og_multiple_limit = og.get("multiple_limit")
                og_items_ids = og.get("items") or []
                og_items = [_resolve_option_item(oid) for oid in og_items_ids]
                option_groups.append(
                    {
                        "id": og.get("id"),
                        "title": og_title,
                        "required": og_required,
                        "multiple_limit": og_multiple_limit,
                        "items": og_items,
                    }
                )

            norm_items.append(
                {
                    "id": node.get("id") or iid,
                    "name": name,
                    "desc": desc,
                    "price": price,
                    "image": image,
                    "badges": badges,
                    "options": option_groups,
                }
            )

        normalized_sections.append(
            {
                "id": sec_id,
                "title": sec_title,
                "items": norm_items,
            }
        )

    return {"sections": normalized_sections, "schema": "frontyo_aggregation_v1"}


def normalize_menu(payload: Any) -> Dict[str, Any]:
    """frontyo 스키마면 전용 파서, 아니면 간단 범용 파서."""
    if isinstance(payload, dict) and "menu_sections" in payload and "menu" in payload:
        return normalize_frontyo_aggregation(payload)

    # 범용(백업) – payload 내부의 items 배열을 납작하게 긁어옴
    sections = payload if isinstance(payload, list) else [payload]
    norm_items = []
    for sec in sections:
        items = sec.get("items") if isinstance(sec, dict) else None
        if not items:
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            name = (it.get("name") or it.get("title") or "").strip()
            desc = (it.get("description") or it.get("subtitle") or "").strip()
            price_raw = it.get("price")
            try:
                price = (
                    int(str(price_raw).replace(",", ""))
                    if price_raw not in (None, "")
                    else None
                )
            except Exception:
                price = None
            image = it.get("original_image") or it.get("image") or ""
            norm_items.append(
                {
                    "name": name,
                    "desc": desc,
                    "price": price,
                    "image": image,
                    "options": [],
                }
            )
    return {"items": norm_items, "schema": "generic_items_v1"}


# ======= 팝업 자동 닫기 유틸 =======
def _auto_dismiss_popups(page):
    """
    요기요가 띄우는 앱 설치/동의/닫기 팝업들을 최대한 자동으로 클릭해서 닫는다.
    실패해도 그냥 넘어가도록 예외는 전부 무시.
    """
    selectors = [
        "text=모바일웹으로 볼게요",
        "text=웹으로 계속",
        "text=브라우저에서 계속",
        "text=괜찮아요",
        "text=나중에",
        "text=닫기",
        "text=동의",
        "button:has-text('닫기')",
        "button:has-text('동의')",
        "button:has-text('확인')",
    ]

    for sel in selectors:
        try:
            page.locator(sel).first.click(timeout=1000)
        except Exception:
            pass


# ======= 메인 작업 함수 =======
def fetch_store_info(
    store_id: str,
    address_text: str,
    *,
    lat: float,
    lng: float,
    order_serving_type: str = "delivery",
    user_data_dir: str = "./yogiyo_profile",
    headless: bool = False,
    slow_mo: int = 100,
    pause_on_finish: bool = False,
) -> Optional[Dict[str, Any]]:
    store_url = f"https://www.yogiyo.co.kr/mobile/#/{store_id}/"

    with open_persistent_chromium(
        user_data_dir=user_data_dir,
        headless=headless,
        slow_mo=slow_mo,
        lat=lat,
        lng=lng,
    ) as context:
        page = context.new_page()

        # 응답 캡처 준비
        captured = []  # (url, status, data, size)

        def on_response(resp):
            try:
                url = resp.url
                status = resp.status
                text = resp.text()
            except Exception:
                return

            data = None
            if looks_like_json(text):
                try:
                    data = json.loads(text)
                except Exception:
                    data = None

            if data is not None:
                size = len(text)
                captured.append((url, status, data, size))
                print(f"[JSON] {status} {url} ({size} bytes)")

        page.on("response", on_response)

        def pick_menu_json():
            candidates = []
            for url, status, data, size in captured:
                score = 0
                if MENU_URL_RE.search(url or ""):
                    score += 4
                score += min(size // 2000, 6)
                if isinstance(data, dict) and (
                    "menu_sections" in data and "menu" in data
                ):
                    score += 5
                elif isinstance(data, dict) and ("items" in data):
                    score += 1
                if status == 200:
                    score += 1
                candidates.append((score, url, data))
            if not candidates:
                return None
            candidates.sort(reverse=True)
            best = candidates[0]
            return {"url": best[1], "data": best[2]} if best[0] >= 3 else None

        def text_of(*locs):
            for loc in locs:
                try:
                    loc.first.wait_for(timeout=1500)
                    t = (loc.first.inner_text() or "").strip()
                    if t:
                        return t
                except Exception:
                    pass
            return ""

        try:
            # 1) 홈 → 주소 확정
            page.goto(
                "https://www.yogiyo.co.kr/mobile/#/",
                wait_until="domcontentloaded",
            )
            _auto_dismiss_popups(page)

            try:
                addr_box = page.locator(
                    "input[placeholder*='건물명'], "
                    "input[placeholder*='도로명'], "
                    "input[placeholder*='지번']"
                ).first
                addr_box.wait_for(timeout=10000)
                addr_box.click()
                addr_box.fill(address_text)

                picked = False
                for sel in [
                    "ul[class*='suggest'] li",
                    "div[class*='suggest'] li",
                    "li:has-text('동작구')",
                    "li",
                ]:
                    try:
                        page.locator(sel).first.wait_for(timeout=3000)
                        page.locator(sel).first.click()
                        picked = True
                        break
                    except TimeoutError:
                        continue

                if not picked:
                    page.keyboard.press("Enter")
                    try:
                        page.get_by_role("button", name="검색").first.click(
                            timeout=2000
                        )
                    except Exception:
                        pass

                page.wait_for_function(
                    """
                    () => {
                        const el = document.querySelector(
                            "input[placeholder*='건물명'],"
                            +"input[placeholder*='도로명'],"
                            +"input[placeholder*='지번']"
                        );
                        return el && el.value && el.value.length >= 4;
                    }
                    """,
                    timeout=8000,
                )
                time.sleep(1.0)

                # 간헐 팝업 닫기 (다시 한 번)
                _auto_dismiss_popups(page)
                for b in [
                    page.get_by_role("button", name="확인"),
                    page.get_by_role("button", name="닫기"),
                    page.get_by_role("button", name="동의"),
                ]:
                    try:
                        b.first.click(timeout=800)
                    except Exception:
                        pass
            except TimeoutError:
                print("[경고] 주소 확정 단계 타임아웃", file=sys.stderr)

            # 2) 상세 페이지 이동
            page.goto(store_url, wait_until="domcontentloaded")
            _auto_dismiss_popups(page)

            page.wait_for_url(f"**/{store_id}/**", timeout=10000)
            if not wait_any_ui(
                page,
                page.locator("ul.nav-tabs"),
                page.locator(".restaurant-name"),
                page.get_by_text("메뉴"),
            ):
                raise TimeoutError("상세 UI 대기 실패")

            # 3) '메뉴' 탭 클릭(이미 열려있으면 예외 무시)
            try:
                page.get_by_text("메뉴").first.click(timeout=3000)
            except TimeoutError:
                try:
                    page.locator("ul.nav-tabs").get_by_text("메뉴").first.click(
                        timeout=3000
                    )
                except TimeoutError:
                    print(
                        "[알림] '메뉴' 탭 클릭 실패(이미 메뉴 탭일 수 있음)",
                        file=sys.stderr,
                    )

            # 4) 네트워크 캡처 → 폴링 + 스크롤 유도
            menu_pick = None
            deadline = time.time() + 3.0
            while time.time() < deadline:
                menu_pick = pick_menu_json()
                if menu_pick:
                    break
                time.sleep(0.2)

            if not menu_pick:
                for _ in range(10):
                    page.mouse.wheel(0, 1600)
                    time.sleep(0.6)
                    menu_pick = pick_menu_json()
                    if menu_pick:
                        break

            # 5) 실패 시 직접 요청(fallback)
            if not menu_pick:
                agg_url = (
                    f"https://frontyo.yogiyo.co.kr/v1/aggregation/shops/{store_id}/menus"
                    f"?lat={lat}&lng={lng}&order_serving_type={order_serving_type}"
                )
                print(f"[fallback] GET {agg_url}")
                r = context.request.get(
                    agg_url, headers={"Accept": "application/json"}
                )
                if r.ok:
                    data = r.json()
                    menu_pick = {"url": agg_url, "data": data}

            if not menu_pick:
                raise TimeoutError(
                    "메뉴 JSON 확보 실패(네트워크 캡처/직접요청 모두 실패)"
                )

            # 6) 저장(원본 + 정규화)
            menu_raw = menu_pick["data"]
            with open("menu_raw.json", "w", encoding="utf-8") as f:
                json.dump(menu_raw, f, ensure_ascii=False, indent=2)

            menu_norm = normalize_menu(menu_raw)
            with open("menu_norm.json", "w", encoding="utf-8") as f:
                json.dump(menu_norm, f, ensure_ascii=False, indent=2)

            # 7) 가게명/주소(백업 추출)
            name = text_of(
                page.locator(".restaurant-name"),
                page.locator("h2"),
                page.locator("h3"),
                page.locator(".name"),
            )
            address = text_of(
                page.locator(
                    "div.info-item:has-text('주소') .info-text"
                ),
            )

            # 8) 스냅샷 + 출력
            page.screenshot(path="yogiyo_debug.png", full_page=True)

            if "sections" in menu_norm:
                total_items = sum(
                    len(s.get("items", [])) for s in menu_norm["sections"]
                )
            elif "items" in menu_norm:
                total_items = len(menu_norm["items"])
            else:
                total_items = 0

            result = {
                "store_id": store_id,
                "name": name or "가게명 추출 실패",
                "address": address or address_text,
                "menu_source_url": menu_pick.get("url", ""),
                "menu_count": total_items,
                "menu_json": menu_norm,
            }

            print(f"[OK] 메뉴 항목 수: {total_items}")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            with open("result.json", "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            print("\n파일 저장 완료:")
            print(" - menu_raw.json    (원본)")
            print(" - menu_norm.json   (정규화)")
            print(" - result.json      (요약 + 정규화)")
            print(" - yogiyo_debug.png (화면 스냅샷)")

            if pause_on_finish:
                try:
                    input(
                        "\n브라우저를 확인했으면 Enter를 눌러 종료하세요..."
                    )
                except Exception:
                    pass

            return result

        except Exception as e:
            print(f"[에러] {e}")
            if pause_on_finish:
                try:
                    input(
                        "\n브라우저를 확인했으면 Enter를 눌러 종료하세요..."
                    )
                except Exception:
                    pass
            return None


if __name__ == "__main__":
    # 테스트 실행용
    res = fetch_store_info(
        store_id="229998",
        address_text="서울특별시 동작구 흑석로 84",
        lat=37.5080617,
        lng=126.95999855,
        order_serving_type="delivery",
        pause_on_finish=False,  # 테스트에서도 자동 종료
    )
    if res:
        print("\n=== RESULT(JSON) ===")
        print(json.dumps(res, ensure_ascii=False, indent=2))
