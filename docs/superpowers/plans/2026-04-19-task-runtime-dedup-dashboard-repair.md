# Task Runtime, Dedup, and Dashboard Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize background collection tasks, make stop requests cooperatively cancel real work, enforce duplicate URL touch-only behavior, and remove the dashboard's hardcoded stats base URL.

**Architecture:** Keep the current in-process thread launcher, but make `backend/app/tasks/collect.py` own a safe sync wrapper for async collectors plus explicit cancellation checkpoints before success/finalization. Centralize duplicate endpoint touch semantics in one helper used by both collection paths, and move dashboard stats fetching onto the shared Axios client through a dedicated frontend API module.

**Tech Stack:** FastAPI, SQLAlchemy, Huey task wrappers, pytest, Vue 3, TypeScript, Axios, Vite, ECharts

---

## File Map

- Modify `backend/app/tasks/collect.py` — add a thread-safe async collector wrapper, cancellation helpers, guarded task finalization, and post-process cancellation checks.
- Create `backend/tests/test_collect_runtime.py` — regression tests for background-thread async execution and cooperative cancellation behavior.
- Create `backend/app/services/collectors/dedup.py` — single-purpose helper for "touch existing endpoint" semantics.
- Modify `backend/app/services/collectors/import_service.py` — replace field-overwrite duplicate handling with the shared dedup helper.
- Modify `backend/app/tasks/collect.py` — replace duplicate overwrite branches with the shared dedup helper.
- Create `backend/tests/test_collect_dedup.py` — regression tests for duplicate URL touch-only behavior in both collection and import flows.
- Create `frontend/src/api/modules/statistics.ts` — typed stats API wrapper built on the shared `http` client.
- Modify `frontend/src/api/http.ts` — stop forcing a hardcoded backend origin in the shared Axios client.
- Modify `frontend/src/types/index.ts` — add dashboard stats response types.
- Modify `frontend/src/views/DashboardView.vue` — replace hardcoded Axios base URL with shared stats module calls and keep the existing empty-state fallback.
- Modify `frontend/vite.config.ts` — proxy `/api` requests to the backend during local development when no explicit API base URL is supplied.

## Task 1: Make async collectors safe inside the background thread

**Files:**
- Create: `backend/tests/test_collect_runtime.py`
- Modify: `backend/app/tasks/collect.py:144-180`
- Test: `backend/tests/test_collect_runtime.py`

- [ ] **Step 1: Write the failing runtime test**

Create `backend/tests/test_collect_runtime.py` with this first regression test:

```python
import asyncio

from app.tasks import collect


class FakeCollector:
    async def run(self, query_str, query_payload, config):
        await asyncio.sleep(0)
        return [{"url": "https://example.com", "ip": "1.1.1.1", "port": 443}]


def test_run_collector_query_uses_fresh_event_loop():
    result = collect.run_collector_query(
        FakeCollector(),
        'title="nginx"',
        {"queries": []},
        {"token": "secret"},
    )

    assert result == [{"url": "https://example.com", "ip": "1.1.1.1", "port": 443}]
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd backend && pytest tests/test_collect_runtime.py::test_run_collector_query_uses_fresh_event_loop -q
```

Expected: FAIL with an error like `module 'app.tasks.collect' has no attribute 'run_collector_query'`.

- [ ] **Step 3: Add the minimal sync wrapper and use it from the task**

In `backend/app/tasks/collect.py`, add the helper near the top-level functions and replace the `asyncio.get_event_loop().run_until_complete(...)` block.

```python
def run_collector_query(collector, query_str: str, query_payload: dict, config: dict):
    return asyncio.run(collector.run(query_str, query_payload, config))
```

Replace the current collector execution block inside `run_collect_task` with:

```python
collector = get_collector(src_name)
config = SystemConfigService.get_decrypted_configs(db, src_name)
assets = run_collector_query(collector, query_str, query_payload, config)
save_assets(db, job, assets, src_name)
```

- [ ] **Step 4: Run the test again and verify it passes**

Run:

```bash
cd backend && pytest tests/test_collect_runtime.py::test_run_collector_query_uses_fresh_event_loop -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit the runtime wrapper change**

Run:

```bash
git add backend/app/tasks/collect.py backend/tests/test_collect_runtime.py
git commit -m "fix: run collectors with a fresh event loop"
```

## Task 2: Add cooperative cancellation and protect final task state

**Files:**
- Modify: `backend/tests/test_collect_runtime.py`
- Modify: `backend/app/tasks/collect.py:116-270`
- Test: `backend/tests/test_collect_runtime.py`

- [ ] **Step 1: Append failing cancellation regressions**

Append these helpers and tests to `backend/tests/test_collect_runtime.py` below the first test:

```python
from types import SimpleNamespace


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.result


class FakeDb:
    def __init__(self, job):
        self.job = job
        self.commit_count = 0
        self.closed = False

    def query(self, model):
        return FakeQuery(self.job)

    def commit(self):
        self.commit_count += 1

    def close(self):
        self.closed = True


class CancelledPostProcessDb(FakeDb):
    def query(self, model):
        if model is collect.CollectJob:
            return FakeQuery(self.job)
        raise AssertionError("cancelled post-process should not query assets")


def test_run_collect_task_keeps_cancelled_status_and_skips_post_process(monkeypatch):
    job = SimpleNamespace(
        id="job-1",
        status="pending",
        started_at=None,
        finished_at=None,
        progress=0,
        error_message=None,
        success_count=0,
        failed_count=0,
        duplicate_count=0,
        total_count=0,
        sources=["fofa"],
        query_payload={"queries": [{"source": "fofa", "query": 'body="ok"'}]},
        dedup_strategy="skip",
        auto_verify=True,
    )
    db = FakeDb(job)
    launched = []

    class FakeCollector:
        async def run(self, query_str, query_payload, config):
            return [{"url": "https://example.com", "ip": "1.1.1.1", "port": 443}]

    monkeypatch.setattr(collect, "SessionLocal", lambda: db)
    monkeypatch.setattr(collect, "get_collector", lambda source: FakeCollector())
    monkeypatch.setattr(
        collect.SystemConfigService,
        "get_decrypted_configs",
        lambda db, source: {"token": "secret"},
    )
    monkeypatch.setattr(
        collect,
        "save_assets",
        lambda db, job, assets, source_name: setattr(job, "status", "cancelled"),
    )
    monkeypatch.setattr(
        collect,
        "run_in_process",
        lambda task, *args, delay=0: launched.append((task, args, delay)),
    )

    collect.run_collect_task.call_local("job-1")

    assert job.status == "cancelled"
    assert job.finished_at is not None
    assert launched == []


def test_run_auto_post_process_returns_immediately_for_cancelled_job(monkeypatch):
    db = CancelledPostProcessDb(SimpleNamespace(id="job-1", status="cancelled"))
    monkeypatch.setattr(collect, "SessionLocal", lambda: db)

    collect.run_auto_post_process.call_local("job-1")

    assert db.closed is True
```

- [ ] **Step 2: Run the cancellation tests and verify they fail**

Run:

```bash
cd backend && pytest tests/test_collect_runtime.py::test_run_collect_task_keeps_cancelled_status_and_skips_post_process tests/test_collect_runtime.py::test_run_auto_post_process_returns_immediately_for_cancelled_job -q
```

Expected: FAIL because `run_collect_task` currently overwrites `cancelled` with `success`, and `run_auto_post_process` continues into asset queries for cancelled jobs.

- [ ] **Step 3: Implement cancellation checkpoints and guarded finalization**

In `backend/app/tasks/collect.py`, add these helpers above `process_csv_import_job`:

```python
def load_job(db: Session, job_id: str):
    return db.query(CollectJob).filter(CollectJob.id == job_id).first()


def is_job_cancelled(db: Session, job_id: str) -> bool:
    current = load_job(db, job_id)
    return bool(current and current.status == "cancelled")


def finish_cancelled_job(job: CollectJob, db: Session) -> None:
    job.status = "cancelled"
    job.finished_at = datetime.utcnow()
    db.commit()
```

Update `run_collect_task` so the control flow looks like this:

```python
job = load_job(db, job_id)
if not job:
    return

job.status = "running"
job.started_at = datetime.utcnow()
db.commit()

if is_job_cancelled(db, job_id):
    finish_cancelled_job(job, db)
    return

if "csv_import" in sources:
    process_csv_import_job(db, job)
    if is_job_cancelled(db, job_id):
        finish_cancelled_job(job, db)
        return
else:
    for q_item in queries:
        if is_job_cancelled(db, job_id):
            finish_cancelled_job(job, db)
            return

        collector = get_collector(src_name)
        config = SystemConfigService.get_decrypted_configs(db, src_name)
        assets = run_collector_query(collector, query_str, query_payload, config)

        if is_job_cancelled(db, job_id):
            finish_cancelled_job(job, db)
            return

        save_assets(db, job, assets, src_name)

        if is_job_cancelled(db, job_id):
            finish_cancelled_job(job, db)
            return

job.status = "success"
job.progress = 100
job.finished_at = datetime.utcnow()
db.commit()

if job.auto_verify and not is_job_cancelled(db, job.id):
    run_in_process(run_auto_post_process, job.id, delay=2)
```

Update `run_auto_post_process` to exit before querying assets when the job is cancelled, and re-check inside the asset write loop:

```python
job = load_job(db, job_id)
if not job or job.status == "cancelled":
    return

# ... after run_screenshot_job(...)
for asset in target_assets:
    if is_job_cancelled(db, job_id):
        return
    asset.screenshot_status = "success"
    # existing screenshot row replacement logic
```

- [ ] **Step 4: Run the runtime test file and verify it passes**

Run:

```bash
cd backend && pytest tests/test_collect_runtime.py -q
```

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit the cancellation fix**

Run:

```bash
git add backend/app/tasks/collect.py backend/tests/test_collect_runtime.py
git commit -m "fix: stop cancelled collection jobs cooperatively"
```

## Task 3: Unify duplicate URL handling so existing assets are only touched

**Files:**
- Create: `backend/app/services/collectors/dedup.py`
- Create: `backend/tests/test_collect_dedup.py`
- Modify: `backend/app/tasks/collect.py:21-113`
- Modify: `backend/app/services/collectors/import_service.py:9-97`
- Test: `backend/tests/test_collect_dedup.py`

- [ ] **Step 1: Write the failing duplicate-handling tests**

Create `backend/tests/test_collect_dedup.py` with these tests:

```python
from datetime import datetime
from types import SimpleNamespace

from app.models.asset import WebEndpoint
from app.tasks import collect
from app.services.collectors.dedup import touch_existing_web_endpoint


class DuplicateQuery:
    def __init__(self, web):
        self.web = web

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.web


class DuplicateDb:
    def __init__(self, web):
        self.web = web
        self.commit_count = 0

    def query(self, model):
        assert model is collect.WebEndpoint
        return DuplicateQuery(self.web)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        raise AssertionError("rollback should not run for duplicate rows")


def test_touch_existing_web_endpoint_only_updates_seen_timestamps():
    original_first_seen = datetime(2026, 4, 18, 8, 0, 0)
    observed_at = datetime(2026, 4, 19, 9, 30, 0)
    web = WebEndpoint(
        normalized_url="https://example.com",
        normalized_url_hash="hash-1",
        title="Keep title",
        status_code=200,
        domain="example.com",
        first_seen_at=original_first_seen,
        last_seen_at=original_first_seen,
    )

    touch_existing_web_endpoint(web, observed_at)

    assert web.first_seen_at == original_first_seen
    assert web.last_seen_at == observed_at
    assert web.title == "Keep title"
    assert web.status_code == 200
    assert web.domain == "example.com"


def test_touch_existing_web_endpoint_backfills_missing_first_seen():
    observed_at = datetime(2026, 4, 19, 9, 30, 0)
    web = WebEndpoint(
        normalized_url="https://example.com",
        normalized_url_hash="hash-2",
        first_seen_at=None,
        last_seen_at=None,
    )

    touch_existing_web_endpoint(web, observed_at)

    assert web.first_seen_at == observed_at
    assert web.last_seen_at == observed_at


def test_save_assets_touches_duplicate_without_overwriting_fields():
    existing = WebEndpoint(
        normalized_url="https://example.com",
        normalized_url_hash=collect.build_url_hash("https://example.com"),
        title="Keep me",
        status_code=200,
        first_seen_at=datetime(2026, 4, 18, 8, 0, 0),
        last_seen_at=datetime(2026, 4, 18, 8, 0, 0),
    )
    db = DuplicateDb(existing)
    job = SimpleNamespace(success_count=0, duplicate_count=0, failed_count=0, dedup_strategy="overwrite")

    collect.save_assets(
        db,
        job,
        [{"url": "https://example.com", "ip": "1.1.1.1", "port": 443, "title": "Replace me"}],
        "fofa",
    )

    assert job.duplicate_count == 1
    assert existing.title == "Keep me"
    assert existing.status_code == 200
    assert existing.last_seen_at > datetime(2026, 4, 18, 8, 0, 0)
```

- [ ] **Step 2: Run the duplicate tests and verify they fail**

Run:

```bash
cd backend && pytest tests/test_collect_dedup.py -q
```

Expected: FAIL because `app.services.collectors.dedup` does not exist yet, and `save_assets()` still overwrites duplicate rows when `dedup_strategy == "overwrite"`.

- [ ] **Step 3: Add the shared dedup helper and switch both call sites to it**

Create `backend/app/services/collectors/dedup.py`:

```python
from datetime import datetime

from app.models import WebEndpoint


def touch_existing_web_endpoint(web: WebEndpoint, observed_at: datetime) -> None:
    if not web.first_seen_at:
        web.first_seen_at = observed_at
    web.last_seen_at = observed_at
```

Update the duplicate branch in `backend/app/tasks/collect.py` to remove overwrite semantics and touch the existing row instead:

```python
from app.services.collectors.dedup import touch_existing_web_endpoint

# inside save_assets()
observed_at = datetime.utcnow()

if existing_web:
    touch_existing_web_endpoint(existing_web, observed_at)
    dup_count += 1
    continue
```

Update the existing-row branch in `backend/app/services/collectors/import_service.py` the same way:

```python
from app.services.collectors.dedup import touch_existing_web_endpoint

# existing row branch
else:
    touch_existing_web_endpoint(web, observed_at)
```

Delete the old title/status overwrite block entirely.

- [ ] **Step 4: Run the duplicate tests and verify they pass**

Run:

```bash
cd backend && pytest tests/test_collect_dedup.py -q
```

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit the dedup consistency change**

Run:

```bash
git add backend/app/services/collectors/dedup.py backend/app/services/collectors/import_service.py backend/app/tasks/collect.py backend/tests/test_collect_dedup.py
git commit -m "fix: only refresh last seen time for duplicate urls"
```

## Task 4: Move dashboard stats fetching onto the shared frontend API client

**Files:**
- Create: `frontend/src/api/modules/statistics.ts`
- Modify: `frontend/src/api/http.ts:1-8`
- Modify: `frontend/src/types/index.ts:69-121`
- Modify: `frontend/src/views/DashboardView.vue:62-208`
- Modify: `frontend/vite.config.ts:5-16`
- Test: `frontend/package.json`

- [ ] **Step 1: Point the dashboard at a shared stats module before it exists**

Edit the script block in `frontend/src/views/DashboardView.vue` so it starts like this:

```ts
import { ref, onMounted, computed } from 'vue'
import { Monitor, Plus, Aim, Warning } from '@element-plus/icons-vue'
import { fetchStatsDistribution, fetchStatsOverview, fetchStatsTrends } from '@/api/modules/statistics'
import type {
  StatsDistributionItem,
  StatsOverview,
  StatsTrendsResponse,
} from '@/types'
```

Update the state declarations so they expect the typed responses:

```ts
const kpiData = ref<StatsOverview>({ total: 0, today: 0, rate: 78, critical: 0 })
const sourceData = ref<StatsDistributionItem[]>([])
const verifyData = ref<StatsDistributionItem[]>([])
const trendData = ref<StatsTrendsResponse>({ dates: [], data: [] })
```

Replace the `axios.get(...)` block with:

```ts
onMounted(async () => {
  try {
    const [ov, dist, tr] = await Promise.all([
      fetchStatsOverview(),
      fetchStatsDistribution(),
      fetchStatsTrends(),
    ])
    kpiData.value = ov
    sourceData.value = dist.sources
    verifyData.value = dist.verify
    trendData.value = tr
  } catch (e) {
    console.error('Stats loading failed', e)
    kpiData.value = { total: 0, today: 0, rate: 0, critical: 0 }
    sourceData.value = []
    verifyData.value = []
    trendData.value = { dates: [], data: [] }
  }
})
```

- [ ] **Step 2: Run the frontend build and verify it fails**

Run:

```bash
cd frontend && npm run build
```

Expected: FAIL with TypeScript errors like `Cannot find module '@/api/modules/statistics'` and missing exported stats types.

- [ ] **Step 3: Create the stats module and remove hardcoded backend origins**

Add these interfaces to `frontend/src/types/index.ts` near the other API payloads:

```ts
export interface StatsOverview {
  total: number
  today: number
  rate: number
  critical: number
}

export interface StatsDistributionItem {
  name: string
  value: number
}

export interface StatsDistributionResponse {
  sources: StatsDistributionItem[]
  verify: StatsDistributionItem[]
}

export interface StatsTrendsResponse {
  dates: string[]
  data: number[]
}
```

Create `frontend/src/api/modules/statistics.ts`:

```ts
import http from '@/api/http'
import type { StatsDistributionResponse, StatsOverview, StatsTrendsResponse } from '@/types'

export async function fetchStatsOverview() {
  const { data } = await http.get<StatsOverview>('/api/v1/stats/overview')
  return data
}

export async function fetchStatsDistribution() {
  const { data } = await http.get<StatsDistributionResponse>('/api/v1/stats/distribution')
  return data
}

export async function fetchStatsTrends() {
  const { data } = await http.get<StatsTrendsResponse>('/api/v1/stats/trends')
  return data
}
```

Update `frontend/src/api/http.ts` so the shared client stops forcing `http://127.0.0.1:9527` when no environment override exists:

```ts
import axios from 'axios'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 10000,
})

export default http
```

Update `frontend/vite.config.ts` to proxy relative `/api` requests during local development:

```ts
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: env.VITE_API_BASE_URL
        ? undefined
        : {
            '/api': {
              target: 'http://127.0.0.1:9527',
              changeOrigin: true,
            },
          },
    },
  }
})
```

Keep the updated `DashboardView.vue` script from Step 1, but delete the old `import axios from 'axios'` line and the `const base = 'http://127.0.0.1:9527/api/v1/stats'` constant entirely.

- [ ] **Step 4: Run the frontend build and verify it passes**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS with Vite build output and no TypeScript errors.

- [ ] **Step 5: Commit the dashboard API wiring fix**

Run:

```bash
git add frontend/src/api/http.ts frontend/src/api/modules/statistics.ts frontend/src/types/index.ts frontend/src/views/DashboardView.vue frontend/vite.config.ts
git commit -m "fix: use shared stats api in dashboard"
```

## Task 5: Run the focused regression suite for the repair

**Files:**
- Verify: `backend/tests/test_collect_runtime.py`
- Verify: `backend/tests/test_collect_dedup.py`
- Verify: `frontend/src/api/modules/statistics.ts`
- Verify: `frontend/src/views/DashboardView.vue`

- [ ] **Step 1: Run the backend regression tests together**

Run:

```bash
cd backend && pytest tests/test_collect_runtime.py tests/test_collect_dedup.py tests/test_jobs_start_task.py -q
```

Expected: PASS with all targeted runtime/dedup job tests green.

- [ ] **Step 2: Re-run the frontend production build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS with Vite build output and no TypeScript errors.

- [ ] **Step 3: Inspect the final diff for the intended files only**

Run:

```bash
git diff -- backend/app/tasks/collect.py backend/app/services/collectors/dedup.py backend/app/services/collectors/import_service.py backend/tests/test_collect_runtime.py backend/tests/test_collect_dedup.py frontend/src/api/http.ts frontend/src/api/modules/statistics.ts frontend/src/types/index.ts frontend/src/views/DashboardView.vue frontend/vite.config.ts
```

Expected: Only runtime, cancellation, dedup, and dashboard API wiring changes appear.

- [ ] **Step 4: Create the final integration commit**

Run:

```bash
git add backend/app/tasks/collect.py backend/app/services/collectors/dedup.py backend/app/services/collectors/import_service.py backend/tests/test_collect_runtime.py backend/tests/test_collect_dedup.py frontend/src/api/http.ts frontend/src/api/modules/statistics.ts frontend/src/types/index.ts frontend/src/views/DashboardView.vue frontend/vite.config.ts
git commit -m "fix: stabilize task runtime and dashboard stats"
```

- [ ] **Step 5: Record the final verification commands in the task notes**

Copy these exact commands into the implementation notes or task summary so the next reviewer can replay them:

```bash
cd backend && pytest tests/test_collect_runtime.py tests/test_collect_dedup.py tests/test_jobs_start_task.py -q
cd frontend && npm run build
```

