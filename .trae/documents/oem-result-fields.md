# OEM 执行结果补充缺失字段

## 概要

OEM 询价单全流程执行成功后，结果弹窗缺少 5 个业务字段：样品费退还、其他费用、样品运费、打样货期、工厂图片。需在后端 summary 中补齐这些字段，并在前端 LABEL_MAP 中补充中文标签映射；工厂图片需渲染为 `<img>` 而非纯 URL 文本。

## 现状分析

### 后端 `app/data_scripts.py`（第 9400-9401 行）

```python
summary = {"order_sn": order_sn, "reason": "OEM 询价单全流程执行成功"}
return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, True, summary)
```

- summary 仅含 `order_sn` 与 `reason`，未放入任何报价业务字段。
- 在该行之前，`detail_list` 已在作用域内可用（来自第 9384 行报价阶段重新查询，或询价阶段后的 detail_list），可直接取 `detail_list[0]` 与其 `sku_detail[0]`。
- factoryQuote 请求体（第 9295-9319 行）已包含 `samples_other_fee`、`samples_freight`、`samples_delivery_time`、`large_other_fee`、`factory_img` 等字段，提交后 OEM 后台返回的 inquiryDetail 中 `detail_list[0]` 与 `sku_detail[0]` 即含最终值。

### 前端 `static/app.js`（第 676 行 `renderChineseSummary`）

- LABEL_MAP 未覆盖：`samples_price_return`、`samples_other_fee`、`samples_freight`、`samples_delivery_time`、`factory_img`。
- 渲染 entries 时统一 `escapeHtml(display)`，对 `factory_img` 会输出 URL 文本而非图片。
- 已有参考：`renderQuoteResult` 的 `infoFields`（第 1220-1231 行）含相同字段中文标签可复用。

### 字段来源映射

| 用户需求字段 | 后端字段 | 数据位置 |
|---|---|---|
| 样品费退还 | `samples_price_return` | `detail_list[0].sku_detail[0]` |
| 其他费用 | `samples_other_fee` | `detail_list[0]` |
| 样品运费 | `samples_freight` | `detail_list[0]` |
| 打样货期 | `samples_delivery_time` | `detail_list[0]` |
| 工厂图片 | `factory_img` | `detail_list[0]` |

## 改动点

### 改动1：后端 `app/data_scripts.py` 第 9400 行 — summary 补充 5 字段

在构建 summary 前，安全取 `detail_list[0]` 与其 `sku_detail[0]`，将 5 个字段加入 summary。

```python
final_detail = detail_list[0] if detail_list else {}
final_sku_list = final_detail.get("sku_detail") or []
final_sku = final_sku_list[0] if final_sku_list else {}
summary = {
    "order_sn": order_sn,
    "reason": "OEM 询价单全流程执行成功",
    "samples_price_return": final_sku.get("samples_price_return") or "0.00",
    "samples_other_fee": final_detail.get("samples_other_fee") or "0.00",
    "samples_freight": final_detail.get("samples_freight") or "0.00",
    "samples_delivery_time": final_detail.get("samples_delivery_time") or 0,
    "factory_img": final_detail.get("factory_img") or "",
}
return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, True, summary)
```

- 不新增 API 调用，直接复用作用域内 `detail_list`（第 9384 行已重新查询）。
- `detail_list` 为空（极端跳过场景）时字段给默认空值，不报错。
- 保留 `reason` 字段不变（前端需求B 已实现成功时删除 reason，不受影响）。

### 改动2：前端 `static/app.js` 第 676 行 LABEL_MAP — 新增 5 字段中文标签

在 LABEL_MAP 中（建议放在 `order_sn` 映射附近）追加：

```javascript
samples_price_return: "样品费退还(元)",
samples_other_fee: "样品其他费用",
samples_freight: "样品运费(元)",
samples_delivery_time: "打样货期(天)",
factory_img: "工厂图片",
```

### 改动3：前端 `static/app.js` `renderChineseSummary` 渲染逻辑 — factory_img 渲染为图片

在渲染 entries 的 `<td class="summary-value">` 处，对 `factory_img` 字段特殊处理为 `<img>`，其余字段保持原 escapeHtml 逻辑。

修改前（压缩代码内）：
```javascript
return `<tr><td class="summary-label">${escapeHtml(label)}</td><td class="summary-value">${escapeHtml(display)}</td></tr>`;
```

修改后：
```javascript
const cellHtml = key === 'factory_img' && val
  ? `<img src="${escapeHtml(String(val))}" style="max-width:200px;max-height:200px" />`
  : escapeHtml(display);
return `<tr><td class="summary-label">${escapeHtml(label)}</td><td class="summary-value">${cellHtml}</td></tr>`;
```

- `factory_img` 为空时走 `escapeHtml(display)`，展示空字符串。
- URL 经 `escapeHtml` 转义后放入 src，防 XSS。

## 假设与决策

1. **"其他费用" = `samples_other_fee`（样品其他费用）**：用户并列提及"样品运费""打样货期"（均样品阶段），故"其他费用"取样品阶段；若用户实际需要 `large_other_fee`（大货其他费用），可在 LABEL_MAP 与 summary 中追加同一字段来源。
2. **"样品费退还" = `samples_price_return`**：取 `sku_detail[0]` 的值；多 SKU 场景仅展示第一个 SKU 的值（OEM 询价单通常一工厂一 detail，SKU 可能多个但退还金额常一致）。
3. **工厂图片渲染为 `<img>`**：用户明确"图片要展示"，纯 URL 不直观。
4. **不新增 API 调用**：复用作用域内 `detail_list`，最小改动。
5. **保留 `reason` 字段**：前端需求B 已在成功时删除 reason，后端无需改动该逻辑。

## 验证步骤

1. 后端改动后语法检查：`python -m py_compile app/data_scripts.py`
2. 触发一次 OEM 全流程执行，确认返回 summary 含 5 个新字段。
3. 前端执行结果弹窗：5 字段中文标签正确展示；工厂图片渲染为缩略图；其余字段不受影响。
4. 失败场景验证：执行失败时仍展示 `reason`（失败原因），新字段可缺省。
