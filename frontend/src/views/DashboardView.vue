<template>
  <div class="page-shell">
    <div class="page-header">
      <h1 class="page-title">仪表盘</h1>
      <p class="page-subtitle">查看服务状态、运行模式和当前基础配置。</p>
    </div>

    <el-row :gutter="16" class="page-section">
      <el-col :span="8">
        <el-card>
          <template #header>服务状态</template>
          <div class="metric-value">{{ healthText }}</div>
          <div class="metric-note">用于确认后端服务当前是否可用。</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>运行模式</template>
          <div class="metric-value">{{ config?.sample_mode ? 'Sample Mode' : 'Live Mode' }}</div>
          <div class="metric-note">当前默认以样例数据流程优先联调。</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>数据库</template>
          <div class="metric-value">{{ config?.database_url ? '已配置' : '未配置' }}</div>
          <div class="metric-note">{{ config?.database_url || '-' }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchHealth, fetchSystemConfig } from '@/api/modules/system'
import type { SystemConfig } from '@/types'

const health = ref<Record<string, string> | null>(null)
const config = ref<SystemConfig | null>(null)
const healthText = computed(() => (health.value?.status === 'ok' ? '后端正常' : '未连接'))

onMounted(async () => {
  try {
    health.value = await fetchHealth()
    config.value = await fetchSystemConfig()
  } catch {
    ElMessage.error('仪表盘数据加载失败')
  }
})
</script>
