import time
import random
from playwright.sync_api import sync_playwright

_BLOCK_URL_KEYWORDS = ["captcha", "robot", "verify", "block"]
_BLOCK_TEXT_PATTERNS = [
    "로봇이 아닙니다", "자동화된 접근", "비정상적인 접근",
    "비정상적인 트래픽", "captcha", "robot check",
]
_BLOCK_SELECTORS = ["#captcha", ".captcha_wrap", "[class*='captcha']", "#robot_check"]
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _detect_block(page) -> bool:
    """Detect if Naver is showing a bot verification or CAPTCHA page."""
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

    # Both main containers missing = page failed to load properly or is blocked
    try:
        if page.locator("#main_pack").count() == 0 and page.locator("#searchIframe").count() == 0:
            return True
    except Exception:
        pass

    return False


class NaverSearchSession:
    """
    Reusable Playwright browser session for bulk Naver keyword checking.
    One browser process is shared across many keyword checks to avoid
    repeated launch overhead and to maintain natural browsing state.

    Bot detection features:
    - Randomized delay between consecutive searches (min_delay ~ max_delay seconds)
    - CAPTCHA / block page detection on every page load
    - Consecutive failure counter: stops checking once max_consecutive_failures is reached

    Usage (explicit start/stop — no indentation change required):
        session = NaverSearchSession()
        session.start()
        try:
            for kw in keywords:
                if session.is_blocked():
                    break
                result = session.check_nodaji(kw)
        finally:
            session.stop()

    Or as a context manager:
        with NaverSearchSession() as session:
            result = session.check_nodaji(kw)
    """

    def __init__(
        self,
        min_delay: float = 7.0,
        max_delay: float = 15.0,
        max_consecutive_failures: int = 3,
        page_wait: float = 2.5,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_consecutive_failures = max_consecutive_failures
        self.page_wait = page_wait

        self._playwright = None
        self._browser = None
        self._page = None
        self._consecutive_failures = 0
        self._total_checks = 0

    # ── lifecycle ──────────────────────────────────────────

    def start(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=False)
        self._page = self._browser.new_page(user_agent=_USER_AGENT)
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

    # ── status ─────────────────────────────────────────────

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def is_blocked(self) -> bool:
        """True once consecutive failures have reached the limit."""
        return self._consecutive_failures >= self.max_consecutive_failures

    # ── internals ──────────────────────────────────────────

    def _random_delay(self):
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    # ── public API ─────────────────────────────────────────

    def check_nodaji(self, keyword: str) -> dict:
        """
        Visit Naver search for the keyword and detect whether any of:
          파워링크(광고), 뷰탭(블로그+카페), 뉴스, 쇼핑
        is present on the result page.

        Returns dict:
            is_nodaji (bool)  – True only when ALL four sections are absent
            has_ad (bool)
            has_view (bool)
            has_news (bool)
            has_shopping (bool)
            blocked (bool)    – set when bot-detection fired
            error (str)       – set on any exception or bot-detection
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

        # Randomized delay between consecutive checks
        if self._total_checks > 0:
            self._random_delay()

        try:
            # Navigate to Naver home first, then type like a human
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

            # Random scroll like a human reading results
            scroll_amount = random.randint(300, 900)
            self._page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            time.sleep(random.uniform(1.0, 2.5))
            self._page.evaluate(f"window.scrollBy(0, {random.randint(-200, 200)})")
            time.sleep(random.uniform(0.5, 1.5))

            if _detect_block(self._page):
                self._consecutive_failures += 1
                result["error"] = "bot_detected"
                result["blocked"] = True
                return result

            # Successful load — reset consecutive failure counter
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

        except Exception as e:
            self._consecutive_failures += 1
            result["error"] = str(e)

        return result


def check_naver_nodaji(keyword: str, delay: float = 1.5) -> dict:
    """
    Single-keyword nodaji check (creates and destroys a browser each call).
    For checking multiple keywords sequentially, use NaverSearchSession instead.
    """
    with NaverSearchSession(min_delay=delay, max_delay=delay * 1.5, page_wait=delay) as session:
        return session.check_nodaji(keyword)
