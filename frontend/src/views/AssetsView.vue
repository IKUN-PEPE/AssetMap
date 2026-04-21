<template>
  <div class="page-shell">
    <div class="page-header">
      <h1 class="page-title">资产列表</h1>
      <p class="page-subtitle">查看当前已导入资产，并执行截图、标签与选择集操作。</p>
    </div>

    <el-card>
      <div class="toolbar-row">
        <el-input v-model="filters.q" placeholder="搜索 URL / 标题" style="width: 260px" clearable />
        <el-select v-model="filters.source" placeholder="按来源筛选" clearable style="width: 180px">
          <el-option label="fofa" value="fofa" />
          <el-option label="fofa_csv" value="fofa_csv" />
          <el-option label="hunter" value="hunter" />
          <el-option label="hunter_csv" value="hunter_csv" />
          <el-option label="zoomeye" value="zoomeye" />
          <el-option label="sample" value="sample" />
        </el-select>
        <el-select v-model="filters.label_status" placeholder="按标签状态筛选" clearable style="width: 180px">
          <el-option label="未标记" value="none" />
          <el-option label="无关资产" value="irrelevant" />
          <el-option label="已登记资产" value="registered" />
        </el-select>
        <el-select v-model="filters.screenshot_status" placeholder="按截图状态筛选" clearable style="width: 180px">
          <el-option label="未截图" value="false" />
          <el-option label="已截图" value="true" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>
    </el-card>

    <el-card>
      <div class="toolbar-row">
        <el-button
          type="success"
          @click="triggerVerify"
          :disabled="selectedIds.length === 0 || isCurrentTaskRunning"
        >
          批量验证并截图
        </el-button>
        <el-button @click="triggerLabel('irrelevant')" :disabled="selectedIds.length === 0">标记无关资产</el-button>
        <el-button @click="triggerLabel('registered')" :disabled="selectedIds.length === 0">标记已登记资产</el-button>
        <el-button type="danger" plain @click="removeSelectedAssets" :disabled="selectedIds.length === 0">批量删除</el-button>
        <el-dropdown style="margin-left: 12px" @command="handleExport">
          <el-button type="primary" plain :disabled="selectedIds.length === 0">
            导出报告<el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="csv" :disabled="selectedIds.length === 0">导出 CSV</el-dropdown-item>
              <el-dropdown-item command="md" :disabled="selectedIds.length === 0">导出 MD 报告</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-card>

    <el-card v-if="currentTask" style="margin-bottom: 16px;">
      <div class="verify-progress-header">
        <span>{{ currentTaskTitle }}</span>
        <div class="verify-progress-actions">
          <el-tag :type="taskStatusTagType(currentTask.status)" size="small">{{ taskStatusText(currentTask.status) }}</el-tag>
          <el-button v-if="isCurrentTaskRunning" size="small" type="danger" plain @click="stopCurrentTask">停止</el-button>
        </div>
      </div>
      <el-progress :percentage="currentTaskPercentage" :status="currentTaskProgressStatus" />
      <div class="verify-progress-meta">
        <span>总数：{{ currentTask.total }}</span>
        <span>已处理：{{ currentTask.processed }}</span>
        <span>成功：{{ currentTask.success }}</span>
        <span>失败：{{ currentTask.failed }}</span>
      </div>
      <div class="verify-progress-message">{{ currentTask.message || '正在获取任务进度...' }}</div>
    </el-card>

    <el-card>
      <div class="toolbar-row" style="margin-bottom: 12px; color: #5b6b7f; font-size: 13px;">
        <span>加载状态：{{ loadState }}</span>
        <span>资产总数：{{ total }}</span>
        <span>当前页数量：{{ assets.length }}</span>
        <span>已选数量：{{ selectedIds.length }}</span>
      </div>
      <el-alert
        v-if="assets.length > 0"
        :title="`首条资产：${assets[0].normalized_url} | 来源：${assets[0].source || 'unknown'}`"
        type="info"
        show-icon
        :closable="false"
        style="margin-bottom: 12px"
      />
      <el-table :data="paginatedAssets" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="normalized_url" label="URL" min-width="260" />
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column label="来源" width="120">
          <template #default="scope">
            <el-tag :type="sourceTagType(scope.row.source)" size="small">{{ scope.row.source || 'unknown' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态码" width="150">
          <template #default="scope">
            <div style="display:flex; align-items:center; gap:8px;">
              <el-tag :type="statusCodeTagType(scope.row.status_code)" size="small">
                {{ scope.row.status_code ?? '-' }}
              </el-tag>
              <el-tag :type="scope.row.verified ? 'success' : 'info'" size="small">
                {{ scope.row.verified ? '已验证' : '未验证' }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="截图预览" width="180">
          <template #default="scope">
            <button
              v-if="scope.row.has_screenshot"
              class="shot-button"
              type="button"
              @click="openScreenshotPreview(scope.row)"
            >
              <img :src="buildScreenshotUrl(scope.row.screenshot_url)" alt="截图预览" class="shot-image" loading="lazy" />
            </button>
            <el-tag v-else-if="scope.row.screenshot_status === 'failed'" type="danger" size="small">截图失败</el-tag>
            <el-tag v-else type="info" size="small">暂无截图</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标签状态" width="120">
          <template #default="scope">
            <el-tag :type="labelStatusTagType(scope.row.label_status)" size="small">
              {{ labelStatusText(scope.row.label_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="首次发现" min-width="160">
          <template #default="scope">
            {{ formatReportDate(scope.row.first_seen_at) }}
          </template>
        </el-table-column>
        <el-table-column label="最近发现" min-width="160">
          <template #default="scope">
            {{ formatReportDate(scope.row.last_seen_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="goDetail(scope.row.id)">详情</el-button>
            <el-button link type="danger" @click="removeAsset(scope.row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 16px; display: flex; justify-content: flex-end;">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200, 500]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="previewVisible"
      append-to-body
      destroy-on-close
      align-center
      width="80vw"
      top="5vh"
      :close-on-click-modal="true"
      :close-on-press-escape="true"
      class="screenshot-preview-dialog"
      @closed="closeScreenshotPreview"
    >
      <template #header>
        <div class="preview-title">截图预览</div>
      </template>
      <div class="preview-body">
        <img v-if="previewImageUrl" :src="previewImageUrl" alt="截图大图" class="preview-image" />
      </div>
    </el-dialog>

    <!-- 资产详情弹窗 -->
    <el-dialog
      v-model="detailVisible"
      title="资产详细信息"
      width="600px"
      destroy-on-close
    >
      <el-descriptions :column="1" border v-if="editingAsset">
        <el-descriptions-item label="UUID">{{ editingAsset.id }}</el-descriptions-item>
        <el-descriptions-item label="目标 URL">{{ editingAsset.normalized_url }}</el-descriptions-item>
        <el-descriptions-item label="网站标题">{{ editingAsset.title || '-' }}</el-descriptions-item>
        <el-descriptions-item label="数据来源">
          <el-tag :type="sourceTagType(editingAsset.source)">{{ editingAsset.source || 'unknown' }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="HTTP 状态">
          <el-tag :type="statusCodeTagType(editingAsset.status_code)">{{ editingAsset.status_code || '-' }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="验证状态">
          {{ editingAsset.verified ? '已验证' : '未验证' }}
        </el-descriptions-item>
        <el-descriptions-item label="验证失败原因">{{ editingAsset.verify_error || '-' }}</el-descriptions-item>
        <el-descriptions-item label="首次发现">{{ formatReportDate(editingAsset.first_seen_at) }}</el-descriptions-item>
        <el-descriptions-item label="最近发现">{{ formatReportDate(editingAsset.last_seen_at) }}</el-descriptions-item>
        <el-descriptions-item label="标签状态">{{ labelStatusText(editingAsset.label_status) }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import axios from 'axios'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { batchLabel, deleteAsset, fetchAssets, verifyAssets } from '@/api/modules/assets'
import { cancelVerifyTask, fetchVerifyTask } from '@/api/modules/jobs'
import type { AssetItem, TaskProgress } from '@/types'

const CURRENT_TASK_STORAGE_KEY = 'assetmap.currentTask'

const router = useRouter()
const assets = ref<AssetItem[]>([])
const selectedIds = ref<string[]>([])
const loadState = ref('loading')
const filters = ref({ q: '', source: '', label_status: '', screenshot_status: '' })
const currentTask = ref<TaskProgress | null>(null)
const previewVisible = ref(false)
const previewImageUrl = ref('')
const detailVisible = ref(false)
const editingAsset = ref<AssetItem | null>(null)
const currentTaskPollMs = 1200
let currentTaskTimer: number | undefined

const currentPage = ref(1)
const pageSize = ref(20)

const total = computed(() => assets.value.length)
const paginatedAssets = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return assets.value.slice(start, end)
})

function handleSizeChange(val: number) {
  pageSize.value = val
  currentPage.value = 1
}

function handleCurrentChange(val: number) {
  currentPage.value = val
}

function handleSearch() {
  currentPage.value = 1
  void loadAssets()
}

const isCurrentTaskRunning = computed(() => currentTask.value?.status === 'running' || currentTask.value?.status === 'pending')
const currentTaskTitle = '批量验证并截图进度'
const currentTaskPercentage = computed(() => {
  if (!currentTask.value || currentTask.value.total <= 0) return 0
  return Math.min(100, Math.round((currentTask.value.processed / currentTask.value.total) * 100))
})
const currentTaskProgressStatus = computed(() => {
  if (!currentTask.value) return undefined
  if (currentTask.value.status === 'failed') return 'exception'
  if (currentTask.value.status === 'cancelled') return 'warning'
  if (currentTask.value.status === 'completed' && currentTask.value.failed > 0) return 'warning'
  if (currentTask.value.status === 'completed') return 'success'
  return undefined
})

function sourceTagType(source?: string | null) {
  switch (source) {
    case 'fofa':
      return 'primary'
    case 'fofa_csv':
      return 'success'
    case 'hunter':
      return 'warning'
    case 'zoomeye':
      return 'danger'
    case 'sample':
      return 'info'
    default:
      return ''
  }
}

function labelStatusTagType(status?: string | null) {
  switch (status) {
    case 'irrelevant':
      return 'warning'
    case 'registered':
      return 'success'
    case 'false_positive':
      return 'warning'
    case 'confirmed':
      return 'success'
    case 'none':
      return 'info'
    default:
      return ''
  }
}

function labelStatusText(status?: string | null) {
  switch (status) {
    case 'irrelevant':
      return '无关资产'
    case 'registered':
      return '已登记资产'
    case 'false_positive':
      return '误报'
    case 'confirmed':
      return '已确认'
    case 'none':
      return '未标记'
    default:
      return '未知'
  }
}

function taskStatusTagType(status?: TaskProgress['status']) {
  switch (status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'danger'
    case 'cancelled':
      return 'warning'
    case 'running':
      return 'warning'
    default:
      return 'info'
  }
}

function taskStatusText(status?: TaskProgress['status']) {
  switch (status) {
    case 'pending':
      return '排队中'
    case 'running':
      return '进行中'
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    case 'cancelled':
      return '已取消'
    default:
      return '未知'
  }
}

function statusCodeTagType(statusCode?: number | null) {
  if (statusCode === 200) return 'success'
  if (statusCode === 302) return 'warning'
  if (statusCode !== undefined && statusCode !== null && statusCode >= 400) return 'danger'
  return 'info'
}

function buildScreenshotUrl(url?: string | null) {
  if (!url) return ''
  if (url.startsWith('http')) return url
  return `http://127.0.0.1:9527${url}`
}

function openScreenshotPreview(asset: AssetItem) {
  previewImageUrl.value = buildScreenshotUrl(asset.screenshot_url)
  previewVisible.value = Boolean(previewImageUrl.value)
}

function closeScreenshotPreview() {
  previewVisible.value = false
  previewImageUrl.value = ''
}

function persistCurrentTask(task: Pick<TaskProgress, 'task_id' | 'task_type'>) {
  window.localStorage.setItem(CURRENT_TASK_STORAGE_KEY, JSON.stringify(task))
}

function clearPersistedCurrentTask() {
  window.localStorage.removeItem(CURRENT_TASK_STORAGE_KEY)
}

function stopCurrentTaskPolling() {
  if (currentTaskTimer) {
    window.clearInterval(currentTaskTimer)
    currentTaskTimer = undefined
  }
}

async function syncCurrentTask(taskId: string, taskType: TaskProgress['task_type']) {
  const task = await fetchVerifyTask(taskId)
  const prev = currentTask.value
  if (
    !prev ||
    prev.status !== task.status ||
    prev.processed !== task.processed ||
    prev.success !== task.success ||
    prev.failed !== task.failed ||
    prev.message !== task.message
  ) {
    currentTask.value = task
  }
  if (task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled') {
    stopCurrentTaskPolling()
    clearPersistedCurrentTask()
    await loadAssets()
    if (task.status === 'completed') {
      ElMessage.success(`批量验证并截图完成，成功 ${task.success} 条，失败 ${task.failed} 条`)
    } else if (task.status === 'cancelled') {
      ElMessage.warning(task.message || '任务已取消')
    } else {
      ElMessage.error(task.message || '任务执行失败')
    }
  }
}

function startCurrentTaskPolling(taskId: string, taskType: TaskProgress['task_type']) {
  stopCurrentTaskPolling()
  currentTaskTimer = window.setInterval(() => {
    void syncCurrentTask(taskId, taskType)
  }, currentTaskPollMs)
}

async function restoreCurrentTask() {
  const storedTask = window.localStorage.getItem(CURRENT_TASK_STORAGE_KEY)
  if (!storedTask) return
  try {
    const parsed = JSON.parse(storedTask) as Pick<TaskProgress, 'task_id' | 'task_type'>
    await syncCurrentTask(parsed.task_id, parsed.task_type)
    if (currentTask.value && (currentTask.value.status === 'pending' || currentTask.value.status === 'running')) {
      startCurrentTaskPolling(parsed.task_id, parsed.task_type)
    }
  } catch {
    clearPersistedCurrentTask()
    currentTask.value = null
  }
}

async function startCurrentTask(taskId: string, taskType: TaskProgress['task_type'], total: number, message: string) {
  currentTask.value = {
    task_id: taskId,
    task_type: taskType,
    status: 'running',
    total,
    processed: 0,
    success: 0,
    failed: 0,
    message,
  }
  persistCurrentTask({ task_id: taskId, task_type: taskType })
  await syncCurrentTask(taskId, taskType)
  if (isCurrentTaskRunning.value) {
    startCurrentTaskPolling(taskId, taskType)
  }
}

async function loadAssets() {
  try {
    const screenshotFilter = filters.value.screenshot_status
    const has_screenshot =
      screenshotFilter === 'true'
        ? true
        : screenshotFilter === 'false'
          ? false
          : undefined

    const screenshot_status =
      screenshotFilter === 'failed' ? 'failed' : undefined

    const data = await fetchAssets({
      q: filters.value.q || undefined,
      source: filters.value.source || undefined,
      label_status: filters.value.label_status || undefined,
      screenshot_status,
      has_screenshot,
    })
    assets.value = Array.isArray(data) ? data : []
    loadState.value = 'loaded'
  } catch (error) {
    if (axios.isAxiosError(error)) {
      console.error('axios response:', error.response)
      console.error('axios request:', error.request)
      console.error('axios detail:', error.toJSON?.())
    }
    loadState.value = 'failed'
    const message = axios.isAxiosError(error)
      ? (error.response?.data?.detail || error.message)
      : '资产列表加载失败'
    ElMessage.error(String(message))
  }
}

onMounted(async () => {
  await loadAssets()
  await restoreCurrentTask()
})

onBeforeUnmount(() => {
  stopCurrentTaskPolling()
})

function resetFilters() {
  filters.value = { q: '', source: '', label_status: '', screenshot_status: '' }
  currentPage.value = 1
  void loadAssets()
}

function onSelectionChange(rows: AssetItem[]) {
  selectedIds.value = rows.map((item) => item.id)
}

function goDetail(id: string) {
  const asset = assets.value.find((item) => item.id === id)
  if (asset) {
    editingAsset.value = asset
    detailVisible.value = true
  }
}

async function triggerVerify() {
  // 立即清空旧任务状态，防止显示残留数据
  currentTask.value = null
  try {
    const result = await verifyAssets(selectedIds.value)
    await startCurrentTask(result.task_id, 'asset_verify', selectedIds.value.length, `正在初始化验证任务...`)
  } catch {
    ElMessage.error('资产验证失败')
  }
}

async function triggerLabel(status: string) {
  if (selectedIds.value.length === 0) return
  try {
    await batchLabel(selectedIds.value, status)
    ElMessage.success('操作成功')
    await loadAssets()
    selectedIds.value = []
  } catch {
    ElMessage.error('标记失败')
  }
}

async function stopCurrentTask() {
  if (!currentTask.value) return
  try {
    currentTask.value = await cancelVerifyTask(currentTask.value.task_id)
    stopCurrentTaskPolling()
    await loadAssets()
    ElMessage.warning(currentTask.value.message || '任务已取消')
  } catch {
    ElMessage.error('停止任务失败')
  }
}


async function removeAsset(id: string) {
  try {
    await ElMessageBox.confirm('确认删除该资产吗？', '删除确认', { type: 'warning' })
    await deleteAsset(id)
    ElMessage.success('资产已删除')
    await loadAssets()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

async function removeSelectedAssets() {
  try {
    await ElMessageBox.confirm(`确认批量删除 ${selectedIds.value.length} 条资产吗？`, '批量删除确认', { type: 'warning' })
    const results = await Promise.allSettled(selectedIds.value.map((id) => deleteAsset(id)))
    const failedCount = results.filter((item) => item.status === 'rejected').length
    const successCount = results.length - failedCount
    selectedIds.value = []
    await loadAssets()
    if (failedCount === 0) {
      ElMessage.success(`批量删除完成，共删除 ${successCount} 条`)
    } else {
      ElMessage.warning(`批量删除完成，成功 ${successCount} 条，失败 ${failedCount} 条`)
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量删除失败')
    }
  }
}

function handleExport(command: 'csv' | 'md') {
  if (selectedIds.value.length === 0) return
  if (command === 'csv') {
    exportCsv()
    return
  }
  exportMd()
}

function getSelectedAssets() {
  const map = new Map<string, AssetItem>()
  assets.value.forEach((item) => map.set(item.id, item))
  return selectedIds.value.map((id) => map.get(id)).filter((item): item is AssetItem => item !== undefined)
}

function formatReportDate(value?: string | null) {
  if (!value) return '-'
  // 将 2026-04-16T00:41:12.525753 转换为 2026/04/16 00:41
  return value.split('.')[0].replace('T', ' ').replace(/-/g, '/').slice(0, 16)
}

function escapeCsvCell(value?: string | null) {
  return `"${String(value || '').replace(/"/g, '""')}"`
}

function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

function getDisplayTime(item: AssetItem) {
  return formatReportDate(item.first_seen_at || item.last_seen_at)
}

function exportCsv() {
  const selectedList = getSelectedAssets()
  const headers = ['URL', '标题', '来源', '截图', '发现时间']
  const csvContent = [
    headers.join(','),
    ...selectedList.map((item) => [
      escapeCsvCell(item.normalized_url),
      escapeCsvCell(item.title),
      escapeCsvCell(item.source),
      escapeCsvCell(item.screenshot_url ? buildScreenshotUrl(item.screenshot_url) : ''),
      escapeCsvCell(getDisplayTime(item)),
    ].join(',')),
  ].join('\n')

  const dateText = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  downloadFile(`\uFEFF${csvContent}`, `${dateText}_资产导出.csv`, 'text/csv;charset=utf-8')
  ElMessage.success(`已导出 ${selectedList.length} 条 CSV 记录`)
}

function exportMd() {
  const selectedList = getSelectedAssets()
  const grouped = new Map<string, AssetItem[]>()

  selectedList.forEach((item) => {
    const groupName = item.title?.trim() || item.normalized_url || '未命名资产'
    const existing = grouped.get(groupName)
    if (existing) {
      existing.push(item)
    } else {
      grouped.set(groupName, [item])
    }
  })

  const dateText = new Date().toISOString().slice(0, 10)
  const sections = Array.from(grouped.entries()).map(([groupName, items], index) => {
    const urlLines = items.map((item) => `- URL：${item.normalized_url}`).join('\n')
    const screenshotLines = items
      .filter((item) => item.screenshot_url)
      .map((item) => `- 页面截图：\n\n  ![${groupName}](${buildScreenshotUrl(item.screenshot_url)})`)
      .join('\n\n')

    return [
      `### 1.${index + 1} ${groupName}`,
      '',
      `发现疑似关键词“${groupName}”的网站：`,
      '',
      urlLines,
      '',
      '截图：',
      '',
      screenshotLines || '  *(截图文件未在当前列表中，如有需要可按同名规则补充)*',
      '',
      ...items.map((item) => `- 来源：${item.source || '-'} | 发现时间：${getDisplayTime(item)}`),
      '',
      '---',
    ].join('\n')
  })

  const mdContent = [
    '# 互联网资产清单（分组版，含截图引用）',
    '',
    `> 报告日期：${dateText}`,
    '',
    '---',
    '',
    '## 1、网站资产',
    '',
    ...sections,
    '',
  ].join('\n')

  downloadFile(mdContent, `${dateText.replace(/-/g, '')}_资产报告.md`, 'text/markdown;charset=utf-8')
  ElMessage.success(`已导出 ${selectedList.length} 条 MD 报告记录`)
}
</script>


<style scoped>
.verify-progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.verify-progress-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.verify-progress-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 12px;
  color: #5b6b7f;
  font-size: 13px;
}

.verify-progress-message {
  margin-top: 8px;
  color: #5b6b7f;
  font-size: 13px;
}

.shot-button {
  width: 140px;
  height: 88px;
  padding: 0;
  border: 1px solid #e3e9f2;
  border-radius: 8px;
  background: #f8faff;
  overflow: hidden;
  cursor: zoom-in;
}

.shot-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: #f8faff;
}

.preview-title {
  font-size: 14px;
  font-weight: 600;
  color: #233044;
}

.preview-body {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  background: #0f172a;
  border-radius: 8px;
  overflow: auto;
}

.preview-image {
  display: block;
  max-width: 100%;
  max-height: 75vh;
  object-fit: contain;
}
</style>

