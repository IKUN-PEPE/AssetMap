# Verify Progress Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real batch-verify task progress bar to the asset list page so users can see processed count, success count, failure count, and completion state while Playwright verification runs.

**Architecture:** Keep the verify action initiated from the asset list, but split it into two backend concerns: create-and-track a lightweight `asset_verify` task record, then update that task as each asset finishes verification. The frontend remains on the asset list page, starts a verify task, polls a task-status endpoint every second, and renders a local progress bar plus summary text until completion triggers a list refresh.

**Tech Stack:** FastAPI, SQLAlchemy, Python, Playwright for Python, Vue 3, TypeScript, Element Plus, axios, pytest

---

## File Map

### Backend
- Create or modify: `backend/app/models/job.py` or the most appropriate existing task/job model file — store minimal verify task progress fields if the current collect job model can be reused cleanly
- Create or modify: `backend/app/schemas/job.py` — expose task progress response shape if schemas are already centralized there
- Modify: `backend/app/api/assets.py` — change verify entry point to create and run a tracked asset-verify task instead of only returning final counts
- Modify: `backend/app/api/jobs.py` or create `backend/app/api/tasks.py` — expose a read endpoint for verify task progress
- Test: `backend/tests/test_verify_progress.py` — cover task creation, progress updates, and status lookup

### Frontend
- Modify: `frontend/src/api/modules/assets.ts` — create verify task instead of expecting final synchronous counts immediately
- Modify: `frontend/src/api/modules/jobs.ts` or create `frontend/src/api/modules/tasks.ts` — add task progress polling client
- Modify: `frontend/src/types/index.ts` — add verify task result/progress types
- Modify: `frontend/src/views/AssetsView.vue` — show progress bar, summary text, task status, and polling behavior

---

### Task 1: Add a failing backend test for verify task creation

**Files:**
- Create: `backend/tests/test_verify_progress.py`
- Modify later: `backend/app/api/assets.py`
- Modify later: backend task read endpoint file

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_verify_progress.py` with a focused creation test first:

```python
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import assets as assets_api
from app.main import app

client = TestClient(app)


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.items


class FakeDB:
    def __init__(self, assets, tasks=None):
        self.assets = assets
        self.tasks = tasks or []
        self.committed = False

    def query(self, model):
        return FakeQuery(self.assets)

    def add(self, obj):
        self.tasks.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, _obj):
        return None


def test_verify_batch_returns_task_id_instead_of_final_counts():
    assets = [SimpleNamespace(id="asset-1", normalized_url="https://example.com", verified=False, status_code=None)]
    fake_db = FakeDB(assets)

    app.dependency_overrides[assets_api.get_db] = lambda: fake_db
    try:
        response = client.post(
            "/api/v1/assets/verify-batch",
            json={"asset_ids": ["asset-1"], "verified": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "task_id" in body
    assert body["status"] in {"pending", "running"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_progress.py::test_verify_batch_returns_task_id_instead_of_final_counts" -v
```

Expected: FAIL because `/verify-batch` still returns only final synchronous counts or a mismatched payload.

- [ ] **Step 3: Write minimal implementation target sketch**

The target response shape for the verify start endpoint is:

```python
return {"task_id": task.id, "status": task.status}
```

Do not implement the full task runner yet. Just define this as the contract you are driving toward.

- [ ] **Step 4: Run test after implementing and verify it passes**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_progress.py::test_verify_batch_returns_task_id_instead_of_final_counts" -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_verify_progress.py backend/app/api/assets.py backend/app/models/job.py backend/app/schemas/job.py
git commit -m "test: cover verify task creation"
```

---

### Task 2: Add minimal task storage and progress fields

**Files:**
- Modify: `backend/app/models/job.py` or the existing job model file that already stores long-running job state
- Modify: `backend/app/schemas/job.py`
- Test: `backend/tests/test_verify_progress.py`

- [ ] **Step 1: Write the failing test for progress fields**

Add this test to `backend/tests/test_verify_progress.py`:

```python
def test_verify_task_progress_shape_contains_counts():
    task = SimpleNamespace(
        id="task-1",
        task_type="asset_verify",
        status="running",
        total=5,
        processed=2,
        success=1,
        failed=1,
        message="正在验证 2 / 5",
    )

    payload = assets_api.serialize_verify_task(task)

    assert payload == {
        "task_id": "task-1",
        "task_type": "asset_verify",
        "status": "running",
        "total": 5,
        "processed": 2,
        "success": 1,
        "failed": 1,
        "message": "正在验证 2 / 5",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_progress.py::test_verify_task_progress_shape_contains_counts" -v
```

Expected: FAIL because `serialize_verify_task` and/or task progress fields do not exist yet.

- [ ] **Step 3: Write minimal implementation**

If the current collect job model can be extended safely, add fields there. Otherwise add a focused verify-task model. The minimal shape needed is:

```python
class VerifyTask(Base):
    __tablename__ = "verify_tasks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    task_type: Mapped[str] = mapped_column(String(32), default="asset_verify")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Add a serializer near `backend/app/api/assets.py` if you are keeping this feature local:

```python
def serialize_verify_task(task) -> dict:
    return {
        "task_id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "total": task.total,
        "processed": task.processed,
        "success": task.success,
        "failed": task.failed,
        "message": task.message,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_progress.py::test_verify_task_progress_shape_contains_counts" -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/job.py backend/app/schemas/job.py backend/app/api/assets.py backend/tests/test_verify_progress.py
git commit -m "feat: add verify task progress fields"
```

---

### Task 3: Add a failing backend test for task status polling

**Files:**
- Modify: backend task read endpoint file (`backend/app/api/jobs.py` or new `backend/app/api/tasks.py`)
- Test: `backend/tests/test_verify_progress.py`

- [ ] **Step 1: Write the failing test**

Add this test to `backend/tests/test_verify_progress.py`:

```python
def test_get_verify_task_returns_current_progress():
    task = SimpleNamespace(
        id="task-1",
        task_type="asset_verify",
        status="running",
        total=3,
        processed=2,
        success=1,
        failed=1,
        message="正在验证 2 / 3",
    )

    fake_db = FakeDB(assets=[])
    fake_db.get = lambda _model, _id: task

    app.dependency_overrides[assets_api.get_db] = lambda: fake_db
    try:
        response = client.get("/api/v1/jobs/task-1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["processed"] == 2
    assert response.json()["message"] == "正在验证 2 / 3"
```

Use the exact endpoint you decide to expose for polling; if you create `/api/v1/tasks/{task_id}`, reflect that in the test and later frontend client.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_progress.py::test_get_verify_task_returns_current_progress" -v
```

Expected: FAIL because the current job/task read endpoint does not return verify-task progress in this shape.

- [ ] **Step 3: Write minimal implementation**

If reusing `backend/app/api/jobs.py`, add a branch that recognizes verify-task payloads and returns the progress shape. If using a separate endpoint, implement the focused read route:

```python
@router.get("/{task_id}")
def get_verify_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(VerifyTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return serialize_verify_task(task)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_progress.py::test_get_verify_task_returns_current_progress" -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/jobs.py backend/app/api/tasks.py backend/tests/test_verify_progress.py
git commit -m "feat: add verify task progress endpoint"
```

---

### Task 4: Track progress during Playwright verification

**Files:**
- Modify: `backend/app/api/assets.py`
- Test: `backend/tests/test_verify_progress.py`

- [ ] **Step 1: Write the failing test for progress updates**

Add this focused progression test:

```python
def test_verify_batch_updates_processed_success_and_failed_counts():
    assets = [
        SimpleNamespace(id="asset-1", normalized_url="https://ok.example", verified=False, status_code=None),
        SimpleNamespace(id="asset-2", normalized_url="https://fail.example", verified=False, status_code=None),
    ]
    task = SimpleNamespace(
        id="task-1",
        task_type="asset_verify",
        status="pending",
        total=2,
        processed=0,
        success=0,
        failed=0,
        message="",
    )
    fake_db = FakeDB(assets)
    fake_db.tasks.append(task)

    with patch("app.api.assets.fetch_status_code_with_playwright", side_effect=[200, None]):
        assets_api.run_verify_task(fake_db, task, assets, verified=True, browser_context=MagicMock())

    assert task.status == "completed"
    assert task.processed == 2
    assert task.success == 1
    assert task.failed == 1
    assert task.message == "验证完成"
    assert assets[0].status_code == 200
    assert assets[1].status_code is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_progress.py::test_verify_batch_updates_processed_success_and_failed_counts" -v
```

Expected: FAIL because `run_verify_task` does not exist or does not update progress fields yet.

- [ ] **Step 3: Write minimal implementation**

Extract task-running logic inside `backend/app/api/assets.py`:

```python
def run_verify_task(db, task, assets, verified: bool, browser_context) -> None:
    task.status = "running"
    task.message = f"正在验证 0 / {task.total}"
    db.commit()

    for index, asset in enumerate(assets, start=1):
        asset.verified = verified
        try:
            status_code = fetch_status_code_with_playwright(browser_context, asset.normalized_url)
        except Exception:
            status_code = None
            task.failed += 1
            logger.warning("Verify asset failed url=%s asset_id=%s", asset.normalized_url, asset.id, exc_info=True)
        else:
            if status_code is None:
                task.failed += 1
            else:
                asset.status_code = status_code
                task.success += 1

        if status_code is None:
            asset.status_code = None

        task.processed = index
        task.message = f"正在验证 {task.processed} / {task.total}"
        db.commit()

    task.status = "completed"
    task.message = "验证完成"
    db.commit()
```

Then adjust the route so it creates the task first, creates the Playwright context, runs `run_verify_task(...)`, and returns the task id/status payload.

- [ ] **Step 4: Run focused tests to verify they pass**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_progress.py" -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/assets.py backend/tests/test_verify_progress.py
git commit -m "feat: track verify task progress"
```

---

### Task 5: Add frontend task types and polling client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/modules/assets.ts`
- Modify or create: `frontend/src/api/modules/jobs.ts` or `frontend/src/api/modules/tasks.ts`

- [ ] **Step 1: Write the failing frontend type usage**

In `frontend/src/views/AssetsView.vue`, begin using task-based types before they exist:

```ts
const verifyTask = ref<VerifyTaskProgress | null>(null)
const startResult = await startVerifyTask(selectedIds.value)
verifyTaskId.value = startResult.task_id
```

- [ ] **Step 2: Run build to verify it fails**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: FAIL because task progress types and start/poll API wrappers do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add to `frontend/src/types/index.ts`:

```ts
export interface VerifyTaskStartResult {
  task_id: string
  status: string
}

export interface VerifyTaskProgress {
  task_id: string
  task_type: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  total: number
  processed: number
  success: number
  failed: number
  message?: string | null
}
```

Update `frontend/src/api/modules/assets.ts`:

```ts
import type { AssetItem, VerifyAssetsResult, VerifyTaskStartResult } from '@/types'

export async function startVerifyTask(asset_ids: string[]) {
  const { data } = await http.post<VerifyTaskStartResult>('/api/v1/assets/verify-batch', { asset_ids, verified: true })
  return data
}
```

Add a polling client in `frontend/src/api/modules/jobs.ts` or new `tasks.ts`:

```ts
import http from '@/api/http'
import type { VerifyTaskProgress } from '@/types'

export async function fetchVerifyTask(taskId: string) {
  const { data } = await http.get<VerifyTaskProgress>(`/api/v1/jobs/${taskId}`)
  return data
}
```

- [ ] **Step 4: Run build to verify it passes this layer**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: It may still fail because `AssetsView.vue` is not fully updated yet, but not because the new types/API wrappers are missing.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/modules/assets.ts frontend/src/api/modules/jobs.ts frontend/src/api/modules/tasks.ts
git commit -m "feat: add verify task progress client types"
```

---

### Task 6: Render the verify progress bar on the asset list page

**Files:**
- Modify: `frontend/src/views/AssetsView.vue`

- [ ] **Step 1: Write the failing UI behavior first**

Add template references before wiring all state:

```vue
<el-card v-if="verifyTask" style="margin-top: 12px;">
  <div class="toolbar-row" style="margin-bottom: 8px;">
    <span>{{ verifyTask.message || '正在验证' }}</span>
    <span>成功 {{ verifyTask.success }}，失败 {{ verifyTask.failed }}</span>
  </div>
  <el-progress :percentage="verifyProgressPercent" :status="verifyProgressStatus" />
</el-card>
```

Update `triggerVerify()` intent to task flow:

```ts
const result = await startVerifyTask(selectedIds.value)
verifyTaskId.value = result.task_id
```

- [ ] **Step 2: Run build to verify it fails**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: FAIL because `verifyTask`, `verifyTaskId`, `verifyProgressPercent`, `verifyProgressStatus`, and the polling loop are not implemented yet.

- [ ] **Step 3: Write minimal implementation**

Add the required state and polling logic:

```ts
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchVerifyTask } from '@/api/modules/jobs'
import { startVerifyTask } from '@/api/modules/assets'
import type { VerifyTaskProgress } from '@/types'

const verifyTaskId = ref('')
const verifyTask = ref<VerifyTaskProgress | null>(null)
let verifyTimer: number | undefined

const verifyProgressPercent = computed(() => {
  if (!verifyTask.value || verifyTask.value.total === 0) return 0
  return Math.round((verifyTask.value.processed / verifyTask.value.total) * 100)
})

const verifyProgressStatus = computed(() => {
  if (!verifyTask.value) return undefined
  if (verifyTask.value.status === 'failed') return 'exception'
  if (verifyTask.value.status === 'completed') return 'success'
  return undefined
})

async function pollVerifyTask() {
  if (!verifyTaskId.value) return
  verifyTask.value = await fetchVerifyTask(verifyTaskId.value)
  if (verifyTask.value.status === 'completed') {
    stopVerifyPolling()
    await loadAssets()
    ElMessage.success(`批量验证完成，成功 ${verifyTask.value.success} 条，失败 ${verifyTask.value.failed} 条`)
  }
  if (verifyTask.value.status === 'failed') {
    stopVerifyPolling()
    ElMessage.error(verifyTask.value.message || '资产验证失败')
  }
}

function startVerifyPolling() {
  stopVerifyPolling()
  verifyTimer = window.setInterval(() => {
    void pollVerifyTask()
  }, 1000)
}

function stopVerifyPolling() {
  if (verifyTimer) {
    window.clearInterval(verifyTimer)
    verifyTimer = undefined
  }
}

async function triggerVerify() {
  try {
    const result = await startVerifyTask(selectedIds.value)
    verifyTaskId.value = result.task_id
    await pollVerifyTask()
    startVerifyPolling()
  } catch {
    ElMessage.error('资产验证失败')
  }
}

onBeforeUnmount(() => {
  stopVerifyPolling()
})
```

Keep the existing button label `批量验证并获取状态码`.

- [ ] **Step 4: Run build to verify it passes**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/AssetsView.vue
git commit -m "feat: add verify progress bar"
```

---

### Task 7: Final verification of the progress-bar flow

**Files:**
- Verify: `backend/tests/test_verify_progress.py`
- Verify: `backend/tests/test_health.py`
- Verify: `frontend/src/views/AssetsView.vue`

- [ ] **Step 1: Run backend tests**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_verify_progress.py" "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_health.py" -v
```

Expected: PASS

- [ ] **Step 2: Run frontend build**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: PASS

- [ ] **Step 3: Manual verification**

Start the app:

```bash
python "C:/Users/Administrator/VScode/AssetMap/main.py"
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run dev
```

Manual checks:
- Open the asset list page
- Select multiple assets
- Click `批量验证并获取状态码`
- Confirm a progress bar appears in-page immediately
- Confirm the text updates from `正在验证 X / Y`
- Confirm success/failed counts move during execution
- Confirm the progress bar reaches 100% on completion
- Confirm the asset list auto-refreshes and status codes appear

- [ ] **Step 4: Commit the verified final state**

```bash
git add backend/app/api/assets.py backend/app/api/jobs.py backend/app/api/tasks.py backend/app/models/job.py backend/app/schemas/job.py backend/tests/test_verify_progress.py frontend/src/api/modules/assets.ts frontend/src/api/modules/jobs.ts frontend/src/api/modules/tasks.ts frontend/src/types/index.ts frontend/src/views/AssetsView.vue
git commit -m "feat: add verify task progress bar"
```

- [ ] **Step 5: Request review**

After tests and manual verification pass, use the normal review workflow before merge.
