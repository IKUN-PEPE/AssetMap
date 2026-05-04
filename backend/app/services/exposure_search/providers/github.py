import logging
import urllib.parse
from typing import Any
from .base import ExposureSearchProvider, ExposureSearchItem
from ..playwright_client import PlaywrightClient

logger = logging.getLogger(__name__)

class GitHubProvider(ExposureSearchProvider):
    @property
    def name(self) -> str:
        return "github"

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
                    logger.warning(f"GitHub detected risk/login ({msg}), retry {retry_count+1}/3")
                    if not self.pw_client.headless:
                        solved = await service.request_intervention(page, task_id, db)
                        if solved == "finish":
                            logger.info("GitHub skip current blocked page query=%s url=%s", query if 'query' in locals() else "", url)
                            return "finish"
                        if solved:
                            retry_count = 0
                            continue
                    retry_count += 1
                    continue

                search_results = await page.query_selector_all(".code-list-item, div[data-testid='results-list'] > div, .repo-list-item")
                if not search_results and retry_count < 2:
                    retry_count += 1
                    continue

                for res in search_results:
                    if stop_check(): break
                    if len(results) >= max_results: break
                    link_el = await res.query_selector("a")
                    if link_el:
                        title = await link_el.inner_text()
                        link = await link_el.get_attribute("href")
                        if link and not link.startswith("http"): link = f"https://github.com{link}"
                        if link:
                            results.append(ExposureSearchItem(source=self.name, query="", title=title.strip(), url=link, snippet=""))

                return True
            finally:
                await page.close()
        return False

    async def search(self, query: str, max_results: int, max_pages: int, record_callback: Any = None, resume_callback: Any = None, finish_callback: Any = None, service: Any = None, task_id: str = None, db: Any = None, **kwargs) -> list[ExposureSearchItem]:
        results = []
        async with self.pw_client.get_context(record_callback=record_callback, resume_callback=resume_callback, finish_callback=finish_callback) as context:
            for page_num in range(1, max_pages + 1):
                if len(results) >= max_results: break
                if service and service.stop_check(task_id, db): break
                encoded_query = urllib.parse.quote(query)
                url = f"https://github.com/search?q={encoded_query}&type=code&p={page_num}"
                success = await self._search_page(context, url, max_results, results, record_callback, service, task_id, db)
                if success == "finish":
                    logger.info("GitHub moving to next query/page after finish signal query=%s page=%s", query, page_num)
                    break
                if not success: break
        return results
