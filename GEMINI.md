# AssetMap 项目指令与规范

AssetMap 是一个面向资产测绘结果管理、批量截图验证和报告输出的项目。

## 1. 项目概览

### 技术栈
- **后端**: FastAPI, SQLAlchemy (PostgreSQL/SQLite), Pydantic, Playwright (截图), Huey (异步任务)
- **前端**: Vue 3 (Composition API), Vite, Element Plus, Pinia, ECharts
- **部署**: 后端与前端分离，支持环境变量驱动配置

### 核心架构 (Backend)
- `backend/app/api/`: 路由处理器，保持轻量
- `backend/app/services/`: 业务逻辑层，核心处理逻辑
- `backend/app/tasks/`: 背景异步任务 (Huey)
- `backend/app/models/`: SQLAlchemy 数据库模型
- `backend/app/schemas/`: Pydantic 数据验证与序列化模型
- `backend/app/core/`: 核心配置、数据库连接与中间件

## 2. 构建与运行

### 环境准备
- **Python**: 推荐 3.10+
- **Node.js**: 推荐 18+

### 后端开发
- **安装依赖**: `python -m pip install -r backend/requirements.txt`
- **初始化数据库**: `python backend/init_db.py` (确保 PostgreSQL 已启动或调整 `.env`)
- **启动服务**: `python main.py` (在项目根目录下运行，默认端口 9527)
- **运行测试**: `python -m pytest backend/tests`

### 前端开发
- **安装依赖**: `cd frontend && npm install`
- **启动开发环境**: `npm run dev` (默认端口 5173)
- **构建生产环境**: `npm run build`

## 3. 开发规范

### 代码风格
- **Python**:
    - 遵循 PEP 8，使用 4 空格缩进。
    - 函数、变量、模块名使用 `snake_case`。
    - 类名使用 `PascalCase`。
    - 强制使用类型注解 (Type Hints)。
    - 业务逻辑应位于 `services/` 或 `tasks/`，不应堆积在 API 路由中。
- **Frontend (Vue/TS)**:
    - 使用 Vue 3 `<script setup>` 组合式 API。
    - 严格遵循 TypeScript 类型定义。
    - 样式优先使用原生的 Vanilla CSS 或 Element Plus 预设，避免滥用外部工具库。

### 测试要求
- 所有新功能或修复均需包含对应的测试用例。
- 后端测试存放于 `backend/tests/`。
- 使用 `pytest` 进行验证。

### 提交规范
- 使用常规提交 (Conventional Commits) 格式：
    - `feat:`: 新功能
    - `fix:`: 修复 Bug
    - `chore:`: 构建过程或辅助工具变动
    - `docs:`: 文档变更
- 摘要应使用动词原形，简明扼要。

## 4. 目录说明
- `main.py`: 统一后端启动入口。
- `backend/`: 后端核心代码、测试与数据。
- `frontend/`: 前端 Vue 3 工程。
- `screenshots/`, `results/`, `logs/`, `report/`: 运行期生成的产物，**严禁提交至版本库**。
- `docs/`: 包含详细的项目方案与数据库设计文档。

## 5. 注意事项
- **安全性**: 严禁将 API Keys (FOFA, Hunter 等) 或数据库密码硬编码在代码中。使用 `backend/.env` 进行配置。
- **环境隔离**: `backend/.env` 不应提交，参考 `backend/.env.example`。
- **数据库**: 默认连接 `postgresql+psycopg://postgres:postgres@localhost:5432/assetmap`。修改配置前请备份现有数据。
