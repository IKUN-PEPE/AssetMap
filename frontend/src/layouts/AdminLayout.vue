<template>
  <el-container class="layout-container">
    <el-aside width="220px" class="sidebar">
      <div class="logo">AssetMap</div>
      <el-menu
        :default-active="activePath"
        class="menu"
        background-color="transparent"
        text-color="#41556b"
        active-text-color="#355caa"
        router
      >
        <el-menu-item index="/">仪表盘</el-menu-item>
        <el-menu-item index="/jobs">采集任务</el-menu-item>
        <el-menu-item index="/assets">资产列表</el-menu-item>
        <el-menu-item index="/selections">选择集</el-menu-item>
        <el-menu-item index="/reports">报告中心</el-menu-item>
        <el-menu-item index="/system">系统配置</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">AssetMap 管理后台</el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activePath = computed(() => route.path)
</script>

<style scoped>
.layout-container {
  min-height: 100vh;
  background: var(--app-bg);
}

.sidebar {
  background: var(--app-sidebar);
  border-right: 1px solid var(--app-border);
  color: var(--app-text);
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  color: var(--app-text);
  border-bottom: 1px solid var(--app-border);
  background: rgba(255, 255, 255, 0.35);
}

.menu {
  border-right: none;
  padding: 12px 10px;
}

.menu :deep(.el-menu-item) {
  margin-bottom: 6px;
  border-radius: 10px;
}

.menu :deep(.el-menu-item:hover) {
  background: var(--app-sidebar-hover);
}

.menu :deep(.el-menu-item.is-active) {
  background: var(--app-primary-soft);
  color: var(--app-primary);
  font-weight: 600;
}

.header {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--app-border);
  color: var(--app-text);
  font-weight: 600;
  display: flex;
  align-items: center;
}

.main-content {
  background: var(--app-bg);
}
</style>
