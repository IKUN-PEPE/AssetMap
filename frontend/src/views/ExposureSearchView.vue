<template>
  <div class="exposure-search-container">
    <el-card class="box-card">
      <template #header>
        <div class="card-header">
          <span>暴露面搜索 / Exposure Search</span>
          <div class="header-actions">
            <el-button :loading="refreshing" @click="manualRefresh">手动刷新</el-button>
            <span class="refresh-label">自动刷新</span>
            <el-switch v-model="autoRefreshEnabled" />
            <el-select v-model="refreshIntervalSec" :disabled="!autoRefreshEnabled" style="width: 110px">
              <el-option :value="5" label="5秒" />
              <el-option :value="10" label="10秒" />
              <el-option :value="15" label="15秒" />
              <el-option :value="30" label="30秒" />
            </el-select>
            <el-button type="primary" @click="showCreateDialog = true">新建搜索任务</el-button>
          </div>
        </div>
      </template>

      <div v-if="failureSummary.total > 0" class="failure-summary-card">
        <div class="failure-summary-header">
          <span>失败总览</span>
          <el-tag type="danger">{{ failureSummary.total }} 条失败语法</el-tag>
        </div>
        <div class="failure-summary-tags">
          <el-tag
            v-for="item in failureSummary.byCategory"
            :key="item.category"
            :type="getErrorCategoryTagType(item.category)"
            effect="plain"
            class="failure-summary-tag"
            @click="selectFailureCategory(item.category)"
          >
            {{ item.category }}: {{ item.count }}
          </el-tag>
        </div>
        <div class="failure-summary-actions">
          <el-button
            type="warning"
            :loading="retryAllTasksLoading"
            :disabled="retryAllTasksLoading"
            @click="retryAllFailedAcrossTasks"
          >
            批量重试全部失败语法
          </el-button>
          <el-button
            v-if="activeFailureCategory"
            size="small"
            @click="activeFailureCategory = ''"
          >
            清除失败分类过滤
          </el-button>
        </div>
      </div>

      <el-table :data="tasks" style="width: 100%" v-loading="loading">
        <el-table-column type="expand">
          <template #default="scope">
            <div class="query-plan-panel">
              <div class="query-plan-header">
                <div class="query-plan-title">搜索语法明细</div>
                <el-radio-group
                  :model-value="queryPlanFilters[scope.row.id] || 'all'"
                  size="small"
                  @change="(value: string | number | boolean) => setQueryPlanFilter(scope.row.id, String(value))"
                >
                  <el-radio-button label="all">全部</el-radio-button>
                  <el-radio-button label="running">运行中</el-radio-button>
                  <el-radio-button label="failed">失败</el-radio-button>
                  <el-radio-button label="completed">已完成</el-radio-button>
                </el-radio-group>
                <el-button
                  v-if="(queryPlanFilters[scope.row.id] || 'all') === 'failed' && filteredQueryPlan(scope.row).length > 0"
                  size="small"
                  type="warning"
                  :loading="isRetryingAllFailed(scope.row.id)"
                  :disabled="isRetryingAllFailed(scope.row.id)"
                  @click="retryAllFailedQueries(scope.row)"
                >
                  重试全部失败语法
                </el-button>
              </div>
              <el-empty
                v-if="filteredQueryPlan(scope.row).length === 0"
                description="暂无语法明细"
              />
              <el-table v-else :data="filteredQueryPlan(scope.row)" size="small" border>
                <el-table-column label="标记" width="70">
                  <template #default="queryScope">
                    <span :class="['query-status-dot', `is-${queryScope.row.status}`]"></span>
                  </template>
                </el-table-column>
                <el-table-column prop="query" label="搜索语法" min-width="320" show-overflow-tooltip />
                <el-table-column prop="status" label="状态" width="120">
                  <template #default="queryScope">
                    <el-tag :type="getQueryStatusType(queryScope.row.status)" size="small">
                      {{ queryScope.row.status }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="结果数" width="100">
                  <template #default="queryScope">
                    <el-button
                      size="small"
                      link
                      type="primary"
                      :disabled="!queryScope.row.results_count"
                      @click="filterResultsByQuery(scope.row, queryScope.row.query)"
                    >
                      {{ queryScope.row.results_count }}
                    </el-button>
                  </template>
                </el-table-column>
                <el-table-column label="失败原因" min-width="220" show-overflow-tooltip>
                  <template #default="queryScope">
                    <template v-if="queryScope.row.status === 'failed'">
                      <div class="error-cell">
                        <el-tag
                          size="small"
                          :type="getErrorCategoryTagType(queryScope.row.error_category)"
                          effect="plain"
                        >
                          {{ queryScope.row.error_category || '其它' }}
                        </el-tag>
                        <span class="error-text">{{ queryScope.row.error_message || '-' }}</span>
                      </div>
                    </template>
                    <template v-else>-</template>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="150">
                  <template #default="queryScope">
                    <el-button
                      v-if="queryScope.row.status === 'failed'"
                      size="small"
                      link
                      type="warning"
                      :loading="isRetryingQuery(scope.row.id, queryScope.row.query)"
                      :disabled="isRetryingQuery(scope.row.id, queryScope.row.query)"
                      @click="retryQuery(scope.row, queryScope.row.query)"
                    >
                      重试
                    </el-button>
                    <el-button size="small" link type="primary" @click="copyQuery(queryScope.row.query)">复制语法</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="name" label="任务名称" min-width="180" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">{{ scope.row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="搜索进度" min-width="300">
          <template #default="scope">
            <div class="progress-cell" :class="progressStateClass(scope.row.status)">
              <el-progress
                :percentage="scope.row.progress_percent || 0"
                :stroke-width="8"
                :status="progressBarStatus(scope.row.status)"
              />
              <div class="progress-meta">
                <span>完成 {{ scope.row.completed_queries || 0 }}/{{ scope.row.total_queries || 0 }}</span>
                <span class="query-line current" :title="scope.row.current_query || ''">当前语法: {{ scope.row.current_query || '-' }}</span>
                <span v-if="scope.row.next_query" class="query-line next" :title="scope.row.next_query || ''">下一条语法: {{ scope.row.next_query }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="total_results" label="总结果数" width="100" />
        <el-table-column prop="imported_count" label="已导入资产" width="110" />
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250">
          <template #default="scope">
            <el-button size="small" @click="viewResults(scope.row)">查看结果</el-button>
            <el-button
              v-if="scope.row.status === 'running' || scope.row.status === 'stopping'"
              size="small"
              type="warning"
              @click="handleStopTask(scope.row)"
            >
              停止
            </el-button>
            <el-button size="small" type="danger" @click="handleDeleteTask(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showCreateDialog" title="新建暴露面搜索任务" width="700px">
      <el-form :model="taskForm" label-width="120px">
        <el-form-item label="任务名称">
          <el-input v-model="taskForm.name" placeholder="例如：深圳地铁暴露面搜索" />
        </el-form-item>
        <el-form-item label="组织关键词">
          <el-input
            v-model="orgKeywordsStr"
            type="textarea"
            :rows="3"
            placeholder="每行一个关键词或简称，例如：&#10;深圳地铁&#10;深铁&#10;SZMC"
          />
        </el-form-item>
        <el-form-item label="标题关键词">
          <el-input
            v-model="titleKeywordsStr"
            type="textarea"
            :rows="2"
            placeholder="可选，例如：&#10;后台管理&#10;登录&#10;OA"
          />
        </el-form-item>
        <el-form-item label="搜索来源">
          <el-checkbox-group v-model="taskForm.sources">
            <el-checkbox label="bing">Bing</el-checkbox>
            <el-checkbox label="baidu">Baidu</el-checkbox>
            <el-checkbox label="github">GitHub</el-checkbox>
            <el-checkbox label="google">Google</el-checkbox>
            <el-checkbox label="web_disk">网盘线索</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="文件类型">
          <el-checkbox-group v-model="taskForm.file_types">
            <el-checkbox label="pdf">PDF</el-checkbox>
            <el-checkbox label="doc">DOC/DOCX</el-checkbox>
            <el-checkbox label="xls">XLS/XLSX</el-checkbox>
            <el-checkbox label="csv">CSV</el-checkbox>
            <el-checkbox label="sql">SQL</el-checkbox>
            <el-checkbox label="json">JSON</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="执行策略">
          <el-switch v-model="taskForm.auto_run" active-text="立即执行" />
          <el-switch
            v-model="taskForm.headless"
            active-text="后台运行"
            inactive-text="窗口交互"
            style="margin-left: 20px"
          />
          <span class="hint">（窗口交互模式可手动处理验证码）</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreateTask" :loading="submitting">创建任务</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showResultsDrawer" :title="`搜索结果: ${currentTask?.name || ''}`" size="85%">
      <div v-if="currentTask" class="drawer-progress-card">
        <div class="drawer-progress-header" :class="progressStateClass(currentTask.status)">
          <span>任务进度</span>
          <el-tag :type="getStatusType(currentTask.status)">{{ currentTask.status }}</el-tag>
        </div>
        <el-progress
          :percentage="currentTask.progress_percent || 0"
          :stroke-width="10"
          :status="progressBarStatus(currentTask.status)"
        />
        <div class="drawer-progress-meta">
          <span>完成 {{ currentTask.completed_queries || 0 }}/{{ currentTask.total_queries || 0 }}</span>
          <span class="query-line two-line current" :title="currentTask.current_query || ''">当前语法: {{ currentTask.current_query || '-' }}</span>
          <span v-if="currentTask.next_query" class="query-line two-line next" :title="currentTask.next_query || ''">下一条语法: {{ currentTask.next_query }}</span>
        </div>
      </div>

      <div class="results-toolbar">
        <el-tag v-if="activeResultQueryFilter" type="primary" effect="plain" class="query-filter-tag">
          当前过滤语法: {{ activeResultQueryFilter }}
        </el-tag>
        <el-button v-if="activeResultQueryFilter" size="small" @click="clearResultQueryFilter">
          清除语法过滤
        </el-button>
        <el-button type="success" @click="handleConfirmImport" :disabled="!selectedResults.length">
          导入选中项为资产
        </el-button>
        <el-button @click="handleBatchUpdateStatus('valid')" :disabled="!selectedResults.length">
          标记为有效线索
        </el-button>
        <el-button @click="handleBatchUpdateStatus('ignored')" :disabled="!selectedResults.length">
          忽略选中
        </el-button>
        <span class="toolbar-hint">
          注：非网页结果（如 PDF、GitHub 代码等）将作为有效线索保留，不进入 Web 资产库。
        </span>
      </div>

      <el-table :data="results" style="width: 100%" v-loading="resultsLoading" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="source" label="来源" width="100">
          <template #default="scope">
            <el-tag size="small">{{ scope.row.source }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="url" label="URL" min-width="250">
          <template #default="scope">
            <el-link
              :href="scope.row.preview_url || scope.row.url"
              target="_blank"
              type="primary"
              class="url-link"
            >
              {{ scope.row.url }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="risk_tags" label="风险标签" width="200">
          <template #default="scope">
            <el-tag v-for="tag in scope.row.risk_tags" :key="tag" size="small" effect="plain" class="risk-tag">
              {{ tag }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="getResultStatusType(scope.row.status)">{{ scope.row.status }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'

import {
  batchUpdateExposureResults,
  confirmImportExposureResults,
  createExposureSearchTask,
  deleteExposureSearchTask,
  getExposureSearchTask,
  listExposureSearchResults,
  listExposureSearchTasks,
  retryExposureSearchQuery,
  stopExposureSearchTask,
} from '@/api/modules/exposureSearch'
import type { ExposureSearchTask } from '@/types'

type ExposureSearchResultItem = {
  id: string
  source: string
  title: string
  url: string
  preview_url?: string | null
  risk_tags: string[]
  status: string
  query?: string
}

const tasks = ref<ExposureSearchTask[]>([])
const loading = ref(false)
const refreshing = ref(false)
const resultsLoading = ref(false)
const showCreateDialog = ref(false)
const submitting = ref(false)
const orgKeywordsStr = ref('')
const titleKeywordsStr = ref('')
const showResultsDrawer = ref(false)
const currentTask = ref<ExposureSearchTask | null>(null)
const results = ref<ExposureSearchResultItem[]>([])
const allResults = ref<ExposureSearchResultItem[]>([])
const selectedResults = ref<ExposureSearchResultItem[]>([])
const activeResultQueryFilter = ref('')
const queryPlanFilters = ref<Record<string, string>>({})
const retryingQueries = ref<Record<string, boolean>>({})
const retryingFailedGroups = ref<Record<string, boolean>>({})
const retryAllTasksLoading = ref(false)
const activeFailureCategory = ref('')
const autoRefreshEnabled = ref(false)
const refreshIntervalSec = ref(10)
let pollingTimer: number | null = null

const taskForm = ref({
  name: '',
  org_keywords: [] as string[],
  title_keywords: [] as string[],
  url_keywords: ['login', 'admin', 'sso'],
  file_types: ['pdf', 'xls', 'xlsx'],
  sources: ['bing', 'github', 'baidu'],
  headless: true,
  auto_run: true,
})

const failureSummary = computed(() => {
  const counts = new Map<string, number>()
  let total = 0
  for (const task of tasks.value) {
    const items = Array.isArray(task.query_plan) ? task.query_plan : []
    for (const item of items) {
      if (item.status !== 'failed') continue
      total += 1
      const category = item.error_category || '其它'
      counts.set(category, (counts.get(category) || 0) + 1)
    }
  }
  return {
    total,
    byCategory: Array.from(counts.entries()).map(([category, count]) => ({ category, count })),
  }
})

const fetchTasks = async () => {
  loading.value = true
  try {
    const res = await listExposureSearchTasks()
    tasks.value = res.data
  } catch (_err) {
    ElMessage.error('获取任务列表失败')
  } finally {
    loading.value = false
  }
}

const handleCreateTask = async () => {
  if (!taskForm.value.name) {
    ElMessage.warning('请输入任务名称')
    return
  }

  taskForm.value.org_keywords = orgKeywordsStr.value.split('\n').map((k) => k.trim()).filter(Boolean)
  taskForm.value.title_keywords = titleKeywordsStr.value.split('\n').map((k) => k.trim()).filter(Boolean)

  if (taskForm.value.org_keywords.length === 0) {
    ElMessage.warning('请输入组织关键词')
    return
  }

  submitting.value = true
  try {
    await createExposureSearchTask(taskForm.value)
    ElMessage.success('任务创建成功')
    showCreateDialog.value = false
    await fetchTasks()
  } catch (_err) {
    ElMessage.error('创建任务失败')
  } finally {
    submitting.value = false
  }
}

const handleDeleteTask = (task: ExposureSearchTask) => {
  ElMessageBox.confirm('确定删除该任务及其所有结果吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(async () => {
    try {
      await deleteExposureSearchTask(task.id)
      ElMessage.success('删除成功')
      await fetchTasks()
    } catch (_err) {
      ElMessage.error('删除失败')
    }
  }).catch(() => {})
}

const handleStopTask = (task: ExposureSearchTask) => {
  ElMessageBox.confirm('确定停止该任务吗？当前已捕获的数据将保留。', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(async () => {
    try {
      await stopExposureSearchTask(task.id)
      ElMessage.success('停止指令已发送')
      await fetchTasks()
    } catch (_err) {
      ElMessage.error('停止失败')
    }
  }).catch(() => {})
}

const viewResults = async (task: ExposureSearchTask) => {
  currentTask.value = task
  showResultsDrawer.value = true
  resultsLoading.value = true
  try {
    const res = await listExposureSearchResults(task.id)
    allResults.value = res.data
    results.value = res.data
    activeResultQueryFilter.value = ''
  } catch (_err) {
    ElMessage.error('获取搜索结果失败')
  } finally {
    resultsLoading.value = false
  }
}

const refreshCurrentTask = async () => {
  if (!currentTask.value) return
  try {
    const res = await getExposureSearchTask(currentTask.value.id)
    currentTask.value = res.data
  } catch {
    // Keep result drawer usable even if task refresh fails temporarily.
  }
}

const handleSelectionChange = (val: ExposureSearchResultItem[]) => {
  selectedResults.value = val
}

const filterResultsByQuery = async (task: ExposureSearchTask, query: string) => {
  await viewResults(task)
  activeResultQueryFilter.value = query
  results.value = allResults.value.filter((item) => item.query === query)
}

const clearResultQueryFilter = () => {
  activeResultQueryFilter.value = ''
  results.value = allResults.value
}

const handleBatchUpdateStatus = async (status: string) => {
  const ids = selectedResults.value.map((r) => r.id)
  try {
    await batchUpdateExposureResults({ ids, status })
    ElMessage.success('状态更新成功')
    if (currentTask.value) await viewResults(currentTask.value)
  } catch (_err) {
    ElMessage.error('更新失败')
  }
}

const handleConfirmImport = async () => {
  const ids = selectedResults.value.map((r) => r.id)
  if (!currentTask.value) return
  try {
    const res = await confirmImportExposureResults(currentTask.value.id, { ids })
    ElMessage.success(res.data.message || '导入成功')
    await viewResults(currentTask.value)
    await fetchTasks()
  } catch (_err) {
    ElMessage.error('导入资产失败')
  }
}

const copyQuery = async (query: string) => {
  if (!query) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(query)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = query
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success('搜索语法已复制')
  } catch (_err) {
    ElMessage.error('复制失败')
  }
}

const retryQuery = async (task: ExposureSearchTask, query: string) => {
  const retryKey = `${task.id}:${query}`
  if (retryingQueries.value[retryKey]) return
  retryingQueries.value = {
    ...retryingQueries.value,
    [retryKey]: true,
  }
  try {
    await retryExposureSearchQuery(task.id, query)
    ElMessage.success('已提交单条语法重试')
    await fetchTasks()
    if (currentTask.value?.id === task.id) {
      await refreshCurrentTask()
      await viewResults(currentTask.value)
    }
  } catch (_err) {
    ElMessage.error('重试失败')
  } finally {
    const nextState = { ...retryingQueries.value }
    delete nextState[retryKey]
    retryingQueries.value = nextState
  }
}

const isRetryingQuery = (taskId: string, query: string) => {
  return Boolean(retryingQueries.value[`${taskId}:${query}`])
}

const retryAllFailedQueries = async (task: ExposureSearchTask) => {
  const retryKey = task.id
  if (retryingFailedGroups.value[retryKey]) return
  const failedQueries = filteredQueryPlan(task)
    .filter((item) => item.status === 'failed' && item.query)
    .map((item) => item.query)
  if (failedQueries.length === 0) return

  retryingFailedGroups.value = {
    ...retryingFailedGroups.value,
    [retryKey]: true,
  }
  setQueryPlanFilter(task.id, 'failed')
  let successCount = 0
  let failedCount = 0
  try {
    for (const query of failedQueries) {
      try {
        await retryExposureSearchQuery(task.id, query)
        successCount += 1
      } catch {
        failedCount += 1
      }
    }
    if (failedCount === 0) {
      ElMessage.success(`已提交 ${successCount} 条失败语法重试`)
    } else {
      ElMessage.warning(`批量重试完成：成功 ${successCount} 条，失败 ${failedCount} 条`)
    }
    await fetchTasks()
    if (currentTask.value?.id === task.id) {
      await refreshCurrentTask()
      await viewResults(currentTask.value)
    }
    setQueryPlanFilter(task.id, 'failed')
    activeResultQueryFilter.value = ''
    results.value = allResults.value
  } catch (_err) {
    ElMessage.error('批量重试失败')
  } finally {
    const nextState = { ...retryingFailedGroups.value }
    delete nextState[retryKey]
    retryingFailedGroups.value = nextState
  }
}

const isRetryingAllFailed = (taskId: string) => {
  return Boolean(retryingFailedGroups.value[taskId])
}

const retryAllFailedAcrossTasks = async () => {
  if (retryAllTasksLoading.value) return
  const failures = tasks.value.flatMap((task) =>
    (Array.isArray(task.query_plan) ? task.query_plan : [])
      .filter((item) => item.status === 'failed' && item.query)
      .map((item) => ({ taskId: task.id, query: item.query as string })),
  )
  if (failures.length === 0) return

  retryAllTasksLoading.value = true
  let successCount = 0
  let failedCount = 0
  try {
    for (const item of failures) {
      try {
        await retryExposureSearchQuery(item.taskId, item.query)
        successCount += 1
      } catch {
        failedCount += 1
      }
    }
    if (failedCount === 0) {
      ElMessage.success(`已提交 ${successCount} 条失败语法重试`)
    } else {
      ElMessage.warning(`批量重试完成：成功 ${successCount} 条，失败 ${failedCount} 条`)
    }
    await fetchTasks()
    if (currentTask.value) {
      await refreshCurrentTask()
    }
  } finally {
    retryAllTasksLoading.value = false
  }
}

const setQueryPlanFilter = (taskId: string, filter: string) => {
  queryPlanFilters.value = {
    ...queryPlanFilters.value,
    [taskId]: filter,
  }
}

const filteredQueryPlan = (task: ExposureSearchTask) => {
  const items = Array.isArray(task.query_plan) ? task.query_plan : []
  const filter = queryPlanFilters.value[task.id] || 'all'
  let result = items
  if (filter !== 'all') {
    result = result.filter((item) => item.status === filter)
  }
  if (activeFailureCategory.value) {
    result = result.filter((item) => item.error_category === activeFailureCategory.value)
  }
  return result
}

const selectFailureCategory = (category: string) => {
  activeFailureCategory.value = activeFailureCategory.value === category ? '' : category
  for (const task of tasks.value) {
    setQueryPlanFilter(task.id, 'failed')
  }
}

const getStatusType = (status: string) => {
  switch (status) {
    case 'completed': return 'success'
    case 'running': return 'warning'
    case 'stopping': return 'warning'
    case 'failed': return 'danger'
    case 'stopped': return 'info'
    default: return 'info'
  }
}

const getResultStatusType = (status: string) => {
  switch (status) {
    case 'imported': return 'success'
    case 'valid': return 'primary'
    case 'ignored': return 'info'
    default: return 'warning'
  }
}

const getQueryStatusType = (status: string) => {
  switch (status) {
    case 'completed': return 'success'
    case 'running': return 'warning'
    case 'failed': return 'danger'
    case 'stopped': return 'info'
    default: return 'info'
  }
}

const progressBarStatus = (status: string) => {
  if (status === 'failed') return 'exception'
  if (status === 'completed') return 'success'
  return undefined
}

const progressStateClass = (status: string) => {
  if (status === 'completed') return 'is-completed'
  if (status === 'failed') return 'is-failed'
  if (status === 'stopped') return 'is-stopped'
  return 'is-running'
}

const getErrorCategoryTagType = (category?: string) => {
  switch (category) {
    case '验证码/风控':
      return 'warning'
    case '超时':
      return 'danger'
    case '页面结构变化':
      return 'info'
    case '无结果':
      return 'primary'
    default:
      return ''
  }
}

const formatTime = (time?: string) => {
  return time ? dayjs(time).format('YYYY-MM-DD HH:mm:ss') : '-'
}

onMounted(() => {
  fetchTasks()
})

onBeforeUnmount(() => {
  if (pollingTimer !== null) {
    window.clearInterval(pollingTimer)
    pollingTimer = null
  }
})

const stopAutoRefresh = () => {
  if (pollingTimer !== null) {
    window.clearInterval(pollingTimer)
    pollingTimer = null
  }
}

const runRefreshCycle = async () => {
  await fetchTasks()
  if (currentTask.value) {
    await refreshCurrentTask()
    if (showResultsDrawer.value) {
      await viewResults(currentTask.value)
    }
  }
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  pollingTimer = window.setInterval(() => {
    void runRefreshCycle()
  }, refreshIntervalSec.value * 1000)
}

const manualRefresh = async () => {
  refreshing.value = true
  try {
    await runRefreshCycle()
  } finally {
    refreshing.value = false
  }
}

watch(autoRefreshEnabled, (enabled) => {
  if (enabled) {
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
})

watch(refreshIntervalSec, () => {
  if (autoRefreshEnabled.value) {
    startAutoRefresh()
  }
})

watch(showResultsDrawer, async (visible) => {
  if (visible && currentTask.value) {
    await refreshCurrentTask()
    await viewResults(currentTask.value)
  }
  activeResultQueryFilter.value = ''
  allResults.value = []
})
</script>

<style scoped>
.exposure-search-container {
  padding: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.refresh-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.failure-summary-card {
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 1px solid #fee2e2;
  border-radius: 8px;
  background: #fff7f7;
}

.failure-summary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  font-weight: 600;
}

.failure-summary-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.failure-summary-tag {
  cursor: pointer;
}

.failure-summary-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.results-toolbar {
  margin-bottom: 16px;
  padding: 12px;
  background-color: #f5f7fa;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.toolbar-hint {
  font-size: 12px;
  color: #909399;
  margin-left: auto;
}

.risk-tag {
  margin-right: 4px;
  margin-bottom: 4px;
}

.url-link {
  word-break: break-all;
  display: block;
}

.query-filter-tag {
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.progress-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-cell.is-completed,
.drawer-progress-header.is-completed {
  color: var(--el-color-success);
}

.progress-cell.is-failed,
.drawer-progress-header.is-failed {
  color: var(--el-color-danger);
}

.progress-cell.is-stopped,
.drawer-progress-header.is-stopped {
  color: var(--el-text-color-secondary);
}

.progress-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.query-plan-panel {
  padding: 12px 8px;
}

.query-plan-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.query-plan-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.query-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.query-line.current {
  color: var(--el-color-primary);
}

.query-line.next {
  color: var(--el-color-success);
}

.query-line.two-line {
  white-space: normal;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.query-status-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #c0c4cc;
}

.query-status-dot.is-running {
  background: var(--el-color-warning);
  box-shadow: 0 0 0 4px rgba(230, 162, 60, 0.16);
}

.query-status-dot.is-completed {
  background: var(--el-color-success);
}

.query-status-dot.is-failed {
  background: var(--el-color-danger);
}

.query-status-dot.is-stopped {
  background: var(--el-text-color-secondary);
}

.drawer-progress-card {
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
}

.drawer-progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  font-weight: 600;
}

.drawer-progress-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.error-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.error-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
