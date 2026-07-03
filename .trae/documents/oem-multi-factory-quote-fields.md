# OEM 询价单全流程 - 报价阶段按工厂数量展开多组报价字段

## 背景

当前 OEM 询价单全流程脚本在「报价阶段」的 8 个金额字段（`samples_price` / `large_price` / `large_other_fee` / `large_freight` / `large_delivery_time` / `large_deposit_rate` / `real_samples_price` / `real_large_price`）是**全局共享**的，所有工厂共用同一组值。

但实际业务中，一个 SKU 询价会调查多家工厂（如 3 个），每家工厂的报价数据都不同，需要为每个工厂独立填写这 8 个字段。

## 用户确认的方案

1. **工厂数量来源**：按 `factory_urls` textarea 的行数自动展开（用户在「询价单提出」section 填几个链接，「报价阶段」就展开几组）
2. **字段范围**：仅「报价阶段」8 个金额字段按工厂独立；`factory_img` / `salesman` / `salesman_phone` 仍所有工厂共用（保留在「询价阶段」section 不变）
3. **展示方式**：在「报价阶段」section 内，每个工厂一个子 `<details>` 折叠块（如「工厂1报价」「工厂2报价」），默认展开

## 当前实现分析

### 前端 `static/app.js`

- `SCRIPT_PARAM_SCHEMAS.oem_full_inquiry_flow`（第 15-50 行）：4 个 section，「报价阶段」section 含 8 个标量字段
- `renderFormField`（第 101-105 行）：支持 text/textarea/select/checkbox/upload/number，**不支持动态重复组**
- `openOemFullInquiryFlowRunForm`（第 1230-1286 行）：读 schema → 按 section 分组渲染 `<details>` → 提交时 `mergeParamValues` 把 form data 合并到 variables
- `mergeParamValues`（第 101 行附近）：按 `fields` 的 name 遍历，name 必须静态存在于 fields 才会写入 variables

### 后端 `app/data_scripts.py` `run_oem_full_inquiry_flow_script`

- 阶段3（第 9163-9273 行）：循环 `detail_list`（每工厂一条），但循环外（9187-9195）只读一次 `variables.get("samples_price")` 等，循环内所有 `d_item` 共用同一组值
- 阶段4（第 9277-9330 行）：`factoryQuoteToUser` 不覆盖金额，沿用阶段3 写入的值

### 数据流

```
factory_urls (textarea, N 行)
  → /api/newInquiry 后端按行生成 N 条 detail_list
  → 阶段3 循环 detail_list，每条 factoryQuote 时所有工厂用同一组 variables.samples_price 等
```

## 提议改动

### 改动1：后端 `app/data_scripts.py` 阶段3 支持 `factory_quotes` 数组

**位置**：`run_oem_full_inquiry_flow_script` 阶段3（约第 9187-9260 行）

**改动**：
- 循环外保留原 8 个全局变量读取，作为**兜底默认值**（向后兼容旧 variables）
- 新增：读取 `factory_quotes = variables.get("factory_quotes") or []`（数组，每元素是 dict 含 8 个字段）
- 循环内（`for idx, d_item in enumerate(detail_list)`）：按 `idx` 从 `factory_quotes` 取该工厂的报价字段，缺失时用全局默认

```python
factory_quotes = variables.get("factory_quotes") or []
# 循环外全局默认（向后兼容）
samples_price_default = variables.get("samples_price") or "12.00"
large_price_default = variables.get("large_price") or "11.00"
large_other_fee_default = variables.get("large_other_fee") or "12.00"
large_freight_default = variables.get("large_freight") or "11.00"
large_delivery_time_default = int(variables.get("large_delivery_time") or 15)
large_deposit_rate_default = variables.get("large_deposit_rate") or "100"
real_samples_price_default = variables.get("real_samples_price") or "10.00"
real_large_price_default = variables.get("real_large_price") or "10.00"

for idx, d_item in enumerate(detail_list):
    fq = factory_quotes[idx] if idx < len(factory_quotes) and isinstance(factory_quotes[idx], dict) else {}
    samples_price = fq.get("samples_price") or samples_price_default
    large_price = fq.get("large_price") or large_price_default
    large_other_fee = fq.get("large_other_fee") or large_other_fee_default
    large_freight = fq.get("large_freight") or large_freight_default
    large_delivery_time = int(fq.get("large_delivery_time") or large_delivery_time_default)
    large_deposit_rate = fq.get("large_deposit_rate") or large_deposit_rate_default
    real_samples_price = fq.get("real_samples_price") or real_samples_price_default
    real_large_price = fq.get("real_large_price") or real_large_price_default
    # ... 后续 quote_body 构造逻辑用上面这些本地变量
```

**为什么这样改**：
- 旧 variables（无 `factory_quotes`）：`fq = {}`，全部用全局默认，行为完全不变
- 新 variables（有 `factory_quotes`）：按 idx 取，每工厂独立
- 不破坏现有 `oem_factory_quote` 用例模板（它仍是单工厂 body 模板）

### 改动2：前端 `static/app.js` 报价阶段动态展开多组

**位置**：`openOemFullInquiryFlowRunForm`（第 1230-1286 行）

**改动**：
1. 渲染时，对「报价阶段」section 特殊处理：
   - 读当前 `factory_urls` 值（从 variables），按 `\n` 拆分得工厂数 N
   - 为每个工厂生成一个子 `<details open>` 块，summary = `工厂{i+1}报价`（如 `工厂1报价`/`工厂2报价`）
   - 块内 8 个字段，name 用 `__fq_{idx}__{fieldName}`（如 `__fq_0__samples_price`），避免与全局字段名冲突
   - 默认值：优先用 `variables.factory_quotes[idx][field]`，缺失时用 `variables[fieldName]` 全局默认
2. 监听 `factory_urls` textarea 的 `input` 事件：行数变化时重新渲染报价阶段子块（保留已填值）
3. 提交时（form submit）：在 `mergeParamValues` 之前，先把所有 `__fq_N__xxx` 字段聚合为 `factory_quotes` 数组写入 variables，然后删除扁平的 `__fq_*` 键

**伪代码**：
```js
function openOemFullInquiryFlowRunForm(flow) {
  let variables = parseJsonText(flow.variables || "{}", {});
  const fields = SCRIPT_PARAM_SCHEMAS.oem_full_inquiry_flow;
  // ... 现有逻辑

  // 特殊处理：报价阶段按 factory_urls 展开多组
  const factoryUrlsValue = variables.factory_urls || "";
  const factoryCount = splitParamList(factoryUrlsValue).length || 1;
  const quoteFields = ["samples_price","large_price","large_other_fee","large_freight",
                       "large_delivery_time","large_deposit_rate","real_samples_price","real_large_price"];
  const factoryQuotes = variables.factory_quotes || [];

  // 渲染报价阶段时：
  for (let i = 0; i < factoryCount; i++) {
    const fq = factoryQuotes[i] || {};
    bodyHtml += `<details open><summary>工厂${i+1}报价</summary><div class="form-grid">`;
    for (const fn of quoteFields) {
      const fieldDef = FIELDS_BY_NAME[fn]; // 原 schema 里的字段定义
      const fieldWithNameSuffix = { ...fieldDef, name: `__fq_${i}__${fn}` };
      const val = fq[fn] ?? variables[fn] ?? fieldDef.default ?? "";
      bodyHtml += renderFormField(fieldWithNameSuffix, val);
    }
    bodyHtml += `</div></details>`;
  }

  // 监听 factory_urls 变化重渲染
  // ...

  // 提交时聚合
  form.addEventListener("submit", (e) => {
    const data = readForm(form);
    const fqList = [];
    const fc = splitParamList(data.factory_urls || "").length || 1;
    for (let i = 0; i < fc; i++) {
      const entry = {};
      for (const fn of quoteFields) {
        const k = `__fq_${i}__${fn}`;
        if (data[k] !== undefined && data[k] !== "") entry[fn] = String(data[k]);
      }
      fqList.push(entry);
    }
    const runtimeVariables = { ...variables, ...其他字段, factory_quotes: fqList };
    // 删除扁平 __fq_* 键（readForm 已不包含，mergeParamValues 也不写入）
    // ...
  });
}
```

**为什么这样改**：
- 不破坏 `renderFormField`（仍用扁平 name）
- 不破坏 `mergeParamValues`（`__fq_*` 不在 fields 里，不会被写入 variables）
- 提交时主动聚合 `__fq_*` → `factory_quotes` 数组，结构清晰
- 监听 factory_urls 变化保证 UI 与工厂数量同步

### 改动3：schema 调整 `static/app.js` `SCRIPT_PARAM_SCHEMAS.oem_full_inquiry_flow`

**位置**：第 41-50 行

**改动**：
- 保留「报价阶段」section 的 8 个字段作为「全局默认值/兜底」（旧 variables 兼容）
- 在 section 标记后增加一个隐藏标记字段 `{ name: "factory_quotes", type: "factory-quotes-group" }`（仅用于 `openOemFullInquiryFlowRunForm` 识别该 section 需要按工厂展开，`renderFormField` 不识别此类型时返回空字符串）

或者更简单：不加标记字段，直接在 `openOemFullInquiryFlowRunForm` 里硬编码判断 `g.label === "报价阶段"` 时走特殊渲染分支。**选这个，更少改动**。

## 不改动

- `app/core/utils.py` 的 `OEM_DATA_SCRIPT_API_CASES`（用例模板仍是单工厂 body，用于单接口调试，不影响全流程）
- `app/routers/data_scripts.py`（路由不变）
- 「询价阶段」的 `factory_img`/`salesman`/`salesman_phone`（仍所有工厂共用）
- 「翻译阶段」字段

## 假设与决策

1. **字段命名约定**：前端临时字段用 `__fq_{idx}__{fieldName}` 前缀，提交时聚合为 `factory_quotes` 数组。避免污染 variables 扁平空间。
2. **工厂数量 = factory_urls 非空行数**：用 `splitParamList`（已存在，按 `\n,，;；` 分割）。空行/空值忽略。
3. **默认展开子块**：`<details open>`，让用户一眼看到所有工厂字段。
4. **factory_quotes 数组长度 > detail_list 长度时**：后端只取前 N 个（N = detail_list 长度），多余的忽略不报错。
5. **factory_quotes 数组长度 < detail_list 长度时**：缺的工厂用全局默认值（向后兼容）。
6. **factory_urls 改变时保留已填值**：重渲染时优先从当前 form 的 `__fq_*` 字段读已填值，再 fallback 到 variables.factory_quotes，再 fallback 到全局默认。

## 验证步骤

1. **后端单测**：用 3 个 factory_urls 跑 `run_oem_full_inquiry_flow_script`，variables 里设 `factory_quotes: [{samples_price:"1.00",...}, {samples_price:"2.00",...}, {samples_price:"3.00",...}]`，验证完成后查询 detail_list 各工厂的 `sku_detail[0].samples_price` 是否分别为 1.00 / 2.00 / 3.00。
2. **向后兼容**：用旧 variables（无 `factory_quotes`，只有全局 `samples_price:"12.00"`）跑全流程，验证所有工厂 samples_price 都是 12.00，行为与改动前一致。
3. **前端 UI 验证**：在数据脚本页打开 OEM询价单全流程执行弹窗，在「询价单提出」section 的 factory_urls 填 3 行链接，确认「报价阶段」section 自动展开 3 个子折叠块「工厂1报价」「工厂2报价」「工厂3报价」，每组 8 个字段；改 factory_urls 为 2 行，确认子块变 2 个；填不同值执行，确认后端收到正确的 `factory_quotes` 数组。
4. **git commit**：自测通过后提交。

## 文件清单

- `app/data_scripts.py`（阶段3 循环按 idx 取 factory_quotes）
- `static/app.js`（`openOemFullInquiryFlowRunForm` 动态渲染 + 聚合提交 + factory_urls 监听）
