<template>
  <el-drawer
    :model-value="visible"
    :title="`任务详情 - ${job?.job_name || ''}`"
    direction="rtl"
    size="60%"
    @update:model-value="$emit('update:visible', $event)"
    @closed="onDrawerClosed"
  >
    <div v-loading="loading" class="drawer-content">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="基础信息" name="info">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="任务ID">{{ job?.id || '-' }}</el-descriptions-item>
            <el-descriptions-item label="任务名称">{{ job?.job_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="getStatusType(job?.status)">{{ getStatusLabel(job?.status) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="采集源">{{ formatSources(job?.sources) }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatTime(job?.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="开始时间">{{ formatTime(job?.started_at ?? undefined) }}</el-descriptions-item>
            <el-descriptions-item label="结束时间">{{ formatTime(job?.finished_at ?? undefined) }}</el-descriptions-item>
            <el-descriptions-item label="执行耗时">{{ job?.duration ? `${job.duration.toFixed(2)}s` : '-' }}</el-descriptions-item>
            <el-descriptions-item label="自动验证">{{ job?.auto_verify ? '已开启' : '未开启' }}</el-descriptions-item>
            <el-descriptions-item label="去重策略">{{ job?.dedup_strategy || '-' }}</el-descriptions-item>
          </el-descriptions>

          <h4 class="section-title">统计信息</h4>
          <div class="counts-grid">
            <div class="count-item"><span>成功</span><strong>{{ job?.success_count ?? 0 }}</strong></div>
            <div class="count-item"><span>重复</span><strong>{{ job?.duplicate_count ?? 0 }}</strong></div>
            <div class="count-item"><span>失败</span><strong>{{ job?.failed_count ?? 0 }}</strong></div>
            <div class="count-item"><span>总数</span><strong>{{ job?.total_count ?? 0 }}</strong></div>
          </div>

          <h4 class="section-title">任务链路</h4>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="采集结果数">
              {{ taskDetails?.collection.result_asset_count ?? 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="观测记录数">
              {{ taskDetails?.collection.observation_count ?? 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="后处理总状态">
              <el-tag size="small" :type="getStageTagType(taskDetails?.post_process.state)">
                {{ formatStageState(taskDetails?.post_process.state) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="验证阶段">
              <el-tag size="small" :type="getStageTagType(taskDetails?.post_process.verify.state)">
                {{ formatStageState(taskDetails?.post_process.verify.state) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="截图阶段">
              <el-tag size="small" :type="getStageTagType(taskDetails?.post_process.screenshot.state)">
                {{ formatStageState(taskDetails?.post_process.screenshot.state) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="验证成功 / 失败">
              {{ taskDetails?.post_process.verify.success ?? 0 }} / {{ taskDetails?.post_process.verify.failed ?? 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="截图成功 / 失败">
              {{ taskDetails?.post_process.screenshot.success ?? 0 }} / {{ taskDetails?.post_process.screenshot.failed ?? 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="验证最后错误">
              {{ taskDetails?.post_process.verify.last_error || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="截图最后错误">
              {{ taskDetails?.post_process.screenshot.last_error || '-' }}
            </el-descriptions-item>
          </el-descriptions>

          <div v-if="job?.error_message">
            <h4 class="section-title">错误信息</h4>
            <el-alert type="error" :closable="false">{{ job.error_message }}</el-alert>
          </div>
        </el-tab-pane>

        <el-tab-pane label="任务参数" name="params">
          <h4 class="section-title">查询语句 / 目标</h4>
          <pre class="log-box">{{ queryText }}</pre>

          <h4 class="section-title">请求参数</h4>
          <pre class="log-box">{{ payloadText }}</pre>

          <h4 class="section-title">模拟执行命令</h4>
          <pre class="log-box">{{ job?.command_line || 'N/A' }}</pre>
        </el-tab-pane>

        <el-tab-pane label="执行日志" name="logs">
          <div class="section-toolbar">
            <span class="muted">按 job 维度实时记录的执行日志</span>
            <el-button size="small" @click="reloadCurrent">刷新</el-button>
          </div>
          <div class="log-state-panel">
            <el-tag :type="getLogStateTagType(logState)" size="small">{{ formatLogState(logState) }}</el-tag>
            <span class="muted">{{ getLogStateDescription(logState) }}</span>
          </div>
          <el-alert
            v-if="logStateHint"
            :title="logStateHint"
            :type="getLogStateAlertType(logState)"
            :closable="false"
            show-icon
            class="log-state-alert"
          />

          <pre v-if="shouldShowLogContent" ref="logBoxRef" class="log-box">{{ logs }}</pre>
          <el-empty v-else-if="logState === 'not_started'" description="任务尚未开始执行，暂无日志。" />
          <el-empty v-else-if="logState === 'running'" description="任务正在运行，但当前还没有新的日志内容。" />
          <el-empty v-else-if="logState === 'log_not_found'" description="任务已执行，但日志文件尚未生成。" />
          <el-empty v-else-if="logState === 'log_empty'" description="日志文件已经存在，但内容为空。" />
          <el-empty v-else description="暂无日志" />
        </el-tab-pane>

        <el-tab-pane :label="`${isPendingImportJob ? '待确认结果' : '结果预览'} (${resultsTotal})`" name="results">
          <div v-if="isPendingImportJob" class="section-toolbar">
            <span class="muted">已选择 {{ selectedPendingIds.length }} 项</span>
            <div class="toolbar-actions">
              <el-button size="small" type="primary" :disabled="selectedPendingIds.length === 0" @click="handleImportSelected">确认导入已选</el-button>
              <el-button size="small" type="success" :disabled="resultsTotal === 0" @click="handleImportAll">确认导入全部</el-button>
              <el-button size="small" type="danger" plain :disabled="resultsTotal === 0" @click="handleDiscardAll">丢弃全部</el-button>
            </div>
          </div>

          <el-table :data="results" stripe height="100%" @selection-change="onPendingSelectionChange">
            <el-table-column v-if="isPendingImportJob" type="selection" width="55" reserve-selection />
            <el-table-column prop="source" label="来源" width="110" show-overflow-tooltip />
            <el-table-column prop="normalized_url" label="URL" min-width="220" show-overflow-tooltip />
            <el-table-column prop="domain" label="Domain" min-width="150" show-overflow-tooltip />
            <el-table-column prop="ip" label="IP" width="140" show-overflow-tooltip />
            <el-table-column prop="port" label="端口" width="90" />
            <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
            <el-table-column prop="status_code" label="状态码" width="90" />
            <el-table-column v-if="!isPendingImportJob" label="后处理" width="120">
              <template #default="scope">
                <el-tag :type="getResultPostProcessTagType(scope.row)" size="small">
                  {{ getResultPostProcessLabel(scope.row) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="!isPendingImportJob" label="验证" width="120">
              <template #default="scope">
                <el-tag :type="scope.row.verified ? 'success' : 'warning'" size="small">
                  {{ scope.row.verified ? '已验证' : '未验证' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="!isPendingImportJob" label="截图" width="120">
              <template #default="scope">
                <el-tag :type="scope.row.screenshot_status === 'success' ? 'success' : scope.row.screenshot_status === 'failed' ? 'danger' : 'info'" size="small">
                  {{ formatScreenshotStatus(scope.row.screenshot_status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="!isPendingImportJob" prop="verify_error" label="验证失败原因" min-width="180" show-overflow-tooltip />
            <el-table-column v-if="!isPendingImportJob" prop="screenshot_error" label="截图失败原因" min-width="180" show-overflow-tooltip />
          </el-table>
          <div class="pagination-row" v-if="resultsTotal > resultsLimit">
            <el-pagination
              background
              layout="prev, pager, next"
              :page-size="resultsLimit"
              :current-page="currentPage"
              :total="resultsTotal"
              @current-change="handlePageChange"
            />
          </div>
          <el-empty v-if="!loading && results.length === 0" description="暂无结果" />
        </el-tab-pane>
      </el-tabs>
    </div>
    <template #footer>
      <div class="drawer-footer">
        <el-button @click="$emit('update:visible', false)">关闭</el-button>
        <el-button v-if="job && canRerun(job.status)" type="primary" @click="handleRerun">重新执行</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  confirmJobImport,
  discardJobImport,
  fetchJobDetails,
  fetchJobLogs,
  fetchJobResults,
  fetchPendingJobAssets,
  rerunJob,
} from '@/api/modules/jobs'
import type {
  CollectJobDetail,
  JobLogResponse,
  JobPendingAssetItem,
  JobTaskDetails,
  JobResultPreviewItem,
} from '@/types'
import dayjs from 'dayjs'

const props = defineProps<{ visible: boolean; jobId: string | null }>()
const emit = defineEmits(['update:visible', 'rerun'])

const loading = ref(false)
const job = ref<CollectJobDetail | null>(null)
const logs = ref('')
const results = ref<Array<JobResultPreviewItem | JobPendingAssetItem>>([])
const resultsTotal = ref(0)
const resultsLimit = ref(20)
const currentPage = ref(1)
const activeTab = ref('info')
const logBoxRef = ref<HTMLElement | null>(null)
const logState = ref<JobLogResponse['log_state']>('not_started')
const taskDetails = ref<JobTaskDetails | null>(null)
const selectedPendingIds = ref<string[]>([])

const isPendingImportJob = computed(() => job.value?.status === 'pending_import')
const shouldShowLogContent = computed(() => Boolean(logs.value))
const logStateHint = computed(() => {
  if (logState.value === 'running' && !logs.value) return '任务已开始，正在等待首批日志写入。'
  if (logState.value === 'log_not_found') return '后端还没有生成日志文件，适合先查看任务结果和后处理状态。'
  if (logState.value === 'log_empty') return '日志文件已经存在，但当前没有可读内容。'
  return ''
})
const queryText = computed(() => {
  const queries = job.value?.query_payload?.queries
  if (!Array.isArray(queries) || queries.length === 0) return 'N/A'
  return queries.map((q) => `[${String(q.source || 'unknown')}] ${String(q.query || '')}`).join('\n')
})
const payloadText = computed(() => {
  if (!job.value?.query_payload) return 'N/A'
  try {
    return JSON.stringify(job.value.query_payload, null, 2)
  } catch {
    return 'N/A'
  }
})

watch(
  () => [props.jobId, props.visible] as const,
  ([jobId, visible], [prevJobId, prevVisible]) => {
    if (jobId && visible && (jobId !== prevJobId || !prevVisible)) {
      currentPage.value = 1
      void loadAllDetails(jobId)
      return
    }
    if (!visible) onDrawerClosed()
  },
)

async function loadJobResults(id: string) {
  if (isPendingImportJob.value) {
    const data = await fetchPendingJobAssets(id, (currentPage.value - 1) * resultsLimit.value, resultsLimit.value)
    results.value = data.items || []
    resultsTotal.value = data.total || 0
    return data
  }
  const data = await fetchJobResults(id, (currentPage.value - 1) * resultsLimit.value, resultsLimit.value)
  results.value = data.items || []
  resultsTotal.value = data.total || 0
  return data
}

async function loadAllDetails(id: string) {
  loading.value = true
  activeTab.value = 'info'
  selectedPendingIds.value = []
  try {
    const [details, logData] = await Promise.all([
      fetchJobDetails(id),
      fetchJobLogs(id),
    ])
    job.value = details
    logState.value = logData.log_state
    logs.value = logData.content || ''
    taskDetails.value = logData.task_details || details.task_details || null
    const resultData = await loadJobResults(id)
    if (!isPendingImportJob.value && 'task_details' in resultData) {
      taskDetails.value = resultData.task_details || taskDetails.value
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error?.message ?? '加载任务详情失败')
    emit('update:visible', false)
  } finally {
    loading.value = false
    setTimeout(() => {
      if (logBoxRef.value) logBoxRef.value.scrollTop = logBoxRef.value.scrollHeight
    }, 100)
  }
}

async function reloadCurrent() {
  if (!props.jobId) return
  await loadAllDetails(props.jobId)
}

function onDrawerClosed() {
  job.value = null
  logs.value = ''
  results.value = []
  resultsTotal.value = 0
  currentPage.value = 1
  activeTab.value = 'info'
  taskDetails.value = null
  logState.value = 'not_started'
  selectedPendingIds.value = []
}

async function handleRerun() {
  if (!props.jobId) return
  try {
    await rerunJob(props.jobId)
    ElMessage.success('已创建新的重跑任务')
    emit('rerun')
    emit('update:visible', false)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error?.message ?? '重新执行失败')
  }
}

async function handlePageChange(page: number) {
  currentPage.value = page
  if (!props.jobId) return
  try {
    loading.value = true
    const resultData = await loadJobResults(props.jobId)
    if (!isPendingImportJob.value && 'task_details' in resultData) {
      taskDetails.value = resultData.task_details || taskDetails.value
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error?.message ?? '加载结果失败')
  } finally {
    loading.value = false
  }
}

function onPendingSelectionChange(rows: Array<JobPendingAssetItem>) {
  selectedPendingIds.value = rows.map((item) => item.id)
}

async function handleImportAll() {
  if (!props.jobId) return
  await ElMessageBox.confirm('确认导入当前任务的全部待确认结果吗？', '确认导入', { type: 'warning' })
  const result = await confirmJobImport(props.jobId, { import_all: true })
  ElMessage.success(`导入完成：成功 ${result.success}，重复 ${result.duplicate}，失败 ${result.failed}`)
  emit('rerun')
  await reloadCurrent()
}

async function handleImportSelected() {
  if (!props.jobId || selectedPendingIds.value.length === 0) return
  await ElMessageBox.confirm(`确认导入已选 ${selectedPendingIds.value.length} 项结果吗？`, '确认导入', { type: 'warning' })
  const result = await confirmJobImport(props.jobId, { import_all: false, ids: [...selectedPendingIds.value] })
  ElMessage.success(`导入完成：成功 ${result.success}，重复 ${result.duplicate}，失败 ${result.failed}`)
  emit('rerun')
  await reloadCurrent()
}

async function handleDiscardAll() {
  if (!props.jobId) return
  await ElMessageBox.confirm('确认丢弃当前任务全部待确认结果吗？该操作不可撤销。', '确认丢弃', { type: 'warning' })
  const result = await discardJobImport(props.jobId)
  ElMessage.success(`已丢弃 ${result.discarded} 条待确认结果`)
  emit('rerun')
  await reloadCurrent()
}

function canRerun(status?: string) {
  return ['success', 'failed', 'cancelled', 'partial_success', 'imported', 'discarded'].includes(status || '')
}

function getStatusType(status?: string) {
  const map: Record<string, string> = {
    pending: 'info',
    running: 'primary',
    success: 'success',
    partial_success: 'warning',
    failed: 'danger',
    cancelled: 'warning',
    pending_import: 'warning',
    imported: 'success',
    discarded: 'info',
  }
  return map[status || ''] ?? 'info'
}

function getStatusLabel(status?: string) {
  const map: Record<string, string> = {
    pending: '排队中',
    running: '运行中',
    success: '已完成',
    partial_success: '部分成功',
    failed: '失败',
    cancelled: '已取消',
    pending_import: '待确认导入',
    imported: '已导入',
    discarded: '已丢弃',
  }
  return (map[status || ''] ?? status) || '-'
}

function getLogStateTagType(state?: string) {
  const map: Record<string, string> = {
    not_started: 'info',
    running: 'primary',
    log_not_found: 'warning',
    log_empty: 'warning',
    finished: 'success',
    log_ready: 'success',
  }
  return map[state || 'not_started'] || 'info'
}

function formatLogState(state?: string) {
  const map: Record<string, string> = {
    not_started: '未启动',
    running: '运行中',
    log_not_found: '日志未生成',
    log_empty: '日志为空',
    finished: '已结束',
    log_ready: '日志就绪',
  }
  return map[state || 'not_started'] || '未知'
}

function getLogStateDescription(state?: string) {
  const map: Record<string, string> = {
    not_started: '任务尚未开始执行，暂无日志。',
    running: '任务正在执行，日志会持续追加。',
    log_not_found: '任务已执行，但日志文件尚未生成。',
    log_empty: '日志文件已经创建，但内容为空。',
    finished: '任务已结束，可查看完整日志。',
    log_ready: '日志已可查看。',
  }
  return map[state || 'not_started'] || '暂无日志状态说明。'
}

function getLogStateAlertType(state?: string) {
  const map: Record<string, 'info' | 'warning' | 'success'> = {
    not_started: 'info',
    running: 'info',
    log_not_found: 'warning',
    log_empty: 'warning',
    finished: 'success',
    log_ready: 'success',
  }
  return map[state || 'not_started'] || 'info'
}

function formatScreenshotStatus(status?: string) {
  const map: Record<string, string> = {
    none: '未执行',
    success: '成功',
    failed: '失败',
  }
  return (map[status || 'none'] ?? status) || '未执行'
}

function getStageTagType(state?: string) {
  const map: Record<string, string> = {
    disabled: 'info',
    pending: 'info',
    running: 'primary',
    success: 'success',
    failed: 'danger',
    partial_failed: 'warning',
  }
  return map[state || 'pending'] || 'info'
}

function formatStageState(state?: string) {
  const map: Record<string, string> = {
    disabled: '未启用',
    pending: '未触发',
    running: '进行中',
    success: '成功',
    failed: '失败',
    partial_failed: '部分失败',
  }
  return map[state || 'pending'] || '未知'
}

function getResultPostProcessLabel(row: JobResultPreviewItem) {
  if (row.screenshot_status === 'failed') return '截图失败'
  if (row.verify_error) return '验证失败'
  if (row.screenshot_status === 'success') return '截图完成'
  if (row.verified) return '验证完成'
  return '未处理'
}

function getResultPostProcessTagType(row: JobResultPreviewItem) {
  if (row.screenshot_status === 'failed' || row.verify_error) return 'danger'
  if (row.screenshot_status === 'success' || row.verified) return 'success'
  return 'info'
}

function formatTime(time?: string) {
  return time ? dayjs(time).format('YYYY-MM-DD HH:mm:ss') : '-'
}

function formatSources(sources: CollectJobDetail['sources'] | undefined): string {
  if (!sources) return 'N/A'
  return (Array.isArray(sources) ? sources : Object.keys(sources)).join(', ')
}
</script>

<style scoped>
.drawer-content { padding: 0 20px; }
.section-title { font-size: 16px; margin: 20px 0 10px; }
.section-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.log-state-panel {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 48px;
}
.log-state-alert {
  margin-bottom: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.log-box {
  background-color: #f5f5f5;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  padding: 10px;
  font-family: monospace;
  white-space: pre-wrap;
  word-wrap: break-word;
  max-height: 400px;
  overflow-y: auto;
}
.counts-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  text-align: center;
}
.count-item strong { display: block; font-size: 18px; }
.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.drawer-footer { text-align: right; }
</style>
