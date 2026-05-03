import logging
from typing import Any
from .base import ExposureSearchProvider, ExposureSearchItem
from ..playwright_client import PlaywrightClient

logger = logging.getLogger(__name__)

class GoogleProvider(ExposureSearchProvider):
    @property
    def name(self) -> str:
        return "google"

    def __init__(self, pw_client: PlaywrightClient):
        self.pw_client = pw_client

    async def search(
        self, 
        query: str, 
        max_results: int, 
        max_pages: int, 
        record_callback: Any = None,
        **kwargs
    ) -> list[ExposureSearchItem]:
        results = []
        async with self.pw_client.get_context(record_callback=record_callback) as context:
            for page_num in range(max_pages):
                if len(results) >= max_results:
                    break
                
                # Google pagination: start=0, 10, 20...
                start = page_num * 10
                url = f"https://www.google.com/search?q={query}&start={start}"
                
                page = await self.pw_client.open_page(context, url)
                
                is_captcha, msg = await self.pw_client.detect_captcha_or_login(page)
                if is_captcha:
                    logger.warning(f"Google provider detected risk control: {msg}")
                    if not self.pw_client.headless:
                        logger.info("Interactive mode: waiting for manual interaction...")
                        solved = await self.pw_client.wait_for_manual_interaction(page)
                        if not solved:
                            break
                    else:
                        break
                
                # Extract results
                search_results = await page.query_selector_all("#search .g, .MjjYud, .g")
                if not search_results:
                    break
                    
                for res in search_results:
                    if len(results) >= max_results:
                        break
                        
                    title_el = await res.query_selector("h3")
                    link_el = await res.query_selector("a")
                    snippet_el = await res.query_selector(".VwiC3b, .st, .y8Z77c")
                    
                    if title_el and link_el:
                        title = await title_el.inner_text()
                        link = await link_el.get_attribute("href")
                        snippet = await snippet_el.inner_text() if snippet_el else ""
                        
                        if link and link.startswith("http") and not link.startswith("https://www.google.com/"):
                            results.append(ExposureSearchItem(
                                source=self.name,
                                query=query,
                                title=title.strip(),
                                url=link,
                                snippet=snippet.strip()
                            ))
                
                await page.close()
                
        return results
