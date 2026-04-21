<template>
  <div class="page-shell">
    <div class="page-header">
      <h1 class="page-title">报告中心</h1>
      <p class="page-subtitle">创建并管理您的资产报告任务。</p>
    </div>

    <!-- 创建报告任务 -->
    <el-card class="box-card create-report-card">
      <template #header>
        <div class="card-header">
          <span>创建新报告</span>
        </div>
      </template>
      <el-form :model="createForm" label-width="100px" :inline="true" class="create-form">
        <el-form-item label="报告名称">
          <el-input v-model="createForm.report_name" placeholder="例如：季度安全审计报告" />
        </el-form-item>
        <el-form-item label="范围类型">
          <el-select v-model="createForm.scope_type" style="width: 150px">
            <el-option label="手动选择" value="manual" />
            <el-option label="选择集" value="selection" disabled />
          </el-select>
        </el-form-item>
        <el-form-item label="排除误报">
          <el-switch v-model="createForm.exclude_false_positive" />
        </el-form-item>
        <el-form-item label="排除已确认">
          <el-switch v-model="createForm.exclude_confirmed" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleCreateReport" :loading="isCreating">立即创建</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 报告任务列表 -->
    <el-card class="box-card report-list-card" v-loading="isLoading">
       <template #header>
        <div class="card-header">
          <span>报告任务列表</span>
          <el-button type="primary" link @click="fetchReports"><i-ep-refresh /> 刷新</el-button>
        </div>
      </template>
      <el-table :data="reports" stripe style="width: 100%">
        <el-table-column prop="report_name" label="报告名称" width="250" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
           <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="finished_at" label="完成时间" width="180">
           <template #default="{ row }">{{ formatTime(row.finished_at) }}</template>
        </el-table-column>
        <el-table-column prop="total_assets" label="资产总数" width="100" />
        <el-table-column label="操作">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleViewDetails(row)">查看详情</el-button>
            <el-button link type="primary" :disabled="row.status === 'generating'" @click="handleRegenerate(row.id)">重新生成</el-button>
            <el-button link type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 报告详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="报告详情" direction="rtl" size="40%">
      <div v-if="selectedReport" class="details-container">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="报告ID">{{ selectedReport.id }}</el-descriptions-item>
          <el-descriptions-item label="报告名称">{{ selectedReport.report_name }}</el-descriptions-item>
          <el-descriptions-item label="状态">
             <el-tag :type="getStatusTagType(selectedReport.status)">{{ selectedReport.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(selectedReport.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ formatTime(selectedReport.finished_at) }}</el-descriptions-item>
          <el-descriptions-item label="资产总数">{{ selectedReport.total_assets }}</el-descriptions-item>
          <el-descriptions-item label="排除资产数">{{ selectedReport.excluded_assets }}</el-descriptions-item>
          <el-descriptions-item v-if="selectedReport.status === 'failed'" label="错误信息">
             <el-alert type="error" :closable="false">{{ selectedReport.error_message }}</el-alert>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'
import type { ReportRead } from '@/types' // Assume this type is defined in types/index.ts or similar

// --- State ---
const isLoading = ref(true)
const isCreating = ref(false)
const reports = ref<ReportRead[]>([])
const createForm = ref({
  report_name: `资产报告 - ${new Date().toLocaleDateString()}`,
  scope_type: 'manual',
  exclude_false_positive: true,
  exclude_confirmed: false,
  report_formats: ['html'],
})

const drawerVisible = ref(false)
const selectedReport = ref<ReportRead | null>(null)

// --- API Methods ---
async function fetchReports() {
  isLoading.value = true
  try {
    const { data } = await http.get<ReportRead[]>('/api/v1/reports/')
    reports.value = data
  } catch (error) {
    ElMessage.error('获取报告列表失败')
  } finally {
    isLoading.value = false
  }
}

async function handleCreateReport() {
  isCreating.value = true
  try {
    await http.post('/api/v1/reports/', createForm.value)
    ElMessage.success('报告任务已创建')
    // Reset form and refresh list
    createForm.value.report_name = `资产报告 - ${new Date().toLocaleDateString()}`;
    await fetchReports()
  } catch {
    ElMessage.error('报告任务创建失败')
  } finally {
    isCreating.value = false
  }
}

async function handleRegenerate(id: string) {
  try {
    await http.post(`/api/v1/reports/${id}/regenerate`)
    ElMessage.success('已提交重新生成任务')
    await fetchReports()
  } catch {
     ElMessage.error('重新生成失败')
  }
}

async function handleDelete(id: string) {
  try {
    await ElMessageBox.confirm('确定要删除这个报告任务吗？此操作不可撤销。', '警告', {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await http.delete(`/api/v1/reports/${id}`)
    ElMessage.success('报告已删除')
    await fetchReports()
  } catch (e) {
    // if user clicks cancel, it throws, so we check
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

// --- UI Methods ---
function handleViewDetails(report: ReportRead) {
  selectedReport.value = report
  drawerVisible.value = true
}

function getStatusTagType(status: string) {
  switch (status) {
    case 'completed': return 'success'
    case 'generating': return 'primary'
    case 'pending': return 'info'
    case 'failed': return 'danger'
    default: return 'info'
  }
}

function formatTime(timeStr: string | null | undefined): string {
    if (!timeStr) return '-'
    return new Date(timeStr).toLocaleString()
}


// --- Lifecycle ---
onMounted(() => {
  fetchReports()
})
</script>

<style scoped lang="scss">
.create-report-card {
  margin-bottom: 20px;
}

.create-form .el-form-item {
  margin-bottom: 0; // Compact form
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.details-container {
  padding: 0 20px;
}
</style>
