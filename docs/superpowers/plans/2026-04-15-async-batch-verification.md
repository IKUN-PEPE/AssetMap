# Migrate Asset Verification to Concurrent Async Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the asset mass-verification backend pipeline (status code fetching + screenshotting) to use native `asyncio`, eliminating multi-threading overhead and vastly improving concurrency.

**Architecture:**
- Create an async `async_playwright` worker pool using `asyncio.Semaphore`.
- Convert the verification loop in `start_verify_task` to an `async def` and dispatch with `asyncio.create_task` instead of a Python `Thread`.
- Each concurrent worker will instantiate its own database session from `SessionLocal` to prevent SQLAlchemy concurrency exceptions, executing fetching and screenshot processing isolated from other workers, then committing and closing its session.
- We will retain the current memory dictionary `VERIFY_TASKS` for this plan to keep scope tightly on performance.

**Tech Stack:** FastAPI, SQLAlchemy, Playwright (`async_playwright`), `asyncio`

---

### Task 1: Refactor the Status Code Fetcher to Async Playwright

Replace the synchronous `fetch_status_code_with_playwright` with an asynchronous equivalent.

**Files:**
- Modify: `backend/app/api/assets.py`

- [ ] **Step 1: Replace implementation in `assets.py`**

Replace:
```python
from playwright.sync_api import sync_playwright
```
with:
```python
from playwright.async_api import async_playwright
```

Replace `fetch_status_code_with_playwright` with this async version:
```python
async def fetch_status_code_with_playwright(context, url: str) -> int | None:
    page = await context.new_page()
    try:
        response = await page.goto(url, wait_until="commit", timeout=8000)
        return response.status if response else None
    except Exception as exc:
        logger.debug("Fetch status code failed for %s: %s", url, exc)
        return None
    finally:
        await page.close()
```

- [ ] **Step 2: Remove old Synchronous Bridge code**

Delete the `run_coroutine_sync` wrapper entirely. In `assets.py`, delete this exact block:
```python
def run_coroutine_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, object] = {}
    error: dict[str, BaseException] = {}

    def runner():
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            error["value"] = exc

    thread = Thread(target=runner)
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result.get("value")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/assets.py
git commit -m "refactor: drop Thread bridge and convert fetch to async playwright"
```

---

### Task 2: Refactor Screenshot Capture to Native Async

Rewrite `capture_asset_screenshot` into an `async def` that directly `await`s the screenshot job without utilizing `run_coroutine_sync`.

**Files:**
- Modify: `backend/app/api/assets.py`

- [ ] **Step 1: Rewrite implementation**

In `backend/app/api/assets.py`, replace `capture_asset_screenshot` with:
```python
async def capture_asset_screenshot_async(asset: WebEndpoint) -> str:
    output_dir = Path(settings.screenshot_output_dir)
    result_csv = Path(settings.result_output_dir) / "assetmap_results.csv"
    summary_txt = Path(settings.result_output_dir) / "assetmap_summary.txt"
    
    await run_screenshot_job(
        asset_rows=[
            {
                "seq": asset.id,
                "host": asset.domain or asset.normalized_url,
                "title": asset.title or "未命名",
                "url": asset.normalized_url,
            }
        ],
        output_dir=output_dir,
        result_csv=result_csv,
        summary_txt=summary_txt,
        skip_existing=False,
    )
    
    file_name = build_output_filename(asset.id, asset.title or "未命名", asset.normalized_url)
    return str(output_dir / file_name)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/assets.py
git commit -m "refactor: rewrite capture screenshot to native async definition"
```

---

### Task 3: Implement Async Asset Processor Worker

Create the standalone async worker factory `process_one_asset` which isolates state per asset, runs both URL fetching and screenshot capture, and manages its own Database session lifecycle.

**Files:**
- Modify: `backend/app/api/assets.py`

- [ ] **Step 1: Define `process_one_asset` coroutine**

Below `capture_asset_screenshot_async` in `backend/app/api/assets.py`, insert:

```python
async def process_one_asset(
    asset_id: str,
    asset_url: str,
    verified: bool,
    context,
    task: SimpleNamespace,
    semaphore: asyncio.Semaphore
):
    async with semaphore:
        if task.cancel_requested:
            return

        db = SessionLocal()
        try:
            asset = db.get(WebEndpoint, asset_id)
            if not asset:
                return

            asset.verified = verified
            status_code = await fetch_status_code_with_playwright(context, asset_url)
            
            if status_code is None:
                task.failed += 1
                asset.status_code = None
            else:
                asset.status_code = status_code
                task.success += 1

            try:
                screenshot_path = await capture_asset_screenshot_async(asset)
                asset.screenshot_status = "success"
                db.query(Screenshot).filter(Screenshot.web_endpoint_id == asset.id).delete(synchronize_session=False)
                db.add(
                    Screenshot(
                        web_endpoint_id=asset.id,
                        file_name=Path(screenshot_path).name,
                        object_path=screenshot_path,
                        status="success",
                    )
                )
            except Exception:
                asset.screenshot_status = "failed"
                logger.warning("Capture screenshot failed url=%s asset_id=%s", asset_url, asset.id, exc_info=True)

            db.commit()
            task.processed += 1
            task.message = f"正在验证并截图 {task.processed} / {task.total}"

            if task.cancel_requested:
                task.status = "cancelled"
                task.message = f"已取消，已处理 {task.processed} / {task.total}"

        except Exception:
            db.rollback()
            logger.warning("Process single asset failed asset_id=%s", asset_id, exc_info=True)
            task.failed += 1
            task.processed += 1
        finally:
            db.close()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/assets.py
git commit -m "feat: implement per-asset isolated db session async worker"
```

---

### Task 4: Rewrite Pipeline Coordinator and Remove Thread

Tie everything together: rewrite `start_verify_task` into an Async version that builds a `Semaphore`, starts `async_playwright`, dispatches tasks via `asyncio.gather`, and finally hook it up properly in the POST `/verify-batch` route via `asyncio.create_task`. Remove the deprecated imports like `Thread`.

**Files:**
- Modify: `backend/app/api/assets.py`

- [ ] **Step 1: Rewrite `start_verify_task`**

Replace `def start_verify_task(task: SimpleNamespace, asset_ids: list[str], verified: bool):` with its async version:

```python
async def start_verify_task_async(task: SimpleNamespace, asset_ids: list[str], verified: bool, assets_data: list[tuple[str, str]]):
    task.status = "running"
    
    semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent browser tabs
    
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=True)
            try:
                process_tasks = []
                for asset_id, url in assets_data:
                    process_tasks.append(
                        process_one_asset(asset_id, url, verified, context, task, semaphore)
                    )
                
                await asyncio.gather(*process_tasks)

                if task.status != "cancelled":
                    task.status = "completed"
                    task.message = "验证并截图完成"
            finally:
                await context.close()
                await browser.close()
    except Exception:
        task.status = "failed"
        task.message = "验证失败"
        logger.warning("Verify task failed task_id=%s", task.task_id, exc_info=True)
```

- [ ] **Step 2: Hook up POST Route and Clean Imports**

In `assets.py`, modify `@router.post("/verify-batch")`:

```python
@router.post("/verify-batch")
def verify_assets(payload: VerifyBatchRequest, db: Session = Depends(get_db)):
    assets = db.query(WebEndpoint).filter(WebEndpoint.id.in_(payload.asset_ids)).all()
    # Cache ID and URL to pass into async task without keeping objects attached to main session
    assets_data = [(a.id, a.normalized_url) for a in assets]
    
    task = SimpleNamespace(
        task_id=str(uuid4()),
        task_type="asset_verify",
        status="pending",
        total=len(assets),
        processed=0,
        success=0,
        failed=0,
        message=f"正在验证 0 / {len(assets)}",
        cancel_requested=False,
    )
    VERIFY_TASKS[task.task_id] = task
    
    # Fire and forget async task
    asyncio.create_task(start_verify_task_async(task, payload.asset_ids, payload.verified, assets_data))
    
    return {"task_id": task.task_id, "status": task.status}
```

Remove `from threading import Thread` from imports at the top of the file.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/assets.py
git commit -m "refactor: switch task runner to asyncio gather instead of daemon thread"
```
