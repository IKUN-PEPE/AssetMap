import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session
from app.models.exposure_search import ExposureSearchTask, ExposureSearchResult
from app.services.exposure_search.playwright_client import PlaywrightClient
from app.services.exposure_search.query_builder import QueryBuilder
from app.services.exposure_search.risk_classifier import RiskClassifier
from app.services.exposure_search.providers.bing import BingProvider
from app.services.exposure_search.providers.baidu import BaiduProvider
from app.services.exposure_search.providers.github import GitHubProvider
from app.services.exposure_search.providers.google import GoogleProvider

logger = logging.getLogger(__name__)

class ExposureSearchService:
    def __init__(self, db: Session, max_concurrent_queries: int = 3, headless: bool = True):
        self.db = db
        self.headless = headless
        self.pw_client = PlaywrightClient(headless=headless)
        self.semaphore = asyncio.Semaphore(max_concurrent_queries)

    async def _handle_manual_clue(self, task_id: str, classifier: RiskClassifier, data: dict):
        """Callback for manual capture from the browser."""
        try:
            url = data.get("url")
            if not url:
                return
            
            # Deduplicate by URL within the task
            existing = self.db.query(ExposureSearchResult).filter(
                ExposureSearchResult.task_id == task_id,
                ExposureSearchResult.url == url
            ).first()
            
            if not existing:
                title = data.get("title", "Manual Capture")
                snippet = data.get("snippet", "")
                source_page = data.get("source_page", "unknown")
                
                risk_tags, matched_keywords = classifier.classify(
                    title, url, snippet
                )
                
                res = ExposureSearchResult(
                    task_id=task_id,
                    source="manual",
                    query=f"Manual Capture from {source_page}",
                    title=title,
                    url=url,
                    snippet=snippet,
                    risk_tags=risk_tags,
                    matched_keywords=matched_keywords,
                    raw_payload={"manual": True, "source_page": source_page},
                    status="valid"  # Mark as valid since user manually captured it
                )
                self.db.add(res)
                
                # Update task result counts
                task = self.db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
                if task:
                    task.total_results += 1
                    task.valid_count += 1
                
                self.db.commit()
                logger.info(f"Manual clue saved for task {task_id}: {url}")
            else:
                logger.info(f"Manual clue already exists for task {task_id}: {url}")
        except Exception as e:
            logger.error(f"Error in _handle_manual_clue: {e}")

    async def run_task(self, task_id: str):
        task = self.db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
        if not task:
            logger.error(f"Task {task_id} not found")
            return

        task.status = "running"
        task.started_at = datetime.utcnow()
        self.db.commit()

        try:
            builder = QueryBuilder(
                org_keywords=task.org_keywords,
                title_keywords=task.title_keywords,
                url_keywords=task.url_keywords,
                file_types=task.file_types,
                sites=["pan.baidu.com", "docs.google.com", "drive.google.com", "onedrive.live.com"] if "web_disk" in task.sources else []
            )
            queries = builder.build_queries()
            # Initialize query plan with results_count
            task.query_plan = [{"query": q, "status": "pending", "results_count": 0} for q in queries]
            self.db.commit()

            classifier = RiskClassifier(org_keywords=task.org_keywords)
            
            # Create the manual capture callback
            async def record_callback(data):
                await self._handle_manual_clue(task_id, classifier, data)

            providers = []
            if "bing" in task.sources:
                providers.append(BingProvider(self.pw_client))
            if "baidu" in task.sources:
                providers.append(BaiduProvider(self.pw_client))
            if "github" in task.sources:
                providers.append(GitHubProvider(self.pw_client))
            if "google" in task.sources:
                providers.append(GoogleProvider(self.pw_client))

            async def process_query(query_item):
                query = query_item["query"]
                query_item["status"] = "running"
                self.db.commit()
                
                query_total = 0
                # Apply concurrency limit to queries
                async with self.semaphore:
                    for provider in providers:
                        try:
                            # 60s timeout per provider per query
                            results = await asyncio.wait_for(
                                provider.search(
                                    query=query,
                                    max_results=10,
                                    max_pages=1,
                                    record_callback=record_callback
                                ),
                                timeout=60.0
                            )
                            
                            for item in results:
                                # Deduplicate by URL within the task
                                existing = self.db.query(ExposureSearchResult).filter(
                                    ExposureSearchResult.task_id == task_id,
                                    ExposureSearchResult.url == item.url
                                ).first()
                                
                                if not existing:
                                    risk_tags, matched_keywords = classifier.classify(
                                        item.title, item.url, item.snippet or ""
                                    )
                                    
                                    res = ExposureSearchResult(
                                        task_id=task_id,
                                        source=item.source,
                                        query=query,
                                        title=item.title,
                                        url=item.url,
                                        snippet=item.snippet,
                                        risk_tags=risk_tags,
                                        matched_keywords=matched_keywords,
                                        raw_payload=item.raw_payload,
                                        status="pending"
                                    )
                                    self.db.add(res)
                                    query_total += 1
                                    # Increment task total results
                                    task.total_results += 1
                            
                            self.db.commit()
                        except asyncio.TimeoutError:
                            logger.warning(f"Provider {provider.name} timed out for query {query}")
                        except Exception as e:
                            logger.warning(f"Provider {provider.name} failed for query {query}: {e}")
                
                query_item["status"] = "completed"
                query_item["results_count"] = query_total
                self.db.commit()

            # Execute queries
            for q_item in task.query_plan:
                await process_query(q_item)

            task.status = "completed"
            task.finished_at = datetime.utcnow()
            self.db.commit()

        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
            task.finished_at = datetime.utcnow()
            self.db.commit()
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
        finally:
            await self.pw_client.stop()
