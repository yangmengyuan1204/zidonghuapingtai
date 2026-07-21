# 数据智能体自然语言命中率提升 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展确定性意图提取覆盖 + 补全 few-shot 示例，将自然语言命中率从 <50% 提升至 75-85%。

**Architecture:** Prompt 层重构（SYSTEM_PROMPT + few-shot + action prompt）已在前序工作中完成。本次实施聚焦：(1) `reduce_intent_fields` 追加订单号/番号/问题产品/支付方式等确定性提取 (2) few-shot 示例补上用户真实失败案例 (3) 回归测试。

**Tech Stack:** Python 3.11, regex, pytest + monkeypatch

## Global Constraints

- 不修改数据库表结构、API 接口签名、工具注册、执行流程、校验逻辑
- 保持现有 `reduce_intent_fields` 函数签名和返回值格式不变
- 现有 `tests/test_data_factory_agent.py` 全部用例必须继续通过
- 用 `.venv\Scripts\python.exe` 运行测试

---

### Task 1: 扩展 `reduce_intent_fields` — 订单号 + 番号 + 问题产品

**Files:**
- Modify: `app/services/data_factory_agent_intent.py:34-171`

**Interfaces:**
- Consumes: 现有 `reduce_intent_fields(state, message)` 签名
- Produces: 新增 `resolved_fields` 中的 `order_sn`、`item_index`、`problem_goods_op` 等键

- [ ] **Step 1: 在 `reduce_intent_fields` 追加订单号提取**

在函数中 `target_patterns` 之后、`per_shop_phrase` 之前插入：

```python
    # --- 订单号提取 ---
    order_sn_long = re.search(r"(\d{16}-\d+)", text)  # 2026071715475684-300001 格式
    order_sn_general = re.search(
        r"(?:订单|订单号|order[. _-]*sn|SN)[. _-]*[：:]*\s*([A-Za-z0-9_-]{6,})",
        text, re.IGNORECASE,
    )
    order_sn_match = order_sn_long or order_sn_general
    if order_sn_match:
        resolve("order_sn", order_sn_match.group(1), order_sn_match.group(0))
```

- [ ] **Step 2: 追加番号提取**

紧接着：

```python
    # --- 番号提取（"1番" / "第2番" / "番1"）---
    item_index_match = re.search(r"(?:第\s*)?(\d+)\s*番", text)
    if item_index_match:
        resolve("item_index", int(item_index_match.group(1)), item_index_match.group(0))
```

- [ ] **Step 3: 追加问题产品操作识别**

紧接着：

```python
    # --- 问题产品操作识别 ---
    problem_goods_patterns = (
        (r"提出.*?问题产品", "提出问题产品"),
        (r"处理.*?问题产品", "处理问题产品"),
        (r"退.*?问题产品", "退问题产品"),
    )
    for pattern, label in problem_goods_patterns:
        pg_match = re.search(pattern, text, re.IGNORECASE)
        if pg_match:
            resolve("problem_goods_op", label, pg_match.group(0))
            break
```

- [ ] **Step 4: 追加单价/价格"改成0"的特殊处理（问题产品退款场景）**

在现有价格提取逻辑的 **`total_price` 之前**添加：

```python
    # --- 问题产品退款：单价改成0 ---
    refund_unit_price = re.search(
        r"(?:单价|报价|价格|offer.?price)\s*(?:改成|改为|调整为|变成|是|为|=|:)\s*0",
        text, re.IGNORECASE,
    )
    if refund_unit_price:
        resolve(
            "pricing",
            {"mode": "uniform_unit", "amount": "0", "amounts": [], "refund_context": True},
            refund_unit_price.group(0),
        )
```

然后修改现有价格提取的 `if total_price:` 为 `elif total_price:`，确保退款场景优先命中后不再被后续价格模式覆盖。具体：将 `if total_price:` 改为 `if not fields.get("pricing") and total_price:`，将后续 `elif` 改为对应的条件判断。更简洁的方案是用 `elif` 链在 refund 之后：

将
```python
    if total_price:
```
改为
```python
    if refund_unit_price:
        pass  # 已在上面处理
    elif total_price:
```

- [ ] **Step 5: 追加支付方式提取**

在 `unchanged` 检测之前：

```python
    # --- 支付方式提取 ---
    payment_mode_match = re.search(
        r"(?:支付方式|付款方式)(?:改成|改为|是|为|=|:)?\s*(银行|余额|合并)",
        text, re.IGNORECASE,
    )
    if not payment_mode_match:
        payment_mode_match = re.search(
            r"(银行)(?:汇款|支付|入金|转账)",
            text, re.IGNORECASE,
        )
    if not payment_mode_match:
        payment_mode_match = re.search(
            r"(?:用|使用)?(余额)(?:支付|付款)",
            text, re.IGNORECASE,
        )
    if payment_mode_match:
        mode_map = {"银行": "bank", "余额": "balance_first", "合并": "merge"}
        resolved = mode_map.get(payment_mode_match.group(1), payment_mode_match.group(1))
        resolve("order_payment_mode", resolved, payment_mode_match.group(0))
```

- [ ] **Step 6: 追加客户 ID 提取**

```python
    # --- 客户ID提取 ---
    customer_match = re.search(
        r"(?:客户|customer)[. _-]*[：:]*\s*(\d+)",
        text, re.IGNORECASE,
    )
    if customer_match:
        existing = fields.get("customer_ids")
        existing_list = existing.get("value", []) if isinstance(existing, dict) else []
        new_id = customer_match.group(1)
        if new_id not in existing_list:
            resolve("customer_ids", existing_list + [new_id], customer_match.group(0))
```

- [ ] **Step 7: 运行测试确认不破坏现有逻辑**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -v -x
```

- [ ] **Step 8: Commit**

```bash
git add app/services/data_factory_agent_intent.py
git commit -m "feat: extend deterministic intent extraction with order_sn/item_index/problem_goods/payment patterns"
```

---

### Task 2: 补全 few-shot 示例 — 用户真实失败案例

**Files:**
- Modify: `app/services/data_factory_agent_prompts.py:57-60`

**Interfaces:**
- Consumes: `ANALYSIS_FEW_SHOT_EXAMPLES` 字符串常量
- Produces: 示例3 替换为包含用户真实案例的版本

- [ ] **Step 1: 替换示例3 为用户真实案例**

将当前示例3：
```
示例3:
用户消息: "订单SN20240701-001，把问题产品处理掉"
正确输出:
{"status":"ready","goal":{"mode":"resume_order"...}}
```

替换为：

```python
示例3:
用户消息: "帮我把2026071715475684-300001这个订单,1番提出问题产品，单价改成0"
正确输出:
{"status":"ready","goal":{"mode":"resume_order","target_node":"","customer_ids":[],"order_sn":"2026071715475684-300001","porder_sn":"","variables":{"order_item_num":1},"intent":{"target_evidence":"","item_count_evidence":"","quantity_evidence":"","pricing":{"mode":"uniform_unit","amount":"0","amounts":[],"evidence":"单价改成0"}},"operations":[{"type":"problem_goods","target_node":"","evidence":"1番提出问题产品"}],"unhandled_requests":[],"summary":"续跑订单2026071715475684-300001第1番问题产品单价退0","assumptions":["退款针对第1番商品"]}}
```

- [ ] **Step 2: 运行相关测试确认 prompt 不损坏**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -v -x -k "prompt or analysis"
```

- [ ] **Step 3: Commit**

```bash
git add app/services/data_factory_agent_prompts.py
git commit -m "feat: update few-shot example 3 with real user failure case (order_sn + item_no + refund)"
```

---

### Task 3: 添加回归测试用例

**Files:**
- Modify: `tests/test_data_factory_agent.py`（文件末尾追加）

**Interfaces:**
- Consumes: `_agent_context()`, `_login()`, `monkeypatch`, `call_local_model_json`
- Produces: 5 个新测试函数

- [ ] **Step 1: 添加测试：订单号长格式确定性提取**

```python
def test_intent_extracts_long_order_sn():
    from app.services.data_factory_agent_intent import reduce_intent_fields
    result = reduce_intent_fields({}, "帮我把2026071715475684-300001这个订单的问题产品处理掉")
    fields = result.get("resolved_fields", {})
    assert fields.get("order_sn", {}).get("value") == "2026071715475684-300001"
```

- [ ] **Step 2: 添加测试：番号确定性提取**

```python
def test_intent_extracts_item_index_fan():
    from app.services.data_factory_agent_intent import reduce_intent_fields
    result = reduce_intent_fields({}, "1番提出问题产品")
    fields = result.get("resolved_fields", {})
    assert fields.get("item_index", {}).get("value") == 1
```

- [ ] **Step 3: 添加测试：问题产品操作识别**

```python
def test_intent_extracts_problem_goods_operation():
    from app.services.data_factory_agent_intent import reduce_intent_fields
    result = reduce_intent_fields({}, "帮我把这个订单提出问题产品")
    fields = result.get("resolved_fields", {})
    assert fields.get("problem_goods_op", {}).get("value") == "提出问题产品"
```

- [ ] **Step 4: 添加测试：单价改成0识别为退款**

```python
def test_intent_extracts_refund_unit_price_zero():
    from app.services.data_factory_agent_intent import reduce_intent_fields
    result = reduce_intent_fields({}, "单价改成0")
    fields = result.get("resolved_fields", {})
    pricing = fields.get("pricing", {}).get("value", {})
    assert pricing.get("mode") == "uniform_unit"
    assert pricing.get("amount") == "0"
    assert pricing.get("refund_context") is True
```

- [ ] **Step 5: 添加测试：支付方式银行识别**

```python
def test_intent_extracts_bank_payment_mode():
    from app.services.data_factory_agent_intent import reduce_intent_fields
    result = reduce_intent_fields({}, "银行汇款支付")
    fields = result.get("resolved_fields", {})
    assert fields.get("order_payment_mode", {}).get("value") == "bank"
```

- [ ] **Step 6: 运行全部新增测试**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -v -k "intent_extracts"
```

- [ ] **Step 7: 运行全量测试确保无回归**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -v
```

- [ ] **Step 8: Commit**

```bash
git add tests/test_data_factory_agent.py
git commit -m "test: add deterministic intent extraction regression tests (order_sn/item_index/problem_goods/payment)"
```

---

### Task 4: 上线前整体验证 + 更新设计文档状态

**Files:**
- Modify: `docs/superpowers/specs/2026-07-17-data-agent-hit-rate-design.md:3`

- [ ] **Step 1: 运行全量智能体测试**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -v
```

- [ ] **Step 2: 将设计文档状态从"设计中"改为"已实施"**

将第3行 `状态: 设计中` 改为 `状态: 已实施`

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-07-17-data-agent-hit-rate-design.md
git commit -m "docs: mark data-agent-hit-rate spec as implemented"
```
