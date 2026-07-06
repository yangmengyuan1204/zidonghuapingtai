# 重新设计 OEM 大货单下单交互

## 背景

当前 `openOemBulkOrderRunForm` 交互存在以下问题：
- option（附加服务）始终为空数组，无法配置 FBA贴标/拍照/挂吊牌等
- 缺少 warehouse 信息输入（warehouse_type / FNSKU / ASIN / 图片）
- 大货字段展示不完整（大货其他费、定金比例、大货费用、大货货期缺失）

后端 `run_oem_bulk_order_script` 已实现完整 newOrder 调用，本次改造聚焦前端交互。

## 设计方案

### 整体布局（单页全展开）

对话框从上到下：

```
[询价单号输入] [查询报价按钮]
     ↓ 查询成功
[商品信息条：名称/状态/工厂链接]
[全局附加服务 option 复选框列表]  ← 默认全选
[SKU 明细表格]  ← 含数量/大货字段 + 仓储列 + 每行「自定义」展开
[底部参数：仓库城市 / 备注]
[提交大货单]
```

### SKU 表格列设计

| 选择 | SKU ID | SKU | 购买数量 | 起订量 | 大货单价 | 大货其他费 | 定金比例 | 大货运费 | 大货货期 | 仓库类型 | FNSKU | ASIN | 标签图片 | 操作 |
|------|--------|-----|----------|--------|----------|-----------|----------|----------|----------|----------|-------|------|----------|------|

- 仓库类型：下拉（1=FBA / 4=其他），默认 1
- FNSKU / ASIN：文本输入
- 标签图片：上传按钮 + 预览缩略图
- 操作：「自定义 option」链接，展开该 SKU 独立 option 配置

### Option 交互

- 表格上方「全局附加服务」区：从 `/common/common/optionList` 拉取，默认全选
- 每个 option 一行：复选框 + 中文名 + 大货单价 + 数量输入
  - 拍照类（id=9 或 name 含"拍照"）数量固定 1
  - 其余 option 数量跟随 SKU 购买数量
- SKU 行「自定义 option」展开：独立复选框列表，勾选后该 SKU 使用自己的 option 配置覆盖全局

### 后端改动

`SCRIPT_PARAM_SCHEMAS.oem_bulk_order` 追加字段：
- `warehouse_city`（仓库城市，默认 2）
- `global_options`（全局 option 配置，JSON 字符串）
- `fnsku` / `asin`（全局默认，可被 SKU 覆盖）

`run_oem_bulk_order_script` 已支持 option + warehouse 构造，无需额外改动。

## 涉及文件

| 文件 | 改动 |
|------|------|
| `static/app.js` L74-80 | `SCRIPT_PARAM_SCHEMAS.oem_bulk_order` 追加 warehouse_city 等字段 |
| `static/app.js` L1934-2161 | 重写 `openOemBulkOrderRunForm`：查报价后调 optionList、渲染全局 option 区、SKU 表格增加仓储列、每行支持自定义 option |

## 验证步骤

1. 点击「OEM大货单下单」弹出对话框
2. 输入询价单号 → 点击「查询报价」
3. 验证：商品信息条显示正确（名称/状态/工厂链接换行）
4. 验证：全局附加服务 option 列表显示，默认全选
5. 验证：SKU 表格显示完整大货字段 + 仓储列
6. 验证：点击「自定义 option」可展开单 SKU 独立配置
7. 验证：勾选 SKU + 填写仓储信息 + 选择 option → 提交 → 后端成功创建大货单
8. 验证：返回 summary 含 new_order_sn
