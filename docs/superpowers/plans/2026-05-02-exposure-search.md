# 暴露面搜索 (Exposure Search) 执行计划

> **对于 AI 代理：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步实现。步骤使用复选框 (`- [ ]`) 语法进行跟踪。

**目标：** 在 AssetMap 中构建一个稳健的“暴露面搜索”模块，用于通过搜索引擎和 GitHub 发现公开暴露线索（OSINT），并提供安全的“审核后导入”工作流。

**架构：** 采用基于 Provider 的服务层，使用 Playwright 提取元数据；实现具有并发限制的任务运行器；建立独立的“线索”存储系统，将原始发现与已验证的资产库分离。最终导入阶段复用标准的 `save_assets` 逻辑。

**技术栈：** FastAPI, SQLAlchemy (PostgreSQL/SQLite), Playwright (Chromium), Vue 3, Element Plus。

---

### 任务 1：数据模型与数据库模式

**文件：**
- 新增：`backend/app/models/exposure_search.py`
- 修改：`backend/app/models/__init__.py`
- 修改：`backend/app/models/asset.py`, `backend/app/models/job.py`, `backend/app/models/support.py` (JSONB -> JSON 迁移)

- [x] **步骤 1：编写模型持久化失败测试**
- [x] **步骤 2：运行测试以验证失败**
- [x] **步骤 3：定义模型并统一 JSON 类型以确保兼容性**
- [x] **步骤 4：运行测试以验证通过**
- [x] **步骤 5：提交代码**

---

### 任务 2：统一 Playwright 客户端与查询构建器

**文件：**
- 新增：`backend/app/services/exposure_search/playwright_client.py`
- 新增：`backend/app/services/exposure_search/query_builder.py`
- 新增：`backend/app/services/exposure_search/risk_classifier.py`

- [x] **步骤 1：为查询构建器和风险分类器编写测试**
- [x] **步骤 2：实现具有  / 登录检测功能的 `PlaywrightClient`**
- [x] **步骤 3：实现用于生成 Dork 语法的 `QueryBuilder`**
- [x] **步骤 4：实现用于元数据标记的 `RiskClassifier`**
- [x] **步骤 5：验证所有工具类测试通过**
- [x] **步骤 6：提交代码**

---

### 任务 3：搜索引擎 Provider 实现 (Bing, 百度, GitHub, Google)

**文件：**
- 新增：`backend/app/services/exposure_search/providers/base.py`
- 新增：`backend/app/services/exposure_search/providers/bing.py`
- 新增：`backend/app/services/exposure_search/providers/baidu.py`
- 新增：`backend/app/services/exposure_search/providers/github.py`
- 新增：`backend/app/services/exposure_search/providers/google.py`

- [x] **步骤 1：定义 `ExposureSearchProvider` 接口**
- [x] **步骤 2：实现具有兜底选择器的 Bing 和百度爬虫**
- [x] **步骤 3：实现 GitHub 代码搜索爬虫**
- [x] **步骤 4：实现具有风控检测功能的 Google 爬虫**
- [x] **步骤 5：编写 Mock Provider 测试以验证元数据提取逻辑**
- [x] **步骤 6：提交代码**

---

### 任务 4：暴露面搜索任务运行器 (服务编排)

**文件：**
- 修改：`backend/app/services/exposure_search/__init__.py`

- [x] **步骤 1：实现带并发限制的 `ExposureSearchService.run_task`**
- [x] **步骤 2：实现状态回写和结果去重逻辑**
- [x] **步骤 3：提交代码**

---

### 任务 5：API 接口与导入逻辑

**文件：**
- 新增：`backend/app/api/exposure_search.py`
- 修改：`backend/app/api/router.py`

- [x] **步骤 1：实现任务和结果的 CRUD 接口**
- [x] **步骤 2：实现 `confirm-import` 导入逻辑**
- [x] **步骤 3：编写 API 集成测试**
- [x] **步骤 4：提交代码**

---

### 任务 6：前端集成 (Vue 3 + Element Plus)

**文件：**
- 新增：`frontend/src/api/modules/exposureSearch.ts`
- 新增：`frontend/src/views/ExposureSearchView.vue`
- 修改：`frontend/src/router/index.ts`, `frontend/src/layouts/AdminLayout.vue`

- [x] **步骤 1：定义前端 API 模块**
- [x] **步骤 2：构建包含任务管理和结果抽屉的 `ExposureSearchView.vue`**
- [x] **步骤 3：注册路由和侧边菜单项**
- [x] **步骤 4：运行 `vue-tsc` 和 `npm run build` 验证生产环境构建**
- [x] **步骤 5：提交代码**

---

### 任务 7：最终验证与安全检查

- [x] **步骤 1：运行所有后端测试**
执行：`pytest backend/tests`
- [x] **步骤 2：验证 `init_db.py` 在干净环境下正常工作**
- [x] **步骤 3：针对组织关键词进行手动的端到端搜索发现检查**
- [x] **步骤 4：提交所有最终微调**
