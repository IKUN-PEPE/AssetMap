import logging
from typing import Any
from .base import ExposureSearchProvider, ExposureSearchItem
from ..playwright_client import PlaywrightClient

logger = logging.getLogger(__name__)

class BingProvider(ExposureSearchProvider):
    @property
    def name(self) -> str:
        return "bing"

    def __init__(self, pw_client: PlaywrightClient):
        self.pw_client = pw_client

    async def _search_page(self, context, url, max_results, results, record_callback, service, task_id, db):
        retry_count = 0
        def stop_check():
            return bool(service and service.stop_check(task_id, db))
        
        while retry_count < 3:
            if stop_check(): return False
            page = await self.pw_client.open_page(context, url)
            try:
                is_captcha, msg = await self.pw_client.detect_captcha_or_login(page)
                if is_captcha:
                    logger.warning(f"Bing detected risk ({msg}), retry {retry_count+1}/3")
                    if not self.pw_client.headless:
                        # Request manual intervention
                        solved = await service.request_intervention(page, task_id, db)
                        if solved == "finish":
                            logger.info("Bing skip current blocked page query=%s url=%s", query if 'query' in locals() else "", url)
                            return "finish"
                        if solved:
                            retry_count = 0 # Reset retries after successful intervention
                            continue
                    
                    retry_count += 1
                    await page.reload()
                    continue

                # Normal extraction
                search_results = await page.query_selector_all("li.b_algo, .b_algo")
                if not search_results and retry_count < 2:
                    retry_count += 1
                    await page.reload()
                    continue

                for res in search_results:
                    if stop_check(): break
                    if len(results) >= max_results: break
                    title_el = await res.query_selector("h2 a, h3 a, a")
                    snippet_el = await res.query_selector(".b_caption p, .b_algo_snippet, .st, p")
                    if title_el:
                        title = await title_el.inner_text()
                        link = await title_el.get_attribute("href")
                        snippet = await snippet_el.inner_text() if snippet_el else ""
                        if link and link.startswith("http") and not link.startswith("https://www.bing.com/"):
                            results.append(ExposureSearchItem(source=self.name, query="", title=title.strip(), url=link, snippet=snippet.strip()))
                
                return True
            finally:
                await page.close()
        return False

    async def search(self, query: str, max_results: int, max_pages: int, record_callback: Any = None, resume_callback: Any = None, finish_callback: Any = None, service: Any = None, task_id: str = None, db: Any = None, **kwargs) -> list[ExposureSearchItem]:
        results = []
        async with self.pw_client.get_context(record_callback=record_callback, resume_callback=resume_callback, finish_callback=finish_callback) as context:
            for page_num in range(max_pages):
                if len(results) >= max_results: break
                if service and service.stop_check(task_id, db): break
                first = page_num * 10 + 1
                url = f"https://www.bing.com/search?q={query}&first={first}"
                success = await self._search_page(context, url, max_results, results, record_callback, service, task_id, db)
                if success == "finish":
                    logger.info("Bing moving to next query/page after finish signal query=%s page=%s", query, page_num + 1)
                    break
                if not success: break
        return results
