# Playwright Asset Verify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current requests-based asset status-code verification with a Playwright-based navigation check while keeping the existing verify-batch API and frontend flow intact.

**Architecture:** Keep `POST /api/v1/assets/verify-batch` as the single entry point, but swap the internal verification helper so it reuses one Playwright browser instance, opens one page per asset, and reads the main document response status for each URL. Preserve the existing frontend API call, result toast, and list refresh behavior so only the verification engine changes.

**Tech Stack:** FastAPI, SQLAlchemy, Python, Playwright for Python, Vue 3, TypeScript, Element Plus, pytest

---

## File Map

### Backend
- Modify: `backend/app/api/assets.py` — replace `requests` verification helper with Playwright verification helper and keep route response shape stable
- Modify: `backend/tests/test_verify_batch.py` — change backend tests to mock the Playwright-based helper instead of the requests-based behavior assumptions
- Possible reference: any existing Playwright-backed screenshot or browser automation code already present under `backend/app/services/screenshot/**`

### Frontend
- Usually no functional change required if current button copy and success toast already match the route response
- Verify only: `frontend/src/views/AssetsView.vue`
- Verify only: `frontend/src/api/modules/assets.ts`

---

### Task 1: Add a failing test for Playwright-backed verify helper behavior

**Files:**
- Modify: `backend/tests/test_verify_batch.py`
- Modify later: `backend/app/api/assets.py`

- [ ] **Step 1: Write the failing test**

Add this focused helper test to `backend/tests/test_verify_batch.py` first:

```python
from unittest.mock import MagicMock

from app.api.assets import fetch_status_code_with_playwright


def test_fetch_status_code_with_playwright_returns_main_document_status():
    page = MagicMock()
    response = MagicMock(status=302)
    page.goto.return_value = response
    browser = MagicMock()
    browser.new_page.return_value = page

    status_code = fetch_status_code_with_playwright(browser, "https://example.com")

    assert status_code == 302
    page.goto.assert_called_once_with("https://example.com", wait_until="domcontentloaded", timeout=8000)
    page.close.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_batch.py::test_fetch_status_code_with_playwright_returns_main_document_status" -v
```

Expected: FAIL because `fetch_status_code_with_playwright` does not exist yet.

- [ ] **Step 3: Write minimal implementation target sketch**

The production target is a helper with this exact shape:

```python
def fetch_status_code_with_playwright(browser, url: str) -> int | None:
    page = browser.new_page()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=8000)
        return response.status if response else None
    finally:
        page.close()
```

Do not change route logic yet beyond what is required for the helper to exist.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_batch.py::test_fetch_status_code_with_playwright_returns_main_document_status" -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_verify_batch.py backend/app/api/assets.py
git commit -m "test: cover playwright status fetch helper"
```

---

### Task 2: Switch verify-batch from requests to Playwright

**Files:**
- Modify: `backend/app/api/assets.py`
- Test: `backend/tests/test_verify_batch.py`

- [ ] **Step 1: Write the failing route test against the new helper name**

Update existing route tests in `backend/tests/test_verify_batch.py` so they patch the new helper rather than the old one:

```python
with patch("app.api.assets.fetch_status_code_with_playwright", side_effect=[200, None]):
```

and:

```python
with patch("app.api.assets.fetch_status_code_with_playwright", side_effect=[RuntimeError("network"), 204]):
```

Also add a new assertion that browser startup is attempted exactly once by patching the Playwright context manager entry point:

```python
with patch("app.api.assets.sync_playwright") as sync_playwright_mock:
    playwright_manager = MagicMock()
    playwright = MagicMock()
    browser = MagicMock()
    playwright.chromium.launch.return_value = browser
    playwright_manager.__enter__.return_value = playwright
    sync_playwright_mock.return_value = playwright_manager
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_batch.py" -v
```

Expected: FAIL because the route still calls the old requests-based helper and does not create a Playwright browser.

- [ ] **Step 3: Write minimal implementation**

Update imports at the top of `backend/app/api/assets.py`:

```python
import logging
from pathlib import Path, PurePosixPath

from playwright.sync_api import sync_playwright
from fastapi import APIRouter, Depends, HTTPException
```

Remove the `requests` import.

Add the new helper near `fetch_status_code`’s current location and replace the old helper entirely:

```python
def fetch_status_code_with_playwright(browser, url: str) -> int | None:
    page = browser.new_page()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=8000)
        return response.status if response else None
    finally:
        page.close()
```

Then replace the route body with a single-browser flow:

```python
@router.post("/verify-batch")
def verify_assets(payload: VerifyBatchRequest, db: Session = Depends(get_db)):
    assets = db.query(WebEndpoint).filter(WebEndpoint.id.in_(payload.asset_ids)).all()
    success_count = 0
    failed_count = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for asset in assets:
                asset.verified = payload.verified
                try:
                    status_code = fetch_status_code_with_playwright(browser, asset.normalized_url)
                except Exception:
                    status_code = None
                    failed_count += 1
                    logger.warning("Verify asset failed url=%s asset_id=%s", asset.normalized_url, asset.id, exc_info=True)
                else:
                    if status_code is None:
                        failed_count += 1
                    else:
                        asset.status_code = status_code
                        success_count += 1

                if status_code is None:
                    asset.status_code = None
        finally:
            browser.close()

    db.commit()
    return {
        "updated": len(assets),
        "verified": payload.verified,
        "success": success_count,
        "failed": failed_count,
    }
```

This keeps behavior the same except for the verification engine.

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_batch.py" -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/assets.py backend/tests/test_verify_batch.py
git commit -m "feat: verify assets with playwright"
```

---

### Task 3: Add a failing test for missing main-document response handling

**Files:**
- Modify: `backend/tests/test_verify_batch.py`
- Modify later: `backend/app/api/assets.py`

- [ ] **Step 1: Write the failing test**

Add a helper test for the “no response object” case:

```python
def test_fetch_status_code_with_playwright_returns_none_when_no_response():
    page = MagicMock()
    page.goto.return_value = None
    browser = MagicMock()
    browser.new_page.return_value = page

    status_code = fetch_status_code_with_playwright(browser, "https://example.com")

    assert status_code is None
    page.close.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails or confirms gap**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_batch.py::test_fetch_status_code_with_playwright_returns_none_when_no_response" -v
```

Expected: If helper already handles `None`, it should PASS immediately and confirm the edge case is covered. If not, it FAILS and you must fix the helper before continuing.

- [ ] **Step 3: Write minimal implementation if needed**

Ensure the helper remains exactly this:

```python
def fetch_status_code_with_playwright(browser, url: str) -> int | None:
    page = browser.new_page()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=8000)
        return response.status if response else None
    finally:
        page.close()
```

- [ ] **Step 4: Run the helper tests together**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_batch.py::test_fetch_status_code_with_playwright_returns_main_document_status" "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_batch.py::test_fetch_status_code_with_playwright_returns_none_when_no_response" -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_verify_batch.py backend/app/api/assets.py
git commit -m "test: cover playwright response edge case"
```

---

### Task 4: Final verification of Playwright-backed verify flow

**Files:**
- Verify: `backend/app/api/assets.py`
- Verify: `backend/tests/test_verify_batch.py`
- Verify only: `frontend/src/views/AssetsView.vue`
- Verify only: `frontend/src/api/modules/assets.ts`

- [ ] **Step 1: Run backend tests**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_batch.py" "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_health.py" -v
```

Expected: PASS

- [ ] **Step 2: Run frontend build**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: PASS

- [ ] **Step 3: Manual verification**

Start the app and verify the user flow still works with the Playwright-backed backend:

```bash
python "C:/Users/Administrator/VScode/AssetMap/main.py"
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run dev
```

Manual checks:
- Open the asset list page
- Confirm the button still says `批量验证并获取状态码`
- Select at least two assets
- Click the verify button
- Confirm the toast still reports `成功 X 条，失败 Y 条`
- Confirm the table refreshes
- Confirm successful assets show status codes in the `状态码` column
- Confirm a failed asset does not prevent the batch from finishing

- [ ] **Step 4: Commit the verified final state**

```bash
git add backend/app/api/assets.py backend/tests/test_verify_batch.py frontend/src/views/AssetsView.vue frontend/src/api/modules/assets.ts frontend/src/types/index.ts
git commit -m "feat: use playwright for asset verification"
```

- [ ] **Step 5: Request review**

After tests and manual checks pass, use the usual review workflow before merge.
