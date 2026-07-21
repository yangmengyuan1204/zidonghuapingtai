# DeepSeek 数据智能体全中文展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 DeepSeek 数据智能体的目标合同、实时事件、权限暂停、最终结果和测试记录汇总全部转换为中文业务展示，同时保留折叠的原始日志。

**Architecture:** 在 `static/data-factory-agent.js` 建立数据智能体专用中文展示层，集中处理字段、节点、工具、事件和枚举值，并导出测试记录渲染函数。`static/app.js` 只负责识别数据智能体聚合日志并调用专用渲染器，其他脚本继续使用现有通用汇总。

**Tech Stack:** 原生 JavaScript、FastAPI 现有静态页面、pytest、Node.js 语法与纯函数行为检查。

## Global Constraints

- 普通用户界面不得显示代码字段名、工具名、节点枚举或状态枚举。
- 只有用户主动展开“查看原始日志”时允许看到原始 JSON。
- 后端接口、数据库、执行合同、AI 配置和数据脚本不变。
- 未知字段显示“其他执行信息”或隐藏，不允许用原代码名兜底。
- 业务编号保留原值，包括订单号、配送单号、客户 ID、问题产品 ID 和测试记录 ID。
- 只修改 `static/data-factory-agent.js`、`static/app.js`、`tests/test_data_factory_agent.py`。
- 使用 `.venv\Scripts\python.exe` 运行 Python 测试，不启动浏览器。
- 使用记录 805、823、824 做只读渲染验收，不执行任何业务操作。
- 保留工作区所有既有改动，不提交、不推送。

---

### Task 1: 建立中文映射与纯格式化接口

**Files:**
- Modify: `tests/test_data_factory_agent.py`
- Modify: `static/data-factory-agent.js:1-32`

**Interfaces:**
- Consumes: 数据智能体接口返回的字段名、节点、工具名、事件类型和枚举值。
- Produces: `fieldLabel(value)`、`nodeLabel(value)`、`toolLabel(value)`、`eventLabel(value)`、`statusLabel(value)`、`operationLabel(value)`、`priceModeLabel(value)`、`quantityRefundLabel(value)`、`freightRefundLabel(value)`、`paymentLabel(value)`、`displayValue(field, value)`、`humanizeText(value)`；通过 `window.DataFactoryAgent.display` 暴露给行为测试和后续渲染任务。

- [ ] **Step 1: 在测试文件中增加 Node 行为测试辅助函数**

```python
import json
import shutil
import subprocess
from pathlib import Path


def _run_data_agent_js(expression: str):
    node = shutil.which("node")
    assert node, "需要Node.js执行数据智能体前端行为测试"
    source_path = json.dumps(str(Path("static/data-factory-agent.js").resolve()))
    script = f"""
global.window = {{}};
const fs = require('fs');
eval(fs.readFileSync({source_path}, 'utf8'));
const value = ({expression});
process.stdout.write(JSON.stringify(value));
"""
    completed = subprocess.run(
        [node, "-e", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)
```

- [ ] **Step 2: 写字段、节点、工具、事件和未知值的失败测试**

```python
def test_data_agent_display_codes_are_mapped_to_chinese():
    result = _run_data_agent_js("({
      field: window.DataFactoryAgent.display.fieldLabel('order_item_num'),
      node: window.DataFactoryAgent.display.nodeLabel('order_offered'),
      tool: window.DataFactoryAgent.display.toolLabel('process_problem_goods'),
      event: window.DataFactoryAgent.display.eventLabel('tool_result'),
      status: window.DataFactoryAgent.display.statusLabel('succeeded'),
      operation: window.DataFactoryAgent.display.operationLabel('problem_goods'),
      priceMode: window.DataFactoryAgent.display.priceModeLabel('goods_total'),
      quantityRefund: window.DataFactoryAgent.display.quantityRefundLabel('all'),
      freightRefund: window.DataFactoryAgent.display.freightRefundLabel('all'),
      payment: window.DataFactoryAgent.display.paymentLabel('bank'),
      message: window.DataFactoryAgent.display.humanizeText('run_full_flow执行成功，current_node=order_offered'),
      unknown: window.DataFactoryAgent.display.fieldLabel('future_internal_key')
    })")

    assert result == {
        "field": "每种商品购买数量",
        "node": "订单待付款",
        "tool": "提出并处理问题产品",
        "event": "工具执行结果",
        "status": "已完成",
        "operation": "处理问题产品",
        "priceMode": "商品金额合计",
        "quantityRefund": "退全部数量",
        "freightRefund": "退全部国内运费",
        "payment": "银行付款并财务入金",
        "message": "创建并推进订单执行成功，当前业务状态=订单待付款",
        "unknown": "其他执行信息",
    }
```

- [ ] **Step 3: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py::test_data_agent_display_codes_are_mapped_to_chinese -q`

Expected: FAIL，原因是 `window.DataFactoryAgent.display` 尚不存在。

- [ ] **Step 4: 在数据智能体前端增加集中映射与无代码兜底函数**

```javascript
const FIELD_LABELS = Object.freeze({
  order_shop_count: "店铺数量",
  order_per_shop: "每店商品种类数",
  order_item_num: "每种商品购买数量",
  keyword: "商品搜索词",
  offer_price: "统一执行单价",
  offer_unit_prices: "逐商品执行单价",
  confirm_price: "采购确认单价",
  confirm_freight: "采购确认国内运费",
  offer_freight: "订单国内运费",
  other_price: "其他费用",
  order_payment_mode: "订单支付方式",
  porder_payment_mode: "配送单支付方式",
  target_node: "目标状态",
  current_node: "当前业务状态",
  detected_start_node: "识别到的起始状态",
  operation_results: "操作完成情况",
  problem_goods_ids: "问题产品编号",
  problem_goods_expected: "问题产品预期结果",
  order_sn: "订单号",
  porder_sn: "配送单号",
  customer_ids: "客户范围",
  child_record_ids: "子执行记录",
  operation_index: "当前操作序号",
  awaiting_permission: "是否等待权限",
  pre_num: "处理后剩余数量",
  pre_price: "处理后商品单价",
  pre_freight: "处理后国内运费",
  problem_num: "问题商品数量",
  status: "执行状态",
  reason: "执行说明",
});

const NODE_LABELS = Object.freeze({
  shopping_cart: "购物车准备完成",
  order_created: "订单已创建",
  order_translated: "订单已翻译",
  order_confirmed: "订单已确认",
  order_offered: "订单待付款",
  order_paid: "订单已付款",
  pending_purchase: "订单待拍下",
  purchase_no_saved: "交易号已保存",
  purchase_wait_modify_price: "采购待改价",
  purchase_wait_pay: "采购待财务付款",
  purchase_paid: "采购已付款",
  checking_started: "采购已开始核查",
  shelf_stored: "商品已上架入库",
  warehouse_delivery_created: "配送单已创建",
  porder_translated: "配送单已翻译",
  porder_confirmed: "配送单已确认",
  porder_wait_offer: "配送单待报价",
  porder_offered: "配送单待付款",
  porder_paid: "配送单已付款",
  full_complete: "全流程已完成",
});

const TOOL_LABELS = Object.freeze({
  run_full_flow: "创建并推进订单",
  resume_order_flow: "继续推进订单",
  resume_porder_flow: "继续推进配送单",
  inspect_order_state: "查询订单实际状态",
  inspect_porder_state: "查询配送单实际状态",
  inspect_problem_goods: "查询问题产品状态",
  process_problem_goods: "提出并处理问题产品",
  add_to_cart: "加入购物车",
  create_order: "创建订单",
  backend_order_flow: "处理后台订单",
  order_balance_payment: "订单余额付款",
  order_bank_payment: "订单银行付款",
  pending_to_shelf: "采购并上架商品",
  warehouse_create_porder: "创建配送单",
  porder_backend_flow: "处理后台配送单",
  porder_balance_payment: "配送单余额付款",
  porder_bank_payment: "配送单银行付款",
});

const EVENT_LABELS = Object.freeze({
  analysis: "目标理解",
  confirmation: "合同确认",
  decision: "执行决策",
  preflight: "执行前安全检查",
  tool_result: "工具执行结果",
  verification: "实际数据校验",
  operation_completed: "操作完成",
  permission: "等待权限",
  permission_resumed: "权限已恢复",
  reconfirmation: "等待补充确认",
  capability_gap: "能力不足",
  guard: "安全保护",
  agent_error: "智能体异常",
  error: "执行异常",
});

const OPERATION_LABELS = Object.freeze({
  advance_order: "推进订单",
  advance_porder: "推进配送单",
  problem_goods: "处理问题产品",
});

const PRICE_MODE_LABELS = Object.freeze({
  goods_total: "商品金额合计",
  uniform_unit: "统一商品单价",
  per_item_unit: "逐商品单价",
  user_unit: "用户指定单价",
  preserve_existing: "保持原订单价格",
  default_unit: "默认商品单价",
  unspecified: "未指定价格",
  ambiguous: "价格口径待确认",
});

const QUANTITY_REFUND_LABELS = Object.freeze({
  all: "退全部数量",
  half: "退一半数量",
  fixed: "退指定数量",
  keep: "数量保持不变",
});

const FREIGHT_REFUND_LABELS = Object.freeze({
  all: "退全部国内运费",
  keep: "国内运费保持不变",
});

const PAYMENT_LABELS = Object.freeze({
  bank: "银行付款并财务入金",
  bank_payment: "银行付款并财务入金",
  balance: "余额付款",
  balance_first: "余额优先",
});

function mappedLabel(mapping, value, unknownText) {
  const key = String(value ?? "").trim();
  return mapping[key] || unknownText;
}

function fieldLabel(value) { return mappedLabel(FIELD_LABELS, value, "其他执行信息"); }
function nodeLabel(value) { return mappedLabel(NODE_LABELS, value, "未识别业务状态"); }
function toolLabel(value) { return mappedLabel(TOOL_LABELS, value, "受控业务操作"); }
function eventLabel(value) { return mappedLabel(EVENT_LABELS, value, "执行进展"); }
function statusLabel(value) { return mappedLabel(STATUS_LABELS, value, "状态待确认"); }
function operationLabel(value) { return mappedLabel(OPERATION_LABELS, value, "执行业务操作"); }
function priceModeLabel(value) { return mappedLabel(PRICE_MODE_LABELS, value, "价格口径待确认"); }
function quantityRefundLabel(value) { return mappedLabel(QUANTITY_REFUND_LABELS, value, "数量处理方式待确认"); }
function freightRefundLabel(value) { return mappedLabel(FREIGHT_REFUND_LABELS, value, "国内运费处理方式待确认"); }
function paymentLabel(value) { return mappedLabel(PAYMENT_LABELS, value, "支付方式保持原值"); }

function displayValue(field, value) {
  if (typeof value === "boolean") return value ? "是" : "否";
  if (value === null || value === undefined || value === "") return "未产生";
  if (["target_node", "current_node", "detected_start_node"].includes(field)) return nodeLabel(value);
  if (field === "status") return statusLabel(value);
  return String(value);
}

function humanizeText(value) {
  let text = String(value ?? "");
  const replacements = {
    stop_after_node: "目标停止状态",
    current_node: "当前业务状态",
    target_node: "目标状态",
    ...NODE_LABELS,
    ...TOOL_LABELS,
  };
  Object.entries(replacements)
    .sort(([left], [right]) => right.length - left.length)
    .forEach(([code, label]) => { text = text.split(code).join(label); });
  return text;
}
```

将导出对象改为：

```javascript
window.DataFactoryAgent = {
  mount,
  display: {
    fieldLabel, nodeLabel, toolLabel, eventLabel, statusLabel,
    operationLabel, priceModeLabel, quantityRefundLabel, freightRefundLabel, paymentLabel,
    displayValue, humanizeText,
  },
};
```

同时将 `statusBadge` 的文字来源改为 `statusLabel(status)`，不得使用 `status` 原值兜底。

- [ ] **Step 5: 运行行为测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py::test_data_agent_display_codes_are_mapped_to_chinese -q`

Expected: PASS。

### Task 2: 中文化实时合同、事件和最终结果

**Files:**
- Modify: `tests/test_data_factory_agent.py`
- Modify: `static/data-factory-agent.js:33-145`

**Interfaces:**
- Consumes: Task 1 的全部中文映射函数，重点使用 `fieldLabel`、`nodeLabel`、`toolLabel`、`eventLabel`、`statusLabel`、`operationLabel`、`priceModeLabel`、`quantityRefundLabel`、`freightRefundLabel`、`paymentLabel`、`displayValue`、`humanizeText`。
- Produces: `goalHtml(goal, session, escapeHtml)`、`eventsHtml(events, escapeHtml)`、`renderResult(result, currentState, recordId, escapeHtml)`，普通页面不出现内部代码字段或枚举值。

- [ ] **Step 1: 增加完整弹窗片段的失败测试**

```python
def test_data_agent_visible_sections_hide_internal_codes():
    expression = """window.DataFactoryAgent.renderVisible({
      status: 'succeeded',
      plan_version: 2,
      record_id: 823,
      goal: {
        target_node: 'order_offered',
        target_label: '',
        variables: {order_item_num: 1, offer_price: '500'},
        defaults_used: [{field: 'order_item_num', value: 1}],
        intent: {corrections: [{field: 'target_node', reason: '根据原话纠正'}]},
        operations: [{type: 'advance_order', target_node: 'order_offered'}]
      },
      events: [{kind: 'tool_result', tool: 'run_full_flow', message: 'run_full_flow执行成功', passed: true, time: '2026-07-16 12:00:00'}],
      result: {reason: 'current_node=order_offered，全部完成', status: 'succeeded', current_node: 'order_offered', order_sn: 'ORDER-1', operation_results: {}},
      current_state: {}
    }, value => String(value))"""
    html = _run_data_agent_js(expression)

    for code in ["order_item_num", "target_node", "run_full_flow", "tool_result", "order_offered", "succeeded", "operation_results"]:
        assert code not in html
    for text in ["每种商品购买数量", "订单待付款", "创建并推进订单", "工具执行结果", "已完成"]:
        assert text in html
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py::test_data_agent_visible_sections_hide_internal_codes -q`

Expected: FAIL，原因是 `renderVisible` 尚未导出，现有页面仍直接显示字段名和工具名。

- [ ] **Step 3: 改造目标合同渲染**

实现以下规则：

```javascript
const defaults = (goal.defaults_used || [])
  .filter(item => FIELD_LABELS[item.field])
  .map(item => `${fieldLabel(item.field)}：${displayValue(item.field, item.value)}`)
  .join("；");

const corrections = (intent.corrections || [])
  .map(item => `${fieldLabel(item.field)}：${item.reason || "已按用户原话纠正"}`)
  .join("；");

const operationName = operationLabel(operation.type);

const targetText = operation.target_node ? nodeLabel(operation.target_node) : "完成已确认的后置操作";
```

目标状态只使用 `goal.target_label` 或 `nodeLabel(goal.target_node)`；不得回退到原始 `target_node`。价格口径、退款数量模式、国内运费退款模式和支付方式分别调用 `priceModeLabel`、`quantityRefundLabel`、`freightRefundLabel`、`paymentLabel`，不得在渲染函数中重新编写枚举判断。

- [ ] **Step 4: 改造实时事件渲染**

```javascript
const title = event.kind === "tool_result"
  ? `${toolLabel(event.tool)}：${event.passed ? "执行成功" : "执行失败"}`
  : humanizeText(event.message || eventLabel(event.kind));
const toolText = event.tool ? toolLabel(event.tool) : "";
const stateText = event.current_node ? nodeLabel(event.current_node) : "";
```

事件详情只展示中文工具名、预期结果、中文节点和时间；不显示 `event.kind`、`event.tool`、`current_node` 的原始值。

- [ ] **Step 5: 实现结构化最终结果渲染**

```javascript
function renderRows(rows, escapeHtml) {
  return `<table class="summary-table"><tbody>${rows.map(([label, value]) => (
    `<tr><td class="summary-label">${escapeHtml(label)}</td><td class="summary-value">${escapeHtml(value)}</td></tr>`
  )).join("")}</tbody></table>`;
}

function renderResult(result, currentState, recordId, escapeHtml) {
  const value = result || {};
  const orderSn = value.order_sn || currentState?.order_sn || "未产生";
  const porderSn = value.porder_sn || currentState?.porder_sn || "未产生";
  const actualNode = value.current_node || currentState?.current_node || currentState?.detected_start_node;
  const problemIds = Array.isArray(value.problem_goods_ids) ? value.problem_goods_ids.join("、") : "未产生";
  const rows = [
    ["执行结果", statusLabel(value.status)],
    ["执行说明", humanizeText(value.reason || "未提供执行说明")],
    ["订单号", orderSn],
    ["配送单号", porderSn],
    ["实际业务状态", actualNode ? nodeLabel(actualNode) : "未识别"],
    ["问题产品编号", problemIds || "未产生"],
    ["聚合测试记录", recordId ? `#${recordId}` : "未产生"],
  ];
  return `<section class="panel"><div class="panel-title"><h3>最终结果</h3></div><div class="panel-body">${renderRows(rows, escapeHtml)}</div></section>`;
}
```

问题产品结果额外读取 `problem_goods_expected` 和 `operation_results` 中的 `items`，按“问题产品编号、处理状态、处理前数量、处理后数量、处理后单价、处理后国内运费”展示；遍历对象时只读取白名单字段，不渲染未知键。

- [ ] **Step 6: 增加并导出纯渲染入口**

```javascript
function renderVisible(session, escapeHtml) {
  const sections = [
    goalHtml(session.goal, session, escapeHtml),
    eventsHtml(session.events, escapeHtml),
  ];
  if (session.result && Object.keys(session.result).length) {
    sections.push(renderResult(session.result, session.current_state, session.record_id, escapeHtml));
  }
  return sections.join("");
}
```

将 `renderVisible` 加入 `window.DataFactoryAgent`，页面 `renderModal` 复用相同函数，避免测试入口和实际页面逻辑分叉。

同步把现有 `goalHtml(goal, escapeHtml)` 改为 `goalHtml(goal, session, escapeHtml)`，合同状态和版本从传入的 `session` 读取；`renderModal` 调用 `goalHtml(session.goal, session, escapeHtml)`，不再依赖纯渲染测试无法设置的全局会话。

- [ ] **Step 7: 运行行为测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py::test_data_agent_visible_sections_hide_internal_codes -q`

Expected: PASS。

### Task 3: 数据智能体测试记录使用专用中文渲染

**Files:**
- Modify: `tests/test_data_factory_agent.py`
- Modify: `static/data-factory-agent.js`
- Modify: `static/app.js:showLog`

**Interfaces:**
- Consumes: `goalHtml`、`eventsHtml`、`renderResult`、`renderVisible`。
- Produces: `window.DataFactoryAgent.renderRecordSummary(parsedLog, escapeHtml) -> string`；`showLog` 在 `parsed.script === "DeepSeek数据智能体"` 时调用。

- [ ] **Step 1: 增加数据智能体记录渲染失败测试**

```python
def test_data_agent_record_summary_is_chinese_and_keeps_raw_log_path():
    expression = """window.DataFactoryAgent.renderRecordSummary({
      script: 'DeepSeek数据智能体',
      goal: {target_node: 'pending_purchase', variables: {order_item_num: 2}},
      events: [{kind: 'tool_result', tool: 'process_problem_goods', message: ''}],
      summary: {
        status: 'succeeded', reason: '全部完成', current_node: 'pending_purchase',
        order_sn: 'ORDER-2', problem_goods_ids: [895193], future_internal_key: 'secret-code'
      }
    }, value => String(value))"""
    html = _run_data_agent_js(expression)

    for code in ["pending_purchase", "order_item_num", "process_problem_goods", "future_internal_key"]:
        assert code not in html
    for text in ["订单待拍下", "每种商品购买数量", "提出并处理问题产品", "895193"]:
        assert text in html

    app_source = Path("static/app.js").read_text(encoding="utf-8")
    assert 'parsed?.script === "DeepSeek数据智能体"' in app_source
    assert "DataFactoryAgent?.renderRecordSummary" in app_source
    assert "查看原始日志" in app_source
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py::test_data_agent_record_summary_is_chinese_and_keeps_raw_log_path -q`

Expected: FAIL，原因是专用记录渲染函数和 `showLog` 分流尚不存在。

- [ ] **Step 3: 在数据智能体模块实现记录渲染函数**

```javascript
function renderRecordSummary(parsedLog, escapeHtml) {
  if (!parsedLog || parsedLog.script !== "DeepSeek数据智能体") {
    return '<div class="empty">数据智能体结果暂时无法展示</div>';
  }
  const session = {
    status: parsedLog.summary?.status,
    plan_version: 1,
    goal: parsedLog.goal || {},
    events: parsedLog.events || [],
    result: parsedLog.summary || {},
    current_state: parsedLog.summary || {},
    record_id: null,
  };
  return renderVisible(session, escapeHtml);
}
```

导出 `renderRecordSummary`，函数不得包含原始 JSON 或未知字段的值。

- [ ] **Step 4: 在 `showLog` 中增加数据智能体专用分流**

在解析 `rawText` 后、通用 `renderChineseSummary` 前增加：

```javascript
const isDataAgentLog = parsed?.script === "DeepSeek数据智能体";
if (isDataAgentLog) {
  const renderer = window.DataFactoryAgent?.renderRecordSummary;
  const summaryHtml = renderer
    ? renderer(parsed, escapeHtml)
    : '<div class="empty">数据智能体结果暂时无法展示</div>';
  modalEl.innerHTML = `
    <div class="modal-head">
      <h3>数据智能体执行结果 #${item.id}</h3>
      <button class="btn secondary" type="button" id="closeModal">关闭</button>
    </div>
    <div class="modal-body">
      <div class="summary-wrap">${summaryHtml}</div>
      <details class="summary-detail"><summary>查看原始日志</summary><pre class="log-view">${escapeHtml(rawText)}</pre></details>
    </div>`;
  modalEl.showModal();
  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
  return;
}
```

- [ ] **Step 5: 运行记录渲染测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py::test_data_agent_record_summary_is_chinese_and_keeps_raw_log_path -q`

Expected: PASS。

### Task 4: 只读真实记录验收与完整回归

**Files:**
- Verify: `static/data-factory-agent.js`
- Verify: `static/app.js`
- Verify: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: `window.DataFactoryAgent.renderRecordSummary` 和数据库中记录 805、823、824 的原始聚合日志。
- Produces: 三类历史结果的中文渲染验收结论，不产生业务调用。

- [ ] **Step 1: 运行数据智能体完整测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -q`

Expected: PASS。

- [ ] **Step 2: 运行相关权限和问题产品回归**

Run: `.venv\Scripts\python.exe -m pytest tests/test_problem_goods_script.py tests/test_permissions.py -q`

Expected: PASS。

- [ ] **Step 3: 运行 JavaScript 语法检查**

Run: `node --check static/data-factory-agent.js`

Expected: 无输出，退出码 0。

Run: `node --check static/app.js`

Expected: 无输出，退出码 0。

- [ ] **Step 4: 使用历史记录做只读渲染验收**

Run:

```powershell
$env:PYTHONIOENCODING='utf-8'; @'
import json
import shutil
import subprocess
from pathlib import Path

from app.database import SessionLocal
from app.models import TestRecord

node = shutil.which("node")
assert node, "未找到Node.js"
source_path = json.dumps(str(Path("static/data-factory-agent.js").resolve()))
node_script = f"""
global.window = {{}};
const fs = require('fs');
eval(fs.readFileSync({source_path}, 'utf8'));
const parsed = JSON.parse(fs.readFileSync(0, 'utf8'));
const escapeHtml = value => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;').replaceAll('"', '&quot;');
process.stdout.write(window.DataFactoryAgent.renderRecordSummary(parsed, escapeHtml));
"""
forbidden = [
    "order_item_num", "target_node", "run_full_flow", "process_problem_goods",
    "operation_results", "current_node", "order_offered", "pending_purchase", "succeeded",
]

db = SessionLocal()
try:
    for record_id in (805, 823, 824):
        record = db.get(TestRecord, record_id)
        assert record, f"记录{record_id}不存在"
        parsed = json.loads(record.log)
        assert parsed.get("script") == "DeepSeek数据智能体", f"记录{record_id}不是数据智能体聚合日志"
        completed = subprocess.run(
            [node, "-e", node_script],
            input=json.dumps(parsed, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        html = completed.stdout
        leaked = [code for code in forbidden if code in html]
        assert not leaked, f"记录{record_id}泄漏代码字段：{leaked}"
        assert any(text in html for text in ("已完成", "已阻止", "等待补充确认", "执行说明"))
        print(f"记录{record_id}：通过")
finally:
    db.close()
'@ | .venv\Scripts\python.exe -
```

脚本只读取数据库并在内存中调用渲染器，不写文件、不调用执行接口、不更新数据库。

Expected: 三条记录全部通过；若某条历史记录不是聚合日志，报告其结构差异并使用同类型最近聚合记录替代，不执行业务。

- [ ] **Step 5: 检查工作区范围**

Run: `git status --short`

Run: `git diff --stat`

Expected: 本次代码范围只有 `static/data-factory-agent.js`、`static/app.js`、`tests/test_data_factory_agent.py`，另有已确认的设计和计划文档；其他既有修改保持原样。

- [ ] **Step 6: 汇报结果**

汇报中文展示覆盖、真实记录只读验收、测试结果和任何未映射但已安全隐藏的字段。明确说明未提交、未推送、未启动浏览器、未执行业务操作。
