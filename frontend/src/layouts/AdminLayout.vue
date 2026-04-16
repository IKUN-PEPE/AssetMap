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
        <el-menu-item index="/logs">实时日志</el-menu-item>
        <el-menu-item index="/system">系统配置</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-inner">
          <div class="header-left">AssetMap 管理后台</div>
          <div class="header-right">
            <el-button
              circle
              :icon="isDark ? Sunny : Moon"
              @click="toggleDark()"
              class="theme-toggle"
            />
          </div>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useDark, useToggle } from '@vueuse/core'
import { Moon, Sunny } from '@element-plus/icons-vue'

const route = useRoute()
const activePath = computed(() => route.path)

const isDark = useDark()
const toggleDark = useToggle(isDark)
</script>

<style scoped>
.layout-container {
  min-height: 100vh;
  background: var(--el-bg-color-page);
}

.sidebar {
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-light);
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  border-bottom: 1px solid var(--el-border-color-light);
}

.header {
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--app-border);
  color: var(--app-text-main);
  font-weight: 700;
  display: flex;
  align-items: center;
  padding: 0; /* 这里的内边距交给 inner 处理 */
  height: 64px;
}

.header-inner {
  width: 100%;
  margin: 0; /* 取消居中 */
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 40px; /* 同步 page-shell 的内边距 */
}

.header-right {
  display: flex;
  align-items: center;
}

.main-content {
  background: var(--el-bg-color-page);
  padding: 0 !important; /* 彻底移除 Main 的默认内边距 */
}
</style>
