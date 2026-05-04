# 2026-04-13 Playwright 资产状态码验证设计

## 背景
当前资产列表中的“批量验证并获取状态码”已经从单纯标记 `verified` 改成了真实请求 URL 并回填 `status_code`。但当前实现使用的是 `requests.get(...)`。用户要求将这套状态码检查实现改为基于 Playwright 的页面导航检查。

本次目标是在不改前端整体交互和不新增接口的前提下，把后端验证内核从 `requests` 切换为 Playwright，并继续保持批量验证、状态码回填、整批不中断的行为。

## 目标
复用现有 `POST /api/v1/assets/verify-batch` 接口，改为使用 Playwright 导航 `normalized_url` 并读取主文档响应状态码，再写回资产 `status_code`。

## 范围
### 本次包含
- 保留现有批量验证接口
- 保留现有前端按钮和列表刷新逻辑
- 后端验证实现从 `requests` 改为 Playwright
- 使用页面主文档响应状态码作为写回值
- 单条失败不中断整批
- 继续返回 `updated / success / failed`

### 本次不包含
- 新建验证页面
- 新增另一套接口
- 保留详细失败原因
- 复杂重试机制
- 一开始就做并发页面验证

## 方案选择
### 方案 A（采用）
保留现有接口和前端交互，仅替换后端验证方式为 Playwright 页面导航检查。

理由：
- 最符合用户要求
- 改动集中在后端验证逻辑
- 前端无需再次重构
- 可以复用项目现有 Playwright 运行环境

### 备选方案
- requests + Playwright 混合兜底：不符合“改为 Playwright 实现”的明确要求
- 新建 Playwright 专用接口：超出本次最小目标

## 后端设计
现有 `/verify-batch` 保持不变，但内部逻辑改为：
1. 查出所选资产
2. 启动一个 Playwright 浏览器实例
3. 对每条资产：
   - 新建页面
   - 导航到 `normalized_url`
   - 读取主文档响应对象
   - 获取状态码
   - 写回 `status_code`
   - 设置 `verified = true`
4. 关闭页面
5. 全部完成后关闭浏览器
6. 提交数据库并返回统计信息

### 状态码规则
- 优先读取主文档响应状态码
- 如果导航异常、超时、或拿不到响应对象，则视为该条失败
- 失败时 `status_code = None`
- 不分析子资源请求
- 不分析 iframe

## 执行方式
为保证稳定性，本次采用：
- 单浏览器实例复用
- 每条资产串行验证
- 每条资产独立页面对象

这样比“每个资产都重启浏览器”更轻，也比直接并发更稳。

## 前端设计
前端交互不变：
- 继续使用“批量验证并获取状态码”按钮
- 继续调用 `/api/v1/assets/verify-batch`
- 继续显示成功/失败统计
- 继续刷新资产列表展示状态码

## 数据流
1. 用户勾选资产
2. 点击“批量验证并获取状态码”
3. 前端请求 `/api/v1/assets/verify-batch`
4. 后端用 Playwright 串行导航 URL
5. 后端写回 `status_code` 和 `verified`
6. 前端刷新列表
7. 用户在状态码列看到结果

## 异常处理
### 单条失败
- 不影响其他资产继续验证
- 该条记入 `failed`
- `status_code = None`
- `verified = true`

### 整批完成
- 返回：
  - `updated`
  - `success`
  - `failed`

### 接口级异常
- 前端继续显示“资产验证失败”

## 关键改动文件
预计涉及：
- `backend/app/api/assets.py`
- `backend/tests/test_verify_batch.py`
- 可能涉及项目里现有 Playwright 调用位置作为参考
- 前端通常无需再改，除非需要微调提示文案

## 测试与验证
### 后端
- 验证成功时能写入 Playwright 获取到的状态码
- 验证导航异常时不中断整批
- 验证成功/失败统计正确

### 前端
- 验证按钮流程不变
- 验证列表刷新后状态码仍能正常显示
- 验证提示文案继续正常工作

## 分阶段实施建议
1. 先把后端验证 helper 切换到 Playwright
2. 保持现有测试思路，改成 mock Playwright 响应
3. 跑后端测试和前端 build
4. 联调资产列表验证按钮行为
