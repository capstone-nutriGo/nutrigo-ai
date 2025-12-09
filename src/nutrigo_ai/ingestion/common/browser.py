from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Iterable
import sys

DEFAULT_USER_DATA_DIR = str(Path.home() / ".playwright-yogiyo-profile")

from playwright.sync_api import sync_playwright, TimeoutError, Page


def looks_like_json(txt: str) -> bool:
    """응답 텍스트가 JSON 같아 보이는지 간단히 확인."""
    if not txt:
        return False
    s = txt.lstrip()
    return s.startswith("{") or s.startswith("[")


@contextmanager
def open_persistent_chromium(
    *,
    user_data_dir: str = "./yogiyo_profile",
    headless: bool = False,
    slow_mo: int = 100,
    locale: str = "ko-KR",
    lat: Optional[float] = None,
    lng: Optional[float] = None,
):
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    """
    Playwright Chromium persistent context를 열어주는 컨텍스트 매니저.

    예)
        with open_persistent_chromium(lat=..., lng=...) as context:
            page = context.new_page()
            ...
    """
    with sync_playwright() as p:
        launch_kwargs = dict(
            user_data_dir=user_data_dir,
            headless=headless,
            slow_mo=slow_mo,
            locale=locale,
        )

        if lat is not None and lng is not None:
            launch_kwargs["permissions"] = ["geolocation"]
            launch_kwargs["geolocation"] = {
                "latitude": lat, 
                "longitude": lng,
            }

        context = p.chromium.launch_persistent_context(**launch_kwargs)
        try:
            yield context
        finally:
            # 이미 닫혀 있으면 에러 무시
            try:
                context.close()
            except Exception as e:
                print(
                    f"[WARN] ignore error while closing browser context: {e}",
                    file=sys.stderr,
                )

def wait_any_ui(page: Page, *locators: Iterable, timeout: int = 8000) -> bool:
    """
    여러 locator 중 하나라도 등장할 때까지 기다림.
    하나라도 성공하면 True, 모두 실패하면 False.
    """
    for loc in locators:
        try:
            loc.first.wait_for(timeout=timeout)
            return True
        except TimeoutError:
            continue
    return False
