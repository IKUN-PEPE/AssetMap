<template>
  <div class="exposure-search-container">
    <el-card class="box-card">
      <template #header>
        <div class="card-header">
          <span>暴露面搜索 / Exposure Search</span>
          <el-button type="primary" @click="showCreateDialog = true">新建搜索任务</el-button>
        </div>
      </template>

      <el-table :data="tasks" style="width: 100%" v-loading="loading">
        <el-table-column prop="name" label="任务名称" />
        <el-table-column prop="status" label="状态">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">{{ scope.row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_results" label="总结果数" width="100" />
        <el-table-column prop="imported_count" label="已导入资产" width="100" />
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250">
          <template #default="scope">
            <el-button size="small" @click="viewResults(scope.row)">查看结果</el-button>
            <el-button size="small" type="danger" @click="handleDeleteTask(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create Task Dialog -->
    <el-dialog v-model="showCreateDialog" title="新建暴露面搜索任务" width="700px">
      <el-form :model="taskForm" label-width="120px">
        <el-form-item label="任务名称">
          <el-input v-model="taskForm.name" placeholder="例如：深圳地铁暴露面搜索" />
        </el-form-item>
        <el-form-item label="组织关键词">
          <el-input v-model="orgKeywordsStr" type="textarea" :rows="3" placeholder="每行一个关键词或简称，例如：\n深圳地铁\n深铁\nSZMC" />
        </el-form-item>
        <el-form-item label="标题关键词">
          <el-input v-model="titleKeywordsStr" type="textarea" :rows="2" placeholder="可选，例如：后台管理\n登录\nOA" />
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
          <el-switch v-model="taskForm.use_playwright" active-text="后台运行" inactive-text="窗口交互" style="margin-left: 20px" />
          <span class="hint">（窗口交互模式可手动处理验证码）</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreateTask" :loading="submitting">创建任务</el-button>
      </template>
    </el-dialog>

    <!-- Results Drawer -->
    <el-drawer v-model="showResultsDrawer" :title="'搜索结果: ' + (currentTask?.name || '')" size="85%">
      <div class="results-toolbar">
        <el-button type="success" @click="handleConfirmImport" :disabled="!selectedResults.length">导入选中项为资产</el-button>
        <el-button @click="handleBatchUpdateStatus('valid')" :disabled="!selectedResults.length">标记为有效线索</el-button>
        <el-button @click="handleBatchUpdateStatus('ignored')" :disabled="!selectedResults.length">忽略选中</el-button>
        <span class="toolbar-hint">注：非网页结果（如PDF、GitHub代码等）将作为有效线索保留，不进入Web资产库。</span>
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
            <el-link :href="scope.row.url" target="_blank" type="primary" class="url-link">{{ scope.row.url }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="risk_tags" label="风险标签" width="200">
          <template #default="scope">
            <el-tag v-for="tag in scope.row.risk_tags" :key="tag" size="small" effect="plain" class="risk-tag">{{ tag }}</el-tag>
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
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import {
  listExposureSearchTasks,
  createExposureSearchTask,
  deleteExposureSearchTask,
  listExposureSearchResults,
  batchUpdateExposureResults,
  confirmImportExposureResults
} from '@/api/modules/exposureSearch'

const tasks = ref<any[]>([])
const loading = ref(false)
const resultsLoading = ref(false)
const showCreateDialog = ref(false)
const submitting = ref(false)

const orgKeywordsStr = ref('')
const titleKeywordsStr = ref('')

const taskForm = ref({
  name: '',
  org_keywords: [] as string[],
  title_keywords: [] as string[],
  url_keywords: ['login', 'admin', 'sso'],
  file_types: ['pdf', 'xls', 'xlsx'],
  sources: ['bing', 'github', 'baidu'],
  use_playwright: true,
  auto_run: true
})

const showResultsDrawer = ref(false)
const currentTask = ref<any>(null)
const results = ref<any[]>([])
const selectedResults = ref<any[]>([])

const fetchTasks = async () => {
  loading.value = true
  try {
    const res = await listExposureSearchTasks()
    tasks.value = res.data
  } catch (err) {
    ElMessage.error('获取任务列表失败')
  } finally {
    loading.value = false
  }
}

const handleCreateTask = async () => {
  if (!taskForm.value.name) return ElMessage.warning('请输入任务名称')
  
  taskForm.value.org_keywords = orgKeywordsStr.value.split('\n').map(k => k.trim()).filter(Boolean)
  taskForm.value.title_keywords = titleKeywordsStr.value.split('\n').map(k => k.trim()).filter(Boolean)
  
  if (taskForm.value.org_keywords.length === 0) return ElMessage.warning('请输入组织关键词')

  submitting.value = true
  try {
    await createExposureSearchTask(taskForm.value)
    ElMessage.success('任务创建成功')
    showCreateDialog.value = false
    fetchTasks()
  } catch (err) {
    ElMessage.error('创建任务失败')
  } finally {
    submitting.value = false
  }
}

const handleDeleteTask = (task: any) => {
  ElMessageBox.confirm('确定删除该任务及其所有结果吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await deleteExposureSearchTask(task.id)
      ElMessage.success('删除成功')
      fetchTasks()
    } catch (err) {
      ElMessage.error('删除失败')
    }
  }).catch(() => {})
}

const viewResults = async (task: any) => {
  currentTask.value = task
  showResultsDrawer.value = true
  resultsLoading.value = true
  try {
    const res = await listExposureSearchResults(task.id)
    results.value = res.data
  } catch (err) {
    ElMessage.error('获取搜索结果失败')
  } finally {
    resultsLoading.value = false
  }
}

const handleSelectionChange = (val: any[]) => {
  selectedResults.value = val
}

const handleBatchUpdateStatus = async (status: string) => {
  const ids = selectedResults.value.map(r => r.id)
  try {
    await batchUpdateExposureResults({ ids, status })
    ElMessage.success('状态更新成功')
    viewResults(currentTask.value)
  } catch (err) {
    ElMessage.error('更新失败')
  }
}

const handleConfirmImport = async () => {
  const ids = selectedResults.value.map(r => r.id)
  try {
    const res = await confirmImportExposureResults(currentTask.value.id, { ids })
    ElMessage.success(res.data.message || '导入成功')
    viewResults(currentTask.value)
    fetchTasks()
  } catch (err) {
    ElMessage.error('导入资产失败')
  }
}

const getStatusType = (status: string) => {
  switch (status) {
    case 'completed': return 'success'
    case 'running': return 'warning'
    case 'failed': return 'danger'
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

const formatTime = (time: string) => {
  return dayjs(time).format('YYYY-MM-DD HH:mm:ss')
}

onMounted(() => {
  fetchTasks()
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
}
.results-toolbar {
  margin-bottom: 16px;
  padding: 12px;
  background-color: #f5f7fa;
  border-radius: 4px;
}
.toolbar-hint {
  font-size: 12px;
  color: #909399;
  margin-left: 16px;
}
.risk-tag {
  margin-right: 4px;
  margin-bottom: 4px;
}
.url-link {
  word-break: break-all;
  display: block;
}
</style>
