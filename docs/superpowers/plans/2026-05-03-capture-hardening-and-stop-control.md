# 交互式采集加固与任务控制执行计划

> **对于 AI 代理：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步实现。步骤使用复选框 (`- [ ]`) 语法进行跟踪。

**目标：** 实现采集模式默认开启、布局锁定（防止遮挡）、点击记录后正常跳转，并增加“停止任务”功能以立即终止所有后台进程。

**架构：**
- **JS 加固**：升级注入脚本，移除点击拦截，增加 `MutationObserver` 锁定布局。
- **任务控制**：在 API 层增加 `/stop` 接口，在服务层增加状态位检查以实现即时退出。
- **状态管理**：引入 `stopped` 状态，确保数据在强制终止前已持久化。

---

### 任务 1：升级 Discovery JS 脚本 (交互与布局加固)

**文件：**
- 修改：`backend/app/services/exposure_search/discovery_script.js`

- [ ] **步骤 1：修改初始化状态与点击逻辑**
将 `captureModeActive` 默认设为 `true`。移除 `click` 监听器中的 `e.preventDefault()`，改为记录后允许事件冒泡。
- [ ] **步骤 2：实现布局锁定逻辑**
使用 `MutationObserver` 监听 `body` 的样式变化，强制保持 `margin-top: 50px !important`。
- [ ] **步骤 3：提交代码**
```bash
git add backend/app/services/exposure_search/discovery_script.js
git commit -m "feat(osint): default capture ON, non-blocking navigation, and layout locking"
```

---

### 任务 2：实现“停止任务”后端接口与逻辑

**文件：**
- 修改：`backend/app/api/exposure_search.py`
- 修改：`backend/app/services/exposure_search/__init__.py`

- [ ] **步骤 1：新增 `/stop` API 接口**
实现 `POST /api/v1/exposure-search/tasks/{task_id}/stop`，将数据库中的任务状态更新为 `stopping`。
- [ ] **步骤 2：在服务执行循环中增加退出检查**
在 `run_task` 的循环（每一个 Dork 查询前后）增加对状态位的检查。若状态为 `stopping` 或已被外部修改，则立即 `break` 循环并清理资源。
- [ ] **步骤 3：实现资源强制清理**
确保在停止时调用 `pw_client.stop()`，并写回最终的 `total_results`。
- [ ] **步骤 4：提交代码**
```bash
git add backend/app/
git commit -m "feat(osint): implement stop task API and service-level termination"
```

---

### 任务 3：前端集成停止功能

**文件：**
- 修改：`frontend/src/api/modules/exposureSearch.ts`
- 修改：`frontend/src/views/ExposureSearchView.vue`

- [ ] **步骤 1：定义停止 API 映射**
- [ ] **步骤 2：在任务列表增加“停止”按钮**
仅在任务状态为 `running` 时显示。点击后触发 `/stop` 请求并刷新列表。
- [ ] **步骤 3：运行 `npm run build` 验证构建**
- [ ] **步骤 4：提交代码**
```bash
git add frontend/
git commit -m "feat(ui): add stop button to exposure search tasks"
```

---

### 任务 4：最终端到端验证

- [ ] **步骤 1：验证默认采集模式**
创建任务，观察浏览器弹窗中工具栏是否默认开启且点击后网页是否正常跳转。
- [ ] **步骤 2：测试强制停止**
启动一个长任务，在 AssetMap 后台点击停止，观察浏览器窗口是否立即关闭，且已捕获数据是否保留。
- [ ] **步骤 3：提交所有最终微调**
