# 设计规格：恢复“新建资产采集任务”中的 CSV 导入链路

## 1. 目标

恢复“新建资产采集任务”弹窗中的“导入CSV文件”能力，并确保前后端链路完整可用：

- 用户可以在弹窗中选择 `导入CSV文件`
- 上传 CSV 后可以预览前几行数据
- 用户可以在第二步配置字段映射
- 创建任务后自动进入现有任务中心的异步执行链路
- 执行结果在任务卡片中可见，包括成功、失败、重复和错误信息

本次恢复不以 FOFA/Hunter 专用 CSV 接口为主链路，而是以“预览 -> 映射 -> 创建标准任务 -> 启动任务”作为统一流程。

## 2. 现状与问题

当前代码中已经存在部分 CSV 相关能力，但链路是断裂的：

- 前端 [JobsView](../../../../frontend/src/views/JobsView.vue) 当前弹窗仅保留常规采集源表单，`导入CSV文件` 入口缺失
- 前端 API 已保留 `/api/v1/jobs/preview` 的调用封装
- 后端 [jobs.py](../../../../backend/app/api/jobs.py) 已保留 CSV 预览接口，也保留 FOFA/Hunter 专用上传导入接口
- 标准建任务接口 `/api/v1/jobs/collect` 已支持接收 `file_path` 和 `field_mapping`
- 但任务执行器 [collect.py](../../../../backend/app/tasks/collect.py) 当前不会处理 `file_path + field_mapping` 的 CSV 导入任务

结果是：

- 就算前端恢复上传和映射界面，标准任务启动后也不会真正导入 CSV
- CSV 能力被拆成“预览链路”和“专用导入链路”两套语义，后续扩展困难

## 3. 设计结论

采用两步式恢复方案，并接入现有任务中心异步任务模型。

### 3.1 用户流程

在“新建资产采集任务”弹窗中提供两种模式：

- `在线采集`
- `导入CSV文件`

当用户选择 `导入CSV文件` 时：

1. 第一步填写任务名、上传 CSV、选择去重策略、选择是否自动验证
2. 点击“下一步”后调用 `/api/v1/jobs/preview`
3. 第二步展示 CSV 表头和前几行预览
4. 用户完成系统字段到 CSV 列的映射
5. 点击“完成创建”后调用 `/api/v1/jobs/collect`
6. 前端继续自动调用 `/api/v1/jobs/{id}/start`
7. 任务进入现有卡片列表，由轮询接口显示进度和结果

### 3.2 核心原则

- CSV 导入必须复用标准任务中心，而不是旁路同步导入
- CSV 解析与字段映射逻辑独立为服务层，不直接塞进视图或路由
- 预览阶段负责“结构确认”，执行阶段负责“正式导入”
- 单行坏数据不应打断整批任务
- 必填映射缺失时不允许创建任务

## 4. 前端设计

### 4.1 弹窗结构调整

修改 [JobsView.vue](../../../../frontend/src/views/JobsView.vue) 中“新建资产采集任务”弹窗，使其支持模式切换。

#### 在线采集模式

保留现有在线采集逻辑：

- 多数据源选择
- 查询条件输入
- 去重策略
- 自动验证

#### 导入CSV文件模式

使用两步式界面：

第一步：

- `任务名称`
- `CSV 文件上传`
- `去重策略`
- `采集完成后自动触发验证与截图`

第二步：

- CSV 表头展示
- CSV 前 5 行预览
- 系统字段映射表单
- 映射合法性校验

### 4.2 字段映射范围

第二步中提供以下系统字段映射：

必填字段：

- `url`
- `ip`
- `port`

可选字段：

- `title`
- `protocol`
- `domain`
- `status_code`
- `org`
- `country`
- `city`
- `host`

自动匹配规则保留，但只作为预填，不可替代最终校验。

### 4.3 前端提交载荷

CSV 模式创建任务时，向 `/api/v1/jobs/collect` 提交：

```json
{
  "job_name": "采集任务_0417_1530",
  "sources": ["csv_import"],
  "queries": [],
  "file_path": "backend/tmp_uploads/example.csv",
  "field_mapping": {
    "url": "link",
    "ip": "ip",
    "port": "port",
    "title": "title"
  },
  "dedup_strategy": "skip",
  "auto_verify": false,
  "created_by": "system"
}
```

成功建任务后，前端继续调用 `startTask(job_id)`，行为与普通采集任务一致。

### 4.4 前端错误处理

以下情况必须在弹窗内阻断流程：

- 未选择 CSV 文件
- 文件不是 `.csv`
- 预览接口返回失败
- CSV 无表头
- 必填映射 `url/ip/port` 缺失
- 创建任务接口失败

错误提示目标是明确指出“哪一步失败”和“为什么失败”，避免用户创建半残任务。

## 5. 后端设计

### 5.1 API 层

[jobs.py](../../../../backend/app/api/jobs.py) 的职责保持清晰：

- `/api/v1/jobs/preview`
  - 接收上传文件
  - 保存至 `backend/tmp_uploads`
  - 返回表头、预览行、临时 `file_path`
- `/api/v1/jobs/collect`
  - 负责创建标准 `CollectJob`
  - 当 `sources=["csv_import"]` 时，只记录任务，不直接执行导入
- `/api/v1/jobs/{job_id}/start`
  - 启动后台任务执行器

现有 `upload-fofa-csv` 和 `upload-hunter-csv` 接口先保留，避免影响其他现存调用方，但不作为弹窗主入口。

### 5.2 新增 CSV 映射服务

新增服务文件：

- [mapped_csv.py](../../../../backend/app/services/collectors/mapped_csv.py)

职责：

- 读取 CSV 文件
- 根据 `field_mapping` 将原始列映射为系统标准字段
- 执行类型转换和默认值补齐
- 产出标准 `record` 列表或可迭代对象

建议输出的标准 record 结构与现有导入服务保持一致：

```python
{
    "source": "csv_import",
    "ip": "1.2.3.4",
    "port": 443,
    "protocol": "https",
    "domain": "example.com",
    "url": "https://example.com",
    "title": "Example",
    "status_code": 200,
    "observed_at": None,
    "country": None,
    "city": None,
    "org": None,
    "host": None,
}
```

字段处理规则：

- `url` 直接取映射列，去空白
- `ip` 直接取映射列，去空白
- `port` 转换为整数，非法时按坏行处理
- `protocol` 可选，缺失时默认 `http`
- `status_code` 可选，转换失败时置为 `None`
- 可选字段为空时统一转为 `None`

### 5.3 任务执行器改造

修改 [collect.py](../../../../backend/app/tasks/collect.py)，新增 `csv_import` 分支。

执行逻辑：

1. 读取 `job.query_payload.file_path`
2. 读取 `job.field_mapping`
3. 调用 `mapped_csv` 服务解析记录
4. 将结果传给现有 [import_service.py](../../../../backend/app/services/collectors/import_service.py)
5. 更新任务计数和状态

建议处理方式：

- 当 `sources` 中包含 `csv_import` 时，优先走 CSV 导入分支
- `job.total_count` 应在正式导入前设置为可处理记录总数
- 导入完成后设置 `progress = 100`
- 若任务整体失败，设置 `status = "failed"` 并写入 `error_message`

### 5.4 去重与入库

CSV 导入继续复用现有导入/保存能力：

- 标准 record 入库复用 [import_service.py](../../../../backend/app/services/collectors/import_service.py)
- 去重策略复用 `CollectJob.dedup_strategy`

如果现有 `SampleImportService` 对去重策略支持不足，则在本次实现中一并补齐，确保 CSV 导入任务与普通任务的重复处理语义一致。

## 6. 错误处理设计

### 6.1 预览阶段

预览阶段失败时，不允许进入映射或创建任务：

- 文件不存在或为空
- 非 CSV 文件
- 解码失败
- 无表头
- 预览读取异常

### 6.2 执行阶段

执行阶段采用“整批任务可失败、单行错误可累计”的策略：

- `file_path` 不存在：任务直接 `failed`
- `field_mapping` 缺失关键字段：任务直接 `failed`
- 单行缺失 `url/ip/port`：计入 `failed_count`
- 单行端口或状态码转换失败：计入 `failed_count`
- 单行数据库写入异常：计入 `failed_count`，继续后续行

任务卡片中需要能看到：

- `success_count`
- `failed_count`
- `duplicate_count`
- `total_count`
- `error_message`

## 7. 测试设计

### 7.1 后端单元测试

新增对 `mapped_csv` 的测试，覆盖：

- 正常字段映射
- 自动默认 `protocol`
- `port` 类型转换
- `status_code` 类型转换
- 空值处理
- 必填字段缺失行

### 7.2 后端任务测试

新增对 `csv_import` 任务分支的测试，覆盖：

- 使用 `file_path + field_mapping` 成功导入
- 导入后任务状态为 `success`
- `total_count / success_count / failed_count` 计算正确
- 文件不存在时任务状态为 `failed`

### 7.3 接口测试

补充 API 级测试，覆盖：

- `/api/v1/jobs/preview` 的文件类型和空文件校验
- `/api/v1/jobs/collect` 对 CSV 任务载荷的接受情况

### 7.4 前端验证

当前前端仓库未配置专门测试框架，本次以前端构建校验和手工冒烟为主：

- `vue-tsc --noEmit`
- `vite build`
- 手工验证两步式弹窗完整流程

## 8. 实施范围

本次设计只覆盖恢复“新建资产采集任务”弹窗中的 CSV 导入能力，不包含：

- 新的 CSV 模板市场或导入模板管理
- 批量列映射保存与复用
- FOFA/Hunter 专用接口的删除或迁移
- 大文件流式导入优化

## 9. 验收标准

满足以下条件视为本次恢复完成：

- 弹窗中可见并可使用 `导入CSV文件`
- CSV 上传后可进入预览与映射步骤
- 必填映射缺失时无法创建任务
- 创建任务后自动进入任务中心异步执行
- CSV 数据可实际入库，不是只有 UI
- 任务卡片能展示执行结果和失败信息
- 前后端验证通过
