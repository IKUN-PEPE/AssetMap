<template>
  <div class="page-shell">
    <div class="page-header">
      <h1 class="page-title">资产列表</h1>
      <p class="page-subtitle">查看当前已导入资产，并执行截图、标签与选择集操作。</p>
    </div>

    <el-card>
      <div class="toolbar-row">
        <el-button type="primary" @click="triggerScreenshot" :disabled="selectedIds.length === 0">批量截图</el-button>
        <el-button @click="triggerLabel('false_positive')" :disabled="selectedIds.length === 0">标记误报</el-button>
        <el-button @click="triggerLabel('confirmed')" :disabled="selectedIds.length === 0">标记已确认</el-button>
        <el-button @click="createSelectionFromAssets" :disabled="selectedIds.length === 0">保存为选择集</el-button>
      </div>
    </el-card>

    <el-card>
      <el-table :data="assets" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="normalized_url" label="URL" min-width="260" />
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column prop="status_code" label="状态码" width="100" />
        <el-table-column prop="screenshot_status" label="截图状态" width="120" />
        <el-table-column prop="label_status" label="标签状态" width="120" />
        <el-table-column label="操作" width="120">
          <template #default="scope">
            <el-button link type="primary" @click="goDetail(scope.row.id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { batchLabel, batchScreenshot, fetchAssets } from '@/api/modules/assets'
import { createSelection } from '@/api/modules/selections'
import type { AssetItem } from '@/types'

const router = useRouter()
const assets = ref<AssetItem[]>([])
const selectedIds = ref<string[]>([])

onMounted(async () => {
  try {
    assets.value = await fetchAssets()
  } catch {
    ElMessage.error('资产列表加载失败')
  }
})

function onSelectionChange(rows: AssetItem[]) {
  selectedIds.value = rows.map((item) => item.id)
}

function goDetail(id: string) {
  router.push(`/assets/${id}`)
}

async function triggerScreenshot() {
  try {
    await batchScreenshot(selectedIds.value)
    ElMessage.success('已触发截图任务')
  } catch {
    ElMessage.error('截图任务提交失败')
  }
}

async function triggerLabel(labelType: string) {
  try {
    await batchLabel(selectedIds.value, labelType)
    ElMessage.success('标签已提交')
  } catch {
    ElMessage.error('标签提交失败')
  }
}

async function createSelectionFromAssets() {
  try {
    await createSelection({
      selection_name: '前端临时选择集',
      selection_type: 'static_ids',
      asset_ids: selectedIds.value,
    })
    ElMessage.success('选择集已保存')
  } catch {
    ElMessage.error('选择集保存失败')
  }
}
</script>
