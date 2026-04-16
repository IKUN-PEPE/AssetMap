<template>
  <div class="page-shell">
    <div class="page-header">
      <h1 class="page-title">系统配置</h1>
      <p class="page-subtitle">查看当前后端运行模式、输出目录和数据库配置。</p>
    </div>

    <el-card>
      <el-descriptions v-if="config" :column="1" border>
        <el-descriptions-item label="Sample Mode">{{ config.sample_mode }}</el-descriptions-item>
        <el-descriptions-item label="截图目录">{{ config.screenshot_output_dir }}</el-descriptions-item>
        <el-descriptions-item label="结果目录">{{ config.result_output_dir }}</el-descriptions-item>
        <el-descriptions-item label="数据库">{{ config.database_url }}</el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchSystemConfig } from '@/api/modules/system'
import type { SystemConfig } from '@/types'

const config = ref<SystemConfig | null>(null)

onMounted(async () => {
  try {
    config.value = await fetchSystemConfig()
  } catch {
    ElMessage.error('系统配置加载失败')
  }
})
</script>
