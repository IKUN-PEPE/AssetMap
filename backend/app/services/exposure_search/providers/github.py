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
                
                encoded_query = urllib.parse.quote(query)
                # GitHub search results (Code search)
                url = f"https://github.com/search?q={encoded_query}&type=code&p={page_num}"
                
                page = await self.pw_client.open_page(context, url)
                
                is_captcha, msg = await self.pw_client.detect_captcha_or_login(page)
                if is_captcha:
                    logger.warning(f"GitHub provider detected risk control/login: {msg}")
                    if not self.pw_client.headless:
                        logger.info("Interactive mode: waiting for manual interaction...")
                        solved = await self.pw_client.wait_for_manual_interaction(page)
                        if not solved:
                            break
                    else:
                        break
                
                # Broad selectors for code/repo results
                search_results = await page.query_selector_all(
                    ".code-list-item, div[data-testid='results-list'] > div, .repo-list-item"
                )
                
                if not search_results:
                    break
                    
                for res in search_results:
                    if len(results) >= max_results:
                        break
                        
                    link_el = await res.query_selector("a")
                    if link_el:
                        title = await link_el.inner_text()
                        link = await link_el.get_attribute("href")
                        if link and not link.startswith("http"):
                            link = f"https://github.com{link}"
                        
                        if link:
                            results.append(ExposureSearchItem(
                                source=self.name,
                                query=query,
                                title=title.strip(),
                                url=link,
                                snippet=""
                            ))
                
                await page.close()
                
        return results
