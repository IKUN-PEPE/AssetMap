<template>
  <el-card>
    <template #header>系统配置</template>
    <el-descriptions v-if="config" :column="1" border>
      <el-descriptions-item label="Sample Mode">{{ config.sample_mode }}</el-descriptions-item>
      <el-descriptions-item label="截图目录">{{ config.screenshot_output_dir }}</el-descriptions-item>
      <el-descriptions-item label="结果目录">{{ config.result_output_dir }}</el-descriptions-item>
      <el-descriptions-item label="数据库">{{ config.database_url }}</el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchSystemConfig } from '@/api/modules/system'
import type { SystemConfig } from '@/types'

const config = ref<SystemConfig | null>(null)

onMounted(async () => {
  config.value = await fetchSystemConfig()
})
</script>
