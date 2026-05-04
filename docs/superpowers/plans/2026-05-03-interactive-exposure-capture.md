# 交互式线索捕获 (Interactive Exposure Capture) 执行计划

> **对于 AI 代理：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步实现。步骤使用复选框 (`- [ ]`) 语法进行跟踪。

**目标：** 在 Playwright 窗口中注入一个交互式工具栏，允许用户通过点击网页链接实时将发现的线索（如 PDF、代码、敏感 URL）保存到 AssetMap 数据库。

**架构：**
- **前端注入**：一个原生的 JavaScript 脚本，通过 Playwright 注入到所有加载的页面。
- **双向通信**：利用 `expose_function` 实现 JS 到 Python 的 RPC 调用。
- **后端持久化**：实时响应点击事件，将元数据写入 `ExposureSearchResult` 记录。

**技术栈：** Playwright (JavaScript injection), FastAPI (Backend), SQLAlchemy.

---

### 任务 1：编写 Discovery JS 注入脚本

**文件：**
- 新增：`backend/app/services/exposure_search/discovery_script.js`

- [x] **步骤 1：实现工具栏 UI 渲染逻辑**
- [x] **步骤 2：实现高亮与点击拦截逻辑**
- [x] **步骤 3：实现 Toast 通知组件**
- [x] **步骤 4：提交代码** (已由系统恢复)

---

### 任务 2：升级 Playwright 客户端以支持注入

**文件：**
- 修改：`backend/app/services/exposure_search/playwright_client.py`

- [x] **步骤 1：编写加载 JS 脚本的辅助函数**
- [x] **步骤 2：在 `open_page` 中配置注入与 RPC 暴露**
- [x] **步骤 3：运行 Mock 注入测试**
- [x] **步骤 4：提交代码** (已由系统恢复)

---

### 任务 3：实现后端线索记录回调

**文件：**
- 修改：`backend/app/services/exposure_search/__init__.py`

- [x] **步骤 1：在 `ExposureSearchService` 中定义记录处理器**
- [x] **步骤 2：在 `run_task` 中绑定处理器到每个新页面**
- [x] **步骤 3：编写集成测试**
- [x] **步骤 4：提交代码** (已由系统恢复)

---

### 任务 4：最终端到端验证与 UI 优化

- [x] **步骤 1：重启服务并创建“窗口交互”任务**
- [x] **步骤 2：测试“点选”记录功能**
- [x] **步骤 3：优化工具栏样式与兼容性**
- [x] **步骤 4：完成并合并**
