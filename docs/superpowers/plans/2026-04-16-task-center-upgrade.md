# 资产采集与调度中心升级实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将资产导入升级为具备预览、映射、去重策略和 Huey 调度能力的中心。

**架构：** 引入 SQLite + Huey 处理异步任务，通过 SQLAlchemy JSONB 存储映射关系，前端采用轮询机制实现实时进度可视化。

**技术栈：** Python/FastAPI, huey, SQLAlchemy, Vue 3, Element Plus.

---

### 任务 1：Huey 基础架构搭建

**文件：**
- 修改：`backend/requirements.txt`
- 创建：`backend/app/core/huey.py`
- 修改：`backend/app/main.py`

- [ ] **步骤 1：安装依赖**
  - 添加 `huey==2.5.2` 到 `backend/requirements.txt`。
  - 运行 `pip install huey`。

- [ ] **步骤 2：初始化 Huey 实例**
  - 创建 `backend/app/core/huey.py`，配置使用 `SqliteHuey`。
  ```python
  from huey import SqliteHuey
  from app.core.config import BASE_DIR

  huey = SqliteHuey(filename=str(BASE_DIR / "huey_db.sqlite3"))
  ```

- [ ] **步骤 3：在 main.py 中集成（可选，仅用于日志确认）**
  - 确保 Worker 能够正确加载任务逻辑。

- [ ] **步骤 4：Commit**
  - `git add . && git commit -m "feat(task): setup huey infrastructure with sqlite backend"`

---

### 任务 2：模型扩展与数据库迁移

**文件：**
- 修改：`backend/app/models/job.py`
- 修改：`backend/app/schemas/job.py`

- [ ] **步骤 1：更新 CollectJob 模型**
  - 增加字段：`progress`, `success_count`, `failed_count`, `duplicate_count`, `total_count`, `dedup_strategy`, `field_mapping`, `auto_verify`。
- [ ] **步骤 2：更新 Pydantic Schema**
  - 对应增加 `CollectJobRead` 和 `CollectJobCreate` 的字段。
- [ ] **步骤 3：执行迁移/更新数据库**
  - 运行 `python backend/init_db.py`（视项目情况而定）。
- [ ] **步骤 4：Commit**
  - `git commit -m "feat(model): extend CollectJob model for detailed tracking"`

---

### 任务 3：后端核心：解析与预览 API

**文件：**
- 修改：`backend/app/api/jobs.py`
- 创建：`backend/app/services/collectors/preview.py`

- [ ] **步骤 1：实现 Preview 逻辑**
  - 创建预览服务，支持读取上传的 CSV 前 10 行。
- [ ] **步骤 2：添加预览接口**
  - `POST /api/v1/jobs/preview`：返回列名和前 10 行样例。
- [ ] **步骤 3：Commit**
  - `git commit -m "feat(api): add csv data preview and field mapping support"`

---

### 任务 4：后端核心：任务引擎实现

**文件：**
- 创建：`backend/app/tasks/collect.py`
- 修改：`backend/app/api/jobs.py`

- [ ] **步骤 1：编写异步采集任务**
  - 使用 `@huey.task()` 封装采集逻辑。
  - 实现流式读取 CSV。
  - 实现去重逻辑（Skip/Overwrite/Keep）。
- [ ] **步骤 2：实现任务控制接口**
  - `POST /api/v1/tasks/{id}/start`
  - `POST /api/v1/tasks/{id}/stop`
- [ ] **步骤 3：Commit**
  - `git commit -m "feat(worker): implement huey collection task with dedup strategy"`

---

### 任务 5：前端 UI 重构 - 任务列表与卡片

**文件：**
- 修改：`frontend/src/views/JobsView.vue`

- [ ] **步骤 1：重构布局**
  - 采用 Apple 风格的卡片式布局。
  - 增加进度条组件。
- [ ] **步骤 2：实现状态轮询**
  - 针对运行中的任务，每 2s 轮询一次接口。
- [ ] **步骤 3：Commit**
  - `git commit -m "feat(ui): upgrade jobs view with apple style cards and progress bars"`

---

### 任务 6：前端 UI 增强 - 映射预览对话框

**文件：**
- 修改：`frontend/src/views/JobsView.vue`
- 创建：`frontend/src/components/JobPreviewDialog.vue`

- [ ] **步骤 1：实现预览 Table**
  - 用户上传后弹出，展示 10 条数据。
- [ ] **步骤 2：实现字段映射选择器**
  - 列头下拉选择（URL, IP, Port...）。
- [ ] **步骤 3：Commit**
  - `git commit -m "feat(ui): add interactive field mapping and data preview"`

---

### 任务 7：模块联动 - 自动截图验证

**文件：**
- 修改：`backend/app/tasks/collect.py`

- [ ] **步骤 1：联动触发**
  - 导入完成后，若 `auto_verify` 为真，则调用 Playwright 截图任务。
- [ ] **步骤 2：Commit**
  - `git commit -m "feat(task): link collection success with playwright verification"`
