# OEM 大货单下单交互式弹窗改造 Spec

## Why
当前大货单脚本只有简单的查询接口调用，缺少交互式下单能力。需要参考 OEM 样品单全流程的交互模式，让用户输入询价单号后拉出报价信息，在弹窗中选择 SKU、设置数量、上传图片、添加附加服务和备注等，然后提交大货单。

## What Changes
- 重写前端执行弹窗：从默认表单改为交互式弹窗 `openOemBulkOrderRunForm`，参考 `openOemSampleFullFlowRunForm` 模式
- 弹窗交互流程：输入询价单号 → 点击查询 → 展示询价单信息和 SKU 明细表（含大货报价）→ 勾选 SKU + 设置数量 → 填写下大货单参数（图片、附加服务、仓库标识、备注）→ 提交
- 重命名脚本类型：`oem_bulk_order_query` → `oem_bulk_order`（语义从"查询"改为"下单"）
- 重写后端脚本：`run_oem_bulk_order_query_script` → `run_oem_bulk_order_script`，支持查询 + 创建大货单
- 更新路由端点：`/data-scripts/oem-bulk-order-query` → `/data-scripts/oem-bulk-order`

## Impact
- Affected code: `static/app.js`、`app/data_scripts.py`、`app/routers/data_scripts.py`、`app/core/utils.py`
- 依赖现有接口：`/api/oem/inquiry-full`（查询询价单报价详情，已实现）
- 大货单创建接口待用户提供后补充

## ADDED Requirements

### Requirement: 交互式大货单下单弹窗
系统 SHALL 提供一个交互式弹窗，用户输入询价单号后可查询报价信息并下大货单。

#### Scenario: 查询询价单信息
- **WHEN** 用户输入询价单号并点击"查询"按钮
- **THEN** 调用 `/api/oem/inquiry-full` 获取询价单详情和报价信息
- **AND** 展示商品名称、状态、工厂链接等基本信息
- **AND** 展示 SKU 明细表，包含大货相关字段（起订量、大货单价、大货其他费、定金比例、大货运费、大货货期）

#### Scenario: 选择 SKU 并设置数量
- **WHEN** 报价信息展示后
- **THEN** 用户可通过勾选框选择要下大货单的 SKU
- **AND** 每行 SKU 可编辑购买数量（数字输入框）

#### Scenario: 填写大货单参数
- **WHEN** SKU 选择完成
- **THEN** 弹窗展示大货单参数区域：
  - 图片上传（支持多选，复用现有 `/api/oem/upload-image` 接口）
  - 附加服务（文本输入或动态行）
  - 仓库标识（文本输入）
  - 备注（文本域）

#### Scenario: 提交大货单
- **WHEN** 用户点击"提交大货单"按钮
- **THEN** 收集勾选的 SKU 列表、数量、图片 URL、附加服务、仓库标识、备注
- **AND** 调用后端脚本接口创建大货单
- **AND** 展示执行结果（成功/失败 + 订单号）

### Requirement: 后端大货单脚本
系统 SHALL 提供后端脚本函数，接收询价单号和大货单参数，执行查询 + 创建流程。

#### Scenario: 正常创建大货单
- **WHEN** 脚本接收到有效的询价单号和 SKU 列表
- **THEN** 先调用 `/api/inquiryDetail` + `/api/quoteDetail` 获取报价信息
- **AND** 调用大货单创建接口（待用户提供 URL 和参数）
- **AND** 返回执行结果和大货单号

#### Scenario: 询价单号缺失
- **WHEN** 未提供询价单号
- **THEN** 返回失败，提示"询价单号不能为空"

#### Scenario: 无报价数据
- **WHEN** 询价单无报价数据
- **THEN** 返回失败，提示"询价单无报价数据"

## MODIFIED Requirements

### Requirement: 前端脚本类型注册
- `BUILTIN_FLOW_DEFINITIONS` 中 `oem_bulk_order_query` 改为 `oem_bulk_order`，名称改为"OEM大货单下单"
- `SCRIPT_PARAM_SCHEMAS` 中 `oem_bulk_order_query` 改为 `oem_bulk_order`，包含：登录信息（账号/密码）、查询参数（询价单号）
- `builtInTypes` 列表中 `oem_bulk_order_query` 改为 `oem_bulk_order`
- `openRunScriptForm` 中为 `oem_bulk_order` 注册专用弹窗 `openOemBulkOrderRunForm`
- `ensureOemBulkOrderQueryFlowScript` 改为 `ensureOemBulkOrderFlowScript`，脚本类型改为 `oem_bulk_order`
- 执行处理块 `oem_bulk_order_query` 改为 `oem_bulk_order`，POST 路径改为 `/data-scripts/oem-bulk-order`
