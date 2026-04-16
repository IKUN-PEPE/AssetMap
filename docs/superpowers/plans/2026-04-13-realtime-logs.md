# Realtime Logs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone realtime logs page that shows task logs, service logs, and combined logs using frontend polling against a new backend log API.

**Architecture:** Add a lightweight in-memory backend log buffer fed by the existing Python logging system, expose a single `/api/v1/logs/recent` endpoint with `source`, `limit`, and `since` filters, then add a Vue logs page that polls for incremental updates and renders a console-style structured log list. Keep the first version intentionally small: no SSE/WebSocket, no persistence, no search, and no auth changes.

**Tech Stack:** FastAPI, Python logging, Vue 3, TypeScript, Element Plus, vue-router, axios, pytest

---

## File Map

### Backend
- Create: `backend/app/services/logs/runtime_buffer.py` — in-memory log entry store and logging handler used by the API
- Create: `backend/app/api/logs.py` — `/api/v1/logs/recent` endpoint, query parsing, response shaping
- Modify: `backend/app/main.py` — register the runtime log handler during app startup
- Modify: `backend/app/api/router.py` — mount the new logs router
- Modify: `backend/app/api/jobs.py` — ensure existing task logs use a stable `task` source name in emitted logger names/messages if needed
- Test: `backend/tests/test_logs_api.py` — API and filtering tests
- Test: `backend/tests/test_runtime_buffer.py` — buffer filtering and truncation tests if split is helpful

### Frontend
- Create: `frontend/src/api/modules/logs.ts` — typed API wrapper for fetching recent logs
- Create: `frontend/src/views/LogsView.vue` — realtime logs page UI, polling, source switching, pause/resume, clear view, auto-follow
- Modify: `frontend/src/router/index.ts` — add `/logs` route
- Modify: `frontend/src/layouts/AdminLayout.vue` — add sidebar nav item for logs page
- Modify: `frontend/src/types/index.ts` — add `LogItem` / `LogsResponse` types
- Test/Verify: `npm --prefix frontend run build`

---

### Task 1: Build the backend runtime log buffer

**Files:**
- Create: `backend/app/services/logs/runtime_buffer.py`
- Test: `backend/tests/test_runtime_buffer.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timedelta, UTC

from app.services.logs.runtime_buffer import RuntimeLogBuffer


def test_runtime_log_buffer_filters_by_source_and_since():
    buffer = RuntimeLogBuffer(max_items=5)
    now = datetime.now(UTC)

    buffer.append(
        {
            "timestamp": (now - timedelta(seconds=2)).isoformat(),
            "level": "info",
            "source": "service",
            "message": "service started",
        }
    )
    buffer.append(
        {
            "timestamp": now.isoformat(),
            "level": "info",
            "source": "task",
            "message": "job created",
        }
    )

    items = buffer.list_recent(source="task", since=(now - timedelta(seconds=1)).isoformat(), limit=10)

    assert [item["message"] for item in items] == ["job created"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_runtime_buffer.py::test_runtime_log_buffer_filters_by_source_and_since" -v
```

Expected: FAIL because `app.services.logs.runtime_buffer` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
from collections import deque
from datetime import datetime
from threading import Lock


class RuntimeLogBuffer:
    def __init__(self, max_items: int = 500):
        self._items = deque(maxlen=max_items)
        self._lock = Lock()

    def append(self, item: dict) -> None:
        with self._lock:
            self._items.append(item)

    def list_recent(self, source: str = "all", since: str | None = None, limit: int = 200) -> list[dict]:
        with self._lock:
            items = list(self._items)

        if source != "all":
            items = [item for item in items if item["source"] == source]
        if since:
            since_dt = datetime.fromisoformat(since)
            items = [item for item in items if datetime.fromisoformat(item["timestamp"]) > since_dt]
        return items[-limit:]
```

Also add a logging handler in the same file:

```python
import logging
from datetime import UTC, datetime


class RuntimeLogHandler(logging.Handler):
    def __init__(self, buffer: RuntimeLogBuffer):
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        source = "task" if record.name.startswith("app.api.jobs") or record.name.startswith("assetmap.screenshot") else "service"
        self.buffer.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname.lower(),
                "source": source,
                "message": self.format(record),
            }
        )
```

And expose singleton instances:

```python
runtime_log_buffer = RuntimeLogBuffer(max_items=500)
runtime_log_handler = RuntimeLogHandler(runtime_log_buffer)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_runtime_buffer.py::test_runtime_log_buffer_filters_by_source_and_since" -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/logs/runtime_buffer.py backend/tests/test_runtime_buffer.py
git commit -m "feat: add runtime log buffer"
```

---

### Task 2: Expose recent logs through the backend API

**Files:**
- Create: `backend/app/api/logs.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_logs_api.py`

- [ ] **Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from app.main import app
from app.services.logs.runtime_buffer import runtime_log_buffer

client = TestClient(app)


def test_logs_recent_endpoint_filters_by_source():
    runtime_log_buffer.append(
        {
            "timestamp": "2026-04-13T12:00:00+00:00",
            "level": "info",
            "source": "task",
            "message": "task entry",
        }
    )
    runtime_log_buffer.append(
        {
            "timestamp": "2026-04-13T12:00:01+00:00",
            "level": "info",
            "source": "service",
            "message": "service entry",
        }
    )

    response = client.get("/api/v1/logs/recent", params={"source": "task", "limit": 10})

    assert response.status_code == 200
    assert [item["message"] for item in response.json()["items"]] == ["task entry"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_logs_api.py::test_logs_recent_endpoint_filters_by_source" -v
```

Expected: FAIL with 404 because `/api/v1/logs/recent` is not registered yet.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/api/logs.py`:

```python
from fastapi import APIRouter, Query

from app.services.logs.runtime_buffer import runtime_log_buffer

router = APIRouter()


@router.get("/recent")
def get_recent_logs(
    source: str = Query("all", pattern="^(task|service|all)$"),
    limit: int = Query(200, ge=1, le=500),
    since: str | None = None,
):
    items = runtime_log_buffer.list_recent(source=source, since=since, limit=limit)
    next_since = items[-1]["timestamp"] if items else since
    return {"items": items, "next_since": next_since}
```

Register router in `backend/app/api/router.py`:

```python
from app.api import assets, jobs, labels, logs, reports, screenshots, selections, system

api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
```

Attach handler in `backend/app/main.py`:

```python
from app.services.logs.runtime_buffer import runtime_log_handler

runtime_log_handler.setFormatter(logging.Formatter("%(message)s"))
logging.getLogger().addHandler(runtime_log_handler)
```

Guard against duplicate handler registration in `main.py`:

```python
root_logger = logging.getLogger()
if runtime_log_handler not in root_logger.handlers:
    root_logger.addHandler(runtime_log_handler)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_logs_api.py::test_logs_recent_endpoint_filters_by_source" -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/logs.py backend/app/api/router.py backend/app/main.py backend/tests/test_logs_api.py
git commit -m "feat: add recent logs api"
```

---

### Task 3: Add coverage for limit and incremental polling semantics

**Files:**
- Modify: `backend/tests/test_logs_api.py`
- Modify: `backend/app/services/logs/runtime_buffer.py` if needed

- [ ] **Step 1: Write the failing test**

```python
def test_logs_recent_endpoint_returns_incremental_items():
    runtime_log_buffer.append(
        {
            "timestamp": "2026-04-13T12:00:00+00:00",
            "level": "info",
            "source": "task",
            "message": "old entry",
        }
    )
    runtime_log_buffer.append(
        {
            "timestamp": "2026-04-13T12:00:05+00:00",
            "level": "info",
            "source": "task",
            "message": "new entry",
        }
    )

    response = client.get(
        "/api/v1/logs/recent",
        params={"source": "task", "since": "2026-04-13T12:00:01+00:00", "limit": 10},
    )

    assert response.status_code == 200
    assert [item["message"] for item in response.json()["items"]] == ["new entry"]
    assert response.json()["next_since"] == "2026-04-13T12:00:05+00:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_logs_api.py::test_logs_recent_endpoint_returns_incremental_items" -v
```

Expected: FAIL if timestamp parsing or `next_since` behavior is wrong.

- [ ] **Step 3: Write minimal implementation**

If necessary, harden `list_recent()` to handle `Z` timestamps and ensure ordering is stable:

```python
def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
```

Use it consistently:

```python
if since:
    since_dt = _parse_timestamp(since)
    items = [item for item in items if _parse_timestamp(item["timestamp"]) > since_dt]
items.sort(key=lambda item: _parse_timestamp(item["timestamp"]))
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_logs_api.py::test_logs_recent_endpoint_returns_incremental_items" -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/logs/runtime_buffer.py backend/tests/test_logs_api.py
git commit -m "test: cover incremental log polling"
```

---

### Task 4: Add frontend log types and API wrapper

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/modules/logs.ts`
- Test/Verify: `npm --prefix frontend run build`

- [ ] **Step 1: Write the failing type usage**

Add imports in the future view first so build will fail until types/module exist:

```ts
import { fetchRecentLogs } from '@/api/modules/logs'
import type { LogItem, LogsResponse } from '@/types'
```

- [ ] **Step 2: Run build to verify it fails**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: FAIL because `@/api/modules/logs` and the new exported types do not exist.

- [ ] **Step 3: Write minimal implementation**

Add to `frontend/src/types/index.ts`:

```ts
export interface LogItem {
  timestamp: string
  level: string
  source: 'task' | 'service'
  message: string
}

export interface LogsResponse {
  items: LogItem[]
  next_since?: string | null
}
```

Create `frontend/src/api/modules/logs.ts`:

```ts
import http from '@/api/http'
import type { LogsResponse } from '@/types'

export async function fetchRecentLogs(params?: {
  source?: 'task' | 'service' | 'all'
  limit?: number
  since?: string
}) {
  const { data } = await http.get<LogsResponse>('/api/v1/logs/recent', { params })
  return data
}
```

- [ ] **Step 4: Run build to verify this part passes**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: It may still fail because the page is not implemented yet, but it should no longer fail due to missing log types/module.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/modules/logs.ts
git commit -m "feat: add frontend log api types"
```

---

### Task 5: Add the realtime logs route and sidebar navigation

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/AdminLayout.vue`
- Create: `frontend/src/views/LogsView.vue`
- Test/Verify: `npm --prefix frontend run build`

- [ ] **Step 1: Write the failing minimal page test via build**

Add route and menu entry pointing to `LogsView` before the file exists:

```ts
const LogsView = () => import('@/views/LogsView.vue')
{ path: 'logs', name: 'logs', component: LogsView }
```

```vue
<el-menu-item index="/logs">实时日志</el-menu-item>
```

- [ ] **Step 2: Run build to verify it fails**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: FAIL because `frontend/src/views/LogsView.vue` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create a minimal `frontend/src/views/LogsView.vue` first:

```vue
<template>
  <div class="page-shell">
    <div class="page-header">
      <h1 class="page-title">实时日志</h1>
      <p class="page-subtitle">查看任务日志与服务日志。</p>
    </div>
    <el-card>
      <span>日志页面初始化完成</span>
    </el-card>
  </div>
</template>
```

- [ ] **Step 4: Run build to verify it passes**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: PASS for route/menu/page existence, unless blocked by pre-existing `import.meta.env` typing issue in `frontend/src/api/http.ts`. If that existing issue still blocks the build, fix it in this task by adding `frontend/src/vite-env.d.ts` with:

```ts
/// <reference types="vite/client" />
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/router/index.ts frontend/src/layouts/AdminLayout.vue frontend/src/views/LogsView.vue frontend/src/vite-env.d.ts
git commit -m "feat: add realtime logs navigation"
```

---

### Task 6: Implement polling and source switching in the logs page

**Files:**
- Modify: `frontend/src/views/LogsView.vue`
- Test/Verify: `npm --prefix frontend run build`

- [ ] **Step 1: Write the failing usage first**

In `LogsView.vue`, reference the reactive state and API calls before defining all helpers:

```ts
const source = ref<'task' | 'service' | 'all'>('all')
const logs = ref<LogItem[]>([])
const nextSince = ref<string | undefined>()

await refreshLogs(true)
```

- [ ] **Step 2: Run build to verify it fails**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: FAIL because `refreshLogs` and related state/helpers are incomplete.

- [ ] **Step 3: Write minimal implementation**

Implement polling in `LogsView.vue`:

```ts
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchRecentLogs } from '@/api/modules/logs'
import type { LogItem } from '@/types'

const source = ref<'task' | 'service' | 'all'>('all')
const logs = ref<LogItem[]>([])
const loading = ref(false)
const polling = ref(true)
const errorText = ref('')
const nextSince = ref<string | undefined>()
const lastUpdatedAt = ref('')
const pollMs = 1500
let timer: number | undefined

async function refreshLogs(reset = false) {
  loading.value = true
  try {
    const response = await fetchRecentLogs({
      source: source.value,
      limit: reset ? 200 : 100,
      since: reset ? undefined : nextSince.value,
    })
    logs.value = reset ? response.items : [...logs.value, ...response.items].slice(-500)
    nextSince.value = response.next_since || nextSince.value
    lastUpdatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    errorText.value = ''
    await nextTick()
    scrollToBottom()
  } catch (error) {
    errorText.value = '日志拉取失败'
  } finally {
    loading.value = false
  }
}

function startPolling() {
  stopPolling()
  timer = window.setInterval(() => {
    if (polling.value) {
      void refreshLogs(false)
    }
  }, pollMs)
}

function stopPolling() {
  if (timer) {
    window.clearInterval(timer)
    timer = undefined
  }
}

function pausePolling() {
  polling.value = false
}

function resumePolling() {
  polling.value = true
  void refreshLogs(false)
}

function clearView() {
  logs.value = []
}

async function changeSource() {
  nextSince.value = undefined
  await refreshLogs(true)
}

onMounted(async () => {
  await refreshLogs(true)
  startPolling()
})

onBeforeUnmount(() => {
  stopPolling()
})
```

Template skeleton:

```vue
<el-card>
  <div class="toolbar-row logs-toolbar">
    <el-segmented v-model="source" :options="sourceOptions" @change="changeSource" />
    <el-tag :type="polling ? 'success' : 'info'">{{ polling ? '自动刷新中' : '已暂停' }}</el-tag>
    <el-button @click="pausePolling" :disabled="!polling">暂停</el-button>
    <el-button type="primary" plain @click="resumePolling" :disabled="polling">继续</el-button>
    <el-button type="danger" plain @click="clearView">清空视图</el-button>
  </div>
</el-card>
```

- [ ] **Step 4: Run build to verify it passes**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/LogsView.vue
git commit -m "feat: add realtime log polling"
```

---

### Task 7: Finish console-style rendering, empty state, and auto-follow behavior

**Files:**
- Modify: `frontend/src/views/LogsView.vue`
- Test/Verify: `npm --prefix frontend run build`

- [ ] **Step 1: Write the failing UI behavior first**

Add template references to the final state before implementing helpers:

```vue
<div ref="logContainer" class="logs-console" @scroll="handleScroll">
  <div v-if="logs.length === 0" class="logs-empty">{{ emptyText }}</div>
  <div v-for="item in logs" :key="`${item.timestamp}-${item.message}`" class="log-line" :class="`log-${item.level}`">
    <span class="log-time">{{ formatTimestamp(item.timestamp) }}</span>
    <span class="log-source">[{{ item.source }}]</span>
    <span class="log-message">{{ item.message }}</span>
  </div>
</div>
```

- [ ] **Step 2: Run build to verify it fails**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: FAIL because `emptyText`, `handleScroll`, `formatTimestamp`, or `logContainer` are missing.

- [ ] **Step 3: Write minimal implementation**

Add the missing helpers:

```ts
const logContainer = ref<HTMLElement | null>(null)
const autoFollow = ref(true)

const sourceOptions = [
  { label: '全部', value: 'all' },
  { label: '任务日志', value: 'task' },
  { label: '服务日志', value: 'service' },
]

const emptyText = computed(() => {
  if (source.value === 'task') return '当前暂无任务日志'
  if (source.value === 'service') return '当前暂无服务日志'
  return '当前暂无日志'
})

function formatTimestamp(value: string) {
  return new Date(value).toLocaleTimeString('zh-CN', { hour12: false })
}

function handleScroll() {
  const element = logContainer.value
  if (!element) return
  const threshold = 24
  autoFollow.value = element.scrollHeight - element.scrollTop - element.clientHeight <= threshold
}

function scrollToBottom() {
  const element = logContainer.value
  if (!element || !autoFollow.value) return
  element.scrollTop = element.scrollHeight
}
```

Add bottom status bar and error message:

```vue
<el-alert v-if="errorText" :title="errorText" type="error" show-icon :closable="false" />
<div class="logs-status-bar">
  <span>当前显示：{{ logs.length }} 条</span>
  <span>最近更新时间：{{ lastUpdatedAt || '-' }}</span>
  <span>轮询间隔：{{ pollMs }}ms</span>
</div>
```

Add styles:

```css
.logs-console {
  height: 520px;
  overflow: auto;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 12px;
  padding: 14px;
  font-family: Consolas, Monaco, monospace;
}
.log-line {
  display: grid;
  grid-template-columns: 96px 72px 1fr;
  gap: 12px;
  padding: 4px 0;
  font-size: 13px;
}
.log-info { color: #dbeafe; }
.log-warning { color: #fde68a; }
.log-error { color: #fca5a5; }
.logs-empty { color: #94a3b8; text-align: center; padding: 180px 0; }
.logs-status-bar { display: flex; gap: 20px; margin-top: 12px; color: #5b6b7f; font-size: 12px; }
```

- [ ] **Step 4: Run build to verify it passes**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/LogsView.vue
git commit -m "feat: finish realtime logs console view"
```

---

### Task 8: Run focused backend tests and final verification

**Files:**
- Test: `backend/tests/test_runtime_buffer.py`
- Test: `backend/tests/test_logs_api.py`
- Verify: `frontend/src/views/LogsView.vue`, `frontend/src/router/index.ts`, `frontend/src/layouts/AdminLayout.vue`

- [ ] **Step 1: Run focused backend tests**

Run:
```bash
python -m pytest "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_runtime_buffer.py" "C:/Users/Administrator/VScode/AssetMap/backend/tests/test_logs_api.py" -v
```

Expected: All PASS

- [ ] **Step 2: Run frontend build**

Run:
```bash
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run build
```

Expected: PASS

- [ ] **Step 3: Manual verification**

Run backend and frontend, then verify:

```bash
python "C:/Users/Administrator/VScode/AssetMap/main.py"
npm --prefix "C:/Users/Administrator/VScode/AssetMap/frontend" run dev
```

Manual checks:
- Open `/logs`
- Switch between `全部` / `任务日志` / `服务日志`
- Confirm page shows new log lines while polling
- Click `暂停`, wait one poll cycle, confirm no new lines append
- Click `继续`, confirm new lines append again
- Click `清空视图`, confirm visible list clears without deleting backend data
- Scroll upward manually, confirm page stops snapping to bottom until near-bottom again

- [ ] **Step 4: Commit final verification-safe state**

```bash
git add backend/app/services/logs/runtime_buffer.py backend/app/api/logs.py backend/app/api/router.py backend/app/main.py backend/tests/test_runtime_buffer.py backend/tests/test_logs_api.py frontend/src/api/modules/logs.ts frontend/src/views/LogsView.vue frontend/src/router/index.ts frontend/src/layouts/AdminLayout.vue frontend/src/types/index.ts frontend/src/vite-env.d.ts
git commit -m "feat: add realtime logs page"
```

- [ ] **Step 5: Request review**

Use the code review flow after all checks are green.

```bash
# no command here; use the project review workflow/tooling after verification
```
