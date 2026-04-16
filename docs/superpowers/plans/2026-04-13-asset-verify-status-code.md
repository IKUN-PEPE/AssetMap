# Asset Verify Status Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing batch asset verify action actually request each asset URL and write back status codes so the asset list shows verification results after refresh.

**Architecture:** Reuse the existing `POST /api/v1/assets/verify-batch` endpoint and extend it from a pure flag update into synchronous URL verification with per-asset success/failure accounting. Keep the frontend flow intact: call the same API, then refresh the asset list, while tightening button and success-copy so the behavior matches what the user sees.

**Tech Stack:** FastAPI, SQLAlchemy, Python, requests/httpx-compatible HTTP client already used by the backend if present, Vue 3, TypeScript, Element Plus, pytest

---

## File Map

### Backend
- Modify: `backend/app/api/assets.py` — replace the current verify-batch flag-only behavior with real URL verification and summary stats
- Create or modify: `backend/tests/test_verify_batch.py` — focused tests for success, partial failure, and response summary
- Possible read-only reference: existing HTTP utilities already present in `backend/app/services/**` if the repo already standardizes outbound web requests

### Frontend
- Modify: `frontend/src/views/AssetsView.vue` — update button label and success toast copy
- Modify: `frontend/src/api/modules/assets.ts` — type the verify response if needed
- Modify: `frontend/src/types/index.ts` — add frontend result type if needed

---

### Task 1: Add failing backend tests for real verify-batch behavior

**Files:**
- Create: `backend/tests/test_verify_batch.py`
- Modify: `backend/app/api/assets.py:92-98` later in the next task

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_verify_batch.py` with this minimal failing test first:

```python
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.api.assets import VerifyBatchRequest

client = TestClient(app)


def test_verify_batch_returns_success_and_failed_counts(monkeypatch):
    fake_response = Mock(status_code=200)

    with patch("app.api.assets.fetch_status_code", side_effect=[200, None]):
        response = client.post(
            "/api/v1/assets/verify-batch",
            json={"asset_ids": ["asset-success", "asset-fail"], "verified": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] == 1
    assert data["failed"] == 1
```
```

Because the route depends on real DB rows, finish the test file with a lightweight database override pattern that already matches this repo’s testing style. Use an in-memory test session or monkeypatch the query path so that two fake assets with `id` and `normalized_url` exist.

Recommended concrete test shape:

```python
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.api import assets as assets_api

client = TestClient(app)


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.items


class FakeDB:
    def __init__(self, items):
        self.items = items
        self.committed = False

    def query(self, _model):
        return FakeQuery(self.items)

    def commit(self):
        self.committed = True


def test_verify_batch_returns_success_and_failed_counts():
    assets = [
        SimpleNamespace(id="asset-success", normalized_url="https://ok.example", verified=False, status_code=None),
        SimpleNamespace(id="asset-fail", normalized_url="https://fail.example", verified=False, status_code=None),
    ]
    fake_db = FakeDB(assets)

    app.dependency_overrides[assets_api.get_db] = lambda: iter([fake_db])
    try:
        with patch("app.api.assets.fetch_status_code", side_effect=[200, None]):
            response = client.post(
                "/api/v1/assets/verify-batch",
                json={"asset_ids": ["asset-success", "asset-fail"], "verified": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"updated": 2, "verified": True, "success": 1, "failed": 1}
    assert assets[0].status_code == 200
    assert assets[0].verified is True
    assert assets[1].status_code is None
    assert assets[1].verified is True
    assert fake_db.committed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_batch.py::test_verify_batch_returns_success_and_failed_counts" -v
```

Expected: FAIL because `app.api.assets.fetch_status_code` does not exist and the route currently does not return `success` / `failed` counts.

- [ ] **Step 3: Write minimal implementation target sketch**

Do not change production code yet beyond the absolute minimum needed for the next step. The target behavior is:

```python
def fetch_status_code(url: str) -> int | None:
    ...

@router.post("/verify-batch")
def verify_assets(payload: VerifyBatchRequest, db: Session = Depends(get_db)):
    ...
    return {"updated": len(assets), "verified": payload.verified, "success": success_count, "failed": failed_count}
```

- [ ] **Step 4: Re-run test after implementation and verify it passes**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_batch.py::test_verify_batch_returns_success_and_failed_counts" -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_verify_batch.py backend/app/api/assets.py
git commit -m "test: cover verify batch status code updates"
```

---

### Task 2: Implement backend URL verification and summary response

**Files:**
- Modify: `backend/app/api/assets.py`
- Test: `backend/tests/test_verify_batch.py`

- [ ] **Step 1: Write the next failing test for non-blocking partial failure**

Add this second test to `backend/tests/test_verify_batch.py`:

```python
def test_verify_batch_continues_when_one_asset_request_raises():
    assets = [
        SimpleNamespace(id="asset-1", normalized_url="https://boom.example", verified=False, status_code=None),
        SimpleNamespace(id="asset-2", normalized_url="https://ok.example", verified=False, status_code=None),
    ]
    fake_db = FakeDB(assets)

    app.dependency_overrides[assets_api.get_db] = lambda: iter([fake_db])
    try:
        with patch("app.api.assets.fetch_status_code", side_effect=[RuntimeError("network"), 204]):
            response = client.post(
                "/api/v1/assets/verify-batch",
                json={"asset_ids": ["asset-1", "asset-2"], "verified": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["success"] == 1
    assert response.json()["failed"] == 1
    assert assets[0].status_code is None
    assert assets[1].status_code == 204
    assert assets[0].verified is True
    assert assets[1].verified is True
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_batch.py::test_verify_batch_continues_when_one_asset_request_raises" -v
```

Expected: FAIL until the route catches per-asset exceptions and continues.

- [ ] **Step 3: Write minimal implementation**

Update `backend/app/api/assets.py` with a focused helper plus route logic. Add imports first:

```python
import logging

import requests
```

Add module logger near the router:

```python
logger = logging.getLogger(__name__)
```

Add helper above the route:

```python
def fetch_status_code(url: str) -> int | None:
    response = requests.get(url, timeout=8, allow_redirects=True)
    return response.status_code
```

Then replace the body of `verify_assets()` with:

```python
@router.post("/verify-batch")
def verify_assets(payload: VerifyBatchRequest, db: Session = Depends(get_db)):
    assets = db.query(WebEndpoint).filter(WebEndpoint.id.in_(payload.asset_ids)).all()
    success_count = 0
    failed_count = 0

    for asset in assets:
        asset.verified = payload.verified
        try:
            status_code = fetch_status_code(asset.normalized_url)
        except Exception:
            status_code = None
            failed_count += 1
            logger.warning("Verify asset failed url=%s asset_id=%s", asset.normalized_url, asset.id, exc_info=True)
        else:
            asset.status_code = status_code
            success_count += 1

        if status_code is None:
            asset.status_code = None

    db.commit()
    return {
        "updated": len(assets),
        "verified": payload.verified,
        "success": success_count,
        "failed": failed_count,
    }
```

This is intentionally minimal: one helper, one loop, one commit, no retry layer.

- [ ] **Step 4: Run focused tests to verify they pass**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_batch.py" -v
```

Expected: PASS for both tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/assets.py backend/tests/test_verify_batch.py
git commit -m "feat: verify assets and update status codes"
```

---

### Task 3: Type the frontend verify response and update action copy

**Files:**
- Modify: `frontend/src/api/modules/assets.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/views/AssetsView.vue`

- [ ] **Step 1: Write the failing frontend type usage**

In `frontend/src/views/AssetsView.vue`, change the verify action to use the returned counts before the type exists:

```ts
const result = await verifyAssets(selectedIds.value)
ElMessage.success(`批量验证完成，成功 ${result.success} 条，失败 ${result.failed} 条`)
```

Also change the button copy in the template to:

```vue
<el-button type="success" @click="triggerVerify" :disabled="selectedIds.length === 0">批量验证并获取状态码</el-button>
```

- [ ] **Step 2: Run build to verify it fails**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: FAIL because `verifyAssets()` is not yet typed to expose `success` / `failed`.

- [ ] **Step 3: Write minimal implementation**

Add to `frontend/src/types/index.ts`:

```ts
export interface VerifyAssetsResult {
  updated: number
  verified: boolean
  success: number
  failed: number
}
```

Update `frontend/src/api/modules/assets.ts`:

```ts
import type { AssetItem, VerifyAssetsResult } from '@/types'

export async function verifyAssets(asset_ids: string[]) {
  const { data } = await http.post<VerifyAssetsResult>('/api/v1/assets/verify-batch', { asset_ids, verified: true })
  return data
}
```

Update `frontend/src/views/AssetsView.vue` in `triggerVerify()`:

```ts
async function triggerVerify() {
  try {
    const result = await verifyAssets(selectedIds.value)
    ElMessage.success(`批量验证完成，成功 ${result.success} 条，失败 ${result.failed} 条`)
    await loadAssets()
  } catch {
    ElMessage.error('资产验证失败')
  }
}
```

And update the template button label:

```vue
<el-button type="success" @click="triggerVerify" :disabled="selectedIds.length === 0">批量验证并获取状态码</el-button>
```

- [ ] **Step 4: Run build to verify it passes**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/modules/assets.ts frontend/src/views/AssetsView.vue
git commit -m "feat: show verify batch result counts"
```

---

### Task 4: Final verification for end-to-end behavior

**Files:**
- Verify: `backend/app/api/assets.py`
- Verify: `frontend/src/views/AssetsView.vue`
- Test: `backend/tests/test_verify_batch.py`

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

- [ ] **Step 3: Manually verify the user flow**

Start the app and confirm the UI behavior:

```bash
python "C:/Users/Administrator/VScode/AssetMap/main.py"
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run dev
```

Manual checks:
- Open the asset list page
- Confirm the button now says `批量验证并获取状态码`
- Select at least two assets
- Click the verify button
- Confirm the toast reports `成功 X 条，失败 Y 条`
- Confirm the table refreshes
- Confirm successful assets now show status codes in the `状态码` column
- Confirm a failed asset does not prevent the batch from finishing

- [ ] **Step 4: Commit the verified final state**

```bash
git add backend/app/api/assets.py backend/tests/test_verify_batch.py frontend/src/api/modules/assets.ts frontend/src/types/index.ts frontend/src/views/AssetsView.vue
git commit -m "feat: batch verify assets and fetch status codes"
```

- [ ] **Step 5: Request review**

After all tests and manual checks pass, use the normal review workflow before merge.
