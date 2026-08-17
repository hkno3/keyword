import os
import json
import time
import random
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import stealth_sync as _stealth_sync
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

_SESSION_FILE = os.path.join(os.path.dirname(__file__), "naver_session.json")
_LOGIN_TIMEOUT = 180  # seconds

_BLOCK_URL_KEYWORDS = ["captcha", "robot", "verify", "block"]
_BLOCK_TEXT_PATTERNS = [
    "로봇이 아닙니다", "자동화된 접근", "비정상적인 접근",
    "비정상적인 트래픽", "captcha", "robot check",
]
_BLOCK_SELECTORS = ["#captcha", ".captcha_wrap", "[class*='captcha']", "#robot_check"]

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

_STEALTH_SCRIPT = """
() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
    window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (p) =>
        p.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(p);
}
"""


def _is_naver_logged_in(context) -> bool:
    cookies = {c["name"] for c in context.cookies()}
    return "NID_AUT" in cookies and "NID_SES" in cookies


def _detect_block(page) -> bool:
    try:
        url = page.url.lower()
        if any(kw in url for kw in _BLOCK_URL_KEYWORDS):
            return True
    except Exception:
        pass

    try:
        content = page.content().lower()
        if any(p.lower() in content for p in _BLOCK_TEXT_PATTERNS):
            return True
    except Exception:
        pass

    for selector in _BLOCK_SELECTORS:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:
            pass

    try:
        if page.locator("#main_pack").count() == 0 and page.locator("#searchIframe").count() == 0:
            return True
    except Exception:
        pass

    return False


class NaverSearchSession:
    """
    Reusable Playwright browser session for bulk Naver keyword checking.

    첫 실행 시 크롬 창에 네이버 로그인 페이지가 열립니다.
    직접 로그인하시면 세션이 naver_session.json에 저장되어
    다음 실행부터는 자동으로 로그인 상태로 시작합니다.
    """

    def __init__(
        self,
        min_delay: float = 7.0,
        max_delay: float = 15.0,
        max_consecutive_failures: int = 3,
        page_wait: float = 2.5,
        restart_every: int = 2,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_consecutive_failures = max_consecutive_failures
        self.page_wait = page_wait
        self.restart_every = restart_every

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._consecutive_failures = 0
        self._total_checks = 0
        self.login_required = False

    # ── lifecycle ──────────────────────────────────────────

    def start(self):
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(
                headless=False,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            self._browser = self._playwright.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )

        viewport = {
            "width": random.choice([1280, 1366, 1440, 1920]),
            "height": random.choice([768, 800, 900, 1080]),
        }
        self._context = self._browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport=viewport,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        self._page = self._context.new_page()
        self._page.add_init_script(_STEALTH_SCRIPT)
        if _HAS_STEALTH:
            _stealth_sync(self._page)

        self._ensure_login()
        return self

    def stop(self):
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.stop()

    # ── login ──────────────────────────────────────────────

    def _ensure_login(self):
        # Try loading saved session first
        if os.path.exists(_SESSION_FILE):
            try:
                with open(_SESSION_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._context.add_cookies(saved["cookies"])
                self._page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=10000)
                time.sleep(1.5)
                if _is_naver_logged_in(self._context):
                    return  # 세션 유효
            except Exception:
                pass

        # Manual login required
        self.login_required = True
        self._page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded", timeout=15000)

        deadline = time.time() + _LOGIN_TIMEOUT
        while time.time() < deadline:
            time.sleep(2)
            if _is_naver_logged_in(self._context):
                self._save_session()
                self.login_required = False
                return

        raise TimeoutError("네이버 로그인 대기 시간 초과 (3분). 다시 시도해주세요.")

    def _save_session(self):
        try:
            cookies = self._context.cookies()
            with open(_SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump({"cookies": cookies}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── status ─────────────────────────────────────────────

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def is_blocked(self) -> bool:
        return self._consecutive_failures >= self.max_consecutive_failures

    # ── internals ──────────────────────────────────────────

    def _random_delay(self):
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    def _close_browser(self):
        """브라우저만 종료 (재시작은 다음 check_nodaji 호출 시)."""
        self.stop()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def _ensure_browser(self):
        """브라우저가 없으면 새로 시작."""
        if self._page is None:
            time.sleep(random.uniform(8, 15))
            self.start()

    # ── public API ─────────────────────────────────────────

    def check_nodaji(self, keyword: str) -> dict:
        """
        Visit Naver search for the keyword and detect whether any of:
          파워링크(광고), 뷰탭(블로그+카페), 뉴스, 쇼핑
        is present on the result page.
        """
        result = {
            "is_nodaji": False,
            "has_ad": False,
            "has_view": False,
            "has_news": False,
            "has_shopping": False,
        }

        if self.is_blocked():
            result["error"] = "bot_detected"
            return result

        # 브라우저가 닫혀 있으면 재시작 (이전 검색 후 종료된 경우)
        self._ensure_browser()

        if self._total_checks > 0:
            self._random_delay()

        try:
            self._page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(0.8, 1.5))

            search_box = self._page.locator("#query, input[name='query']").first
            search_box.wait_for(state="visible", timeout=5000)
            search_box.click()
            time.sleep(random.uniform(0.3, 0.6))
            for ch in keyword:
                search_box.type(ch, delay=random.randint(60, 180))
            time.sleep(random.uniform(0.3, 0.7))
            search_box.press("Enter")
            self._page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(self.page_wait)

            scroll_amount = random.randint(300, 900)
            self._page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            time.sleep(random.uniform(1.0, 2.0))

            if _detect_block(self._page):
                self._consecutive_failures += 1
                result["error"] = "bot_detected"
                result["blocked"] = True
                return result

            self._consecutive_failures = 0
            self._total_checks += 1

            result["has_ad"] = (
                self._page.locator("#sp_nt").count() > 0
                or self._page.locator(".power_link_area").count() > 0
                or self._page.locator("[class*='power_link']").count() > 0
            )
            result["has_view"] = (
                self._page.locator("#view").count() > 0
                or self._page.locator(".view_wrap").count() > 0
                or self._page.locator("[class*='view_lst']").count() > 0
            )
            result["has_news"] = (
                self._page.locator("#news").count() > 0
                or self._page.locator(".news_area").count() > 0
                or self._page.locator("[class*='news_wrap']").count() > 0
            )
            result["has_shopping"] = (
                self._page.locator("#shopping").count() > 0
                or self._page.locator(".shopping_wrap").count() > 0
                or self._page.locator("[class*='shopping_lst']").count() > 0
            )
            result["is_nodaji"] = not any([
                result["has_ad"],
                result["has_view"],
                result["has_news"],
                result["has_shopping"],
            ])

            # restart_every 검색 완료 시 브라우저 즉시 종료
            if self.restart_every > 0 and self._total_checks % self.restart_every == 0:
                self._close_browser()

        except Exception as e:
            self._consecutive_failures += 1
            result["error"] = str(e)

        return result


def check_naver_nodaji(keyword: str, delay: float = 1.5) -> dict:
    """Single-keyword nodaji check. For bulk use NaverSearchSession instead."""
    with NaverSearchSession(min_delay=delay, max_delay=delay * 1.5, page_wait=delay) as session:
        return session.check_nodaji(keyword)
