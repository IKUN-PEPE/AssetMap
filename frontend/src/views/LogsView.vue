<template>
  <div class="page-shell">
    <div class="page-header">
      <h1 class="page-title">实时日志</h1>
      <p class="page-subtitle">查看任务日志与服务日志。</p>
    </div>

    <el-card>
      <div class="toolbar-row logs-toolbar">
        <el-segmented v-model="source" :options="sourceOptions" @change="changeSource" />
        <el-tag :type="polling ? 'success' : 'info'">{{ polling ? '自动刷新中' : '已暂停' }}</el-tag>
        <el-button @click="pausePolling" :disabled="!polling">暂停</el-button>
        <el-button type="primary" plain @click="resumePolling" :disabled="polling">继续</el-button>
        <el-button type="danger" plain @click="clearView">清空视图</el-button>
      </div>
    </el-card>

    <el-card>
      <el-alert v-if="errorText" :title="errorText" type="error" show-icon :closable="false" style="margin-bottom: 12px" />
      <div ref="logContainer" class="logs-console" @scroll="handleScroll">
        <div v-if="logs.length === 0" class="logs-empty">{{ emptyText }}</div>
        <div v-for="item in logs" :key="`${item.timestamp}-${item.message}`" class="log-line" :class="`log-${item.level}`">
          <span class="log-time">{{ formatTimestamp(item.timestamp) }}</span>
          <span class="log-source">[{{ item.source }}]</span>
          <span class="log-message">{{ item.message }}</span>
        </div>
      </div>
      <div class="logs-status-bar">
        <span>当前显示：{{ logs.length }} 条</span>
        <span>最近更新时间：{{ lastUpdatedAt || '-' }}</span>
        <span>轮询间隔：{{ pollMs }}ms</span>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchRecentLogs } from '@/api/modules/logs'
import type { LogItem } from '@/types'

const source = ref<'task' | 'service' | 'all'>('all')
const logs = ref<LogItem[]>([])
const loading = ref(false)
const polling = ref(true)
const errorText = ref('')
const nextSince = ref<string | undefined>()
const lastUpdatedAt = ref('')
const logContainer = ref<HTMLElement | null>(null)
const autoFollow = ref(true)
const pollMs = 1500
const sourceOptions = [
  { label: '全部', value: 'all' },
  { label: '任务日志', value: 'task' },
  { label: '服务日志', value: 'service' },
]
let timer: number | undefined

const emptyText = computed(() => {
  if (source.value === 'task') return '当前暂无任务日志'
  if (source.value === 'service') return '当前暂无服务日志'
  return '当前暂无日志'
})

function formatTimestamp(value: string) {
  return new Date(value).toLocaleTimeString('zh-CN', { hour12: false })
}

function handleScroll() {
  const element = logContainer.value
  if (!element) return
  const threshold = 24
  autoFollow.value = element.scrollHeight - element.scrollTop - element.clientHeight <= threshold
}

function scrollToBottom() {
  const element = logContainer.value
  if (!element || !autoFollow.value) return
  element.scrollTop = element.scrollHeight
}

async function refreshLogs(reset = false) {
  loading.value = true
  try {
    const response = await fetchRecentLogs({
      source: source.value,
      limit: reset ? 200 : 100,
      since: reset ? undefined : nextSince.value,
    })
    logs.value = reset ? response.items : [...logs.value, ...response.items].slice(-500)
    nextSince.value = response.next_since || nextSince.value
    lastUpdatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    errorText.value = ''
    await nextTick()
    scrollToBottom()
  } catch {
    errorText.value = '日志拉取失败'
  } finally {
    loading.value = false
  }
}

function startPolling() {
  stopPolling()
  timer = window.setInterval(() => {
    if (polling.value) {
      void refreshLogs(false)
    }
  }, pollMs)
}

function stopPolling() {
  if (timer) {
    window.clearInterval(timer)
    timer = undefined
  }
}

function pausePolling() {
  polling.value = false
}

function resumePolling() {
  polling.value = true
  void refreshLogs(false)
}

function clearView() {
  logs.value = []
}

async function changeSource() {
  nextSince.value = undefined
  await refreshLogs(true)
}

onMounted(async () => {
  await refreshLogs(true)
  startPolling()
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.logs-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.logs-console {
  height: 520px;
  overflow: auto;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 12px;
  padding: 14px;
  font-family: Consolas, Monaco, monospace;
}

.log-line {
  display: grid;
  grid-template-columns: 96px 72px 1fr;
  gap: 12px;
  padding: 4px 0;
  font-size: 13px;
}

.log-info {
  color: #dbeafe;
}

.log-warning {
  color: #fde68a;
}

.log-error {
  color: #fca5a5;
}

.logs-empty {
  color: #94a3b8;
  text-align: center;
  padding: 180px 0;
}

.logs-status-bar {
  display: flex;
  gap: 20px;
  margin-top: 12px;
  color: #5b6b7f;
  font-size: 12px;
}

.log-time,
.log-source {
  opacity: 0.8;
}

.log-message {
  word-break: break-word;
}
</style>
