# Asset Collection / System Config / CSV Import / Host Verification Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair only the collection task module, system settings module, CSV import flow, and host verification flow so FOFA/Hunter/ZoomEye/Quake can be configured, executed, imported, and verified end-to-end.

**Architecture:** Keep the existing FastAPI + SQLAlchemy + Vue task center architecture, but make the current job payloads and collectors actually carry source-specific execution options. Reuse the existing `CollectJob`, `WebEndpoint`, `SourceObservation`, and verification task flow rather than introducing a new subsystem; extend them with minimal metadata needed for real results, CSV source detection, and visible verification outcomes.

**Tech Stack:** FastAPI, SQLAlchemy ORM, Pydantic v2, httpx, Huey local task wrapper, Playwright, Vue 3, TypeScript, Element Plus

---

## File Structure

**Backend files to modify**
- `backend/app/schemas/job.py` — accept online collector options and CSV source type in job payloads.
- `backend/app/api/jobs.py` — persist richer query payloads, improve results preview, CSV preview metadata, and real task creation/start behavior.
- `backend/app/tasks/collect.py` — execute source options, compute real counts/statuses, record logs, persist observation metadata, and run CSV imports by selected/detected source.
- `backend/app/services/system_service.py` — add Hunter/ZoomEye/Quake config defaults and keep sensitive masking behavior.
- `backend/app/api/system.py` — expose current config endpoint compatibility and better per-platform connection test errors.
- `backend/app/services/collectors/base.py` — add small shared helpers for config validation and typed option parsing.
- `backend/app/services/collectors/fofa.py` — harden FOFA search/test_connection with option-driven pagination and clear errors.
- `backend/app/services/collectors/hunter.py` — replace stub with real async HTTP collector.
- `backend/app/services/collectors/zoomeye.py` — replace stub with real async HTTP collector.
- `backend/app/services/collectors/__init__.py` — register Quake collector.
- `backend/app/services/collectors/mapped_csv.py` — support reusable alias-based extraction and preserve source metadata.
- `backend/app/services/collectors/preview.py` — return detected CSV source/header mapping hints.
- `backend/app/services/collectors/import_service.py` — keep touch-only dedup and preserve metadata for imported records.
- `backend/app/api/assets.py` — persist visible verification error details and improve verification/screenshot logging.

**Backend files to create**
- `backend/app/services/collectors/quake.py` — Quake collector implementation.
- `backend/app/services/collectors/zoomeye_csv.py` — ZoomEye CSV adapter.
- `backend/app/services/collectors/quake_csv.py` — Quake CSV adapter.

**Frontend files to modify**
- `frontend/src/views/SystemView.vue` — add Hunter username/email and Quake settings UI; keep same page/layout.
- `frontend/src/views/JobsView.vue` — enable Hunter/ZoomEye/Quake online sources, add source execution options, add CSV source selection/detection, and keep current page structure.
- `frontend/src/api/modules/jobs.ts` — send new job payload fields.
- `frontend/src/types/index.ts` — extend job/task/asset types used by the four target modules.
- `frontend/src/views/AssetsView.vue` — show verification failure reason in existing verification-related detail area only.
- `frontend/src/views/AssetDetailView.vue` — surface verification error if present.

**Backend tests to modify/add**
- `backend/tests/test_jobs_csv_validation.py`
- `backend/tests/test_collect_csv_import.py`
- `backend/tests/test_mapped_csv.py`
- `backend/tests/test_system.py`
- `backend/tests/test_verify_batch.py`
- `backend/tests/test_verify_progress.py`
- `backend/tests/test_collect_runtime.py`
- Create `backend/tests/test_platform_collectors.py`
- Create `backend/tests/test_job_results_preview.py`

**Frontend verification**
- `npm run build`

---

### Task 1: Complete system source configuration and compatibility endpoints

**Files:**
- Modify: `backend/app/services/system_service.py`
- Modify: `backend/app/api/system.py`
- Modify: `backend/app/schemas/system.py`
- Modify: `frontend/src/views/SystemView.vue`
- Modify: `backend/tests/test_system.py`

- [ ] **Step 1: Write the failing tests for system config defaults and compatibility endpoint**

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_system_config_endpoint():
    response = client.get("/api/v1/system/config")
    assert response.status_code == 200
    data = response.json()
    assert "sample_mode" in data
    assert "database_url" in data


def test_system_list_endpoint_masks_sensitive_values():
    response = client.get("/api/v1/system/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

- [ ] **Step 2: Run the failing system tests**

Run: `pytest backend/tests/test_system.py -q`
Expected: FAIL because `/api/v1/system/config` is not implemented and new platform defaults are not present.

- [ ] **Step 3: Add Hunter username and Quake defaults in the service layer**

```python
defaults = [
    ("fofa_email", "", "fofa", False),
    ("fofa_key", "", "fofa", True),
    ("fofa_page_size", "100", "fofa", False),
    ("fofa_max_pages", "10", "fofa", False),
    ("hunter_username", "", "hunter", False),
    ("hunter_api_key", "", "hunter", True),
    ("hunter_page_size", "100", "hunter", False),
    ("hunter_max_pages", "10", "hunter", False),
    ("hunter_base_url", "https://hunter.qianxin.com", "hunter", False),
    ("zoomeye_api_key", "", "zoomeye", True),
    ("zoomeye_page_size", "20", "zoomeye", False),
    ("zoomeye_max_pages", "10", "zoomeye", False),
    ("zoomeye_base_url", "https://api.zoomeye.ai", "zoomeye", False),
    ("quake_api_key", "", "quake", True),
    ("quake_page_size", "10", "quake", False),
    ("quake_max_pages", "10", "quake", False),
    ("quake_base_url", "https://quake.360.net", "quake", False),
]
```

- [ ] **Step 4: Add the compatibility config endpoint and clearer test-connection errors**

```python
@router.get("/config")
def get_runtime_system_config():
    return {
        "sample_mode": settings.sample_mode,
        "screenshot_output_dir": settings.screenshot_output_dir,
        "result_output_dir": settings.result_output_dir,
        "database_url": settings.database_url,
    }

@router.post("/test-connection")
async def test_platform_connection(payload: ConfigTestRequest, db: Session = Depends(get_db)):
    collector = get_collector(payload.platform)
    config_to_test = SystemConfigService.get_decrypted_configs(db, payload.platform)
    for key, value in payload.config.items():
        if value != "******":
            config_to_test[key] = value
    success = await collector.test_connection(config_to_test)
    return {"success": success, "platform": payload.platform}
```

- [ ] **Step 5: Update the system page UI without changing layout scope**

```vue
<el-tab-pane label="Quake" name="quake">
  <el-card shadow="never" class="config-card">
    <template #header>
      <div class="card-header">
        <span>Quake 平台配置</span>
        <el-button type="primary" link @click="testConnection('quake')">测试连接</el-button>
      </div>
    </template>
    <el-form label-position="top">
      <el-row :gutter="20">
        <el-col :span="24"><el-form-item label="Quake API Key"><el-input v-model="configMap.quake_api_key" type="password" show-password /></el-form-item></el-col>
        <el-col :xs="24" :sm="12"><el-form-item label="默认每页数量"><el-input-number v-model="configMap.quake_page_size" :min="1" :max="100" style="width: 100%" /></el-form-item></el-col>
        <el-col :xs="24" :sm="12"><el-form-item label="默认最大页数"><el-input-number v-model="configMap.quake_max_pages" :min="1" :max="100" style="width: 100%" /></el-form-item></el-col>
        <el-col :span="24"><el-form-item label="Base URL"><el-input v-model="configMap.quake_base_url" /></el-form-item></el-col>
      </el-row>
    </el-form>
  </el-card>
</el-tab-pane>
```

- [ ] **Step 6: Re-run the system tests**

Run: `pytest backend/tests/test_system.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/system_service.py backend/app/api/system.py backend/app/schemas/system.py frontend/src/views/SystemView.vue backend/tests/test_system.py
git commit -m "feat: complete source system settings"
```

### Task 2: Implement real FOFA / Hunter / ZoomEye / Quake collectors

**Files:**
- Modify: `backend/app/services/collectors/base.py`
- Modify: `backend/app/services/collectors/fofa.py`
- Modify: `backend/app/services/collectors/hunter.py`
- Modify: `backend/app/services/collectors/zoomeye.py`
- Modify: `backend/app/services/collectors/__init__.py`
- Create: `backend/app/services/collectors/quake.py`
- Test: `backend/tests/test_platform_collectors.py`

- [ ] **Step 1: Write failing collector tests for config validation and request shaping**

```python
import pytest
from app.services.collectors.fofa import FOFACollector
from app.services.collectors.hunter import HunterCollector
from app.services.collectors.zoomeye import ZoomEyeCollector
from app.services.collectors.quake import QuakeCollector

@pytest.mark.asyncio
async def test_fofa_test_connection_requires_email_and_key():
    with pytest.raises(ValueError, match="FOFA email 未配置"):
        await FOFACollector().test_connection({})

@pytest.mark.asyncio
async def test_quake_test_connection_requires_api_key():
    with pytest.raises(ValueError, match="Quake API Key 未配置"):
        await QuakeCollector().test_connection({})
```

- [ ] **Step 2: Run the failing collector tests**

Run: `pytest backend/tests/test_platform_collectors.py -q`
Expected: FAIL because Hunter/ZoomEye are still stubs and Quake collector does not exist.

- [ ] **Step 3: Add small shared helpers in `BaseCollector`**

```python
class BaseCollector(ABC):
    def require_config(self, config: Dict[str, Any], key: str, label: str) -> str:
        value = str(config.get(key, "")).strip()
        if not value:
            raise ValueError(f"{label} 未配置")
        return value

    def get_int_option(self, options: Dict[str, Any], config: Dict[str, Any], option_key: str, config_key: str, default: int) -> int:
        raw = options.get(option_key, config.get(config_key, default))
        return max(1, int(raw))
```

- [ ] **Step 4: Implement the four collectors with clear auth, pagination, and normalize logic**

```python
class QuakeCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "quake"

    async def test_connection(self, config: Dict[str, Any]) -> bool:
        token = self.require_config(config, "quake_api_key", "Quake API Key")
        base_url = str(config.get("quake_base_url") or "https://quake.360.net").rstrip("/")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}/api/v3/user/info", headers={"X-QuakeToken": token})
            if resp.status_code == 401:
                raise RuntimeError("Quake 认证失败")
            resp.raise_for_status()
            return True
```

```python
async def run(self, query: str, options: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    token = self.require_config(config, "quake_api_key", "Quake API Key")
    page_size = self.get_int_option(options, config, "page_size", "quake_page_size", 10)
    max_pages = self.get_int_option(options, config, "max_pages", "quake_max_pages", 10)
    base_url = str(config.get("quake_base_url") or "https://quake.360.net").rstrip("/")
    results: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=float(options.get("timeout") or 30)) as client:
        for page in range(max_pages):
            payload = {"query": query, "start": page * page_size, "size": page_size}
            resp = await client.post(f"{base_url}/api/v3/search/quake_service", json=payload, headers={"X-QuakeToken": token})
            resp.raise_for_status()
            data = resp.json().get("data") or []
            if not data:
                break
            for item in data:
                raw = {
                    "ip": item.get("ip"),
                    "port": item.get("port"),
                    "protocol": item.get("service"),
                    "host": item.get("host"),
                    "domain": item.get("domain"),
                    "title": item.get("title"),
                    "server": item.get("server"),
                    "country": item.get("country"),
                    "city": item.get("city"),
                    "url": item.get("url") or item.get("http_load_url"),
                }
                results.append(self.normalize(raw))
    return results
```

- [ ] **Step 5: Register Quake and re-run collector tests**

Run: `pytest backend/tests/test_platform_collectors.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/collectors/base.py backend/app/services/collectors/fofa.py backend/app/services/collectors/hunter.py backend/app/services/collectors/zoomeye.py backend/app/services/collectors/quake.py backend/app/services/collectors/__init__.py backend/tests/test_platform_collectors.py
git commit -m "feat: implement four source collectors"
```

### Task 3: Repair collection task creation, execution, logging, and results preview

**Files:**
- Modify: `backend/app/schemas/job.py`
- Modify: `backend/app/api/jobs.py`
- Modify: `backend/app/tasks/collect.py`
- Modify: `frontend/src/views/JobsView.vue`
- Modify: `frontend/src/api/modules/jobs.ts`
- Modify: `frontend/src/types/index.ts`
- Test: `backend/tests/test_jobs_start_task.py`
- Test: `backend/tests/test_collect_runtime.py`
- Create: `backend/tests/test_job_results_preview.py`

- [ ] **Step 1: Write failing tests for richer payloads and real job results preview**

```python
def test_start_task_dispatches_collect_job_in_process(monkeypatch):
    ...
    assert result == {"message": "Job started in background", "job_id": "job-1"}


def test_get_job_results_returns_assets_from_observations():
    response = client.get("/api/v1/jobs/job-1/results")
    assert response.status_code == 200
    assert response.json()[0]["normalized_url"] == "https://example.com"
```

- [ ] **Step 2: Run the failing job tests**

Run: `pytest backend/tests/test_jobs_start_task.py backend/tests/test_collect_runtime.py backend/tests/test_job_results_preview.py -q`
Expected: FAIL because results preview is empty and query options/source metadata are not persisted.

- [ ] **Step 3: Extend the job payload to carry source options and CSV source type**

```python
class CollectJobCreate(BaseModel):
    job_name: str
    sources: list[str]
    queries: list[dict]
    time_window: dict | None = None
    file_path: str | None = None
    source_type: str | None = None
    created_by: str = "system"
    dedup_strategy: str = "skip"
    field_mapping: dict[str, str] = Field(default_factory=dict)
    auto_verify: bool = False
```

- [ ] **Step 4: Persist richer query payloads and return real job result previews**

```python
query_payload = {
    "queries": payload.queries,
    "time_window": payload.time_window,
    "source_type": payload.source_type,
}
if payload.file_path:
    query_payload["file_path"] = payload.file_path
```

```python
@router.get("/{job_id}/results")
def get_job_results(job_id: str, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    observations = (
        db.query(SourceObservation)
        .filter(SourceObservation.collect_job_id == job_id)
        .order_by(desc(SourceObservation.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    assets = []
    seen = set()
    for obs in observations:
        web_id = (obs.raw_payload or {}).get("web_endpoint_id")
        if not web_id or web_id in seen:
            continue
        asset = db.get(WebEndpoint, web_id)
        if asset:
            assets.append(serialize_asset(asset))
            seen.add(web_id)
    return assets
```

- [ ] **Step 5: Repair `save_assets()` and `run_collect_task()` so counts, duplicate observations, statuses, and progress are real**

```python
if existing_web:
    touch_existing_web_endpoint(existing_web, observed_at)
    web = existing_web
    dup_count += 1
else:
    web = WebEndpoint(...)
    db.add(web)
    success_count += 1

db.flush()
raw_payload = dict(asset_data.get("raw_data") or {})
raw_payload.update({
    "web_endpoint_id": web.id,
    "normalized_url": norm_url,
    "source": source_name,
})
db.add(SourceObservation(
    collect_job_id=job.id,
    source_name=source_name,
    raw_payload=raw_payload,
    observed_at=observed_at,
))
```

```python
source_errors: list[str] = []
...
except Exception as exc:
    logger.exception("Collector %s failed", src_name)
    source_errors.append(f"{src_name} failed: {exc}")
...
if source_errors and (job.success_count > 0 or job.duplicate_count > 0):
    job.status = "partial_success"
elif source_errors:
    job.status = "failed"
else:
    job.status = "success"
job.progress = 100
job.error_message = " | ".join(source_errors) or None
```

- [ ] **Step 6: Enable the four online sources and source execution options in the existing jobs page**

```ts
const sourceOptions = [
  { label: 'FOFA', value: 'fofa' },
  { label: 'Hunter', value: 'hunter' },
  { label: 'ZoomEye', value: 'zoomeye' },
  { label: 'Quake', value: 'quake' },
]
```

```ts
const createForm = reactive({
  job_name: '',
  selectedSources: ['fofa'] as string[],
  queries: { fofa: '', hunter: '', zoomeye: '', quake: '' } as Record<string, string>,
  page_size: 20,
  max_pages: 5,
  limit: 100,
  timeout: 30,
  concurrency: 5,
  dedup_strategy: 'skip',
  auto_verify: false,
})
```

```ts
const queries = createForm.selectedSources.map((source) => ({
  source,
  query: createForm.queries[source] ?? '',
  page_size: createForm.page_size,
  max_pages: createForm.max_pages,
  limit: createForm.limit,
  timeout: createForm.timeout,
  concurrency: createForm.concurrency,
}))
```

- [ ] **Step 7: Re-run the targeted backend tests**

Run: `pytest backend/tests/test_jobs_start_task.py backend/tests/test_collect_runtime.py backend/tests/test_job_results_preview.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/job.py backend/app/api/jobs.py backend/app/tasks/collect.py frontend/src/views/JobsView.vue frontend/src/api/modules/jobs.ts frontend/src/types/index.ts backend/tests/test_jobs_start_task.py backend/tests/test_collect_runtime.py backend/tests/test_job_results_preview.py
git commit -m "fix: make collection tasks execute and preview real results"
```

### Task 4: Add four-source CSV import support with detection and mapping hints

**Files:**
- Modify: `backend/app/services/collectors/mapped_csv.py`
- Modify: `backend/app/services/collectors/preview.py`
- Modify: `backend/app/tasks/collect.py`
- Modify: `backend/app/api/jobs.py`
- Modify: `frontend/src/views/JobsView.vue`
- Modify: `frontend/src/types/index.ts`
- Create: `backend/app/services/collectors/zoomeye_csv.py`
- Create: `backend/app/services/collectors/quake_csv.py`
- Test: `backend/tests/test_mapped_csv.py`
- Test: `backend/tests/test_collect_csv_import.py`
- Test: `backend/tests/test_jobs_csv_validation.py`

- [ ] **Step 1: Write failing tests for source detection and ZoomEye/Quake CSV parsing**

```python
def test_parse_mapped_csv_counts_bad_rows_and_defaults_protocol():
    ...


def test_detect_csv_source_returns_zoomeye_for_zoomeye_headers():
    assert detect_csv_source(["site", "ip", "portinfo.port"]) == "zoomeye"
```

- [ ] **Step 2: Run the failing CSV tests**

Run: `pytest backend/tests/test_mapped_csv.py backend/tests/test_collect_csv_import.py backend/tests/test_jobs_csv_validation.py -q`
Expected: FAIL because CSV source detection and ZoomEye/Quake adapters do not exist.

- [ ] **Step 3: Add CSV detection and adapter dispatch**

```python
def detect_csv_source(headers: list[str]) -> str | None:
    normalized = {header.strip().lower() for header in headers}
    if {"link", "ip", "port"}.issubset(normalized):
        return "fofa"
    if {"ip", "端口", "网站标题"}.issubset(normalized):
        return "hunter"
    if {"site", "ip", "portinfo.port"}.intersection(normalized):
        return "zoomeye"
    if {"ip", "port", "service", "url"}.intersection(normalized):
        return "quake"
    return None
```

```python
if source_type == "fofa":
    records = parse_fofa_csv(file_path)
elif source_type == "hunter":
    records = parse_hunter_csv(file_path)
elif source_type == "zoomeye":
    records = parse_zoomeye_csv(file_path)
elif source_type == "quake":
    records = parse_quake_csv(file_path)
else:
    parse_result = parse_mapped_csv(file_path, job.field_mapping or {})
```

- [ ] **Step 4: Return detection metadata from preview and expose source selection in the jobs page**

```python
preview_data = get_csv_preview(target_path)
return {
    **preview_data,
    "file_path": str(target_path),
    "detected_source_type": detect_csv_source(preview_data["headers"]),
}
```

```ts
const csvSourceType = ref<'auto' | 'fofa' | 'hunter' | 'zoomeye' | 'quake'>('auto')
...
const res = await createCollectJob({
  job_name: createForm.job_name,
  sources: ['csv_import'],
  queries: [],
  file_path: csvPreview.value.file_path,
  source_type: csvSourceType.value,
  field_mapping: fieldMapping,
  dedup_strategy: createForm.dedup_strategy,
  auto_verify: createForm.auto_verify,
})
```

- [ ] **Step 5: Re-run the CSV tests**

Run: `pytest backend/tests/test_mapped_csv.py backend/tests/test_collect_csv_import.py backend/tests/test_jobs_csv_validation.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/collectors/mapped_csv.py backend/app/services/collectors/preview.py backend/app/tasks/collect.py backend/app/api/jobs.py frontend/src/views/JobsView.vue frontend/src/types/index.ts backend/app/services/collectors/zoomeye_csv.py backend/app/services/collectors/quake_csv.py backend/tests/test_mapped_csv.py backend/tests/test_collect_csv_import.py backend/tests/test_jobs_csv_validation.py
git commit -m "feat: support four-source csv imports"
```

### Task 5: Repair host verification visibility and failure reporting

**Files:**
- Modify: `backend/app/api/assets.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/views/AssetsView.vue`
- Modify: `frontend/src/views/AssetDetailView.vue`
- Test: `backend/tests/test_verify_batch.py`
- Test: `backend/tests/test_verify_progress.py`

- [ ] **Step 1: Write failing verification tests for visible failure reasons**

```python
@pytest.mark.asyncio
async def test_process_one_asset_records_verify_error_on_status_failure():
    ...
    assert asset.source_meta["verify_error"] == "请求超时"
```

- [ ] **Step 2: Run the failing verification tests**

Run: `pytest backend/tests/test_verify_batch.py backend/tests/test_verify_progress.py -q`
Expected: FAIL because verification failures do not persist a user-visible error reason.

- [ ] **Step 3: Persist verification error details and improve runtime messages**

```python
async def fetch_status_code_with_playwright(context, url: str) -> tuple[int | None, str | None]:
    page = await context.new_page()
    try:
        response = await page.goto(url, wait_until="commit", timeout=8000)
        return (response.status if response else None, None if response else "未收到响应")
    except Exception as exc:
        logger.warning("Verify request failed for %s: %s", url, exc)
        return None, str(exc)
    finally:
        await page.close()
```

```python
meta = dict(asset.source_meta or {})
status_code, verify_error = await fetch_status_code_with_playwright(context, asset_url)
asset.verified = status_code is not None and verified
asset.status_code = status_code
if verify_error:
    meta["verify_error"] = verify_error
else:
    meta.pop("verify_error", None)
asset.source_meta = meta
```

```python
return {
    "id": asset.id,
    "normalized_url": asset.normalized_url,
    ...,
    "verify_error": source_meta.get("verify_error"),
}
```

- [ ] **Step 4: Show the failure reason in the existing verification-related detail UI only**

```ts
export interface AssetItem {
  id: string
  normalized_url: string
  ...
  verify_error?: string | null
}
```

```vue
<el-descriptions-item label="验证失败原因">
  {{ editingAsset.verify_error || '-' }}
</el-descriptions-item>
```

- [ ] **Step 5: Re-run the verification tests**

Run: `pytest backend/tests/test_verify_batch.py backend/tests/test_verify_progress.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/assets.py frontend/src/types/index.ts frontend/src/views/AssetsView.vue frontend/src/views/AssetDetailView.vue backend/tests/test_verify_batch.py backend/tests/test_verify_progress.py
git commit -m "fix: make host verification results visible"
```

### Task 6: Final targeted verification

**Files:**
- Verify only: backend tests and frontend build affected by the four target modules.

- [ ] **Step 1: Run all targeted backend tests**

Run: `pytest backend/tests/test_system.py backend/tests/test_platform_collectors.py backend/tests/test_jobs_start_task.py backend/tests/test_collect_runtime.py backend/tests/test_job_results_preview.py backend/tests/test_mapped_csv.py backend/tests/test_collect_csv_import.py backend/tests/test_jobs_csv_validation.py backend/tests/test_verify_batch.py backend/tests/test_verify_progress.py -q`
Expected: PASS

- [ ] **Step 2: Run frontend build**

Run: `npm run build`
Expected: PASS

- [ ] **Step 3: Manual smoke check**

Run:
- Open `/system` and save/test FOFA/Hunter/ZoomEye/Quake config.
- Open `/jobs` and create one online collection task with FOFA/Hunter/ZoomEye/Quake.
- Open `/jobs` and create one CSV import task with explicit `source_type` and one with `auto`.
- Open `/assets` and run batch verification.
Expected:
- Jobs move through pending/running/success or partial_success.
- Logs show request start, failure reason, and write summary.
- Assets appear in results preview and asset list.
- Verification result and failure reason are visible.

- [ ] **Step 4: Commit**

```bash
git add backend frontend
git commit -m "fix: repair collection config csv and verify flow"
```
