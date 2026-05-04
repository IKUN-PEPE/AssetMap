import asyncio
import logging
import os
from typing import Callable, Optional
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

class PlaywrightClient:
    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.playwright = None
        self.browser = None
        self._discovery_script = None
        self._user_done_event = asyncio.Event()
        self._finish_query_event = asyncio.Event()

    def _get_discovery_script(self) -> str:
        if self._discovery_script is None:
            script_path = os.path.join(os.path.dirname(__file__), "discovery_script.js")
            if os.path.exists(script_path):
                try:
                    with open(script_path, "r", encoding="utf-8") as f:
                        self._discovery_script = f.read()
                except Exception as e:
                    logger.error(f"Failed to read discovery script: {e}")
                    self._discovery_script = ""
        return self._discovery_script

    async def start(self, headless: bool = None):
        h = headless if headless is not None else self.headless
        if not self.playwright:
            self.playwright = await async_playwright().start()
        if not self.browser:
            self.browser = await self.playwright.chromium.launch(
                headless=h,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
        return self.browser

    async def stop(self):
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

    @asynccontextmanager
    async def get_context(
        self,
        headless: bool = None,
        record_callback: Optional[Callable] = None,
        resume_callback: Optional[Callable] = None,
        finish_callback: Optional[Callable] = None,
        **kwargs,
    ):
        browser = await self.start(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True,
            bypass_csp=True,
            **kwargs
        )
        context.set_default_timeout(self.timeout)

        self._user_done_event = asyncio.Event()
        self._finish_query_event = asyncio.Event()

        if record_callback:
            await context.expose_function("__am_record_clue", record_callback)

            async def legacy_finish_callback():
                logger.info("Legacy finish signal received.")
                self._user_done_event.set()

            async def leave_current_query_callback():
                logger.info("Finish current query signal received.")
                self._finish_query_event.set()
                if finish_callback is not None:
                    result = finish_callback()
                    if asyncio.iscoroutine(result):
                        await result

            await context.expose_function("__am_finish_capture", legacy_finish_callback)
            await context.expose_function("__am_finish_and_continue", leave_current_query_callback)
            if resume_callback:
                await context.expose_function("__am_resume_auto", resume_callback)

            script_content = self._get_discovery_script()
            if script_content:
                await context.add_init_script(script_content)

        try:
            yield context
        finally:
            await context.close()

    async def wait_for_user_done(self, page: Page, timeout_ms: int = 300000, stop_check: Optional[Callable] = None):
        if self.headless: return True
        
        self._user_done_event.clear()
        
        logger.info(f"Waiting for manual finish on {page.url}...")
        try:
            start_time = asyncio.get_running_loop().time()
            while (asyncio.get_running_loop().time() - start_time) < (timeout_ms / 1000):
                if self._user_done_event.is_set(): return True
                if page.is_closed(): return True
                # Check for external stop signal
                if stop_check and stop_check():
                    logger.info("Stop signal detected during wait_for_user_done.")
                    return True
                await asyncio.sleep(0.1)
            return False
        except Exception as e:
            logger.error(f"Error waiting for user: {e}")
            return False

    async def open_page(self, context: BrowserContext, url: str) -> Page:
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        return page

    async def wait_for_manual_interaction(self, page: Page, timeout_ms: int = 60000, stop_check: Optional[Callable] = None):
        try:
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < (timeout_ms / 1000):
                is_captcha, _ = await self.detect_captcha_or_login(page)
                if not is_captcha: return True
                if stop_check and stop_check():
                    return False
                await asyncio.sleep(2)
        except Exception: pass
        return False

    async def detect_captcha_or_login(self, page: Page) -> tuple[bool, str | None]:
        try: content = await page.content()
        except Exception: return False, None
        content_lower = content.lower()
        indicators = {"captcha": "人机验证", "verify": "安全验证", "登录": "登录限制", "sign in": "需要登录"}
        for key, msg in indicators.items():
            if key in content_lower: return True, msg
        return False, None
