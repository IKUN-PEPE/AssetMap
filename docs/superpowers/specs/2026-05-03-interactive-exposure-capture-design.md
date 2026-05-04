# 交互式线索捕获 (Interactive Exposure Capture) 设计方案

**日期：** 2026-05-03
**状态：** 已评审

## 1. 目标
在 AssetMap 的“暴露面搜索”模块中，实现在 Playwright 交互模式下（非无头模式）通过简单的鼠标操作（点选）实时记录搜索引擎、GitHub 或网盘页面的敏感线索。

## 2. 系统架构

### 2.1 注入层 (Client-side Injection)
- **技术：** Playwright `page.add_init_script`
- **逻辑：** 
    - 注入一段 AssetMap 专用的 JavaScript。
    - 在页面顶部创建一个 `z-index: 2147483647` 的悬浮工具栏。
    - 工具栏包含：AssetMap 标识、采集开关、已捕获计数器。

### 2.2 通信层 (RPC Bridge)
- **技术：** Playwright `page.expose_function`
- **函数名：** `__am_record_clue(data)`
- **数据结构：**
  ```json
  {
    "title": "文件名/标题",
    "url": "跳转链接",
    "snippet": "网页摘要/正文片段",
    "source": "bing/baidu/github/manual"
  }
  ```

### 2.3 后端处理 (Python Service)
- **适配：** `ExposureSearchService` 增加回调处理器。
- **持久化：** 收到数据后，通过 `ExposureSearchResult` 模型入库，状态默认设为 `valid`。

## 3. 交互流程
1. **高亮：** 鼠标悬停在任何包含 `href` 的元素上时，注入脚本计算该链接的权重。
2. **确认：** 元素边框变为蓝色虚线，提示“可记录”。
3. **操作：** 用户点击该元素。
4. **反馈：** 脚本拦截点击，调用 `__am_record_clue`，并在浏览器内弹出 Toast 提示。

## 4. 关键代码位置
- **后端：** `backend/app/services/exposure_search/playwright_client.py` (注入逻辑)
- **后端：** `backend/app/services/exposure_search/__init__.py` (回调处理)

## 5. 测试计划
- **注入测试：** 模拟加载一个 HTML 页面，验证工具栏是否渲染。
- **回调测试：** 通过 `page.evaluate` 手动触发 `__am_record_clue`，验证后端数据库是否新增记录。
- **去重测试：** 验证同一 URL 在同一任务下不会被重复记录。
