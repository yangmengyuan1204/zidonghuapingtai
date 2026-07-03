# OEM 询价单全流程 - SKU 动态化 + 基础参数移除 + 商品类型下拉

## 概述

OEM 询价单全流程弹窗的三项 UI 改造：
1. SKU 输入从固定 3 组改为动态增删（默认 1 组，可手动添加 N 组）
2. 移除"基础参数"分组（仅含 order_sn 字段，用户不需要）
3. 商品类型（goods_type）从数字输入框改为文字下拉选择

## 当前状态分析

### SKU 输入（固定 3 组）
- Schema 硬编码 6 个字段：`sku1/sku1_num/sku2/sku2_num/sku3/sku3_num`
- 位置：`static/app.js` 第 32-37 行
- 后端 `app/data_scripts.py` 第 9074-9080 行：若 `variables.sku_info` 非列表则用 sku1/sku2/sku3 固定构造 3 项
- 后端已支持 `sku_info` 列表格式，前端只需发送即可

### "基础参数"分组
- 分组逻辑在 `static/app.js` 第 1296 行：遇到第一个 section 前的字段归入"基础参数"
- 当前 schema 中只有 `order_sn`（第 17 行）在第一个 section 之前
- 即"基础参数"分组仅含 order_sn 一个字段

### 商品类型（goods_type）
- Schema 第 23 行：`{ name: "goods_type", label: "商品类型", type: "number", default: 1 }`
- 后端第 9098 行：`"goods_type": int(variables.get("goods_type") or 1)`
- OEM API 模板 `app/core/utils.py` 第 783 行也硬编码 `goods_type: 1`
- 另有 `goods_class`（默认 110）在后端发送但前端不暴露

### 参考模式：工厂链接动态行
- `renderFactoryUrlsDynamic()` 第 1340-1349 行：容器 + 动态行 + 添加按钮
- `renderFactoryUrlRow(idx, value, canDelete)` 第 1333-1338 行：单行渲染
- `syncFactoryUrlsToHidden()` 第 1385-1400 行：同步到隐藏字段
- `renumberFactoryUrlRows()` 第 1403-1424 行：删除后重编号
- 事件绑定第 1471-1488 行：添加/删除按钮

## 改动方案

### 文件1：`static/app.js`

#### 改动 A：移除"基础参数"分组
- **删除** schema 第 17 行 `{ name: "order_sn", label: "询价单号(留空则自动创建)" }`
- 删除后第一个字段就是 `__section_create`，"基础参数"分组为空不会被渲染
- order_sn 仍可在后端自动生成（`variables.get("order_sn")` 为空时自动创建）

#### 改动 B：SKU 动态化
1. **删除** schema 第 32-37 行的 6 个固定 SKU 字段
2. **新增** 字段：`{ name: "sku_info", label: "SKU列表", type: "sku-dynamic" }`，放在 `goods_img` 之后
3. **新增** `renderSkuDynamic()` 函数（参考 `renderFactoryUrlsDynamic()`）：
   - 容器 `#skuContainer`
   - 默认渲染 1 行 SKU（名称 + 数量 + 删除按钮）
   - "+ 添加SKU" 按钮
   - 从 `values.sku_info`（数组或 JSON 字符串）恢复已有数据
4. **新增** `renderSkuRow(idx, skuName, skuNum, canDelete)` 函数：
   - 名称输入框 `name="sku_name_${idx}"`
   - 数量输入框 `name="sku_num_${idx}"` type=number
   - 删除按钮（第 0 行不可删除）
5. **新增** `syncSkuToHidden()` 函数：
   - 遍历 `#skuContainer` 中所有行
   - 收集 `{sku: name, num: Number(num)}` 到数组
   - 写入隐藏字段 `<input type="hidden" name="sku_info">` 的 JSON 字符串
6. **新增** `renumberSkuRows()` 函数（参考 `renumberFactoryUrlRows()`）
7. **新增** `onDeleteSku(idx)` 函数（参考 `onDeleteFactoryUrl()`）
8. 在分组渲染循环（第 1358-1364 行）中增加 `sku-dynamic` 类型处理
9. 在 `formFields` 过滤逻辑（第 1283 行）中排除 `sku-dynamic` 类型（与 `factory-urls-dynamic` 同处理）
10. 添加/删除 SKU 的事件绑定（参考第 1471-1488 行工厂链接的模式）
11. 在 `input` 事件监听（第 1491-1496 行）中增加 SKU 输入的同步
12. 在 submit handler（第 1504-1533 行）中：
    - 调用 `syncSkuToHidden()` 确保 sku_info 已同步
    - 从 `data.sku_info`（JSON 字符串）解析为数组
    - 设置到 `merged.sku_info`
    - 删除旧的 `sku1/sku2/sku3` 残留

#### 改动 C：商品类型下拉
1. **执行时第一步**：调 OEM API 抓取商品类型列表
   - 登录 OEM 后台 `POST /admin/login`
   - 尝试常见端点：`/admin/goodsType`、`/admin/goodsTypeList`、`/admin/goodsClass` 等
   - 若找不到专用接口，从已有询价单详情中提取 `goods_class.class_name` 作为参考
   - 也可检查 OEM 后台前端页面 `https://oemadmin.rakumart.cn` 的 JS 文件
2. 拿到列表后，将 schema 中 `goods_type` 改为 `select` 类型：
   ```javascript
   { name: "goods_type", label: "商品类型", type: "select", default: "1",
     options: [
       { value: "1", label: "文字描述1" },
       // ...
     ] }
   ```
3. 后端无需修改（已支持 `int(variables.get("goods_type") or 1)`）

### 默认值映射表更新
- 第 833-834 行：移除 `sku1/sku2/sku3/sku1_num/sku2_num/sku3_num`
- 添加 `sku_info: [{sku:"sku1", num:1}]`

## 假设与决策

1. **"基础参数"分组仅含 order_sn**：已确认 schema 中 order_sn 是第一个 section 之前的唯一字段
2. **后端 sku_info 已支持列表**：data_scripts.py 第 9074 行逻辑保证前端发列表时直接使用
3. **goods_type 下拉选项需运行时抓取**：OEM API 端点未知，执行时先探测
4. **goods_class 不暴露给前端**：用户未提及，保持默认 110
5. **后端无需修改**：sku_info 列表格式已被后端支持

## 验证步骤

1. 启动 FastAPI 服务器，打开前端
2. 点击"OEM询价单全流程"执行按钮，检查弹窗：
   - 不再有"基础参数"分组
   - SKU 区域默认 1 行（名称+数量），可点"+"添加更多，可删除非首行
   - 商品类型为下拉选择，有文字标签
3. 填入参数执行全流程，检查后端日志：
   - `sku_info` 正确收到 N 项
   - 全流程通过
4. 测试动态增删 SKU 后提交，验证数据完整性
