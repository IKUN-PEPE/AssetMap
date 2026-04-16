<template>
  <div class="page-shell dashboard-page">
    <div class="page-header">
      <h1 class="page-title">安全运营分析中心</h1>
      <p class="page-subtitle">实时监控资产态势、验证效能及风险分布。</p>
    </div>

    <!-- 顶部 KPI 卡片区 -->
    <el-row :gutter="20" class="stat-row">
      <el-col :span="6" v-for="item in kpiList" :key="item.title">
        <div class="kpi-card" :class="item.color">
          <div class="kpi-icon">
            <el-icon><component :is="item.icon" /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-label">{{ item.title }}</div>
            <div class="kpi-value">{{ item.value }}</div>
          </div>
          <div class="kpi-badge" v-if="item.trend">{{ item.trend }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- 图表展示区 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="12">
        <el-card class="chart-card">
          <template #header>
            <div class="card-header">
              <span>资产来源分布</span>
              <el-tag size="small" type="info">实时更新</el-tag>
            </div>
          </template>
          <v-chart class="chart-box" :option="sourceOption" autoresize />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="chart-card">
          <template #header>
            <div class="card-header">
              <span>自动化验证状态</span>
              <el-tag size="small" type="success">验证中</el-tag>
            </div>
          </template>
          <v-chart class="chart-box" :option="verifyOption" autoresize />
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势分析区 -->
    <el-row class="trend-row">
      <el-col :span="24">
        <el-card class="chart-card full-width">
          <template #header>资产发现趋势（7日累积）</template>
          <v-chart class="chart-box main-trend" :option="trendOption" autoresize />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import { Monitor, Plus, Aim, Warning } from '@element-plus/icons-vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, BarChart, LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
} from 'echarts/components'
import VChart from 'vue-echarts'

// 注册 ECharts 组件
use([
  CanvasRenderer,
  PieChart,
  BarChart,
  LineChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
])

const kpiData = ref({ total: 0, today: 0, rate: 78, critical: 0 })
const sourceData = ref<{ name: string; value: number }[]>([])
const verifyData = ref<{ name: string; value: number }[]>([])
const trendData = ref({ dates: [], data: [] })

const kpiList = computed(() => [
  { title: '资产总额', value: kpiData.value.total, icon: Monitor, color: 'blue' },
  { title: '今日新增', value: kpiData.value.today, icon: Plus, color: 'green', trend: '+5%' },
  { title: '资产发现率', value: kpiData.value.rate + '%', icon: Aim, color: 'purple' },
  { title: '风险资产', value: kpiData.value.critical, icon: Warning, color: 'red' }
])

// ECharts 配置项 (类苹果红黑主题风格)
const sourceOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'item' },
  legend: { bottom: '0', icon: 'circle', textStyle: { color: '#94a3b8' } },
  series: [{
    name: '来源分布',
    type: 'pie',
    radius: ['45%', '75%'],
    avoidLabelOverlap: false,
    itemStyle: {
      borderRadius: 10,
      borderColor: 'transparent',
      borderWidth: 2
    },
    label: { show: false },
    data: sourceData.value.length ? sourceData.value : [{ name: '暂无数据', value: 0 }],
    color: ['#3b82f6', '#ef4444', '#8b5cf6', '#10b981', '#f59e0b']
  }]
}))

const verifyOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' },
  grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
  xAxis: {
    type: 'category',
    data: verifyData.value.map(i => i.name),
    axisLine: { lineStyle: { color: '#334155' } },
    axisLabel: { color: '#94a3b8' }
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
    axisLabel: { color: '#94a3b8' }
  },
  series: [{
    data: verifyData.value.map(i => i.value),
    type: 'bar',
    barWidth: '40%',
    itemStyle: {
      color: {
        type: 'linear',
        x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: '#3b82f6' },
          { offset: 1, color: '#1d4ed8' }
        ]
      },
      borderRadius: [6, 6, 0, 0]
    }
  }]
}))

const trendOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' },
  grid: { left: '3%', right: '4%', bottom: '5%', top: '10%', containLabel: true },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: trendData.value.dates,
    axisLine: { lineStyle: { color: '#334155' } },
    axisLabel: { color: '#94a3b8' }
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
    axisLabel: { color: '#94a3b8' }
  },
  series: [{
    name: '累积发现资产',
    data: trendData.value.data,
    type: 'line',
    smooth: true,
    showSymbol: false,
    lineStyle: { width: 4, color: '#3b82f6' },
    areaStyle: {
      color: {
        type: 'linear',
        x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(59, 130, 246, 0.3)' },
          { offset: 1, color: 'rgba(59, 130, 246, 0)' }
        ]
      }
    }
  }]
}))

onMounted(async () => {
  const base = 'http://127.0.0.1:9527/api/v1/stats'
  try {
    const [ov, dist, tr] = await Promise.all([
      axios.get(`${base}/overview`),
      axios.get(`${base}/distribution`),
      axios.get(`${base}/trends`)
    ])
    kpiData.value = ov.data
    sourceData.value = dist.data.sources
    verifyData.value = dist.data.verify
    trendData.value = tr.data
  } catch (e) {
    console.error('Stats loading failed', e)
    // 降级显示模拟数据以保持界面完整
    kpiData.value = { total: 0, today: 0, rate: 0, critical: 0 }
  }
})
</script>

<style scoped>
.dashboard-page { padding-bottom: 20px; }
.stat-row { margin-bottom: 24px; }
.kpi-card {
  background: var(--app-card-bg);
  border: 1px solid var(--app-border);
  padding: 24px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  position: relative;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.kpi-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--app-shadow-lg);
}
.kpi-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 18px;
  font-size: 24px;
}
.kpi-card.blue .kpi-icon { background: rgba(59, 130, 246, 0.1); color: #3b82f6; }
.kpi-card.green .kpi-icon { background: rgba(16, 185, 129, 0.1); color: #10b981; }
.kpi-card.purple .kpi-icon { background: rgba(139, 92, 246, 0.1); color: #8b5cf6; }
.kpi-card.red .kpi-icon { background: rgba(239, 68, 68, 0.1); color: #ef4444; }

.kpi-label { font-size: 14px; color: var(--app-text-dim); margin-bottom: 4px; }
.kpi-value { font-size: 30px; font-weight: 850; color: var(--app-text-main); letter-spacing: -1px; }

.kpi-badge {
  position: absolute;
  top: 16px;
  right: 16px;
  padding: 2px 8px;
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.chart-card { border-radius: 16px !important; margin-bottom: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 700; }

.chart-box { height: 320px; width: 100%; }
.main-trend { height: 360px; }

/* 配合暗黑模式微调图表内边距 */
:deep(.el-card__header) { padding: 18px 24px !important; border-bottom: 1px solid var(--app-border) !important; }
</style>
