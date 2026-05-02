import logging
from .base import ExposureSearchProvider, ExposureSearchItem
from ..playwright_client import PlaywrightClient

logger = logging.getLogger(__name__)

class BaiduProvider(ExposureSearchProvider):
    @property
    def name(self) -> str:
        return "baidu"

    def __init__(self, pw_client: PlaywrightClient):
        self.pw_client = pw_client

    async def search(self, query: str, max_results: int, max_pages: int, **kwargs) -> list[ExposureSearchItem]:
        results = []
        async with self.pw_client.get_context() as context:
            for page_num in range(max_pages):
                if len(results) >= max_results:
                    break
                
                # Baidu pagination: pn=0, 10, 20...
                pn = page_num * 10
                url = f"https://www.baidu.com/s?wd={query}&pn={pn}"
                
                page = await self.pw_client.open_page(context, url)
                
                is_captcha, msg = await self.pw_client.detect_captcha_or_login(page)
                if is_captcha:
                    logger.warning(f"Baidu provider detected risk control: {msg}")
                    break
                
                # Extract results
                search_results = await page.query_selector_all(".result.c-container, .result-op.c-container, .c-container")
                if not search_results:
                    break
                    
                for res in search_results:
                    if len(results) >= max_results:
                        break
                        
                    title_el = await res.query_selector("h3 a, .c-title a, a")
                    snippet_el = await res.query_selector(".c-abstract, .content-right_8Zs8z, .c-font-normal")
                    
                    if title_el:
                        title = await title_el.inner_text()
                        link = await title_el.get_attribute("href")
                        snippet = await snippet_el.inner_text() if snippet_el else ""
                        
                        if link:
                            results.append(ExposureSearchItem(
                                source=self.name,
                                query=query,
                                title=title.strip(),
                                url=link,
                                snippet=snippet.strip()
                            ))
                
                await page.close()
                
        return results
