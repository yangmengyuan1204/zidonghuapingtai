# DeepSeek 数据智能体意图、Option、退款与进度展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复记录 828 暴露的数量、option、全额退款、重复追问和错误成功问题，并让执行弹窗稳定显示实时节点进度。

**Architecture:** DeepSeek 只产生带原文证据的候选意图，后端合同编译器按“明确证据优先、无证据不得覆盖”合并结果。工具层复用现有订单 option 和问题产品能力，增加只读目录匹配、退款三部分校验和进度回调；前端采用稳定 DOM 与局部刷新展示中文进度。

**Tech Stack:** Python 3.11、FastAPI、现有数据脚本、原生 JavaScript、pytest、Node.js。

## Global Constraints

- 不修改数据库结构、AI 配置和问题产品业务流程。
- 复用订单脚本已有 `order_option_counts` 与问题产品已有 `option_new` 能力。
- 记录 828 只读核验，不重复执行。
- 实际业务测试的退款预览必须低于 500 元；达到阈值时停止，不自动选择部长账号。
- 使用 `.venv\Scripts\python.exe` 运行 Python 测试。
- 不覆盖或回退工作区既有改动，不提交、不推送。
- 不启动浏览器；弹窗行为使用 Node/DOM 契约测试验证。
- 此计划统一覆盖此前独立的全中文展示计划。

---

### Task 1: 修复数量、全退语义和合同优先级

**Files:**
- Modify: `app/services/data_factory_agent.py:330-1165`
- Test: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: DeepSeek `goal.intent` 中的 `quantity_evidence`、`item_count_evidence`、操作证据和用户消息。
- Produces: `_model_evidenced_count(raw_goal, source_text, field) -> tuple[int | None, str]`、扩展后的 `_explicit_count_intent`、`_problem_goods_intent` 和无冲突的最终 `goal`。

- [ ] **Step 1: 写记录 828 的失败测试**

```python
def test_agent_compiles_record_828_quantity_and_full_refund():
    instruction = (
        "帮我造一条单子，客户id300001，两番商品，每番商品数量10,商品总价1000，"
        "然后每番随机添加3个option，单子状态到待拍下，最后提出两次问题产品，"
        "把两番商品金额、数量、国内运费和option全退了"
    )
    payload = {
        "status": "ready",
        "goal": {
            "mode": "new",
            "target_node": "pending_purchase",
            "customer_ids": ["300001"],
            "variables": {"order_shop_count": 2, "order_per_shop": 1, "order_item_num": 10},
            "intent": {
                "item_count_evidence": "两番商品",
                "quantity_evidence": "每番商品数量10",
                "pricing": {"mode": "goods_total", "amount": 1000, "evidence": "商品总价1000"},
            },
            "operations": [{"type": "advance_order"}, {"type": "problem_goods"}],
        },
    }

    status, goal, question = agent_service._normalize_goal(payload, [{"role": "user", "content": instruction}])

    assert status == "awaiting_confirmation"
    assert question == ""
    assert goal["variables"]["order_shop_count"] == 1
    assert goal["variables"]["order_per_shop"] == 2
    assert goal["variables"]["order_item_num"] == 10
    assert goal["intent"]["pricing"]["effective_unit_prices"] == ["50", "50"]
    problem = goal["operations"][1]
    assert problem["scope"] == "all_candidates"
    assert problem["quantity_refund_mode"] == "all"
    assert problem["freight_refund_mode"] == "all"
    assert problem["option_refund_mode"] == "all"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py::test_agent_compiles_record_828_quantity_and_full_refund -q`

Expected: FAIL；当前 `order_item_num` 为 1，问题产品数量模式为 `keep`。

- [ ] **Step 3: 扩展模型提示中的结构化操作合同**

将问题产品操作格式明确为：

```python
{
    "type": "problem_goods",
    "scope": "all_candidates或single",
    "quantity_refund_mode": "all或half或fixed或keep",
    "quantity_refund_value": None,
    "freight_refund_mode": "all或keep",
    "option_refund_mode": "all或keep",
    "evidence": "对应用户原话",
}
```

提示词增加规则：“多个退款字段列举后句尾出现全退、都退、清零时，所有列举字段均为 all；数量成0等价于 quantity_refund_mode=all。”

- [ ] **Step 4: 扩展确定性数量与退款解析**

在 `_explicit_count_intent` 的每种数量正则中加入 `每番`：

```python
quantity_match = re.search(
    rf"(?:每(?:个|种|款|件|番)?(?:商品|货品|sku)|每番|{_COUNT_TOKEN}番(?:商品|货品)|每(?:个|种)?数量)"
    rf"(?:购买|数量|买)?(?:是|为|=|:)?({_COUNT_TOKEN})(?:件|个|份)?(?:数量)?",
    text,
    re.IGNORECASE,
)
```

在 `_problem_goods_intent` 增加：

```python
listed_all = re.search(
    r"(?:商品金额|商品数量|两番数量|数量).{0,30}(?:国内运费|运费).{0,30}(?:option|附加服务).{0,12}(?:全退|都退|清零)",
    evidence,
    re.IGNORECASE,
)
zero_quantity = re.search(r"(?:问题产品|商品)?数量(?:改|变|成|为|=|:)?0", evidence)
if listed_all or zero_quantity:
    quantity_mode = "all"
if listed_all or re.search(r"(?:option|附加服务).{0,12}(?:全退|都退|清零|改成?0)", evidence, re.IGNORECASE):
    option_mode = "all"
```

范围规则：两个商品且出现“两番、全部商品、所有商品、提出两次问题产品”时使用 `all_candidates`。

- [ ] **Step 5: 实现“有证据才覆盖”的数量优先级**

```python
def _model_evidenced_count(raw_goal, source_text, field, evidence_key):
    intent = raw_goal.get("intent") if isinstance(raw_goal.get("intent"), dict) else {}
    evidence = str(intent.get(evidence_key) or "").strip()
    variables = raw_goal.get("variables") if isinstance(raw_goal.get("variables"), dict) else {}
    value = variables.get(field)
    if value in (None, "") or not evidence:
        return None, ""
    if _compact_semantic_text(evidence) not in _compact_semantic_text(source_text):
        return None, ""
    return _positive_int(value, field), evidence
```

`order_item_num` 选择顺序固定为：确定性数量证据、模型数量证据、新订单默认值 1。默认值不得覆盖模型证据。

- [ ] **Step 6: 增加执行前合同冲突检查**

新增 `_contract_conflicts(goal) -> list[str]`，至少检查：原文数量证据与执行数量、全退证据与问题产品模式、option 数量与 option 合同、商品总价精确换算。存在冲突时返回 `clarifying`，业务工具调用为零。

- [ ] **Step 7: 运行相关测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -q -k "record_828 or quantity or refund or conflict"`

Expected: PASS。

### Task 2: 字段级会话状态与最多一次追问

**Files:**
- Modify: `app/services/data_factory_agent.py:180-330,1160-1250,1580-1630`
- Test: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: `AgentSessionState.messages` 和每轮 `question_field`。
- Produces: `AgentSessionState.intent_state: dict`、`clarification_counts: dict[str, int]`、具体追问事件。

- [ ] **Step 1: 写取消、恢复和追问上限测试**

```python
def test_option_intent_can_be_cancelled_and_restored_without_repeating_question():
    state = {}
    state = agent_service._reduce_intent_state(state, "每番随机添加3个option")
    assert state["options"]["enabled"] is True
    state = agent_service._reduce_intent_state(state, "option不添加了")
    assert state["options"]["enabled"] is False
    state = agent_service._reduce_intent_state(state, "还是需要，每番随机3个option")
    assert state["options"] == {"enabled": True, "mode": "random", "count": 3, "names": []}


def test_same_clarification_field_is_not_asked_more_than_once():
    session = agent_service.AgentSessionState(id="S", user_id=1, project_id=1, env_id=1, status="clarifying")
    session.clarification_counts["options"] = 1
    question = agent_service._bounded_clarification(session, "options", "请选择option")
    assert question["blocked"] is True
    assert "无法可靠确定" in question["message"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -q -k "cancelled_and_restored or not_asked_more_than_once"`

Expected: FAIL；状态归并和追问计数尚不存在。

- [ ] **Step 3: 扩展会话状态**

```python
intent_state: Dict[str, Any] = field(default_factory=dict)
clarification_counts: Dict[str, int] = field(default_factory=dict)
```

实现 `_reduce_intent_state`，仅处理可证明的字段更新：

```python
def _reduce_intent_state(state: Dict[str, Any], message: str) -> Dict[str, Any]:
    result = copy.deepcopy(state) if isinstance(state, dict) else {}
    text = _compact_semantic_text(message)
    options = dict(result.get("options") or {})
    if re.search(r"(?:option|附加服务).{0,8}(?:不要|不添加|取消)", text, re.IGNORECASE):
        options = {"enabled": False, "mode": "none", "count": 0, "names": []}
    option_count = re.search(r"(?:每番|每个商品)?.{0,8}(?:随机)?(?:添加|加)?(\d+)个(?:option|附加服务)", text, re.IGNORECASE)
    if option_count:
        options = {"enabled": True, "mode": "random", "count": int(option_count.group(1)), "names": []}
    if re.search(r"(?:还是|恢复|继续).{0,8}(?:需要|添加).{0,8}(?:option|附加服务)", text, re.IGNORECASE):
        options["enabled"] = True
    if options:
        result["options"] = options
    return result


def _bounded_clarification(session: AgentSessionState, field_name: str, message: str) -> Dict[str, Any]:
    count = int(session.clarification_counts.get(field_name, 0)) + 1
    session.clarification_counts[field_name] = count
    if count > 1:
        return {"blocked": True, "message": f"无法可靠确定{field_name}，请取消该要求或重新明确描述。"}
    return {"blocked": False, "message": message}
```

新增消息先更新状态，再构造本轮分析上下文；已取消 option 不再进入 `unhandled_requests`。

- [ ] **Step 4: 保存具体追问事件**

分析结果增加 `question_field`。事件记录：

```python
_event(
    "clarification",
    question,
    field=question_field,
    count=session.clarification_counts.get(question_field, 0),
    evidence=session.intent_state.get(question_field),
)
```

第二次仍无法确定同一字段时进入 `blocked`，明确列出能力限制和“取消该要求/重新描述”的选择，不再继续问。

- [ ] **Step 5: 运行测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -q -k "clarification or intent_state or option"`

Expected: PASS。

### Task 3: 注册真实订单 Option 目录与执行合同

**Files:**
- Modify: `app/data_scripts/orders.py`
- Modify: `app/data_scripts/__init__.py`
- Modify: `app/services/data_factory_agent.py`
- Modify: `app/services/data_factory_agent_tools.py`
- Test: `tests/test_data_factory_agent.py`
- Test: `tests/test_permissions.py`

**Interfaces:**
- Produces: `inspect_order_options(env, variables) -> dict`、工具 `inspect_order_options`、`_resolve_order_options(context, catalog) -> dict[str, int]`。

- [ ] **Step 1: 写目录读取和稳定随机选择失败测试**

```python
def test_agent_resolves_three_random_options_with_stable_seed():
    catalog = [
        {"key": "1", "name": "A"}, {"key": "2", "name": "B"},
        {"key": "3", "name": "C"}, {"key": "4", "name": "D"},
    ]
    operation = {"mode": "random", "count": 3, "names": []}
    first = agent_tools._resolve_option_counts(operation, catalog, "contract-123")
    second = agent_tools._resolve_option_counts(operation, catalog, "contract-123")
    assert first == second
    assert len(first) == 3
    assert set(first.values()) == {1}


def test_agent_resolves_named_options_exactly():
    catalog = [{"key": "79", "name": "詳細検品", "name_translate": "详细检查"}]
    assert agent_tools._resolve_option_counts({"mode": "named", "names": ["詳細検品"]}, catalog, "x") == {"79": 1}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -q -k "resolves_three_random_options or resolves_named_options"`

Expected: FAIL；目录工具和匹配函数不存在。

- [ ] **Step 3: 在订单脚本增加只读目录函数**

`inspect_order_options` 复用 `_runtime_from_variables`、`RakumartClient`、`_fetch_order_option_catalog` 和 `_public_order_options`，只登录并读取 option，不创建订单：

```python
def inspect_order_options(env: Env, variables: Dict[str, Any] | None = None) -> Dict[str, Any]:
    _sync_compat_globals()
    values = dict(variables or {})
    runtime = _runtime_from_variables(values)
    log = {"script": "查询订单附加服务", "read_only": True}
    if runtime:
        client, _base_url, _timeout, _token, _cached = runtime.client(env, values, log=log)
    else:
        base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
        timeout = _as_int(values.get("timeout"), env.timeout or 25)
        client = bulk_cart.RakumartClient(base_url, timeout)
        _configure_client_api_paths(client, values)
        _call_with_retry("client login", lambda: client.login(str(values.get("account") or ""), str(values.get("password") or ""), str(values.get("client_tool") or "1")))
    catalog, _payload, path = _fetch_order_option_catalog(client, values)
    return {"path": path, "options": _public_order_options(catalog), "count": len(catalog)}
```

从 `app/data_scripts/__init__.py` 导出该函数。

- [ ] **Step 4: 注册只读工具和匹配函数**

`TOOL_SPECS` 增加 `inspect_order_options`。实现：

```python
def _resolve_option_counts(operation: Dict[str, Any], catalog: list[Dict[str, Any]], contract_hash: str) -> Dict[str, int]:
    rows = sorted((row for row in catalog if str(row.get("key") or "").strip()), key=lambda row: str(row.get("key")))
    mode = str(operation.get("mode") or "none")
    if mode == "random":
        count = int(operation.get("count") or 0)
        if count <= 0 or count > len(rows):
            raise ValueError(f"可用option数量{len(rows)}，无法选择{count}个")
        selected = random.Random(str(contract_hash)).sample(rows, count)
        return {str(row["key"]): 1 for row in selected}
    if mode == "named":
        result: Dict[str, int] = {}
        for requested in operation.get("names") or []:
            matches = [
                row for row in rows
                if str(requested).strip() in {
                    str(row.get("key") or "").strip(), str(row.get("name") or "").strip(),
                    str(row.get("label") or "").strip(), str(row.get("name_translate") or "").strip(),
                }
            ]
            if len(matches) != 1:
                raise ValueError(f"option“{requested}”匹配到{len(matches)}项")
            result[str(matches[0]["key"])] = 1
        return result
    return {}
```

匹配失败或重名转换成一次性澄清结果。

- [ ] **Step 5: 将 option 写入合同和执行变量**

`ALLOWED_VARIABLE_KEYS` 增加 `order_option_counts`。目标合同增加：

```python
"options": {"enabled": True, "mode": "random", "count": 3, "names": [], "evidence": "每番随机添加3个option"}
```

运行订单工具前只读查询并解析 option，将 `order_option_counts` 注入 `context.public_variables` 和 `context.variables`；保存所选 option 到 `context.state["selected_order_options"]`。

- [ ] **Step 6: 扩展订单实际校验**

`_order_inspection` 为每个商品返回 option 白名单字段。`_verify_goal` 检查每个商品的 option key 集合与合同一致；缺失时失败，不进入问题产品。

- [ ] **Step 7: 运行测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py tests/test_permissions.py -q -k "option"`

Expected: PASS。

### Task 4: 问题产品全退 Option 与三部分退款校验

**Files:**
- Modify: `app/services/data_factory_agent_tools.py:575-840`
- Test: `tests/test_data_factory_agent.py`
- Test: `tests/test_problem_goods_script.py`

**Interfaces:**
- Produces: `_zero_option_values(options) -> list[dict]`、`_expected_refund_components(candidate, operation) -> dict`、真实退款组件校验。

- [ ] **Step 1: 写失败测试**

```python
def test_problem_goods_full_refund_zeroes_quantity_freight_and_options():
    options = [
        {"name": "詳細検品", "price_type": "0", "num": "10", "price": "2", "checked": True},
        {"name": "圧縮包装", "price_type": "1", "num": "10", "price": "5", "checked": True},
    ]
    zeroed = agent_tools._zero_option_values(options)
    assert [(row["num"], row["price"]) for row in zeroed] == [("0", "0"), ("0", "0")]
    assert [row["name"] for row in zeroed] == ["詳細検品", "圧縮包装"]
```

扩展现有问题产品工具测试，断言传给脚本的变量包含：

```python
assert captured["pre_num"] == 0
assert captured["pre_freight"] == "0"
assert captured["option_deal_suggest"] == 1
assert all(row["num"] == "0" and row["price"] == "0" for row in captured["option_new"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py tests/test_problem_goods_script.py -q -k "full_refund_zeroes or option_new"`

Expected: FAIL；当前工具使用数量 `keep`，没有生成 `option_new`。

- [ ] **Step 3: 实现 option 清零与预期组件**

```python
def _zero_option_values(options):
    rows = []
    for source in options if isinstance(options, list) else []:
        if not isinstance(source, dict):
            continue
        row = dict(source)
        row["num"] = "0"
        row["price"] = "0"
        rows.append(row)
    return rows
```

问题产品 `option_refund_mode=all` 时注入 `option_deal_suggest=1` 和清零后的 `option_new`。数量 all 注入 `pre_num=0`；运费 all 注入 `pre_freight=0`；`pre_price` 保持原值。

- [ ] **Step 4: 校验退款三部分**

执行前根据候选记录保存 `goods_refund_expected`、`freight_refund_expected`、`option_refund_expected`。执行后同时验证：问题产品状态 6、`pre_num=0`、`pre_freight=0`、`option_new` 全为 0，并从预览账单 `adjust_detail`/金额核对商品、运费和 option。缺少任何组件时 `completed_all=False`，聚合会话不能成功。

- [ ] **Step 5: 运行问题产品回归**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py tests/test_problem_goods_script.py -q`

Expected: PASS。

### Task 5: 增加全流程和问题产品实时进度回调

**Files:**
- Modify: `app/data_scripts/full_flow.py`
- Modify: `app/services/data_factory_agent_tools.py`
- Modify: `app/services/data_factory_agent.py`
- Test: `tests/test_permissions.py`
- Test: `tests/test_data_factory_agent.py`

**Interfaces:**
- Produces: `ProgressCallback = Callable[[dict], None]`；`run_full_flow_script(..., progress_callback=None)`、续跑同签名；`AgentToolContext.progress_callback`。

- [ ] **Step 1: 写进度顺序失败测试**

```python
def test_full_flow_emits_progress_before_and_after_each_coarse_node(monkeypatch):
    events = []
    patch_full_flow_report(monkeypatch)
    monkeypatch.setattr(data_scripts, "run_shopping_cart_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应补购物车")))
    monkeypatch.setattr(data_scripts, "run_order_quote_script", lambda env, variables: (True, "", "", {"order_sn": "ORDER-PROGRESS"}))
    monkeypatch.setattr(data_scripts, "run_balance_payment_script", lambda env, variables: (True, "", "", {"payment_type": "balance", "order_sn": "ORDER-PROGRESS"}))
    monkeypatch.setattr(
        data_scripts,
        "run_purchase_to_shelf_script",
        lambda env, variables: (True, "", "", data_scripts._paused_summary("pending_purchase", {"order_sn": "ORDER-PROGRESS"})),
    )
    monkeypatch.setattr(data_scripts, "run_warehouse_delivery_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应创建配送单")))
    passed, _log, _report, summary = data_scripts.run_full_flow_script(
        full_flow_env(),
        {"stop_after_node": "pending_purchase"},
        progress_callback=events.append,
    )
    assert passed is True
    assert [(item["node"], item["status"]) for item in events] == [
        ("order_offered", "running"), ("order_offered", "completed"),
        ("order_paid", "running"), ("order_paid", "completed"),
        ("pending_purchase", "running"), ("pending_purchase", "completed"),
    ]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_permissions.py -q -k "emits_progress"`

Expected: FAIL；函数不接受 `progress_callback`。

- [ ] **Step 3: 扩展全流程签名并上报粗粒度节点**

```python
ProgressCallback = Callable[[Dict[str, Any]], None]

def _emit_progress(callback, node, status, next_node="", **extra):
    if callable(callback):
        callback({"node": node, "status": status, "next_node": next_node, "updated_at": datetime.now().isoformat(), **extra})
```

`run_full_flow_script`、`run_resume_order_flow_script`、`run_resume_porder_flow_script` 增加可选回调。每个粗粒度子脚本调用前发 `running`，返回后发 `completed` 或 `failed`；默认 `None` 保持其他调用方兼容。

- [ ] **Step 4: 将进度桥接到会话状态**

`AgentToolContext` 增加 `progress_callback: Callable[[dict], None] | None = None`。创建上下文时注入闭包，将进度写入：

```python
state["progress"] = {
    "operation_index": operation_index + 1,
    "operation_total": len(_goal_operations(goal)),
    "current_node": update.get("node"),
    "next_node": update.get("next_node"),
    "node_status": update.get("status"),
    "item_index": update.get("item_index"),
    "item_total": update.get("item_total"),
    "problem_goods_id": update.get("problem_goods_id"),
    "started_at": state.get("progress", {}).get("started_at") or _now_text(),
    "updated_at": _now_text(),
}
```

同步调用 `_sync_runtime_state` 并追加 `progress` 事件；相同节点心跳只更新状态，不无限追加事件。

- [ ] **Step 5: 问题产品逐商品上报进度**

处理每个候选前上报 `running` 和 `item_index/item_total`，完成或待授权时上报对应状态并带 `problem_goods_id`。

- [ ] **Step 6: 运行进度测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_permissions.py tests/test_data_factory_agent.py -q -k "progress"`

Expected: PASS。

### Task 6: 稳定弹窗、最小化、中文进度和记录展示

**Files:**
- Modify: `static/data-factory-agent.js`
- Modify: `static/app.js:showLog`
- Test: `tests/test_data_factory_agent.py`

**Interfaces:**
- Produces: `updateModal(session)`、`progressHtml(progress)`、`minimizeModal()`、`renderRecordSummary(log, escapeHtml)`。

- [ ] **Step 1: 写前端源契约和 Node 行为失败测试**

测试断言：

```python
source = Path("static/data-factory-agent.js").read_text(encoding="utf-8")
assert "function updateModal" in source
assert "modalEl.innerHTML" not in source[source.index("async function refreshSession"):source.index("async function sendMessage")]
assert "data-agent-progress" in source
assert "dataAgentMinimize" in source
assert "renderRecordSummary" in source
```

Node 行为测试加载模块后调用 `progressHtml`，断言 `pending_purchase` 显示“订单待拍下”，不显示代码值；未知字段不直接展示原名称。

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -q -k "modal or progress_html or record_summary"`

Expected: FAIL；当前轮询每秒调用 `renderModal()` 重建全部 HTML。

- [ ] **Step 3: 建立一次性弹窗骨架和局部更新区域**

首次打开生成带稳定 ID 的区域：`data-agent-status`、`data-agent-progress`、`data-agent-goal`、`data-agent-question`、`data-agent-events`、`data-agent-result`、`data-agent-actions`。`refreshSession` 获取新会话后调用 `updateModal(currentSession)`，只更新区域内容变化的节点。

更新前保存并恢复：`.modal-body.scrollTop`、所有 `details.open`、活动元素 ID/选择区间、问题输入值。

- [ ] **Step 4: 增加固定进度区和最小化入口**

进度区展示当前操作、当前节点、下一节点、节点状态、总体操作数、商品进度、问题产品编号、已耗时和最后更新时间。弹窗最小化时关闭 dialog 但保留轮询，并在数据智能体面板显示“任务执行中/待确认/已完成”按钮；只有取消按钮调用后端取消接口。

- [ ] **Step 5: 合并全中文展示**

集中映射字段、节点、工具、事件、退款模式、状态和 option。所有普通界面禁止原代码兜底。`app.js` 检测 `parsed.script === "DeepSeek数据智能体"` 后调用 `window.DataFactoryAgent.renderRecordSummary`；折叠原始日志保持原 JSON。

- [ ] **Step 6: 运行前端测试和语法检查**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -q -k "modal or display or record_summary"`

Run: `node --check static/data-factory-agent.js`

Run: `node --check static/app.js`

Expected: 全部 PASS/退出码 0。

### Task 7: 完整回归、真实 DeepSeek 矩阵和小额业务体验

**Files:**
- Verify: all files above

- [ ] **Step 1: 运行相关完整测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py tests/test_problem_goods_script.py tests/test_permissions.py -q`

Expected: PASS。

- [ ] **Step 2: 运行真实 DeepSeek 两轮识别矩阵**

至少 20 条用户口吻指令，两轮共至少 40 次，只创建识别会话不确认执行。必须覆盖记录 828 原话、每番数量、句尾统一全退、数量成 0、随机 option、指定 option、取消和恢复。明确指令一次生成完整合同，真正歧义每字段最多追问一次。

- [ ] **Step 3: 只读查询低价 option 并选择小额测试参数**

使用 `inspect_order_options` 查询目录，选择 3 个低价 option；根据 option 计价规则计算预估退款，确保商品金额 20 元加运费和 option 后低于 500 元。

- [ ] **Step 4: 执行一条小额真实业务链路**

客户 300001，2 个商品，每个数量 2，商品总价 20，每个商品相同 3 个 option，到待拍下后，两条问题产品全部退商品金额、国内运费和 option。若退款预览达到 500 元，停在待授权并终止本次业务体验，不自动选择账号。

- [ ] **Step 5: 实际结果验收**

确认订单每个商品数量 2、单价 5、三个 option 齐全；两个问题产品状态完成、`pre_num=0`、`pre_freight=0`、option 最终计费为 0；预览包含商品、运费和 option 三部分。任一不一致不得记录成功。

- [ ] **Step 6: 记录 828 只读回归**

核对记录 828 和问题产品 895194/895195，确认历史数据未被重复处理；使用其原话运行新合同编译器，期望数量 10、单价 50、两个商品、三个 option、全额退款合同。

- [ ] **Step 7: 检查工作区并汇报**

Run: `git status --short`

Run: `git diff --stat`

仅汇报本次修改文件、既有未提交文件、测试结论、真实识别矩阵和小额业务结果。明确未提交、未推送、未启动浏览器。
