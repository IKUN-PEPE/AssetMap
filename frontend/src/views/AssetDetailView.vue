<template>
  <el-card>
    <template #header>资产详情</template>
    <el-descriptions v-if="asset" :column="1" border>
      <el-descriptions-item label="ID">{{ asset.id }}</el-descriptions-item>
      <el-descriptions-item label="URL">{{ asset.normalized_url }}</el-descriptions-item>
      <el-descriptions-item label="标题">{{ asset.title }}</el-descriptions-item>
      <el-descriptions-item label="状态码">{{ asset.status_code }}</el-descriptions-item>
      <el-descriptions-item label="截图状态">{{ asset.screenshot_status }}</el-descriptions-item>
      <el-descriptions-item label="标签状态">{{ asset.label_status }}</el-descriptions-item>
      <el-descriptions-item label="验证失败原因">{{ asset.verify_error || '-' }}</el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { fetchAssetDetail } from '@/api/modules/assets'
import type { AssetItem } from '@/types'

const route = useRoute()
const asset = ref<AssetItem | null>(null)

onMounted(async () => {
  asset.value = await fetchAssetDetail(String(route.params.id))
})
</script>
