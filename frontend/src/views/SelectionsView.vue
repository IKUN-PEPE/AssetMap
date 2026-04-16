<template>
  <div class="page-shell">
    <div class="page-header">
      <h1 class="page-title">选择集</h1>
      <p class="page-subtitle">保存筛选结果或静态资产集合，便于后续截图和报告复用。</p>
    </div>

    <el-card>
      <div class="toolbar-row">
        <el-input v-model="selectionName" placeholder="选择集名称" style="width: 240px" />
        <el-button type="primary" @click="submit">新建选择集</el-button>
      </div>
    </el-card>

    <el-card>
      <el-table :data="selections">
        <el-table-column prop="selection_name" label="名称" />
        <el-table-column prop="selection_type" label="类型" width="180" />
        <el-table-column prop="created_by" label="创建人" width="160" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createSelection, fetchSelections } from '@/api/modules/selections'
import type { SelectionItem } from '@/types'

const selections = ref<SelectionItem[]>([])
const selectionName = ref('默认选择集')

async function loadSelections() {
  try {
    selections.value = await fetchSelections()
  } catch {
    ElMessage.error('选择集加载失败')
  }
}

async function submit() {
  try {
    await createSelection({
      selection_name: selectionName.value,
      selection_type: 'dynamic_filter',
      filter_snapshot: {},
    })
    ElMessage.success('创建成功')
    await loadSelections()
  } catch {
    ElMessage.error('创建失败')
  }
}

onMounted(loadSelections)
</script>
