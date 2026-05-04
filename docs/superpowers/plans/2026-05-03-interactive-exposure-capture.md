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

- [ ] **步骤 1：实现工具栏 UI 渲染逻辑**
编写 JS 代码，创建一个固定在页面顶部的控制条，包含“采集模式”开关和计数器。
- [ ] **步骤 2：实现高亮与点击拦截逻辑**
添加 `mouseover` 监听器实现蓝色虚线边框；添加 `click` 监听器，若采集开启则拦截并调用全局函数 `__am_record_clue`。
- [ ] **步骤 3：实现 Toast 通知组件**
在 JS 中实现一个简单的弹窗，提供“记录成功”的视觉反馈。
- [ ] **步骤 4：提交代码**
```bash
git add backend/app/services/exposure_search/discovery_script.js
git commit -m "feat(osint): implement discovery injection script"
```

---

### 任务 2：升级 Playwright 客户端以支持注入

**文件：**
- 修改：`backend/app/services/exposure_search/playwright_client.py`

- [ ] **步骤 1：编写加载 JS 脚本的辅助函数**
读取 `discovery_script.js` 的内容。
- [ ] **步骤 2：在 `open_page` 中配置注入与 RPC 暴露**
在 `page.goto` 之前调用 `page.add_init_script` 注入脚本；调用 `page.expose_function` 绑定后端回调。
- [ ] **步骤 3：运行 Mock 注入测试**
使用 `pytest` 模拟浏览器启动，验证脚本是否被正确添加到 `context` 初始化配置中。
- [ ] **步骤 4：提交代码**
```bash
git add backend/app/services/exposure_search/playwright_client.py
git commit -m "feat(osint): support JS injection and RPC bridge in PlaywrightClient"
```

---

### 任务 3：实现后端线索记录回调

**文件：**
- 修改：`backend/app/services/exposure_search/__init__.py`

- [ ] **步骤 1：在 `ExposureSearchService` 中定义记录处理器**
编写一个函数，接收来自 JS 的 JSON 数据，执行 URL 去重，并写入数据库。
- [ ] **步骤 2：在 `run_task` 中绑定处理器到每个新页面**
确保每个 Provider 打开的页面都正确关联了该记录函数。
- [ ] **步骤 3：编写集成测试**
手动在测试代码中执行 `page.evaluate("__am_record_clue({...})")`，验证数据库中是否出现了状态为 `valid` 的结果。
- [ ] **步骤 4：提交代码**
```bash
git add backend/app/services/exposure_search/__init__.py
git commit -m "feat(osint): implement backend handler for manual clue recording"
```

---

### 任务 4：最终端到端验证与 UI 优化

- [ ] **步骤 1：重启服务并创建“窗口交互”任务**
验证在弹出的浏览器中，工具栏是否出现。
- [ ] **步骤 2：测试“点选”记录功能**
点击一个 PDF 链接，验证 AssetMap 系统的“查看结果”抽屉中是否实时出现了该条目。
- [ ] **步骤 3：优化工具栏样式与兼容性**
确保工具栏在不同背景色的网页上（如百度 vs GitHub）均清晰可见。
- [ ] **步骤 4：完成并合并**
