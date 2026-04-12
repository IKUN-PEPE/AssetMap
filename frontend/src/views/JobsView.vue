<template>
  <el-card>
    <template #header>创建采集任务</template>
    <el-form label-width="100px">
      <el-form-item label="任务名称">
        <el-input v-model="form.job_name" />
      </el-form-item>
      <el-form-item label="数据源">
        <el-checkbox-group v-model="form.sources">
          <el-checkbox label="sample" />
          <el-checkbox label="fofa" />
          <el-checkbox label="hunter" />
          <el-checkbox label="zoomeye" />
        </el-checkbox-group>
      </el-form-item>
      <el-form-item label="查询 JSON">
        <el-input v-model="queryText" type="textarea" :rows="8" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="submit">提交任务</el-button>
      </el-form-item>
    </el-form>
    <el-alert v-if="result" :title="`已创建任务：${result.job_id}`" type="success" show-icon />
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createCollectJob } from '@/api/modules/jobs'
import type { JobCreateResult } from '@/types'

const form = ref({ job_name: '样例采集任务', sources: ['sample'] as string[] })
const queryText = ref('[{"source":"sample","query":"demo"}]')
const result = ref<JobCreateResult | null>(null)

async function submit() {
  try {
    result.value = await createCollectJob({
      job_name: form.value.job_name,
      sources: form.value.sources,
      queries: JSON.parse(queryText.value),
      time_window: null,
    })
    ElMessage.success('任务创建成功')
  } catch {
    ElMessage.error('任务创建失败')
  }
}
</script>
