# AssetMap

AssetMap 是一个面向资产测绘结果管理、批量截图验证和报告输出的项目。当前版本已经具备 **后端基础版** 和 **Vue 3 + Element Plus 前端基础版**，围绕 FOFA、Hunter、ZoomEye 三类数据源的统一资产模型、截图服务、标签管理、选择集和报告任务完成了第一阶段落地。

## 当前实现状态

### 已实现

#### 后端
- FastAPI 后端基础骨架
- PostgreSQL 数据模型与数据库连接层
- 资产相关核心模型：`collect_jobs`、`source_observations`、`hosts`、`services`、`web_endpoints`、`screenshots`、`labels`、`label_audit_logs`、`saved_selections`、`selection_items`、`reports`
- 基础 API 路由
- sample 模式资产导入链路
- Playwright 截图服务封装
- 标签、选择集、报告任务基础接口
- 数据库初始化入口 `backend/init_db.py`
- 主目录统一启动入口 `main.py`
- 基础测试

#### 前端
- Vue 3 + Vite + Element Plus 工程骨架
- 管理后台布局
- 仪表盘页面
- 采集任务页面
- 资产列表页面
- 资产详情页面
- 选择集页面
- 报告中心页面
- 系统配置页面
- 基础 API 封装与类型定义
- 与后端第一阶段接口的基础对接
- 前端环境变量文件：`.env.development`、`.env.example`

### 当前未完成

- 真实 FOFA / Hunter / ZoomEye API 接入
- HTML / PDF 报告真实生成
- 完整认证和权限控制
- Celery / Redis 异步任务系统
- Alembic 数据迁移
- 前端登录页、权限页、完整状态管理
- 前端生产代理配置与部署配置

## 目录说明

- `main.py`：项目根目录统一启动入口（默认启动后端）
- `backend/`：后端代码、测试、依赖、数据库初始化脚本
- `frontend/`：前端 Vue 3 管理后台工程
- `archive/docs/`：方案文档与总结文档归档目录
- `archive/legacy-prototype/`：早期原型脚本、测试与压缩包归档目录
- `archive/runtime/`：运行产物归档目录（截图、结果、日志）

## 启动方式

### 1. 安装后端依赖

```bash
python -m pip install -r backend/requirements.txt
```

### 2. 安装前端依赖

```bash
cd frontend
npm install
```

### 3. 初始化数据库

```bash
python backend/init_db.py
```

> 注意：默认数据库配置为 PostgreSQL，本机需要先启动数据库服务，并保证连接参数正确。

### 4. 从主目录启动后端

```bash
python main.py
```

默认后端地址：

- Host: `127.0.0.1`
- Port: `9527`

### 5. 启动前端

```bash
cd frontend
npm run dev
```

默认前端地址：

- `http://127.0.0.1:5173`

### 6. 前端环境变量

前端已支持通过环境变量配置后端地址。

开发环境默认文件：

- `frontend/.env.development`

示例文件：

- `frontend/.env.example`

当前配置项：

```env
VITE_API_BASE_URL=http://127.0.0.1:9527
```

### 7. 运行测试

```bash
python -m pytest backend/tests
```

### 8. 构建前端

```bash
cd frontend
npm run build
```

前端构建产物输出在：

- `frontend/dist/`

## 当前前端页面

当前前端已包含以下页面：

- 仪表盘
- 采集任务
- 资产列表
- 资产详情
- 选择集
- 报告中心
- 系统配置

当前页面已完成与后端基础接口的第一轮对接，但仍属于第一阶段骨架版。

## 当前 API 范围

已实现接口包括：

- `GET /health`
- `POST /api/v1/jobs/collect`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/assets`
- `GET /api/v1/assets/{asset_id}`
- `POST /api/v1/screenshots/batch`
- `POST /api/v1/labels/batch`
- `POST /api/v1/selections`
- `GET /api/v1/selections`
- `POST /api/v1/reports`
- `GET /api/v1/system/config`

## 文档索引

以下文档已整理归档，可直接查看：

- [AssetMap 本地总结报告](./archive/docs/AssetMap-本地总结报告.md)
- [AssetMap 系统设计说明书](./archive/docs/AssetMap-系统设计说明书.md)
- [AssetMap 数据库与 API 设计](./archive/docs/AssetMap-数据库与API设计.md)
- [AssetMap 项目方案文档](./archive/docs/AssetMap%20项目方案文档.md)
- [数据库初始化说明](./backend/INIT_DB.md)

## 当前已知问题

- 如果 PostgreSQL 未启动，`backend/init_db.py` 和后端数据库相关接口会失败。
- 当前 sample 导入模式可用，真实数据源尚未接通。
- 报告接口当前仅完成任务创建，还未生成真实 HTML / PDF。
- 前端虽然已支持 `VITE_API_BASE_URL`，但尚未补生产环境配置。
- 前端构建虽然成功，但首版打包体积偏大，后续可按需拆包优化。

## 下一步建议

建议按以下顺序继续推进：

1. 增加后端 `.env.example` 并切换数据库配置到环境变量模式
2. 修通 PostgreSQL 本地连接
3. 接入真实 FOFA / Hunter / ZoomEye API
4. 增加报告 HTML / PDF 生成
5. 开始前端登录与权限控制
