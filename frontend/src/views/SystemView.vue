<template>
  <div class="page-shell">
    <div class="page-header">
      <h1 class="page-title">系统配置中心</h1>
      <p class="page-subtitle">管理各采集平台 API Key、本地工具路径及全局运行参数。</p>
    </div>

    <div v-loading="loading" class="config-container">
      <el-tabs v-model="activeTab" tab-position="left" class="config-tabs">
        
        <!-- 全局运行配置 -->
        <el-tab-pane label="全局配置" name="system">
          <el-card shadow="never" class="config-card">
            <template #header><div class="card-header">全局运行配置</div></template>
            <el-form label-position="top">
              <el-row :gutter="20">
                <el-col :xs="24" :sm="12"><el-form-item label="数据输出目录"><el-input v-model="configMap.data_output_dir" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="截图输出目录"><el-input v-model="configMap.screenshot_output_dir" /></el-form-item></el-col>
                <el-col :xs="12" :sm="6"><el-form-item label="资产自动去重"><el-switch v-model="configMap.auto_dedup" active-value="true" inactive-value="false" /></el-form-item></el-col>
                <el-col :xs="12" :sm="6"><el-form-item label="自动写入列表"><el-switch v-model="configMap.auto_import" active-value="true" inactive-value="false" /></el-form-item></el-col>
              </el-row>
            </el-form>
          </el-card>
        </el-tab-pane>

        <!-- FOFA -->
        <el-tab-pane label="FOFA" name="fofa">
          <el-card shadow="never" class="config-card">
            <template #header>
              <div class="card-header">
                <span>FOFA 平台配置</span>
                <el-button type="primary" link @click="testConnection('fofa')">测试连接</el-button>
              </div>
            </template>
            <el-form label-position="top">
              <el-row :gutter="20">
                <el-col :xs="24" :sm="12"><el-form-item label="FOFA Email"><el-input v-model="configMap.fofa_email" placeholder="请输入注册邮箱" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="FOFA API Key"><el-input v-model="configMap.fofa_key" type="password" show-password placeholder="请输入 API Key" @focus="revealSensitiveConfig('fofa_key')" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="默认每页数量"><el-input-number v-model="configMap.fofa_page_size" :min="1" :max="1000" style="width: 100%" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="默认最大页数"><el-input-number v-model="configMap.fofa_max_pages" :min="1" :max="100" style="width: 100%" /></el-form-item></el-col>
                <el-col :span="24"><el-form-item label="Base URL"><el-input v-model="configMap.fofa_base_url" placeholder="可留空使用默认值" /></el-form-item></el-col>
              </el-row>
            </el-form>
          </el-card>
        </el-tab-pane>
        
        <!-- 鹰图 Hunter -->
        <el-tab-pane label="鹰图" name="hunter">
          <el-card shadow="never" class="config-card">
            <template #header>
              <div class="card-header">
                <span>鹰图 (Hunter) 平台配置</span>
                <el-button type="primary" link @click="testConnection('hunter')">测试连接</el-button>
              </div>
            </template>
            <el-form label-position="top">
              <el-row :gutter="20">
                <el-col :xs="24" :sm="12"><el-form-item label="Hunter 用户名 / 邮箱"><el-input v-model="configMap.hunter_username" placeholder="请输入用户名或邮箱" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="Hunter API Key"><el-input v-model="configMap.hunter_api_key" type="password" show-password placeholder="请输入 API Key" @focus="revealSensitiveConfig('hunter_api_key')" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="默认每页数量"><el-input-number v-model="configMap.hunter_page_size" :min="1" :max="100" style="width: 100%" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="默认最大页数"><el-input-number v-model="configMap.hunter_max_pages" :min="1" :max="100" style="width: 100%" /></el-form-item></el-col>
                <el-col :span="24"><el-form-item label="Base URL"><el-input v-model="configMap.hunter_base_url" placeholder="可留空使用默认值" /></el-form-item></el-col>
              </el-row>
            </el-form>
          </el-card>
        </el-tab-pane>

        <!-- ZoomEye -->
        <el-tab-pane label="ZoomEye" name="zoomeye">
          <el-card shadow="never" class="config-card">
            <template #header>
              <div class="card-header">
                <span>ZoomEye 平台配置</span>
                <el-button type="primary" link @click="testConnection('zoomeye')">测试连接</el-button>
              </div>
            </template>
            <el-form label-position="top">
              <el-row :gutter="20">
                <el-col :span="24"><el-form-item label="ZoomEye API Key"><el-input v-model="configMap.zoomeye_api_key" type="password" show-password placeholder="请输入 API Key" @focus="revealSensitiveConfig('zoomeye_api_key')" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="默认每页数量"><el-input-number v-model="configMap.zoomeye_page_size" :min="1" :max="1000" style="width: 100%" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="默认最大页数 (免费版仅支持1页)"><el-input-number v-model="configMap.zoomeye_max_pages" :min="1" :max="100" style="width: 100%" /></el-form-item></el-col>
                <el-col :span="24"><el-form-item label="Base URL"><el-input v-model="configMap.zoomeye_base_url" placeholder="可留空使用默认值" /></el-form-item></el-col>
              </el-row>
            </el-form>
          </el-card>
        </el-tab-pane>
        
        <!-- Quake -->
        <el-tab-pane label="Quake" name="quake">
          <el-card shadow="never" class="config-card">
            <template #header>
              <div class="card-header">
                <span>Quake 平台配置</span>
                <el-button type="primary" link @click="testConnection('quake')">测试连接</el-button>
              </div>
            </template>
            <el-form label-position="top">
              <el-row :gutter="20">
                <el-col :span="24"><el-form-item label="Quake API Key"><el-input v-model="configMap.quake_api_key" type="password" show-password placeholder="请输入 API Key" @focus="revealSensitiveConfig('quake_api_key')" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="默认每页数量"><el-input-number v-model="configMap.quake_page_size" :min="1" :max="100" style="width: 100%" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="默认最大页数"><el-input-number v-model="configMap.quake_max_pages" :min="1" :max="100" style="width: 100%" /></el-form-item></el-col>
                <el-col :span="24"><el-form-item label="Base URL"><el-input v-model="configMap.quake_base_url" placeholder="可留空使用默认值" /></el-form-item></el-col>
              </el-row>
            </el-form>
          </el-card>
        </el-tab-pane>

        <!-- OneForAll -->
        <el-tab-pane label="OneForAll" name="oneforall">
          <el-card shadow="never" class="config-card">
            <template #header>
              <div class="card-header">
                <span>OneForAll 工具配置</span>
                <el-button type="primary" link @click="testConnection('oneforall')">检查路径</el-button>
              </div>
            </template>
            <el-form label-position="top">
               <el-row :gutter="20">
                <el-col :xs="24" :sm="12"><el-form-item label="OneForAll.py 绝对路径"><el-input v-model="configMap.oneforall_path" placeholder="例如: /usr/local/OneForAll/oneforall.py" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="Python 解释器路径"><el-input v-model="configMap.python_path" placeholder="例如: /usr/bin/python3" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="默认线程数"><el-input-number v-model="configMap.oneforall_threads" :min="1" :max="100" style="width: 100%" /></el-form-item></el-col>
                <el-col :xs="24" :sm="12"><el-form-item label="默认超时(秒)"><el-input-number v-model="configMap.oneforall_timeout" :min="1" :max="300" style="width: 100%" /></el-form-item></el-col>
                 <el-col :span="24"><el-form-item label="输出目录"><el-input v-model="configMap.oneforall_output_dir" placeholder="OneForAll 结果输出目录" /></el-form-item></el-col>
              </el-row>
              <p class="tips">提示：请确保本地已安装相关依赖并可通过上述路径调用。</p>
            </el-form>
          </el-card>
        </el-tab-pane>

      </el-tabs>

      <div class="actions mt-4">
        <el-button type="primary" size="large" round @click="handleSave" :loading="saving">保存所有配置</el-button>
        <el-button size="large" round @click="loadConfigs">重置所有修改</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  initSystemConfigs,
  listSystemConfigs,
  testSystemConnection,
  updateSystemConfigs,
} from '@/api/modules/system'
import type { SystemConfig, SystemConfigItem } from '@/types'

const loading = ref(true)
const saving = ref(false)
const activeTab = ref('system')
const configMap = reactive<SystemConfig>({})

const numKeys = [
  'fofa_page_size',
  'fofa_max_pages',
  'hunter_page_size',
  'hunter_max_pages',
  'zoomeye_page_size',
  'zoomeye_max_pages',
  'oneforall_threads',
  'oneforall_timeout',
  'quake_page_size',
  'quake_max_pages',
]

function applyConfigItems(items: SystemConfigItem[]) {
  Object.keys(configMap).forEach((key) => delete configMap[key])
  items.forEach((item) => {
    if (numKeys.includes(item.config_key)) {
      configMap[item.config_key] = Number(item.config_value)
    } else {
      configMap[item.config_key] = item.config_value
    }
  })
}

async function loadConfigs(revealSensitive = false) {
  loading.value = true
  try {
    const data = await listSystemConfigs(revealSensitive)
    applyConfigItems(data)
  } catch (error: any) {
    if (error.response?.status === 404) {
      ElMessage.info('未找到配置，正在尝试初始化...')
      await initSystemConfigs()
      await loadConfigs(revealSensitive)
    } else {
      ElMessage.error('加载配置失败: ' + (error.response?.data?.detail || error.message))
    }
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    await updateSystemConfigs(configMap)
    ElMessage.success('配置已保存')
    await loadConfigs()
  } catch (error: any) {
    const msg =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      (typeof error.response?.data === 'string' ? error.response.data : error.message)
    ElMessage.error('保存失败: ' + (msg ? String(msg) : '未知错误'))
  } finally {
    saving.value = false
  }
}

async function revealSensitiveConfig(key: string) {
  try {
    await loadConfigs(true)
    if (!configMap[key] || configMap[key] === '******') {
      ElMessage.warning('未读取到真实配置值')
    }
  } catch {
    ElMessage.error('读取真实配置失败')
  }
}

async function testConnection(platform: string) {
  const loadingInstance = ElMessage({
    message: `正在测试 ${platform} 连接...`,
    type: 'info',
    duration: 0,
  })

  try {
    const relevantConfigs: Record<string, any> = {}
    Object.keys(configMap).forEach((key) => {
      if (key.startsWith(platform)) {
        relevantConfigs[key] = configMap[key]
      }
    })

    const data = await testSystemConnection({
      platform,
      config: relevantConfigs,
    })

    loadingInstance.close()

    if (data.success) {
      ElMessageBox.alert('连接测试成功！', '提示', { type: 'success' })
    } else {
      ElMessageBox.alert(`连接测试失败: ${data.error || '未知错误'}`, '错误', { type: 'error' })
    }
  } catch (error: any) {
    loadingInstance.close()
    ElMessageBox.alert(`接口调用失败: ${error.response?.data?.detail || error.message}`, '错误', { type: 'error' })
  }
}

onMounted(loadConfigs)
</script>

<style scoped lang="scss">
.config-container {
  max-width: 1200px;
}
.config-tabs {
  min-height: 400px;
}
.config-card {
  border: none;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 1.1em;
}
.tips {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 8px;
}
.actions {
  display: flex;
  gap: 15px;
  justify-content: center;
  padding: 20px 0;
}
.mt-4 { margin-top: 20px; }
</style>
