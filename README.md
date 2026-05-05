# AssetMap

## 项目说明

AssetMap 是一个包含后端 API、前端管理后台、资产采集管理、截图验证、报告输出和暴露面搜索的项目。

项目目录分为两部分：

- `backend/`：FastAPI 后端
- `frontend/`：Vue 3 + Vite 前端

## 运行环境

建议环境：

- Python 3.11+
- Node.js 20+
- npm 10+
- Docker Desktop
- GNU Make 或兼容的 `make`
- PostgreSQL 16（如果不用 Docker）

Windows 下如果没有 `make`，也可以直接执行文档里的 `docker compose`、`python`、`npm` 命令。

## 需要安装的依赖

### 后端依赖文件

后端依赖定义在：

- `backend/requirements.txt`

安装命令：

```bash
python -m pip install -r backend/requirements.txt
```

当前主要依赖包括：

- `fastapi`
- `uvicorn`
- `sqlalchemy`
- `psycopg[binary]`
- `pydantic`
- `pydantic-settings`
- `playwright`
- `openpyxl`
- `httpx`
- `huey`
- `pytest`

如果要使用暴露面搜索的浏览器能力，还需要安装 Playwright 浏览器：

```bash
python -m playwright install chromium
```

### 前端依赖文件

前端依赖定义在：

- `frontend/package.json`

安装命令：

```bash
cd frontend
npm install
```

当前主要依赖包括：

- `vue`
- `vue-router`
- `pinia`
- `element-plus`
- `axios`
- `dayjs`
- `echarts`
- `vue-echarts`
- `vite`
- `typescript`
- `vue-tsc`

## 数据库一键启动

项目根目录已提供：

- `docker-compose.yml`
- `Makefile`

### 启动数据库

```bash
make db-up
```

### 初始化数据库

```bash
make db-init
```

### 常用数据库命令

```bash
make db-down
make db-reset
make db-logs
```

如果本机 `5432` 已被占用，可以改端口：

```bash
POSTGRES_PORT=55432 make db-up
```

## 环境变量

### 后端环境变量

示例文件：

- `backend/.env.example`

主要配置：

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/assetmap
```

如果你已经有自己的 PostgreSQL，请把 `backend/.env` 改成你的实际连接串。

### 前端环境变量

示例文件：

- `frontend/.env.example`
- `frontend/.env.development`

主要配置：

```env
VITE_API_BASE_URL=http://127.0.0.1:9527
```

## 启动项目

### 启动后端

在项目根目录执行：

```bash
python main.py
```

默认后端地址：

- `http://127.0.0.1:9527`

### 启动前端

```bash
cd frontend
npm run dev
```

默认前端地址：

- `http://127.0.0.1:5173`

### Windows 快速重启脚本

项目根目录提供：

- `dev-restart.ps1`
- `dev-stop.ps1`

使用方式：

```powershell
powershell -ExecutionPolicy Bypass -File .\dev-restart.ps1
```

## 项目使用流程

推荐顺序：

1. 启动数据库
2. 初始化数据库
3. 启动后端
4. 启动前端
5. 打开前端页面开始使用

### 常见功能

#### 资产采集

- 进入采集任务页面
- 配置数据源和查询条件
- 启动采集任务

#### 资产管理

- 在资产列表查看采集结果
- 执行截图验证
- 标记标签
- 查看资产详情

#### 暴露面搜索

- 进入暴露面搜索页面
- 新建搜索任务
- 查看搜索进度、当前语法、下一条语法
- 在结果中筛选、标记、导入资产

#### 报告功能

- 在报告中心创建报告
- 下载生成结果

## 测试与构建

### 后端测试

```bash
python -m pytest backend/tests
```

单测示例：

```bash
pytest backend/tests/test_reports.py -q
```

### 前端构建

```bash
cd frontend
npm run build
```

构建产物目录：

- `frontend/dist/`

## 常见问题

### 1. 数据库启动失败

通常是本机 `5432` 端口被占用。可改成：

```bash
POSTGRES_PORT=55432 make db-up
```

并同步调整 `backend/.env` 里的 `DATABASE_URL` 端口。

### 2. 暴露面搜索浏览器功能不可用

通常是没有安装 Playwright 浏览器：

```bash
python -m playwright install chromium
```

### 3. 前端打不开接口

检查：

- 后端是否已启动
- `frontend/.env.development` 的 `VITE_API_BASE_URL` 是否正确

### 4. Make 命令不可用

Windows 下如果没有 `make`，直接使用：

```bash
docker compose up -d postgres
python backend/init_db.py
```

## 相关文件

- `backend/requirements.txt`
- `backend/.env.example`
- `backend/init_db.py`
- `frontend/package.json`
- `frontend/.env.example`
- `docker-compose.yml`
- `Makefile`
