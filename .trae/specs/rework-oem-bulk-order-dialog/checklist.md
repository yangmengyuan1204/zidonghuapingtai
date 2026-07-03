# Checklist

- [x] 前端 `BUILTIN_FLOW_DEFINITIONS` 中 `oem_bulk_order` 类型定义正确，名称为"OEM大货单下单"
- [x] 前端 `SCRIPT_PARAM_SCHEMAS.oem_bulk_order` 包含登录信息（account/password）和查询参数（order_sn）
- [x] 前端 `openOemBulkOrderRunForm` 函数实现交互式弹窗：输入询价单号 → 查询 → SKU 表 → 参数填写 → 提交
- [x] 前端 SKU 表展示大货相关字段（起订量、大货单价、大货其他费、定金比例、大货运费、大货货期）
- [x] 前端图片上传功能复用 `/api/oem/upload-image` 接口，支持多选
- [x] 前端提交时收集 sku_list（含 sku_id、num、option）、图片 URL、附加服务、仓库标识、备注
- [x] 前端 `openRunScriptForm` 中 `oem_bulk_order` 路由到 `openOemBulkOrderRunForm`
- [x] 前端 `builtInTypes` 列表包含 `oem_bulk_order`
- [x] 前端 `ensureOemBulkOrderFlowScript` 函数正确注册流程
- [x] 后端 `run_oem_bulk_order_script` 函数实现查询报价逻辑（复用 `fetch_oem_full_quote`）
- [x] 后端路由 `/data-scripts/oem-bulk-order` 正确注册
- [x] 后端 import 更新为 `run_oem_bulk_order_script`
- [x] `app/core/utils.py` 中 API Case key 更新为 `oem_bulk_order`
