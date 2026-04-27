<template>
  <div class="page-shell">
    <div class="page-header">
      <h1 class="page-title">报告中心</h1>
      <p class="page-subtitle">查看数据库中已登记的报告，支持下载、删除和重新生成。</p>
    </div>

    <el-card class="report-card">
      <template #header>
        <div class="card-header">
          <span>报告列表</span>
          <el-button type="primary" link @click="loadReports">刷新</el-button>
        </div>
      </template>

      <el-table :data="reports" v-loading="loading" stripe>
        <el-table-column prop="report_name" label="报告名称" min-width="220" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)">{{ getStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="report_type" label="报告类型" width="100" />
        <el-table-column prop="object_path" label="文件路径" min-width="280">
          <template #default="{ row }">
            <el-text v-if="row.object_path" truncated>{{ row.object_path }}</el-text>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="file_missing" label="文件" width="120">
          <template #default="{ row }">
            <el-tag :type="row.file_missing ? 'danger' : 'success'" size="small">
              {{ row.file_missing ? '文件缺失' : '已保存' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="生成时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="finished_at" label="完成时间" width="180">
          <template #default="{ row }">{{ formatTime(row.finished_at) }}</template>
        </el-table-column>
        <el-table-column prop="file_size" label="文件大小" width="120">
          <template #default="{ row }">{{ formatFileSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :disabled="!row.download_url || row.file_missing" @click="download(row)">下载</el-button>
            <el-button link type="primary" @click="regenerate(row.id)">重新生成</el-button>
            <el-button link type="danger" @click="remove(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="create-card">
      <template #header>
        <div class="card-header">
          <span>创建新报告</span>
        </div>
      </template>

      <el-form :model="createForm" label-width="100px" class="create-form">
        <el-form-item label="报告名称">
          <el-input v-model="createForm.report_name" placeholder="例如：本月资产导出" />
        </el-form-item>
        <el-form-item label="报告格式">
          <el-select v-model="createFormat" style="width: 180px">
            <el-option label="Markdown" value="md" />
            <el-option label="CSV" value="csv" />
          </el-select>
        </el-form-item>
        <el-form-item label="文件内容">
          <el-input v-model="createForm.report_content" type="textarea" :rows="6" placeholder="填写报告正文或导出内容" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="creating" @click="create">创建并保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createReport, deleteReport, downloadReport, fetchReports, regenerateReport } from '@/api/modules/reports'
import type { ReportCreatePayload, ReportRead } from '@/types'

const loading = ref(false)
const creating = ref(false)
const reports = ref<ReportRead[]>([])
const createForm = ref<ReportCreatePayload>({
  report_name: `资产报告 - ${new Date().toLocaleDateString()}`,
  scope_type: 'manual',
  report_formats: ['md'],
  report_content: '',
  file_name: '',
  exclude_false_positive: true,
  exclude_confirmed: false,
})
const createFormat = ref<'md' | 'csv'>('md')

function getReportDownloadFallbackName(row: ReportRead) {
  const objectPathBaseName = row.object_path?.split(/\\|\//).pop()
  if (objectPathBaseName) {
    return objectPathBaseName
  }
  return `${row.report_name}.${row.report_type || 'txt'}`
}

async function loadReports() {
  loading.value = true
  try {
    reports.value = await fetchReports()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error?.message ?? '获取报告列表失败')
  } finally {
    loading.value = false
  }
}

async function create() {
  if (!createForm.value.report_content?.trim()) {
    ElMessage.warning('请输入报告内容')
    return
  }

  creating.value = true
  try {
    const report = await createReport({
      ...createForm.value,
      report_formats: [createFormat.value],
      file_name: createForm.value.file_name || undefined,
    })

    createForm.value.report_name = `资产报告 - ${new Date().toLocaleDateString()}`
    createForm.value.report_content = ''
    createForm.value.file_name = ''
    await loadReports()

    if (report.status === 'completed') {
      ElMessage.success('报告已保存')
      return
    }

    ElMessage.error(report.error_message || `报告状态为 ${getStatusLabel(report.status)}`)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error?.message ?? '创建报告失败')
  } finally {
    creating.value = false
  }
}

async function download(row: ReportRead) {
  if (!row.download_url || row.file_missing) return

  try {
    const blob = await downloadReport(row.id)
    const resolvedFileName = blob.fileName || getReportDownloadFallbackName(row)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = resolvedFileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error?.message ?? '下载失败')
  }
}

async function regenerate(id: string) {
  try {
    const report = await regenerateReport(id)
    if (report.status === 'completed' || report.status === 'running' || report.status === 'pending') {
      ElMessage.success('已提交重新生成')
    } else {
      ElMessage.error(report.error_message || `重新生成失败：${getStatusLabel(report.status)}`)
    }
    await loadReports()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error?.message ?? '重新生成失败')
  }
}

async function remove(id: string) {
  try {
    await ElMessageBox.confirm('确定删除这份报告吗？', '确认删除', { type: 'warning' })
    await deleteReport(id)
    ElMessage.success('报告已删除')
    await loadReports()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail ?? error?.message ?? '删除失败')
    }
  }
}

function getStatusTagType(status?: ReportRead['status']) {
  switch (status) {
    case 'completed':
      return 'success'
    case 'running':
      return 'primary'
    case 'pending':
      return 'warning'
    case 'failed':
      return 'danger'
    case 'file_missing':
      return 'danger'
    default:
      return 'info'
  }
}

function getStatusLabel(status?: ReportRead['status']) {
  switch (status) {
    case 'completed':
      return '已完成'
    case 'running':
      return '生成中'
    case 'pending':
      return '待生成'
    case 'failed':
      return '失败'
    case 'file_missing':
      return '文件缺失'
    default:
      return status || '-'
  }
}

function formatTime(value?: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function formatFileSize(value?: number | null) {
  if (!value) return '-'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

onMounted(() => {
  void loadReports()
})
</script>

<style scoped lang="scss">
.report-card,
.create-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.create-form :deep(.el-form-item) {
  margin-bottom: 16px;
}
</style>
