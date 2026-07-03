# Tasks

- [x] Task 1: 前端重命名脚本类型并创建交互式弹窗函数
  - [x] SubTask 1.1: 在 `static/app.js` 中将 `oem_bulk_order_query` 重命名为 `oem_bulk_order`（BUILTIN_FLOW_DEFINITIONS、SCRIPT_PARAM_SCHEMAS、builtInTypes、ensureOem*FlowScript、执行处理块）
  - [x] SubTask 1.2: 新增 `openOemBulkOrderRunForm(flow)` 函数，参考 `openOemSampleFullFlowRunForm` 实现
  - [x] SubTask 1.3: 在 `openRunScriptForm` 中注册 `oem_bulk_order` → `openOemBulkOrderRunForm`

- [x] Task 2: 后端重写脚本函数和路由
  - [x] SubTask 2.1: 在 `app/data_scripts.py` 中将 `run_oem_bulk_order_query_script` 重写为 `run_oem_bulk_order_script`
  - [x] SubTask 2.2: 在 `app/routers/data_scripts.py` 中更新 import 和路由端点为 `/data-scripts/oem-bulk-order`
  - [x] SubTask 2.3: 在 `app/core/utils.py` 中更新 API Case key 为 `oem_bulk_order`

# Task Dependencies
- Task 2 依赖 Task 1 的命名约定（脚本类型名 `oem_bulk_order`）
- Task 1 和 Task 2 可并行开发，但需保持命名一致
