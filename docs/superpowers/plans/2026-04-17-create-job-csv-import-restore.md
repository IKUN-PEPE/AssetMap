# Restore CSV Import In Create Job Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the two-step CSV import flow in the create-collect-job dialog and wire it into the existing async task center so CSV uploads preview, map, create, and execute successfully end to end.

**Architecture:** Add server-side guardrails for CSV jobs, introduce a focused `mapped_csv` parser service, and route `csv_import` jobs through the existing task-side persistence path in `backend/app/tasks/collect.py` so dedup, progress, and job counters stay consistent. On the frontend, rebuild the create-job dialog into a mode-based flow that drives `preview -> mapping -> collect -> startTask` while keeping the existing online-source workflow intact.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, Huey, Vue 3, Element Plus, TypeScript, pytest, vue-tsc, Vite

---

## File Map

- Create: `backend/app/services/collectors/mapped_csv.py`
  - Parse a CSV file plus `field_mapping` into normalized records and count bad rows.
- Create: `backend/tests/test_jobs_csv_validation.py`
  - Lock CSV-specific schema and preview guardrails.
- Create: `backend/tests/test_mapped_csv.py`
  - Unit-test record mapping, defaults, and bad-row counting.
- Create: `backend/tests/test_collect_csv_import.py`
  - Verify the collect-task CSV branch updates counters and reuses task-side persistence.
- Modify: `backend/app/schemas/job.py`
  - Reject `csv_import` payloads missing `file_path` or required mappings.
- Modify: `backend/app/services/collectors/preview.py`
  - Reject headerless CSV files during preview.
- Modify: `backend/app/tasks/collect.py`
  - Add a dedicated `process_csv_import_job()` helper and branch `csv_import` jobs into it.
- Modify: `frontend/src/views/JobsView.vue`
  - Restore the two-step CSV dialog flow, preview request, mapping validation, and create/start path.

## Task 1: Add CSV Guardrails At The Boundary

**Files:**
- Modify: `backend/app/schemas/job.py`
- Modify: `backend/app/services/collectors/preview.py`
- Test: `backend/tests/test_jobs_csv_validation.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.job import CollectJobCreate
from app.services.collectors.preview import get_csv_preview


def test_collect_job_create_requires_file_path_and_required_mapping_for_csv_import():
    with pytest.raises(
        ValidationError,
        match="csv_import requires file_path and field_mapping for url, ip, port",
    ):
        CollectJobCreate(
            job_name="csv-import",
            sources=["csv_import"],
            queries=[],
            file_path=None,
            field_mapping={"url": "link", "ip": "ip"},
        )


def test_get_csv_preview_rejects_headerless_file(tmp_path: Path):
    csv_path = tmp_path / "no-header.csv"
    csv_path.write_text("https://example.com,1.1.1.1,443\n", encoding="utf-8-sig")

    with pytest.raises(ValueError, match="CSV 文件缺少表头"):
        get_csv_preview(csv_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run from `backend/`:

```bash
pytest tests/test_jobs_csv_validation.py -q
```

Expected: FAIL because `CollectJobCreate` currently accepts the invalid payload and `get_csv_preview()` currently returns empty headers instead of raising.

- [ ] **Step 3: Write minimal implementation**

Update `backend/app/schemas/job.py`:

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CollectJobCreate(BaseModel):
    job_name: str
    sources: list[str]
    queries: list[dict]
    time_window: dict | None = None
    file_path: str | None = None
    created_by: str = "system"
    dedup_strategy: str = "skip"
    field_mapping: dict[str, str] = Field(default_factory=dict)
    auto_verify: bool = False

    @model_validator(mode="after")
    def validate_csv_import_payload(self):
        if "csv_import" not in self.sources:
            return self

        required_fields = {"url", "ip", "port"}
        missing_fields = sorted(
            field for field in required_fields if not self.field_mapping.get(field)
        )
        if not self.file_path or missing_fields:
            raise ValueError(
                "csv_import requires file_path and field_mapping for url, ip, port"
            )
        return self
```

Update `backend/app/services/collectors/preview.py`:

```python
def get_csv_preview(file_path: Path) -> dict:
    headers = []
    rows = []

    if not file_path.exists():
        logger.error("File not found for preview: %s", file_path)
        return {"headers": [], "rows": []}

    with open(file_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames if reader.fieldnames else []
        if not headers:
            raise ValueError("CSV 文件缺少表头")

        for count, row in enumerate(reader):
            if count >= 10:
                break
            rows.append({k: (v if v is not None else "") for k, v in row.items()})

    return {"headers": headers, "rows": rows}
```

- [ ] **Step 4: Run test to verify it passes**

Run from `backend/`:

```bash
pytest tests/test_jobs_csv_validation.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/job.py backend/app/services/collectors/preview.py backend/tests/test_jobs_csv_validation.py
git commit -m "test(api): add csv payload guardrails"
```

## Task 2: Add The Mapped CSV Parser Service

**Files:**
- Create: `backend/app/services/collectors/mapped_csv.py`
- Test: `backend/tests/test_mapped_csv.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from app.services.collectors.mapped_csv import MappedCsvParseResult, parse_mapped_csv


def test_parse_mapped_csv_maps_required_and_optional_fields(tmp_path: Path):
    csv_path = tmp_path / "assets.csv"
    csv_path.write_text(
        "link,host_ip,svc_port,site_title,proto,status\n"
        "https://demo.example.com,1.1.1.1,443,Portal,https,200\n",
        encoding="utf-8-sig",
    )

    result = parse_mapped_csv(
        csv_path,
        {
            "url": "link",
            "ip": "host_ip",
            "port": "svc_port",
            "title": "site_title",
            "protocol": "proto",
            "status_code": "status",
        },
    )

    assert result == MappedCsvParseResult(
        records=[
            {
                "source": "csv_import",
                "ip": "1.1.1.1",
                "port": 443,
                "protocol": "https",
                "domain": None,
                "url": "https://demo.example.com",
                "title": "Portal",
                "status_code": 200,
                "observed_at": None,
                "country": None,
                "city": None,
                "org": None,
                "host": None,
            }
        ],
        failed_rows=0,
    )


def test_parse_mapped_csv_counts_bad_rows_and_defaults_protocol(tmp_path: Path):
    csv_path = tmp_path / "assets.csv"
    csv_path.write_text(
        "url,ip,port,title\n"
        "https://demo.example.com,1.1.1.1,443,Portal\n"
        "https://broken.example.com,2.2.2.2,not-a-port,Broken\n"
        ",3.3.3.3,8443,Missing Url\n",
        encoding="utf-8-sig",
    )

    result = parse_mapped_csv(
        csv_path,
        {"url": "url", "ip": "ip", "port": "port", "title": "title"},
    )

    assert result.failed_rows == 2
    assert result.records == [
        {
            "source": "csv_import",
            "ip": "1.1.1.1",
            "port": 443,
            "protocol": "http",
            "domain": None,
            "url": "https://demo.example.com",
            "title": "Portal",
            "status_code": None,
            "observed_at": None,
            "country": None,
            "city": None,
            "org": None,
            "host": None,
        }
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run from `backend/`:

```bash
pytest tests/test_mapped_csv.py -q
```

Expected: FAIL with `ModuleNotFoundError` because `mapped_csv.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/collectors/mapped_csv.py`:

```python
import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(eq=True)
class MappedCsvParseResult:
    records: list[dict]
    failed_rows: int


def parse_mapped_csv(
    file_path: str | Path, field_mapping: dict[str, str]
) -> MappedCsvParseResult:
    path = Path(file_path)
    records: list[dict] = []
    failed_rows = 0

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                url = _get_value(row, field_mapping, "url")
                ip = _get_value(row, field_mapping, "ip")
                port = _coerce_int(_get_value(row, field_mapping, "port"))
                if not url or not ip or port is None:
                    failed_rows += 1
                    continue

                status_code = _coerce_int(_get_value(row, field_mapping, "status_code"))
                records.append(
                    {
                        "source": "csv_import",
                        "ip": ip,
                        "port": port,
                        "protocol": _get_value(row, field_mapping, "protocol") or "http",
                        "domain": _get_value(row, field_mapping, "domain") or None,
                        "url": url,
                        "title": _get_value(row, field_mapping, "title") or None,
                        "status_code": status_code,
                        "observed_at": None,
                        "country": _get_value(row, field_mapping, "country") or None,
                        "city": _get_value(row, field_mapping, "city") or None,
                        "org": _get_value(row, field_mapping, "org") or None,
                        "host": _get_value(row, field_mapping, "host") or None,
                    }
                )
            except ValueError:
                failed_rows += 1

    return MappedCsvParseResult(records=records, failed_rows=failed_rows)


def _get_value(row: dict[str, str], field_mapping: dict[str, str], target_field: str) -> str:
    column_name = field_mapping.get(target_field)
    if not column_name:
        return ""
    return (row.get(column_name) or "").strip()


def _coerce_int(raw_value: str) -> int | None:
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run from `backend/`:

```bash
pytest tests/test_mapped_csv.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/collectors/mapped_csv.py backend/tests/test_mapped_csv.py
git commit -m "feat(collectors): add mapped csv parser"
```

## Task 3: Route `csv_import` Jobs Through The Collect Task

**Files:**
- Modify: `backend/app/tasks/collect.py`
- Test: `backend/tests/test_collect_csv_import.py`

- [ ] **Step 1: Write the failing tests**

```python
from types import SimpleNamespace

import pytest

from app.services.collectors.mapped_csv import MappedCsvParseResult
from app.tasks import collect


class FakeDb:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def test_process_csv_import_job_updates_counts_and_reuses_save_assets(monkeypatch):
    job = SimpleNamespace(
        id="job-1",
        query_payload={"file_path": "assets.csv"},
        field_mapping={"url": "link", "ip": "ip", "port": "port"},
        success_count=0,
        failed_count=0,
        duplicate_count=0,
        total_count=0,
        progress=0,
    )
    db = FakeDb()
    seen = {}

    monkeypatch.setattr(
        collect,
        "parse_mapped_csv",
        lambda *args, **kwargs: MappedCsvParseResult(
            records=[
                {
                    "source": "csv_import",
                    "ip": "1.1.1.1",
                    "port": 443,
                    "protocol": "https",
                    "domain": None,
                    "url": "https://demo.example.com",
                    "title": "Portal",
                    "status_code": 200,
                    "observed_at": None,
                    "country": None,
                    "city": None,
                    "org": None,
                    "host": None,
                }
            ],
            failed_rows=1,
        ),
    )

    def fake_save_assets(db, job, assets, source_name):
        seen["assets"] = assets
        seen["source_name"] = source_name
        job.success_count += 1

    monkeypatch.setattr(collect, "save_assets", fake_save_assets)

    collect.process_csv_import_job(db, job)

    assert seen["source_name"] == "csv_import"
    assert seen["assets"][0]["raw_data"]["status_code"] == 200
    assert job.total_count == 2
    assert job.failed_count == 1
    assert job.progress == 100


def test_process_csv_import_job_requires_file_path():
    job = SimpleNamespace(
        query_payload={},
        field_mapping={"url": "link", "ip": "ip", "port": "port"},
        success_count=0,
        failed_count=0,
        duplicate_count=0,
        total_count=0,
        progress=0,
    )

    with pytest.raises(ValueError, match="csv_import job is missing file_path"):
        collect.process_csv_import_job(FakeDb(), job)
```

- [ ] **Step 2: Run test to verify it fails**

Run from `backend/`:

```bash
pytest tests/test_collect_csv_import.py -q
```

Expected: FAIL because `process_csv_import_job()` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Update `backend/app/tasks/collect.py` imports:

```python
from app.services.collectors.mapped_csv import parse_mapped_csv
```

Add the helper to `backend/app/tasks/collect.py`:

```python
def process_csv_import_job(db: Session, job: CollectJob):
    query_payload = job.query_payload or {}
    file_path = query_payload.get("file_path")
    if not file_path:
        raise ValueError("csv_import job is missing file_path")

    parse_result = parse_mapped_csv(file_path, job.field_mapping or {})
    job.total_count = len(parse_result.records) + parse_result.failed_rows
    db.commit()

    assets = [
        {
            "ip": record["ip"],
            "port": record["port"],
            "url": record["url"],
            "title": record.get("title"),
            "protocol": record.get("protocol"),
            "raw_data": record,
        }
        for record in parse_result.records
    ]
    save_assets(db, job, assets, "csv_import")
    job.failed_count += parse_result.failed_rows
    job.total_count = job.success_count + job.failed_count + job.duplicate_count
    job.progress = 100
    db.commit()
```

Branch the main task body in `backend/app/tasks/collect.py`:

```python
        sources = job.sources
        query_payload = job.query_payload or {}

        if "csv_import" in sources:
            process_csv_import_job(db, job)
        else:
            queries = query_payload.get("queries", [])
            for q_item in queries:
                src_name = q_item.get("source")
                query_str = q_item.get("query")
                if not src_name or not query_str:
                    continue

                logger.info("Starting collection for %s with query: %s", src_name, query_str)
                try:
                    collector = get_collector(src_name)
                    config = SystemConfigService.get_decrypted_configs(db, src_name)
                    loop = asyncio.get_event_loop()
                    assets = loop.run_until_complete(
                        collector.run(query_str, query_payload, config)
                    )
                    save_assets(db, job, assets, src_name)
                except Exception as e:
                    logger.exception("Collector %s failed", src_name)
                    job.error_message = f"{src_name} failed: {str(e)}"
                    db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run from `backend/`:

```bash
pytest tests/test_collect_csv_import.py tests/test_mapped_csv.py tests/test_jobs_csv_validation.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/collect.py backend/tests/test_collect_csv_import.py
git commit -m "feat(tasks): add csv import collect branch"
```

## Task 4: Restore The Two-Step CSV Dialog In `JobsView`

**Files:**
- Modify: `frontend/src/views/JobsView.vue`

Note: this repo does not have a dedicated frontend unit-test runner, so use incremental `vite`/`vue-tsc` build checks as the verification gate for this task.

- [ ] **Step 1: Refactor the dialog state and methods for mode-based create flows**

Replace the `JobsView.vue` create-dialog state and imports with:

```ts
import { ref, computed, onMounted, onUnmounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, MoreFilled, UploadFilled } from '@element-plus/icons-vue'
import {
  listJobs,
  startTask,
  stopTask,
  getTaskStatus,
  createCollectJob,
  previewCsv,
} from '@/api/modules/jobs'

type CreateMode = 'online' | 'csv'
type CsvFieldKey =
  | 'url'
  | 'ip'
  | 'port'
  | 'title'
  | 'protocol'
  | 'domain'
  | 'status_code'
  | 'org'
  | 'country'
  | 'city'
  | 'host'

const requiredCsvFieldKeys: CsvFieldKey[] = ['url', 'ip', 'port']
const optionalCsvFieldKeys: CsvFieldKey[] = [
  'title',
  'protocol',
  'domain',
  'status_code',
  'org',
  'country',
  'city',
  'host',
]

const createMode = ref<CreateMode>('online')
const createStep = ref<1 | 2>(1)
const previewLoading = ref(false)
const selectedCsvFile = ref<File | null>(null)
const csvPreview = ref<{
  headers: string[]
  rows: Array<Record<string, string>>
  file_path: string
}>({
  headers: [],
  rows: [],
  file_path: '',
})

const csvFieldMapping = reactive<Record<CsvFieldKey, string>>({
  url: '',
  ip: '',
  port: '',
  title: '',
  protocol: '',
  domain: '',
  status_code: '',
  org: '',
  country: '',
  city: '',
  host: '',
})

function resetCreateDialog() {
  createMode.value = 'online'
  createStep.value = 1
  selectedCsvFile.value = null
  csvPreview.value = { headers: [], rows: [], file_path: '' }
  for (const key of [...requiredCsvFieldKeys, ...optionalCsvFieldKeys]) {
    csvFieldMapping[key] = ''
  }
  createForm.job_name = `采集任务_${dayjs().format('MMDD_HHmm')}`
  createForm.selectedSources = ['fofa']
  createForm.queries = { fofa: '', oneforall: '' }
  createForm.dedup_strategy = 'skip'
  createForm.auto_verify = false
}

function openCreateDialog() {
  resetCreateDialog()
  showCreateDialog.value = true
}

function onCsvFileChange(uploadFile: File) {
  selectedCsvFile.value = uploadFile
}

function autoMatchCsvFields(headers: string[]) {
  const rules: Record<CsvFieldKey, string[]> = {
    url: ['url', 'link', '链接'],
    ip: ['ip', 'host_ip', 'ip地址'],
    port: ['port', 'svc_port', '端口'],
    title: ['title', 'site_title', '标题'],
    protocol: ['protocol', 'proto', 'scheme'],
    domain: ['domain', 'host', '域名'],
    status_code: ['status_code', 'status', 'code'],
    org: ['org', 'organization'],
    country: ['country'],
    city: ['city'],
    host: ['host'],
  }

  for (const key of Object.keys(rules) as CsvFieldKey[]) {
    const match = headers.find((header) =>
      rules[key].some((rule) => header.toLowerCase().includes(rule.toLowerCase())),
    )
    csvFieldMapping[key] = match ?? ''
  }
}

async function goToCsvMapping() {
  if (!selectedCsvFile.value) {
    ElMessage.error('请先选择 CSV 文件')
    return
  }

  previewLoading.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedCsvFile.value)
    const preview = await previewCsv(formData)
    csvPreview.value = preview
    autoMatchCsvFields(preview.headers)
    createStep.value = 2
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error.message ?? 'CSV 预览失败')
  } finally {
    previewLoading.value = false
  }
}

function validateCsvMapping() {
  const missing = requiredCsvFieldKeys.filter((key) => !csvFieldMapping[key])
  if (missing.length > 0) {
    ElMessage.error(`缺少必填映射: ${missing.join(', ')}`)
    return false
  }
  return true
}
```

- [ ] **Step 2: Run build to verify the script refactor still compiles before the template swap**

Run from the repo root:

```bash
npm --prefix frontend run build
```

Expected: PASS.

- [ ] **Step 3: Replace the dialog template and submit path with the two-step CSV flow**

Replace the create dialog block in `frontend/src/views/JobsView.vue` with:

```vue
<el-dialog v-model="showCreateDialog" title="新建资产采集任务" width="720px" custom-class="apple-dialog">
  <el-form v-if="createMode === 'online'" :model="createForm" label-position="top" ref="createFormRef">
    <el-form-item label="任务名称" required>
      <el-input v-model="createForm.job_name" placeholder="请输入任务名称" />
    </el-form-item>

    <el-form-item label="任务模式" required>
      <el-radio-group v-model="createMode">
        <el-radio-button label="online">在线采集</el-radio-button>
        <el-radio-button label="csv">导入CSV文件</el-radio-button>
      </el-radio-group>
    </el-form-item>

    <el-form-item label="采集来源" required>
      <el-checkbox-group v-model="createForm.selectedSources">
        <el-checkbox-button v-for="opt in sourceOptions" :key="opt.value" :label="opt.value" :disabled="opt.disabled">
          {{ opt.label }}
        </el-checkbox-button>
      </el-checkbox-group>
    </el-form-item>

    <div v-for="src in createForm.selectedSources" :key="src" class="query-input-box mb-3">
      <div class="box-header">
        <el-tag size="small">{{ src.toUpperCase() }}</el-tag>
        <span class="example">{{ getExample(src) }}</span>
      </div>
      <el-input v-model="createForm.queries[src]" type="textarea" :rows="2" :placeholder="getPlaceholder(src)" />
    </div>

    <el-form-item>
      <el-checkbox v-model="createForm.auto_verify">采集完成后自动触发验证与截图</el-checkbox>
    </el-form-item>
  </el-form>

  <div v-else>
    <el-form v-if="createStep === 1" :model="createForm" label-position="top">
      <el-form-item label="任务名称" required>
        <el-input v-model="createForm.job_name" placeholder="请输入任务名称" />
      </el-form-item>

      <el-form-item label="任务模式" required>
        <el-radio-group v-model="createMode">
          <el-radio-button label="online">在线采集</el-radio-button>
          <el-radio-button label="csv">导入CSV文件</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="CSV 文件" required>
        <el-upload :auto-upload="false" :show-file-list="false" accept=".csv" :on-change="(file) => onCsvFileChange(file.raw!)">
          <el-button type="primary" plain>
            <el-icon><UploadFilled /></el-icon>
            {{ selectedCsvFile ? selectedCsvFile.name : '选择 CSV 文件' }}
          </el-button>
        </el-upload>
      </el-form-item>

      <el-form-item label="去重策略">
        <el-select v-model="createForm.dedup_strategy" style="width: 100%">
          <el-option label="跳过重复 (Skip)" value="skip" />
          <el-option label="覆盖更新 (Overwrite)" value="overwrite" />
        </el-select>
      </el-form-item>

      <el-form-item>
        <el-checkbox v-model="createForm.auto_verify">采集完成后自动触发验证与截图</el-checkbox>
      </el-form-item>
    </el-form>

    <div v-else class="csv-mapping-step">
      <div class="section-title">CSV 预览</div>
      <el-table :data="csvPreview.rows.slice(0, 5)" size="small" border>
        <el-table-column v-for="header in csvPreview.headers" :key="header" :prop="header" :label="header" min-width="140" />
      </el-table>

      <div class="section-title mt-4">字段映射</div>
      <div class="mapping-grid">
        <div v-for="fieldKey in [...requiredCsvFieldKeys, ...optionalCsvFieldKeys]" :key="fieldKey" class="mapping-item">
          <label class="mapping-label">{{ fieldKey }}</label>
          <el-select v-model="csvFieldMapping[fieldKey]" clearable filterable>
            <el-option v-for="header in csvPreview.headers" :key="header" :label="header" :value="header" />
          </el-select>
        </div>
      </div>
    </div>
  </div>

  <template #footer>
    <el-button @click="showCreateDialog = false">取消</el-button>
    <template v-if="createMode === 'online'">
      <el-button type="primary" round @click="submitCreate" :loading="submitting">立即创建并开始</el-button>
    </template>
    <template v-else-if="createStep === 1">
      <el-button type="primary" round @click="goToCsvMapping" :loading="previewLoading">下一步：字段映射</el-button>
    </template>
    <template v-else>
      <el-button @click="createStep = 1">上一步</el-button>
      <el-button type="primary" round @click="submitCreate" :loading="submitting">完成创建并开始</el-button>
    </template>
  </template>
</el-dialog>
```

Update `submitCreate()` in `frontend/src/views/JobsView.vue`:

```ts
async function submitCreate() {
  submitting.value = true
  try {
    if (createMode.value === 'csv') {
      if (!validateCsvMapping()) {
        return
      }

      const payload = {
        job_name: createForm.job_name,
        sources: ['csv_import'],
        queries: [],
        file_path: csvPreview.value.file_path,
        field_mapping: Object.fromEntries(
          Object.entries(csvFieldMapping).filter(([, value]) => Boolean(value)),
        ),
        dedup_strategy: createForm.dedup_strategy,
        auto_verify: createForm.auto_verify,
      }

      const res = await createCollectJob(payload)
      ElMessage.success('CSV 导入任务已创建')
      showCreateDialog.value = false
      await startTask(res.job_id)
      await fetchJobs()
      return
    }

    if (createForm.selectedSources.length === 0) {
      ElMessage.warning('请至少选择一个在线采集来源')
      return
    }

    const queries = createForm.selectedSources.map((src) => ({
      source: src,
      query: createForm.queries[src],
    }))

    const res = await createCollectJob({
      job_name: createForm.job_name,
      sources: createForm.selectedSources,
      queries,
      dedup_strategy: createForm.dedup_strategy,
      auto_verify: createForm.auto_verify,
    })
    ElMessage.success('采集任务已创建')
    showCreateDialog.value = false
    await startTask(res.job_id)
    await fetchJobs()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error.message ?? '创建任务失败')
  } finally {
    submitting.value = false
  }
}
```

Update the job-card footer in `frontend/src/views/JobsView.vue` so failed CSV tasks expose their error:

```vue
<div class="job-card-footer">
  <span class="time" :title="job.error_message || formatTime(job.created_at)">
    {{ job.error_message || formatTime(job.created_at) }}
  </span>
  <el-button type="primary" link size="small" @click="viewDetails(job)">详情</el-button>
</div>
```

- [ ] **Step 4: Run build to verify it passes**

Run from the repo root:

```bash
npm --prefix frontend run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/JobsView.vue
git commit -m "feat(frontend): restore csv import create flow"
```

## Task 5: Run Focused Verification And Manual Smoke

**Files:**
- Modify: none
- Test: `backend/tests/test_jobs_csv_validation.py`
- Test: `backend/tests/test_mapped_csv.py`
- Test: `backend/tests/test_collect_csv_import.py`

- [ ] **Step 1: Run the backend CSV-focused test slice**

Run from `backend/`:

```bash
pytest tests/test_jobs_csv_validation.py tests/test_mapped_csv.py tests/test_collect_csv_import.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the frontend build gate**

Run from the repo root:

```bash
npm --prefix frontend run build
```

Expected: PASS.

- [ ] **Step 3: Manual smoke-test the CSV flow with the repo sample file**

Use the existing sample CSV at:

```text
C:\Users\Administrator\VScode\AssetMap\360鹰图导入.csv
```

Manual checklist:

- Open the task center page
- Click `新建资产采集任务`
- Switch to `导入CSV文件`
- Upload `360鹰图导入.csv`
- Confirm preview appears and `url/ip/port` can be mapped
- Click `完成创建并开始`
- Confirm a new task card appears and leaves `pending/running`
- Confirm `success_count / failed_count / duplicate_count / total_count` update

- [ ] **Step 4: Verify the failure path**

Manual checklist:

- Re-open the dialog
- Switch to `导入CSV文件`
- Upload the CSV
- Clear the `url` mapping
- Click `完成创建并开始`
- Confirm the dialog shows a validation error and no new task is created

- [ ] **Step 5: Record the outcome in the final handoff**

Include in the final completion note:

- The three backend test commands that passed
- The frontend build result
- Whether the manual smoke used `360鹰图导入.csv`
- Any remaining risk, especially around non-UTF-8 CSVs or uncommon column names
