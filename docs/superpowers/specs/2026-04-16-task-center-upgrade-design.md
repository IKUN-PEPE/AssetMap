# 设计规格：资产采集与调度中心升级

## 1. 目标 (Goals)
将 AssetMap 的资产导入功能从简单的 CSV 上传工具升级为功能完备、可视化、可调度的“资产采集中心”。

## 2. 核心架构变更 (Architectural Changes)

### 2.1 后端模型扩展 (SQLAlchemy)
在 `CollectJob` 模型中增加以下字段：
- `progress`: Integer (0-100) - 当前进度。
- `success_count`: Integer - 成功导入的数量。
- `failed_count`: Integer - 导入失败的数量（如格式错误）。
- `duplicate_count`: Integer - 触发去重策略而被过滤的数量。
- `total_count`: Integer - 预估总记录数。
- `dedup_strategy`: String - `skip` (默认), `overwrite`, `keep_all`。
- `field_mapping`: JSONB - 存储用户定义的 CSV 字段与系统字段的映射关系。
- `cron_expr`: String (Optional) - 支持定时采集。
- `auto_verify`: Boolean - 导入完成后是否自动触发截图和验证。

### 2.2 异步任务框架 (ARQ)
- **引入 arq**: 替换简单的 `BackgroundTasks`。
- **任务控制**: 
  - `start`: 启动或重新启动任务。
  - `stop`: 终止 arq worker 中的当前 job。
  - `pause`: 通过 Redis 标志位实现逻辑暂停。

### 2.3 采集适配器 (Collectors)
- **BaseCollector**: 定义统一接口 `stream_records()`。
- **CSV Streamer**: 支持分块读取大文件，防止 OOM。
- **API Collectors**: FOFA / ZoomEye API 集成，支持分页抓取。

## 3. 详细功能设计 (Functional Design)

### 3.1 数据预览与映射 (Crucial)
1. **上传流程**: 用户上传文件 -> 后端解析前 10 行 -> 返回 JSON 给前端。
2. **映射 UI**: 前端弹窗展示表格 preview，每列顶部有下拉框选择对应字段（url, ip, port, title, tags）。
3. **确认导入**: 用户核对映射无误后，点击“确认执行”，后端正式创建 `CollectJob`。

### 3.2 去重策略 (Deduplication)
按 `(url, ip, port)` 作为资产唯一性标识：
- **Skip (默认)**: 发现已存在资产则跳过，仅记录 `duplicate_count`。
- **Overwrite**: 使用新数据更新已存在资产的 title 和 tags。
- **Keep All**: 强制插入（不推荐，主要用于调试）。

### 3.3 验证模块联动
- 任务配置中增加“联动验证”开关。
- 若开启，任务状态变为 `success` 后，自动调用 `assets.py` 中的 `verify_assets` 逻辑，将该任务导入的所有 ID 投入 Playwright 队列。

## 4. UI/UX 设计 (Apple Style)
- **布局**:
  - **上部**: 任务创建区。支持拖拽上传，采用磨砂玻璃背景 (`backdrop-filter: blur`)。
  - **下部**: 任务列表。卡片式布局，大圆角 (12px-16px)，淡色阴影。
- **动态效果**:
  - 进度条使用细长条设计，带有微弱的呼吸灯动画。
  - 状态切换采用平滑的 Transition。

## 5. 安全与防御
- **路径安全**: 强制对上传文件名执行 `os.path.basename`，并存储于 UUID 命名的子目录。
- **速率限制**: API 采集需遵循目标平台（FOFA/ZoomEye）的 Rate Limit，通过信号量控制并发。

## 6. 测试策略
- **单元测试**: 测试各种去重策略的逻辑。
- **集成测试**: 模拟 CSV 映射流程，验证映射后的字段是否正确入库。
- **压力测试**: 测试 10w+ 级数据的导入性能与内存消耗。
