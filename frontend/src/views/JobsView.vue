<template>
  <div class="page-shell">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">任务中心</h1>
        <p class="page-subtitle">采集任务调度与实时状态监控中心</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" round class="apple-button" @click="openCreateDialog">
          <el-icon><Plus /></el-icon>
          新建采集任务
        </el-button>
      </div>
    </div>

    <!-- 任务统计面板 -->
    <div class="stats-grid mb-6">
      <div class="stats-card apple-card">
        <div class="stats-label">总任务数</div>
        <div class="stats-value">{{ jobs.length }}</div>
      </div>
      <div class="stats-card apple-card">
        <div class="stats-label">运行中</div>
        <div class="stats-value text-primary">{{ runningCount }}</div>
      </div>
      <div class="stats-card apple-card">
        <div class="stats-label">已完成</div>
        <div class="stats-value text-success">{{ completedCount }}</div>
      </div>
    </div>

    <!-- 任务列表 (响应式卡片流) -->
    <el-row :gutter="20">
      <el-col v-for="job in jobs" :key="job.id" :xs="24" :sm="12" :lg="8" class="mb-5">
        <div class="job-card apple-card" :class="{ 'is-running': job.status === 'running' }">
          <div class="job-card-header">
            <div class="job-info">
              <h3 class="job-name text-truncate" :title="job.job_name">{{ job.job_name }}</h3>
              <div class="job-meta">
                <el-tag :type="getStatusType(job.status)" size="small" round effect="light">
                  {{ getStatusLabel(job.status) }}
                </el-tag>
                <span class="job-time">{{ formatTime(job.created_at) }}</span>
              </div>
            </div>
            <div class="job-actions">
              <el-tooltip content="刷新状态" placement="top">
                <el-button link @click="refreshJob(job.id)">
                  <el-icon><Refresh /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
          </div>

          <div class="job-card-content">
            <!-- 进度条 -->
            <div class="progress-section mb-4">
              <div class="progress-info">
                <span>处理进度</span>
                <span>{{ job.progress }}%</span>
              </div>
              <el-progress 
                :percentage="job.progress" 
                :status="getProgressStatus(job.status)"
                :stroke-width="10"
                :show-text="false"
                round
              />
            </div>

            <!-- 数据统计 -->
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
                <div class="count-label">总量</div>
              </div>
            </div>
          </div>

          <div class="job-card-footer">
            <div class="footer-left">
              <span v-if="job.error_message" class="error-text text-truncate" :title="job.error_message">
                {{ job.error_message }}
              </span>
            </div>
            <div class="footer-right">
              <el-button 
                v-if="job.status !== 'running' && job.status !== 'pending'" 
                type="primary" 
                size="small" 
                round 
                @click="handleStart(job.id)"
              >
                开始任务
              </el-button>
              <el-button 
                v-if="job.status === 'running' || job.status === 'pending'" 
                type="danger" 
                size="small" 
                round 
                plain
                @click="handleStop(job.id)"
              >
                停止任务
              </el-button>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 空状态 -->
    <el-empty v-if="jobs.length === 0" description="暂无采集任务" />

    <!-- 创建任务对话框 (分步式) -->
    <el-dialog 
      v-model="showCreateDialog" 
      :title="createStep === 1 ? '新建采集任务' : '配置字段映射'" 
      width="850px" 
      custom-class="apple-dialog"
    >
      <!-- 第一步：基本信息与上传 -->
      <div v-if="createStep === 1">
        <el-form :model="createForm" label-width="100px">
          <el-form-item label="任务名称">
            <el-input v-model="createForm.job_name" placeholder="请输入任务名称" />
          </el-form-item>
          <el-form-item label="任务来源">
            <el-radio-group v-model="createForm.sourceType">
              <el-radio label="csv">CSV 文件导入</el-radio>
              <el-radio label="sample">样例数据 (Sample)</el-radio>
            </el-radio-group>
          </el-form-item>
          
          <template v-if="createForm.sourceType === 'csv'">
            <el-form-item label="CSV 文件">
              <div class="upload-area">
                <input type="file" accept=".csv" @change="onFileChange" id="csv-upload" hidden />
                <label for="csv-upload" class="upload-label">
                  <el-icon v-if="!selectedFile"><Upload /></el-icon>
                  <span v-if="!selectedFile">点击上传 CSV 文件</span>
                  <span v-else class="text-primary">{{ selectedFile.name }}</span>
                </label>
              </div>
            </el-form-item>
          </template>

          <template v-else>
            <el-form-item label="查询指令">
              <el-input v-model="createForm.queryText" type="textarea" :rows="4" placeholder='[{"source":"sample","query":"demo"}]' />
            </el-form-item>
          </template>

          <el-form-item label="去重策略">
            <el-select v-model="createForm.dedup_strategy" style="width: 100%">
              <el-option label="跳过重复 (Skip)" value="skip" />
              <el-option label="覆盖更新 (Overwrite)" value="overwrite" />
              <el-option label="全部保留 (Keep All)" value="keep_all" />
            </el-select>
          </el-form-item>
        </el-form>
      </div>

      <!-- 第二步：预览与映射 -->
      <div v-else class="mapping-container">
        <div class="preview-section mb-4">
          <div class="section-title">数据预览 (前 5 行)</div>
          <el-table :data="previewData.rows.slice(0, 5)" size="small" border stripe class="preview-table">
            <el-table-column v-for="h in previewData.headers" :key="h" :prop="h" :label="h" min-width="120" show-overflow-tooltip />
          </el-table>
        </div>

        <div class="mapping-section">
          <div class="section-title">字段映射 (系统字段 -> CSV 列)</div>
          <div class="mapping-grid">
            <div v-for="field in systemFields" :key="field.key" class="mapping-item">
              <div class="field-label">
                {{ field.label }} 
                <span v-if="field.required" class="required">*</span>
              </div>
              <el-select v-model="fieldMapping[field.key]" placeholder="请选择列" clearable>
                <el-option v-for="h in previewData.headers" :key="h" :label="h" :value="h" />
              </el-select>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="showCreateDialog = false">取消</el-button>
          
          <template v-if="createForm.sourceType === 'csv'">
            <el-button v-if="createStep === 1" type="primary" round @click="goToMapping" :loading="previewLoading">
              下一步：配置映射
            </el-button>
            <template v-else>
              <el-button @click="createStep = 1">上一步</el-button>
              <el-button type="primary" round @click="submitCreate">完成创建</el-button>
            </template>
          </template>
          
          <el-button v-else type="primary" round @click="submitCreate">立即创建</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Upload } from '@element-plus/icons-vue'
import { listJobs, startTask, stopTask, getTaskStatus, createCollectJob, previewCsv } from '@/api/modules/jobs'
import type { CollectJob } from '@/types'
import dayjs from 'dayjs'

const jobs = ref<CollectJob[]>([])
const loading = ref(false)
const showCreateDialog = ref(false)
const createStep = ref(1)
const previewLoading = ref(false)

const createForm = ref({
  job_name: '新采集任务',
  sourceType: 'csv',
  sources: ['csv_import'],
  queryText: '[{"source":"sample","query":"demo"}]',
  dedup_strategy: 'skip'
})

const selectedFile = ref<File | null>(null)
const previewData = ref<{ headers: string[], rows: any[], file_path: string }>({ headers: [], rows: [], file_path: '' })
const fieldMapping = ref<Record<string, string>>({
  url: '',
  ip: '',
  port: '',
  title: '',
  tags: ''
})

const systemFields = [
  { key: 'url', label: 'URL 地址', required: true },
  { key: 'ip', label: 'IP 地址', required: true },
  { key: 'port', label: '端口号', required: true },
  { key: 'title', label: '页面标题', required: false },
  { key: 'tags', label: '标签/分类', required: false }
]

let timer: number | null = null

const runningCount = computed(() => jobs.value.filter(j => j.status === 'running' || j.status === 'pending').length)
const completedCount = computed(() => jobs.value.filter(j => j.status === 'success').length)

async function fetchJobs() {
  try {
    jobs.value = await listJobs()
  } catch (error) {
    console.error('Fetch jobs failed:', error)
  }
}

function openCreateDialog() {
  showCreateDialog.value = true
  createStep.value = 1
  selectedFile.value = null
  createForm.value.job_name = `采集任务_${dayjs().format('MMDD_HHmm')}`
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  selectedFile.value = target.files?.[0] || null
}

async function goToMapping() {
  if (!selectedFile.value) {
    ElMessage.error('请先选择 CSV 文件')
    return
  }
  
  previewLoading.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    previewData.value = await previewCsv(formData)
    
    // 自动尝试匹配
    autoMatchFields()
    
    createStep.value = 2
  } catch (error) {
    ElMessage.error('CSV 预览失败: ' + error)
  } finally {
    previewLoading.value = false
  }
}

function autoMatchFields() {
  const headers = previewData.value.headers.map(h => h.toLowerCase())
  const mapping: Record<string, string> = { url: '', ip: '', port: '', title: '', tags: '' }
  
  const rules: Record<string, string[]> = {
    url: ['url', 'address', 'link', '目标'],
    ip: ['ip', 'host', 'ipv4', '地址'],
    port: ['port', '端口'],
    title: ['title', 'name', '标题', '网站名称'],
    tags: ['tags', 'category', '标签', '分类']
  }
  
  for (const [key, patterns] of Object.entries(rules)) {
    const match = previewData.value.headers.find(h => {
      const lowerH = h.toLowerCase()
      return patterns.some(p => lowerH.includes(p))
    })
    if (match) mapping[key] = match
  }
  
  fieldMapping.value = mapping
}

async function submitCreate() {
  if (createForm.value.sourceType === 'csv') {
    // 验证必填映射
    if (!fieldMapping.value.url || !fieldMapping.value.ip || !fieldMapping.value.port) {
      ElMessage.error('URL、IP 和端口号为必填映射字段')
      return
    }
  }

  try {
    const payload: any = {
      job_name: createForm.value.job_name,
      sources: createForm.value.sourceType === 'csv' ? ['csv_import'] : ['sample'],
      dedup_strategy: createForm.value.dedup_strategy,
      created_by: 'admin'
    }

    if (createForm.value.sourceType === 'csv') {
      payload.file_path = previewData.value.file_path
      payload.field_mapping = fieldMapping.value
      payload.queries = []
    } else {
      payload.queries = JSON.parse(createForm.value.queryText || '[]')
    }

    await createCollectJob(payload)
    ElMessage.success('任务创建成功')
    showCreateDialog.value = false
    fetchJobs()
  } catch (error) {
    ElMessage.error('创建任务失败: ' + error)
  }
}

async function refreshJob(id: string) {
  try {
    const status = await getTaskStatus(id)
    const index = jobs.value.findIndex(j => j.id === id)
    if (index !== -1) {
      Object.assign(jobs.value[index], status)
    }
  } catch (error) {
    console.error(`Refresh job ${id} failed:`, error)
  }
}

async function handleStart(id: string) {
  try {
    await startTask(id)
    ElMessage.success('任务已启动')
    fetchJobs()
  } catch (error) {
    ElMessage.error('启动失败')
  }
}

async function handleStop(id: string) {
  try {
    await stopTask(id)
    ElMessage.warning('已请求停止任务')
    fetchJobs()
  } catch (error) {
    ElMessage.error('停止请求失败')
  }
}

function startPolling() {
  timer = window.setInterval(() => {
    fetchJobs()
  }, 3000)
}

function stopPolling() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function getStatusType(status: string) {
  const map: Record<string, string> = {
    'pending': 'info',
    'running': 'primary',
    'success': 'success',
    'failed': 'danger',
    'cancelled': 'warning'
  }
  return map[status] || 'info'
}

function getStatusLabel(status: string) {
  const map: Record<string, string> = {
    'pending': '排队中',
    'running': '进行中',
    'success': '已完成',
    'failed': '失败',
    'cancelled': '已取消'
  }
  return map[status] || status
}

function getProgressStatus(status: string) {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'exception'
  if (status === 'cancelled') return 'warning'
  return ''
}

function formatTime(time?: string) {
  if (!time) return '-'
  return dayjs(time).format('YYYY-MM-DD HH:mm')
}

onMounted(() => {
  fetchJobs()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped lang="scss">
.mb-6 { margin-bottom: 24px; }
.mb-5 { margin-bottom: 20px; }
.mb-4 { margin-bottom: 16px; }

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
}

.apple-card {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.05);
  padding: 20px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.apple-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.08);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.stats-card {
  text-align: center;
  .stats-label {
    font-size: 13px;
    color: var(--el-text-color-secondary);
    margin-bottom: 8px;
  }
  .stats-value {
    font-size: 28px;
    font-weight: 600;
  }
}

.job-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  &.is-running {
    border-color: var(--el-color-primary-light-5);
    background: rgba(var(--el-color-primary-rgb), 0.02);
  }
}

.job-card-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;
  .job-name {
    font-size: 17px;
    font-weight: 600;
    margin: 0 0 8px 0;
  }
  .job-meta {
    display: flex;
    align-items: center;
    gap: 10px;
    .job-time { font-size: 12px; color: var(--el-text-color-secondary); }
  }
}

.counts-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  background: rgba(0, 0, 0, 0.03);
  border-radius: 12px;
  padding: 12px;
  text-align: center;
  .count-item { border-right: 1px solid rgba(0, 0, 0, 0.05); &:last-child { border-right: none; } }
  .count-value { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
  .count-label { font-size: 11px; color: var(--el-text-color-secondary); }
}

.job-card-footer {
  margin-top: auto;
  padding-top: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  .error-text { font-size: 12px; color: var(--el-color-danger); max-width: 150px; }
}

.upload-area {
  width: 100%;
  .upload-label {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 30px;
    border: 2px dashed rgba(0, 0, 0, 0.1);
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.3s;
    &:hover { border-color: var(--el-color-primary); background: rgba(var(--el-color-primary-rgb), 0.02); }
    .el-icon { font-size: 32px; color: var(--el-text-color-secondary); margin-bottom: 10px; }
  }
}

.section-title { font-weight: 600; margin-bottom: 12px; font-size: 14px; color: var(--el-text-color-primary); }

.mapping-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.mapping-item {
  .field-label { font-size: 13px; margin-bottom: 6px; color: var(--el-text-color-regular); }
  .required { color: var(--el-color-danger); margin-left: 4px; }
  .el-select { width: 100%; }
}

.preview-table {
  border-radius: 8px;
  overflow: hidden;
}

.text-truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.apple-button { font-weight: 500; }

:deep(.apple-dialog) {
  border-radius: 20px;
  backdrop-filter: blur(30px);
  background: rgba(255, 255, 255, 0.85);
  .el-dialog__header { border-bottom: 1px solid rgba(0, 0, 0, 0.05); }
  .el-dialog__title { font-weight: 600; }
}
</style>
