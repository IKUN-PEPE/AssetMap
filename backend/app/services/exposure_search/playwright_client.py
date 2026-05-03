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

    def _get_discovery_script(self) -> str:
        """Read and cache the discovery script content."""
        if self._discovery_script is None:
            script_path = os.path.join(os.path.dirname(__file__), "discovery_script.js")
            if os.path.exists(script_path):
                try:
                    with open(script_path, "r", encoding="utf-8") as f:
                        self._discovery_script = f.read()
                except Exception as e:
                    logger.error(f"Failed to read discovery script: {e}")
                    self._discovery_script = ""
            else:
                logger.warning(f"Discovery script not found at {script_path}")
                self._discovery_script = ""
        return self._discovery_script

    async def start(self, headless: bool = None):
        h = headless if headless is not None else self.headless
        if not self.playwright:
            self.playwright = await async_playwright().start()
        
        if not self.browser:
            self.browser = await self.playwright.chromium.launch(
                headless=h,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
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
    async def get_context(self, headless: bool = None, record_callback: Optional[Callable] = None, **kwargs):
        browser = await self.start(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True,
            **kwargs
        )
        context.set_default_timeout(self.timeout)

        # Anti-bot script for all pages in this context
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Inject discovery script and expose record function if callback provided
        if record_callback:
            await context.expose_function("__am_record_clue", record_callback)
            script_content = self._get_discovery_script()
            if script_content:
                await context.add_init_script(script_content)
                logger.info("Injected discovery script into browser context")

        try:
            yield context
        finally:
            await context.close()

    async def open_page(self, context: BrowserContext, url: str) -> Page:
        page = await context.new_page()
        # Note: anti-bot is now handled at context level in get_context
        await page.goto(url, wait_until="domcontentloaded")
        return page

    async def wait_for_manual_interaction(self, page: Page, timeout_ms: int = 60000):
        """
        When risk control is detected and headless=False, wait for the user to solve it.
        We'll wait until the indicators are gone or timeout occurs.
        """
        try:
            # Wait for user to solve captcha or login
            # We check every 2 seconds if the captcha is still there
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < (timeout_ms / 1000):
                is_captcha, _ = await self.detect_captcha_or_login(page)
                if not is_captcha:
                    return True
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Error during manual interaction wait: {e}")
        return False

    async def detect_captcha_or_login(self, page: Page) -> tuple[bool, str | None]:
        content = await page.content()
        content_lower = content.lower()
        
        # Expanded indicators based on requirement 1
        indicators = {
            "captcha": "检测到 ，需要人机验证",
            "verify": "检测到安全验证",
            "人机验证": "检测到人机验证",
            "安全验证": "检测到安全验证",
            "登录": "检测到登录限制",
            "sign in": "检测到需要登录",
            "access denied": "访问被拒绝 (Access Denied)",
            "abnormal traffic": "检测到异常流量",
            "robot": "疑似机器人流量",
            "recaptcha": "Google reCAPTCHA 验证"
        }
        
        for key, msg in indicators.items():
            if key in content_lower:
                return True, msg
        
        # Check for visible captcha frames or images if needed
        # (Simplified for now)
        
        return False, None
