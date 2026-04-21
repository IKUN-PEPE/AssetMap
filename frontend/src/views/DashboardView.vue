<template>
  <div class="page-shell dashboard-page">
    <div class="page-header">
      <h1 class="page-title">安全运营分析中心</h1>
      <p class="page-subtitle">实时监控资产态势、验证效能及风险分布。</p>
    </div>

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
import { Monitor, Plus, Aim, Warning } from '@element-plus/icons-vue'
import { fetchStatsDistribution, fetchStatsOverview, fetchStatsTrends } from '@/api/modules/statistics'
import type {
  StatsDistributionItem,
  StatsOverview,
  StatsTrendsResponse,
} from '@/types'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, BarChart, LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'

use([
  CanvasRenderer,
  PieChart,
  BarChart,
  LineChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
])

const kpiData = ref<StatsOverview>({ total: 0, today: 0, rate: 78, critical: 0 })
const sourceData = ref<StatsDistributionItem[]>([])
const verifyData = ref<StatsDistributionItem[]>([])
const trendData = ref<StatsTrendsResponse>({ dates: [], data: [] })

const kpiList = computed(() => [
  { title: '资产总额', value: kpiData.value.total, icon: Monitor, color: 'blue' },
  { title: '今日新增', value: kpiData.value.today, icon: Plus, color: 'green', trend: '+5%' },
  { title: '资产发现率', value: kpiData.value.rate + '%', icon: Aim, color: 'purple' },
  { title: '风险资产', value: kpiData.value.critical, icon: Warning, color: 'red' },
])

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
      borderWidth: 2,
    },
    label: { show: false },
    data: sourceData.value.length ? sourceData.value : [{ name: '暂无数据', value: 0 }],
    color: ['#3b82f6', '#ef4444', '#8b5cf6', '#10b981', '#f59e0b'],
  }],
}))

const verifyOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' },
  grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
  xAxis: {
    type: 'category',
    data: verifyData.value.map((i: StatsDistributionItem) => i.name),
    axisLine: { lineStyle: { color: '#334155' } },
    axisLabel: { color: '#94a3b8' },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
    axisLabel: { color: '#94a3b8' },
  },
  series: [{
    data: verifyData.value.map((i: StatsDistributionItem) => i.value),
    type: 'bar',
    barWidth: '40%',
    itemStyle: {
      color: {
        type: 'linear',
        x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: '#3b82f6' },
          { offset: 1, color: '#1d4ed8' },
        ],
      },
      borderRadius: [6, 6, 0, 0],
    },
  }],
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
    axisLabel: { color: '#94a3b8' },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
    axisLabel: { color: '#94a3b8' },
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
          { offset: 1, color: 'rgba(59, 130, 246, 0)' },
        ],
      },
    },
  }],
}))

onMounted(async () => {
  try {
    const [ov, dist, tr] = await Promise.all([
      fetchStatsOverview(),
      fetchStatsDistribution(),
      fetchStatsTrends(),
    ])
    kpiData.value = ov
    sourceData.value = dist.sources
    verifyData.value = dist.verify
    trendData.value = tr
  } catch (e) {
    console.error('Stats loading failed', e)
    kpiData.value = { total: 0, today: 0, rate: 0, critical: 0 }
    sourceData.value = []
    verifyData.value = []
    trendData.value = { dates: [], data: [] }
  }
})
</script>

<style scoped>
.dashboard-page { padding-bottom: 20px; }
.stat-row { margin-bottom: 24px; }
.kpi-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 22px;
  border-radius: 20px;
  color: #fff;
  min-height: 120px;
}
.kpi-card.blue { background: linear-gradient(135deg, #1d4ed8, #3b82f6); }
.kpi-card.green { background: linear-gradient(135deg, #047857, #10b981); }
.kpi-card.purple { background: linear-gradient(135deg, #6d28d9, #8b5cf6); }
.kpi-card.red { background: linear-gradient(135deg, #b91c1c, #ef4444); }
.kpi-icon { font-size: 28px; opacity: 0.9; }
.kpi-label { font-size: 14px; opacity: 0.85; }
.kpi-value { font-size: 28px; font-weight: 700; margin-top: 6px; }
.kpi-badge {
  position: absolute;
  right: 18px;
  top: 18px;
  background: rgba(255,255,255,0.16);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
}
.chart-row, .trend-row { margin-top: 20px; }
.chart-card { border-radius: 18px; }
.chart-box { height: 360px; }
.main-trend { height: 420px; }
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
