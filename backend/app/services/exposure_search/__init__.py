import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import func
from app.core.db import SessionLocal
from app.models.exposure_search import ExposureSearchTask, ExposureSearchResult
from app.services.exposure_search.playwright_client import PlaywrightClient
from app.services.exposure_search.query_builder import QueryBuilder
from app.services.exposure_search.risk_classifier import RiskClassifier
from app.services.exposure_search.providers.bing import BingProvider
from app.services.exposure_search.providers.baidu import BaiduProvider
from app.services.exposure_search.providers.github import GitHubProvider
from app.services.exposure_search.providers.google import GoogleProvider

logger = logging.getLogger(__name__)

DOCUMENT_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "sql"}


def _infer_file_type(url: str, raw_file_type: str | None) -> str | None:
    normalized_type = (raw_file_type or "").strip().lower()
    if normalized_type:
        return normalized_type
    suffix = Path((url or "").split("?", 1)[0]).suffix.lower().lstrip(".")
    return suffix or None


def _matches_task_filters(task: ExposureSearchTask, file_type: str | None) -> bool:
    normalized_type = (file_type or "").strip().lower()
    is_document = normalized_type in DOCUMENT_EXTENSIONS
    if task.only_documents and not is_document:
        return False
    if task.only_webpages and is_document:
        return False
    return True


def _categorize_query_error(error_message: str | None) -> str:
    text = str(error_message or "").lower()
    if any(token in text for token in ("captcha", "verify", "login", "auth", "风控", "验证码", "登录")):
        return "验证码/风控"
    if any(token in text for token in ("timeout", "timed out", "超时")):
        return "超时"
    if any(token in text for token in ("selector", "queryselector", "locator", "页面结构", "element", "dom")):
        return "页面结构变化"
    if any(token in text for token in ("no result", "empty result", "无结果")):
        return "无结果"
    return "其它"


def _build_provider_list(task: ExposureSearchTask, pw_client: PlaywrightClient):
    providers = []
    if "bing" in task.sources: providers.append(BingProvider(pw_client))
    if "baidu" in task.sources: providers.append(BaiduProvider(pw_client))
    if "github" in task.sources: providers.append(GitHubProvider(pw_client))
    if "google" in task.sources: providers.append(GoogleProvider(pw_client))
    return providers


def _derive_progress_fields(task: ExposureSearchTask) -> dict[str, int | str | None]:
    query_plan = task.query_plan if isinstance(task.query_plan, list) else []
    total_queries = len(query_plan)
    completed_statuses = {"completed", "stopped", "failed"}
    completed_queries = sum(1 for item in query_plan if (item or {}).get("status") in completed_statuses)
    terminal_task_statuses = {"completed", "stopped", "failed"}
    current_item = None if task.status in terminal_task_statuses else next((item for item in query_plan if (item or {}).get("status") == "running"), None)
    next_item = None if task.status in terminal_task_statuses else next((item for item in query_plan if (item or {}).get("status") == "pending"), None)
    progress_percent = int((completed_queries / total_queries) * 100) if total_queries else 0
    if task.status == "completed" and total_queries > 0:
        progress_percent = 100
    return {
        "current_query": (current_item or {}).get("query"),
        "next_query": (next_item or {}).get("query"),
        "completed_queries": completed_queries,
        "total_queries": total_queries,
        "progress_percent": progress_percent,
    }

class ExposureSearchService:
    def __init__(self, db: Session = None, max_concurrent_queries: int = 3, headless: bool = True):
        self.db = db
        self.headless = headless
        self.pw_client = PlaywrightClient(headless=headless)
        self.semaphore = asyncio.Semaphore(max_concurrent_queries)
        self.resume_event = asyncio.Event()
        self.finish_query_event = asyncio.Event()
        self.query_plan_lock = asyncio.Lock()

    def _create_session(self) -> Session:
        if self.db is not None and getattr(self.db, "bind", None) is not None:
            factory = sessionmaker(
                bind=self.db.bind,
                autoflush=False,
                autocommit=False,
                future=True,
            )
            return factory()
        return SessionLocal()

    async def _update_query_plan_item(
        self,
        task_id: str,
        query: str,
        *,
        status: str | None = None,
        results_count: int | None = None,
        error_message: str | None = None,
        error_category: str | None = None,
    ) -> None:
        async with self.query_plan_lock:
            db = self._create_session()
            try:
                task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
                if not task or not isinstance(task.query_plan, list):
                    return
                updated_plan = []
                for item in task.query_plan:
                    current = dict(item or {})
                    if current.get("query") == query:
                        if status is not None:
                            current["status"] = status
                        if results_count is not None:
                            current["results_count"] = results_count
                        if error_message is not None:
                            current["error_message"] = error_message
                        if error_category is not None:
                            current["error_category"] = error_category
                    updated_plan.append(current)
                task.query_plan = updated_plan
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    async def retry_query(self, task_id: str, query: str) -> None:
        db = self._create_session()
        try:
            task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
            if not task:
                raise ValueError(f"Task not found: {task_id}")

            await self._update_query_plan_item(task_id, query, status="running", results_count=0, error_message="")

            classifier = RiskClassifier(org_keywords=task.org_keywords)
            query_db = self._create_session()
            providers = _build_provider_list(task, self.pw_client)
            remaining_limit = max(int(task.max_results or 0), 0)
            query_total = 0
            query_failed = False

            async def record_cb(data): await self._handle_manual_clue(task_id, classifier, data, db)
            async def resume_cb(): await self._handle_resume_signal()
            async def finish_cb(): await self._handle_finish_signal()

            try:
                for provider in providers:
                    if remaining_limit <= 0:
                        break
                    try:
                        results = await asyncio.wait_for(
                            provider.search(
                                query=query,
                                max_results=remaining_limit,
                                max_pages=task.max_pages,
                                record_callback=record_cb,
                                resume_callback=resume_cb,
                                finish_callback=finish_cb,
                                service=self,
                                task_id=task_id,
                                db=query_db,
                            ),
                            timeout=600.0 if not self.headless else 60.0,
                        )
                        for item in results:
                            file_type = _infer_file_type(item.url, getattr(item, "file_type", None))
                            if not _matches_task_filters(task, file_type):
                                continue
                            existing = query_db.query(ExposureSearchResult).filter(
                                ExposureSearchResult.task_id == task_id,
                                ExposureSearchResult.url == item.url,
                            ).first()
                            if not existing:
                                risk_tags, matched_keywords = classifier.classify(item.title, item.url, item.snippet or "")
                                query_db.add(
                                    ExposureSearchResult(
                                        task_id=task_id,
                                        source=item.source,
                                        query=query,
                                        title=item.title,
                                        url=item.url,
                                        snippet=item.snippet,
                                        file_type=file_type,
                                        risk_tags=risk_tags,
                                        matched_keywords=matched_keywords,
                                        raw_payload=item.raw_payload,
                                        status="pending",
                                    )
                                )
                                query_total += 1
                                remaining_limit -= 1
                                if remaining_limit <= 0:
                                    break
                        query_db.commit()
                    except Exception as exc:
                        query_db.rollback()
                        await self._update_query_plan_item(
                            task_id,
                            query,
                            status="failed",
                            results_count=query_total,
                            error_message=str(exc),
                            error_category=_categorize_query_error(str(exc)),
                        )
                        query_failed = True
                        break
            finally:
                query_db.close()

            if not query_failed:
                await self._update_query_plan_item(
                    task_id,
                    query,
                    status="completed",
                    results_count=query_total,
                    error_message="",
                    error_category="",
                )
                self.sync_task_counts(db, task_id)
        finally:
            db.close()

    @staticmethod
    def build_task_schema(task: ExposureSearchTask):
        from app.schemas.exposure_search import ExposureSearchTaskSchema

        payload = ExposureSearchTaskSchema.model_validate(task)
        derived = _derive_progress_fields(task)
        for key, value in derived.items():
            setattr(payload, key, value)
        return payload

    async def _handle_manual_clue(self, task_id: str, classifier: RiskClassifier, data: dict, _unused_db: Session | None = None):
        """Callback for manual capture from the browser. Uses its own session for thread safety."""
        db = _unused_db or self.db or SessionLocal()
        owns_session = db is not (_unused_db or self.db)
        try:
            url = data.get("url")
            if not url: return
            
            existing = db.query(ExposureSearchResult).filter(
                ExposureSearchResult.task_id == task_id,
                ExposureSearchResult.url == url
            ).first()
            
            if not existing:
                title = data.get("title", "Manual Capture")
                snippet = data.get("snippet", "")
                source_page = data.get("source_page", "unknown")
                query = data.get("query") or f"Manual Capture from {source_page}"
                risk_tags, matched_keywords = classifier.classify(title, url, snippet)
                
                res = ExposureSearchResult(
                    task_id=task_id, source="manual", query=query,
                    title=title, url=url, snippet=snippet, risk_tags=risk_tags, matched_keywords=matched_keywords,
                    raw_payload={"manual": True, "source_page": source_page}, status="valid"
                )
                db.add(res)
                # Re-query task to update counts
                task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
                if task:
                    task.total_results += 1
                    task.valid_count += 1
                db.commit()
                logger.info(f"[RPC] Manual clue saved: {url} (Task: {task_id})")
            else:
                logger.info(f"[RPC] Manual clue skipped (exists): {url}")
        except Exception as e:
            logger.error(f"[RPC] Error in _handle_manual_clue: {e}")
            db.rollback()
        finally:
            if owns_session:
                db.close()

    async def _handle_resume_signal(self):
        """Callback for manual resume signal from the browser."""
        logger.info("Received manual resume signal from browser.")
        self.resume_event.set()

    async def _handle_finish_signal(self):
        """Callback for leaving the current intervention page and continuing to next query/page."""
        logger.info("Received finish-current-query signal from browser.")
        self.finish_query_event.set()

    @staticmethod
    def sync_task_counts(db: Session, task_id: str):
        """Recalculate all counts for a task from the results table to ensure sync."""
        try:
            from sqlalchemy import func
            task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
            if not task: return

            task.total_results = db.query(func.count(ExposureSearchResult.id)).filter(
                ExposureSearchResult.task_id == task_id
            ).scalar() or 0

            task.valid_count = db.query(func.count(ExposureSearchResult.id)).filter(
                ExposureSearchResult.task_id == task_id,
                ExposureSearchResult.status == "valid"
            ).scalar() or 0

            task.ignored_count = db.query(func.count(ExposureSearchResult.id)).filter(
                ExposureSearchResult.task_id == task_id,
                ExposureSearchResult.status == "ignored"
            ).scalar() or 0

            task.imported_count = db.query(func.count(ExposureSearchResult.id)).filter(
                ExposureSearchResult.task_id == task_id,
                ExposureSearchResult.status == "imported"
            ).scalar() or 0

            db.commit()
            return task
        except Exception as e:
            logger.error(f"Error syncing task counts for {task_id}: {e}")
            db.rollback()

    @staticmethod
    def sync_task_query_plan_counts(db: Session, task_id: str):
        try:
            task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
            if not task or not isinstance(task.query_plan, list):
                return task

            rows = (
                db.query(ExposureSearchResult.query, func.count(ExposureSearchResult.id))
                .filter(ExposureSearchResult.task_id == task_id)
                .group_by(ExposureSearchResult.query)
                .all()
            )
            counts = {query: int(count or 0) for query, count in rows}
            updated_plan = []
            seen_queries: set[str] = set()
            for item in task.query_plan:
                current = dict(item or {})
                query_text = str(current.get("query") or "")
                current["results_count"] = counts.get(query_text, 0)
                seen_queries.add(query_text)
                updated_plan.append(current)
            for query_text, count in counts.items():
                if query_text in seen_queries:
                    continue
                updated_plan.append(
                    {
                        "query": query_text,
                        "status": "completed",
                        "results_count": count,
                    }
                )
            task.query_plan = updated_plan
            db.commit()
            return task
        except Exception as e:
            logger.error(f"Error syncing task query-plan counts for {task_id}: {e}")
            db.rollback()
            return None

    def stop_check(self, task_id: str, db: Session) -> bool:
        """Check if the task has been stopped by re-querying the DB."""
        try:
            db.expire_all()
            task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
            if task and task.status in ["stopping", "stopped"]:
                return True
        except Exception as e:
            logger.error(f"Error in stop_check: {e}")
        return False

    async def request_intervention(self, page: Any, task_id: str, db: Session):
        """Called by providers to request user intervention when stuck."""
        if self.headless: return False
        
        self.resume_event.clear()
        self.finish_query_event.clear()
        logger.warning(f"Intervention required for {page.url}. Waiting for user signal...")
        try:
            start_time = asyncio.get_running_loop().time()
            while (asyncio.get_running_loop().time() - start_time) < 600.0: # 10 mins max
                if self.finish_query_event.is_set():
                    logger.info(
                        "Finish-current-query signal received for task=%s page=%s -> skip blocked page and continue to next query/page",
                        task_id,
                        getattr(page, "url", ""),
                    )
                    return "finish"
                if self.resume_event.is_set():
                    logger.info(
                        "Resume signal received for task=%s page=%s -> continue current query/page",
                        task_id,
                        getattr(page, "url", ""),
                    )
                    return True
                if self.stop_check(task_id, db):
                    logger.info("Stop signal detected during intervention.")
                    return False
                await asyncio.sleep(1.0)
            
            logger.warning("Intervention timeout reached.")
            return False
        except Exception as e:
            logger.error(f"Error in request_intervention: {e}")
            return False

    async def run_task(self, task_id: str):
        # Use an injected session in tests, otherwise create a dedicated background session.
        db = self.db or SessionLocal()
        owns_session = self.db is None
        try:
            task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
            if not task:
                logger.error(f"Task {task_id} not found in background session")
                return

            task.status = "running"
            task.started_at = datetime.utcnow()
            db.commit()

            builder = QueryBuilder(
                org_keywords=task.org_keywords,
                title_keywords=task.title_keywords,
                url_keywords=task.url_keywords,
                file_types=task.file_types,
                sites=["pan.baidu.com", "docs.google.com", "drive.google.com", "onedrive.live.com"] if "web_disk" in task.sources else []
            )
            queries = builder.build_queries()
            task.query_plan = [{"query": q, "status": "pending", "results_count": 0} for q in queries]
            db.commit()

            classifier = RiskClassifier(org_keywords=task.org_keywords)
            
            async def record_cb(data): await self._handle_manual_clue(task_id, classifier, data, db)
            async def resume_cb(): await self._handle_resume_signal()
            async def finish_cb(): await self._handle_finish_signal()

            providers = _build_provider_list(task, self.pw_client)

            async def process_query(query_item):
                query = query_item["query"]
                await self._update_query_plan_item(task_id, query, status="running")

                query_total = 0
                remaining_limit = max(int(task.max_results or 0), 0)
                query_failed = False
                query_db = self._create_session()
                async with self.semaphore:
                    try:
                        for provider in providers:
                            if self.stop_check(task_id, query_db):
                                return
                            if remaining_limit <= 0:
                                break

                            try:
                                results = await asyncio.wait_for(
                                    provider.search(
                                        query=query,
                                    max_results=remaining_limit,
                                    max_pages=task.max_pages,
                                    record_callback=record_cb,
                                    resume_callback=resume_cb,
                                    finish_callback=finish_cb,
                                    service=self,
                                    task_id=task_id,
                                    db=query_db,
                                    ),
                                    timeout=600.0 if not self.headless else 60.0
                                )

                                for item in results:
                                    if self.stop_check(task_id, query_db):
                                        break
                                    file_type = _infer_file_type(item.url, getattr(item, "file_type", None))
                                    if not _matches_task_filters(task, file_type):
                                        continue
                                    existing = query_db.query(ExposureSearchResult).filter(
                                        ExposureSearchResult.task_id == task_id, ExposureSearchResult.url == item.url
                                    ).first()
                                    if not existing:
                                        risk_tags, matched_keywords = classifier.classify(item.title, item.url, item.snippet or "")
                                        res = ExposureSearchResult(
                                            task_id=task_id, source=item.source, query=query,
                                            title=item.title, url=item.url, snippet=item.snippet, file_type=file_type,
                                            risk_tags=risk_tags, matched_keywords=matched_keywords,
                                            raw_payload=item.raw_payload, status="pending"
                                        )
                                        query_db.add(res)
                                        query_total += 1
                                        remaining_limit -= 1
                                        if remaining_limit <= 0:
                                            break
                                query_db.commit()
                                self.sync_task_counts(query_db, task_id)
                            except Exception as e:
                                query_db.rollback()
                                logger.warning(f"Provider {provider.name} failed for query {query}: {e}")
                                await self._update_query_plan_item(
                                    task_id,
                                    query,
                                    status="failed",
                                    results_count=query_total,
                                    error_message=str(e),
                                    error_category=_categorize_query_error(str(e)),
                                )
                                query_failed = True
                                break
                    finally:
                        query_db.close()

                if not query_failed:
                    await self._update_query_plan_item(
                        task_id,
                        query,
                        status="completed",
                        results_count=query_total,
                        error_message="",
                        error_category="",
                    )

            # Execute queries
            if not self.headless:
                for q_item in task.query_plan:
                    if self.stop_check(task_id, db):
                        break
                    await process_query(q_item)
            else:
                query_tasks = [process_query(q_item) for q_item in task.query_plan]
                for q_task in asyncio.as_completed(query_tasks):
                    await q_task
                    if self.stop_check(task_id, db):
                        break

            # Finalize task status
            db.expire_all()
            task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
            if task.status == "stopping":
                task.status = "stopped"
            else:
                task.status = "completed"
            task.finished_at = datetime.utcnow()
            query_plan = task.query_plan if isinstance(task.query_plan, list) else []
            task.query_plan = [
                {
                    **dict(item or {}),
                    "status": ("completed" if (item or {}).get("status") == "running" else (item or {}).get("status")),
                }
                for item in query_plan
            ]
            db.commit()
            self.sync_task_counts(db, task_id)
            logger.info(f"Task {task_id} finished with status: {task.status}")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            try:
                # Attempt to mark as failed in DB
                db.rollback()
                task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
                if task:
                    task.status = "failed"
                    task.error_message = str(e)
                    task.finished_at = datetime.utcnow()
                    db.commit()
            except: pass
        finally:
            await self.pw_client.stop()
            if owns_session:
                db.close()
