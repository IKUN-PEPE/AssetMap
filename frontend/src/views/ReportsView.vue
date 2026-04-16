<template>
  <div class="page-shell">
    <div class="page-header">
      <h1 class="page-title">报告中心</h1>
      <p class="page-subtitle">创建报告任务，后续将用于统一生成资产交付文档。</p>
    </div>

    <el-card>
      <el-form label-width="120px">
        <el-form-item label="报告名称">
          <el-input v-model="form.report_name" />
        </el-form-item>
        <el-form-item label="范围类型">
          <el-select v-model="form.scope_type">
            <el-option label="selection" value="selection" />
            <el-option label="manual" value="manual" />
          </el-select>
        </el-form-item>
        <el-form-item label="排除误报">
          <el-switch v-model="form.exclude_false_positive" />
        </el-form-item>
        <el-form-item label="排除已确认">
          <el-switch v-model="form.exclude_confirmed" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="submit">创建报告任务</el-button>
        </el-form-item>
      </el-form>
      <el-alert v-if="result" :title="`已创建报告：${result.report_id}`" type="success" show-icon />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createReport } from '@/api/modules/reports'
import type { ReportCreateResult } from '@/types'

const form = ref({
  report_name: '默认报告',
  scope_type: 'manual',
  exclude_false_positive: true,
  exclude_confirmed: false,
})
const result = ref<ReportCreateResult | null>(null)

async function submit() {
  try {
    result.value = await createReport({
      report_name: form.value.report_name,
      scope_type: form.value.scope_type,
      report_formats: ['html'],
      exclude_false_positive: form.value.exclude_false_positive,
      exclude_confirmed: form.value.exclude_confirmed,
    })
    ElMessage.success('报告任务已创建')
  } catch {
    ElMessage.error('报告任务创建失败')
  }
}
</script>
