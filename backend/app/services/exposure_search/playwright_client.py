import asyncio
import logging
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

class PlaywrightClient:
    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.playwright = None
        self.browser = None

    async def start(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
        if not self.browser:
            # Added common bypass arguments
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
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
    async def get_context(self, **kwargs):
        browser = await self.start()
        # Randomized viewport and user agent to reduce bot detection
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True,
            **kwargs
        )
        context.set_default_timeout(self.timeout)
        try:
            yield context
        finally:
            await context.close()

    async def open_page(self, context: BrowserContext, url: str) -> Page:
        page = await context.new_page()
        # Basic bypass for webdriver detection
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        await page.goto(url, wait_until="domcontentloaded")
        return page

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
