<template>
  <div class="page-shell">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">资产采集任务</h1>
        <p class="page-subtitle">统一管理在线采集任务和 CSV 导入任务。</p>
      </div>
      <div class="header-actions">
        <el-radio-group v-model="taskListView" size="small">
          <el-radio-button label="active">当前任务</el-radio-button>
          <el-radio-button label="completed">已完成任务</el-radio-button>
        </el-radio-group>
        <el-button type="primary" round @click="openCreateDialog">
          <el-icon><Plus /></el-icon>
          新建资产采集任务
        </el-button>
      </div>
    </div>

    <div class="stats-grid mb-6">
      <div class="stats-card">
        <div class="stats-label">任务总数</div>
        <div class="stats-value">{{ jobs.length }}</div>
      </div>
      <div class="stats-card">
        <div class="stats-label">运行中</div>
        <div class="stats-value text-primary">{{ runningCount }}</div>
      </div>
      <div class="stats-card">
        <div class="stats-label">已完成</div>
        <div class="stats-value text-success">{{ completedCount }}</div>
      </div>
    </div>

    <el-empty v-if="visibleJobs.length === 0" :description="emptyDescription" />

    <el-row v-else :gutter="20">
      <el-col v-for="job in visibleJobs" :key="job.id" :xs="24" :sm="12" :lg="8" class="mb-5">
        <div class="job-card" :class="{ 'is-running': isJobRunning(job.status) }">
          <div class="job-card-header">
            <div class="job-info">
              <h3 class="job-name text-truncate" :title="job.job_name">{{ job.job_name }}</h3>
              <div class="job-meta">
                <el-tag
                  v-for="source in normalizeSources(job.sources)"
                  :key="`${job.id}-${source}`"
                  size="small"
                  effect="plain"
                  class="mr-1"
                >
                  {{ formatSourceLabel(source) }}
                </el-tag>
                <el-tag :type="getStatusType(job.status)" size="small" round>
                  {{ getStatusLabel(job.status) }}
                </el-tag>
              </div>
            </div>
            <el-button link @click="refreshJob(job.id)" title="刷新状态">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>

          <div class="job-card-content">
            <div class="progress-section mb-4">
              <div class="progress-info">
                <span>处理进度</span>
                <span>{{ job.progress }}%</span>
              </div>
              <el-progress :percentage="job.progress" :status="getProgressStatus(job.status)" :show-text="false" round />
            </div>

            <div class="counts-grid">
              <div class="count-item">
                <div class="count-value">{{ job.success_count }}</div>
                <div class="count-label">成功</div>
              </div>
              <div class="count-item">
                <div class="count-value text-warning">{{ job.duplicate_count }}</div>
                <div class="count-label">重复</div>
              </div>
              <div class="count-item">
                <div class="count-value text-danger">{{ job.failed_count }}</div>
                <div class="count-label">失败</div>
              </div>
              <div class="count-item">
                <div class="count-value">{{ job.total_count }}</div>
                <div class="count-label">总数</div>
              </div>
            </div>
          </div>

          <div class="job-card-footer">
            <div class="footer-left">
              <span class="time text-truncate" :title="job.error_message || formatTime(job.created_at)">
                {{ job.error_message || formatTime(job.created_at) }}
              </span>
            </div>
            <div class="footer-actions">
              <el-button v-if="!isJobRunning(job.status)" type="primary" link size="small" @click="handleStart(job.id)">
                开始
              </el-button>
              <el-button v-else type="danger" link size="small" @click="handleStop(job.id)">
                停止
              </el-button>
              <el-button type="primary" link size="small" @click="viewDetails(job)">详情</el-button>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-dialog
      v-model="showCreateDialog"
      title="新建资产采集任务"
      width="760px"
      custom-class="apple-dialog"
      @closed="resetCreateDialogState"
    >
      <el-form label-position="top">
        <el-form-item label="任务名称" required>
          <el-input v-model="createForm.job_name" placeholder="请输入任务名称" />
        </el-form-item>

        <el-form-item label="任务模式" required>
          <el-radio-group v-model="createMode" @change="handleCreateModeChange">
            <el-radio-button label="online">在线采集</el-radio-button>
            <el-radio-button label="csv">导入CSV文件</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="createMode === 'online'">
          <el-form-item label="采集来源" required>
            <el-checkbox-group v-model="createForm.selectedSources">
              <el-checkbox-button v-for="opt in sourceOptions" :key="opt.value" :label="opt.value">
                {{ opt.label }}
              </el-checkbox-button>
            </el-checkbox-group>
          </el-form-item>

          <el-row :gutter="20">
            <el-col :span="12"><el-form-item label="每页数量"><el-input-number v-model="createForm.page_size" :min="1" :max="1000" style="width:100%" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="最大页数"><el-input-number v-model="createForm.max_pages" :min="1" :max="100" style="width:100%" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="结果上限"><el-input-number v-model="createForm.limit" :min="1" :max="10000" style="width:100%" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="超时(秒)"><el-input-number v-model="createForm.timeout" :min="1" :max="300" style="width:100%" /></el-form-item></el-col>
          </el-row>

          <div v-for="src in createForm.selectedSources" :key="src" class="query-input-box mb-3">
            <div class="box-header">
              <el-tag size="small">{{ formatSourceLabel(src) }}</el-tag>
              <span class="example">{{ getExample(src) }}</span>
            </div>
            <el-input
              v-model="createForm.queries[src]"
              type="textarea"
              :rows="2"
              :placeholder="getPlaceholder(src)"
            />
          </div>
        </template>

        <template v-else>
          <div v-if="createStep === 1">
            <el-form-item label="CSV 文件" required>
              <input ref="csvInputRef" type="file" accept=".csv" class="hidden-input" @change="onCsvFileChange" />
              <div class="csv-upload-box" @click="triggerCsvFileDialog">
                <el-icon class="upload-icon"><UploadFilled /></el-icon>
                <div class="upload-title">{{ selectedCsvFile ? selectedCsvFile.name : '点击选择 CSV 文件' }}</div>
                <div class="upload-hint">支持 UTF-8 / UTF-8 BOM 编码的 .csv 文件</div>
              </div>
            </el-form-item>
          </div>

          <div v-else class="csv-mapping-step">
            <div class="section-title">CSV 预览</div>
            <el-table :data="csvPreview.rows.slice(0, 5)" size="small" border class="preview-table">
              <el-table-column v-for="header in csvPreview.headers" :key="header" :prop="header" :label="header" min-width="140" show-overflow-tooltip />
            </el-table>

            <el-form-item label="CSV 来源类型">
              <el-select v-model="csvSourceType" style="width:100%">
                <el-option label="自动识别 / 手动映射" value="auto" />
                <el-option label="FOFA" value="fofa" />
                <el-option label="Hunter" value="hunter" />
                <el-option label="ZoomEye" value="zoomeye" />
                <el-option label="Quake" value="quake" />
              </el-select>
            </el-form-item>

            <div class="section-title mt-4">字段映射</div>
            <div class="mapping-note">至少映射一个身份字段：URL / IP / 域名 / 主机名。</div>
            <div class="mapping-grid">
              <div v-for="field in csvFieldConfigs" :key="field.key" class="mapping-item">
                <label class="mapping-label">
                  {{ field.label }}
                  <span v-if="field.identity" class="identity-hint">身份字段</span>
                </label>
                <el-select v-model="csvFieldMapping[field.key]" clearable filterable placeholder="请选择 CSV 列" :disabled="csvSourceType !== 'auto'">
                  <el-option v-for="header in csvPreview.headers" :key="`${field.key}-${header}`" :label="header" :value="header" />
                </el-select>
              </div>
            </div>
          </div>
        </template>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="去重策略">
              <el-select v-model="createForm.dedup_strategy" style="width: 100%">
                <el-option label="跳过重复 (Skip)" value="skip" />
                <el-option label="覆盖更新 (Overwrite)" value="overwrite" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="自动验证">
              <el-checkbox v-model="createForm.auto_verify">采集完成后自动触发验证与截图</el-checkbox>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

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

    <JobDetailDrawer v-model:visible="isDrawerVisible" :job-id="selectedJobId" @rerun="onJobRerun" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh, UploadFilled } from '@element-plus/icons-vue'
import {
  createCollectJob,
  getTaskStatus,
  listJobs,
  previewCsv,
  startTask,
  stopTask,
} from '@/api/modules/jobs'
import type { CollectJob, CsvPreviewResponse } from '@/types'
import dayjs from 'dayjs'
import JobDetailDrawer from './JobDetailDrawer.vue'

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

type CsvSourceType = 'auto' | 'fofa' | 'hunter' | 'zoomeye' | 'quake'
type CsvFieldConfig = { key: CsvFieldKey; label: string; identity?: boolean }

const jobs = ref<CollectJob[]>([])
const taskListView = ref<'active' | 'completed'>('active')
const submitting = ref(false)
const previewLoading = ref(false)
const showCreateDialog = ref(false)
const createMode = ref<CreateMode>('online')
const createStep = ref<1 | 2>(1)
const selectedCsvFile = ref<File | null>(null)
const csvInputRef = ref<HTMLInputElement | null>(null)
const isDrawerVisible = ref(false)
const selectedJobId = ref<string | null>(null)
const csvSourceType = ref<CsvSourceType>('auto')

const sourceOptions = [
  { label: 'FOFA', value: 'fofa' },
  { label: 'Hunter', value: 'hunter' },
  { label: 'ZoomEye', value: 'zoomeye' },
  { label: 'Quake', value: 'quake' },
]

const csvFieldConfigs: CsvFieldConfig[] = [
  { key: 'url', label: 'URL', identity: true },
  { key: 'ip', label: 'IP', identity: true },
  { key: 'port', label: '端口' },
  { key: 'title', label: '标题' },
  { key: 'protocol', label: '协议' },
  { key: 'domain', label: '域名', identity: true },
  { key: 'status_code', label: '状态码' },
  { key: 'org', label: '组织' },
  { key: 'country', label: '国家' },
  { key: 'city', label: '城市' },
  { key: 'host', label: '主机名', identity: true },
]

const csvIdentityFieldKeys: CsvFieldKey[] = ['url', 'ip', 'domain', 'host']

const createForm = reactive({
  job_name: '',
  selectedSources: ['fofa'] as string[],
  queries: {
    fofa: '',
    hunter: '',
    zoomeye: '',
    quake: '',
  } as Record<string, string>,
  page_size: 20,
  max_pages: 5,
  limit: 100,
  timeout: 30,
  dedup_strategy: 'skip',
  auto_verify: false,
})

const csvPreview = ref<CsvPreviewResponse>({
  headers: [],
  rows: [],
  file_path: '',
  detected_source_type: null,
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

let timer: number | null = null

const activeStatuses: CollectJob['status'][] = ['pending', 'running']
const completedStatuses: CollectJob['status'][] = ['success', 'partial_success', 'failed', 'cancelled']

const runningCount = computed(() =>
  jobs.value.filter((job) => activeStatuses.includes(job.status)).length,
)
const completedCount = computed(() =>
  jobs.value.filter((job) => completedStatuses.includes(job.status)).length,
)
const visibleJobs = computed(() =>
  jobs.value.filter((job) =>
    taskListView.value === 'completed'
      ? completedStatuses.includes(job.status)
      : activeStatuses.includes(job.status),
  ),
)
const emptyDescription = computed(() =>
  taskListView.value === 'completed' ? '暂无已结束任务' : '暂无运行中或待处理任务',
)

watch(
  () => [...createForm.selectedSources],
  (sources) => {
    for (const source of sources) {
      if (!(source in createForm.queries)) {
        createForm.queries[source] = ''
      }
    }
  },
  { immediate: true },
)

async function fetchJobs() {
  try {
    jobs.value = await listJobs()
  } catch (error) {
    console.error('Fetch jobs failed:', error)
  }
}

function resetCreateDialogState() {
  createMode.value = 'online'
  createStep.value = 1
  csvSourceType.value = 'auto'
  selectedCsvFile.value = null
  csvPreview.value = {
    headers: [],
    rows: [],
    file_path: '',
    detected_source_type: null,
  }
  for (const field of csvFieldConfigs) {
    csvFieldMapping[field.key] = ''
  }
  createForm.job_name = `采集任务_${dayjs().format('MMDD_HHmm')}`
  createForm.selectedSources = ['fofa']
  createForm.queries = { fofa: '', hunter: '', zoomeye: '', quake: '' }
  createForm.page_size = 20
  createForm.max_pages = 5
  createForm.limit = 100
  createForm.timeout = 30
  createForm.dedup_strategy = 'skip'
  createForm.auto_verify = false
  if (csvInputRef.value) {
    csvInputRef.value.value = ''
  }
}

function openCreateDialog() {
  resetCreateDialogState()
  showCreateDialog.value = true
}

function handleCreateModeChange(mode: CreateMode | string | number) {
  if (mode === 'online') {
    createMode.value = 'online'
    createStep.value = 1
    selectedCsvFile.value = null
    csvPreview.value = { headers: [], rows: [], file_path: '', detected_source_type: null }
    return
  }

  createMode.value = 'csv'
  createStep.value = 1
}

function triggerCsvFileDialog() {
  csvInputRef.value?.click()
}

function onCsvFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  selectedCsvFile.value = target.files?.[0] ?? null
}

function autoMatchCsvFields(headers: string[]) {
  const rules: Record<CsvFieldKey, string[]> = {
    url: ['url', 'link', '链接', 'http_load_url', 'site'],
    ip: ['ip', 'host_ip', 'ip地址'],
    port: ['port', 'svc_port', '端口', 'portinfo.port'],
    title: ['title', 'site_title', '标题'],
    protocol: ['protocol', 'proto', 'scheme', 'service', 'service.app'],
    domain: ['domain', 'host', '域名'],
    status_code: ['status_code', 'status', 'code', '网站状态码'],
    org: ['org', 'organization', 'company', '备案单位'],
    country: ['country', '国家'],
    city: ['city', '市区'],
    host: ['host', 'web资产'],
  }

  for (const field of csvFieldConfigs) {
    const match = headers.find((header) => {
      const normalizedHeader = header.toLowerCase()
      return rules[field.key].some((rule) => normalizedHeader.includes(rule.toLowerCase()))
    })
    csvFieldMapping[field.key] = match ?? ''
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
    if (preview.detected_source_type && ['fofa', 'hunter', 'zoomeye', 'quake'].includes(preview.detected_source_type)) {
      csvSourceType.value = preview.detected_source_type as CsvSourceType
    }
    createStep.value = 2
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error.message ?? 'CSV 预览失败')
  } finally {
    previewLoading.value = false
  }
}

function validateCsvMapping() {
  if (csvSourceType.value !== 'auto') {
    return true
  }

  const hasIdentityField = csvIdentityFieldKeys.some((field) => Boolean(csvFieldMapping[field]))
  if (!hasIdentityField) {
    ElMessage.error('至少映射一个身份字段：URL、IP、域名、主机名')
    return false
  }
  return true
}

function validateOnlineQueries() {
  if (createForm.selectedSources.length === 0) {
    ElMessage.warning('请至少选择一个采集来源')
    return false
  }

  const emptySources = createForm.selectedSources.filter((source) => {
    const query = createForm.queries[source]
    return typeof query !== 'string' || query.trim().length === 0
  })

  if (emptySources.length > 0) {
    ElMessage.error(`已选择采集源但查询条件为空：${emptySources.map(formatSourceLabel).join('、')}`)
    return false
  }

  const hasAnyValidQuery = createForm.selectedSources.some((source) => {
    const query = createForm.queries[source]
    return typeof query === 'string' && query.trim().length > 0
  })

  if (!hasAnyValidQuery) {
    ElMessage.error('未提供有效查询条件，无法创建采集任务')
    return false
  }

  return true
}

async function submitCreate() {
  submitting.value = true
  try {
    if (createMode.value === 'csv') {
      if (!csvPreview.value.file_path) {
        ElMessage.error('请先完成 CSV 预览')
        return
      }
      if (!validateCsvMapping()) {
        return
      }

      const fieldMapping = Object.fromEntries(
        Object.entries(csvFieldMapping).filter(([, value]) => Boolean(value)),
      )

      const res = await createCollectJob({
        job_name: createForm.job_name,
        sources: ['csv_import'],
        queries: [],
        file_path: csvPreview.value.file_path,
        source_type: csvSourceType.value === 'auto' ? null : csvSourceType.value,
        field_mapping: fieldMapping,
        dedup_strategy: createForm.dedup_strategy,
        auto_verify: createForm.auto_verify,
      })
      ElMessage.success('CSV 导入任务已创建')
      showCreateDialog.value = false
      await startTask(res.job_id)
      await fetchJobs()
      return
    }

    if (!validateOnlineQueries()) {
      return
    }

    const queries = createForm.selectedSources.map((source) => ({
      source,
      query: (createForm.queries[source] ?? '').trim(),
      page_size: createForm.page_size,
      max_pages: createForm.max_pages,
      limit: createForm.limit,
      timeout: createForm.timeout,
    }))

    const res = await createCollectJob({
      job_name: createForm.job_name,
      sources: [...createForm.selectedSources],
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

async function refreshJob(id: string) {
  try {
    const status = await getTaskStatus(id)
    const index = jobs.value.findIndex((job) => job.id === id)
    if (index !== -1) {
      const currentJob = jobs.value[index]
      jobs.value[index] = {
        ...currentJob,
        status: status.status as CollectJob['status'],
        progress: status.progress,
        success_count: status.success_count,
        failed_count: status.failed_count,
        duplicate_count: status.duplicate_count,
        total_count: status.total_count,
        finished_at: status.finished_at ?? currentJob.finished_at,
        error_message: status.error_message ?? currentJob.error_message,
      }
    }
  } catch (error) {
    console.error('Refresh job failed:', error)
  }
}

async function handleStart(id: string) {
  try {
    await startTask(id)
    ElMessage.success('任务已开始')
    await fetchJobs()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error.message ?? '启动任务失败')
  }
}

async function handleStop(id: string) {
  try {
    await stopTask(id)
    ElMessage.warning('已请求停止任务')
    await fetchJobs()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error.message ?? '停止任务失败')
  }
}

function viewDetails(job: CollectJob) {
  selectedJobId.value = job.id
  isDrawerVisible.value = true
}

function onJobRerun() {
  fetchJobs()
}

function isJobRunning(status: CollectJob['status']) {
  return status === 'running'
}

function normalizeSources(sources: CollectJob['sources']) {
  return Array.isArray(sources) ? sources : Object.values(sources).map(String)
}

function formatSourceLabel(source: string) {
  const sourceLabelMap: Record<string, string> = {
    fofa: 'FOFA',
    hunter: 'Hunter',
    zoomeye: 'ZoomEye',
    quake: 'Quake',
    oneforall: 'OneForAll',
    csv_import: 'CSV',
    sample: 'Sample',
  }
  return sourceLabelMap[source] ?? source.toUpperCase()
}

function getExample(src: string) {
  if (src === 'fofa') return '示例: app="HIKVISION-视频联网报警平台"'
  if (src === 'hunter') return '示例: web.title="后台管理"'
  if (src === 'zoomeye') return '示例: app:"nginx"'
  if (src === 'quake') return '示例: service:"http" AND country:"China"'
  return ''
}

function getPlaceholder(src: string) {
  if (src === 'fofa') return '请输入 FOFA 查询语句'
  if (src === 'hunter') return '请输入 Hunter 查询语句'
  if (src === 'zoomeye') return '请输入 ZoomEye 查询语句'
  if (src === 'quake') return '请输入 Quake 查询语句'
  return '请输入查询内容'
}

function getStatusType(status: string) {
  const map: Record<string, string> = {
    pending: 'info',
    running: 'primary',
    success: 'success',
    partial_success: 'warning',
    failed: 'danger',
    cancelled: 'warning',
  }
  return map[status] ?? 'info'
}

function getStatusLabel(status: string) {
  const map: Record<string, string> = {
    pending: '排队中',
    running: '运行中',
    success: '已完成',
    partial_success: '部分成功',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[status] ?? status
}

function getProgressStatus(status: string) {
  if (status === 'success') return 'success'
  if (status === 'partial_success') return 'warning'
  if (status === 'failed') return 'exception'
  return ''
}

function formatTime(time?: string) {
  return time ? dayjs(time).format('YYYY-MM-DD HH:mm') : '-'
}

onMounted(() => {
  fetchJobs()
  timer = window.setInterval(fetchJobs, 3000)
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
  }
})
</script>

<style scoped lang="scss">
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.page-subtitle {
  margin: 8px 0 0;
  color: var(--app-text-dim);
  font-size: 14px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stats-card {
  padding: 20px;
  border-radius: 18px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-border);
  box-shadow: var(--app-shadow);
}

.stats-label {
  color: var(--app-text-dim);
  font-size: 13px;
}

.stats-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 700;
  color: var(--app-text-main);
}

.job-card {
  display: flex;
  flex-direction: column;
  min-height: 260px;
  padding: 20px;
  border-radius: 18px;
  border: 1px solid var(--app-border);
  background: var(--app-card-bg);
  box-shadow: var(--app-shadow);
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.job-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--app-shadow-lg);
}

.job-card.is-running {
  border-color: var(--el-color-primary-light-5);
}

.job-card-header,
.job-card-footer,
.progress-info,
.box-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.job-card-content {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.job-name {
  margin: 0 0 10px;
  font-size: 17px;
  font-weight: 700;
  color: var(--app-text-main);
}

.job-meta,
.footer-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.progress-section {
  margin-bottom: 16px;
}

.progress-info {
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--app-text-dim);
}

.counts-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.count-item {
  padding: 12px 10px;
  text-align: center;
  border-radius: 14px;
  background: color-mix(in srgb, var(--app-card-bg) 78%, transparent);
  border: 1px solid var(--app-border);
}

.count-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--app-text-main);
}

.count-label,
.time,
.example,
.section-title,
.mapping-label,
.upload-hint {
  color: var(--app-text-dim);
}

.count-label {
  margin-top: 6px;
  font-size: 12px;
}

.job-card-footer {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--app-border);
}

.footer-left {
  flex: 1;
  min-width: 0;
}

.time {
  display: inline-block;
  max-width: 100%;
  font-size: 12px;
}

.query-input-box,
.csv-upload-box,
.mapping-item {
  border: 1px solid var(--app-border);
  border-radius: 16px;
  background: var(--app-card-bg);
}

.query-input-box {
  padding: 14px;
}

.example,
.section-title,
.mapping-label {
  font-size: 13px;
}

.csv-upload-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 180px;
  cursor: pointer;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.csv-upload-box:hover {
  border-color: var(--el-color-primary);
  transform: translateY(-1px);
}

.upload-icon {
  font-size: 32px;
  color: var(--el-color-primary);
}

.upload-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text-main);
}

.mapping-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.mapping-item {
  padding: 14px;
}

.mapping-label {
  display: block;
  margin-bottom: 8px;
}

.identity-hint {
  margin-left: 6px;
  color: var(--el-color-primary);
  font-size: 12px;
}

.mapping-note {
  margin-bottom: 12px;
  color: var(--app-text-dim);
  font-size: 12px;
}

.required-mark {
  color: var(--el-color-danger);
}

.preview-table {
  margin-bottom: 16px;
}

.hidden-input {
  display: none;
}

.text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.text-primary {
  color: var(--el-color-primary);
}

.text-success {
  color: var(--el-color-success);
}

.text-warning {
  color: var(--el-color-warning);
}

.text-danger {
  color: var(--el-color-danger);
}

.mr-1 {
  margin-right: 4px;
}

.mb-5 {
  margin-bottom: 20px;
}

@media (max-width: 1200px) {
  .stats-grid,
  .mapping-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .page-header,
  .header-actions,
  .job-card-header,
  .job-card-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .stats-grid,
  .mapping-grid,
  .counts-grid {
    grid-template-columns: 1fr;
  }
}
</style>

