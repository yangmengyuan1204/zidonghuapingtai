# Data Agent Core Hit-Rate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make explicit Japanese-site data instructions produce a correct confirmable contract on the first turn, with deterministic defaults, customer context, payment fallback, and resumable 500-yuan permission handling.

**Architecture:** Keep DeepSeek as a semantic candidate generator, but move final business decisions into a deterministic contract compiler. Preserve existing script interfaces; pass page/environment context into the compiler and keep execution recovery in the tool layer.

**Tech Stack:** Python 3.11, FastAPI 0.115, SQLAlchemy 2.0, SQLite, vanilla JavaScript, pytest.

## Global Constraints

- Run every Python test with `.venv\Scripts\python.exe`.
- Preserve all existing workspace changes and never stage unrelated files.
- Do not change public data-script function signatures or existing script return contracts.
- Explicit natural-language instructions must reach a confirmable contract at least 95% of the time in each live-model evaluation round.
- Temporary credentials must never enter logs, records, database rows, serialized sessions, or API responses.
- Do not start a browser unless the user explicitly requests browser verification.

---

### Task 1: Restore the Existing Agent Regression Baseline

**Files:**
- Modify: `app/services/data_factory_agent.py:509-521`
- Modify: `tests/test_data_factory_agent.py:316-453,615-632,765-811,887-901,1200-1265`

**Interfaces:**
- Consumes: existing `_bounded_clarification(session, field_name, message)`.
- Produces: clarification counters that exclude `_global` from per-field totals; model test doubles that accept the production `system_prompt` keyword.

- [ ] **Step 1: Tighten the clarification regression test**

```python
def test_same_clarification_field_can_be_answered_more_than_once_without_blocking():
    session = agent_service.AgentSessionState(
        id="clarify", user_id=1, project_id=1, env_id=1, status="clarifying"
    )
    first = agent_service._bounded_clarification(session, "pricing", "请说明价格口径")
    second = agent_service._bounded_clarification(session, "pricing", "仍缺少价格口径")
    assert first["blocked"] is False
    assert second["blocked"] is False
    assert second["count"] == 2
    assert second["lifetime"] == 2
```

- [ ] **Step 2: Run the focused test and verify the current failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py::test_same_clarification_field_can_be_answered_more_than_once_without_blocking -v`

Expected: FAIL because `_global` is counted as a normal clarification field.

- [ ] **Step 3: Exclude the lifetime counter from the field total**

```python
count = int(session.clarification_counts.get(field_name, 0)) + 1
session.clarification_counts[field_name] = count
total_rounds = sum(
    int(value)
    for key, value in session.clarification_counts.items()
    if key != "_global"
)
lifetime = int(session.clarification_counts.get("_global", 0)) + 1
session.clarification_counts["_global"] = lifetime
blocked = total_rounds >= MAX_CLARIFICATION_TOTAL_ROUNDS or lifetime >= MAX_LIFETIME_CLARIFICATIONS
return {
    "blocked": blocked,
    "message": str(message or "请补充该字段。"),
    "count": count,
    "lifetime": lifetime,
}
```

- [ ] **Step 4: Update affected model doubles to accept production keywords**

Add the unused `system_prompt` keyword to each affected test double while preserving that test's existing response logic. For the common analysis/finish double, use:

```python
def fake_model(config, prompt, timeout=120, system_prompt=""):
    if "本轮只理解目标" in prompt:
        return _ready_goal()
    return {"action": "finish", "reason": "测试中的目标已达到"}
```

- [ ] **Step 5: Run the current agent and script-contract suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py tests/test_data_script_contract.py -q`

Expected: PASS.

- [ ] **Step 6: Commit only the baseline files**

```powershell
git add app/services/data_factory_agent.py tests/test_data_factory_agent.py
git commit -m "fix: restore data agent regression baseline"
```

---

### Task 2: Introduce the Deterministic Contract Compiler

**Files:**
- Create: `app/services/data_factory_agent_contract.py`
- Modify: `app/services/data_factory_agent.py:1068-1484`
- Test: `tests/test_data_factory_agent_contract.py`

**Interfaces:**
- Consumes: `compile_agent_contract(payload, messages, intent_state, context, force_ready=False)`.
- Produces: `ContractCompileResult(status: str, goal: dict, question: str)`.

- [ ] **Step 1: Write failing default-contract tests**

```python
from app.services.data_factory_agent_contract import compile_agent_contract


def test_minimal_new_order_uses_confirmed_business_defaults():
    result = compile_agent_contract(
        {"status": "ready", "goal": {"mode": "new", "variables": {}}},
        [{"role": "user", "content": "帮我造一个订单"}],
        {},
        {"topbar_customer_ids": [], "bound_customer_ids": ["300001"]},
    )
    assert result.status == "awaiting_confirmation"
    assert result.goal["target_node"] == "order_offered"
    assert result.goal["customer_ids"] == ["300001"]
    assert result.goal["variables"]["order_shop_count"] == 1
    assert result.goal["variables"]["order_per_shop"] == 1
    assert result.goal["variables"]["order_item_num"] == 1
    assert result.goal["variables"]["offer_price"] == "10"
    assert result.goal["variables"]["keyword"] == "衣服"
    assert result.goal["variables"]["shop_type"] == "1688"
    assert set(result.goal["defaults_used"]) >= {
        "target_node", "customer_ids", "order_shop_count", "order_per_shop",
        "order_item_num", "offer_price", "keyword", "shop_type",
    }
```

- [ ] **Step 2: Run the new test and verify import failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent_contract.py -v`

Expected: FAIL because the compiler module does not exist.

- [ ] **Step 3: Create compiler result and defaults**

```python
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class ContractCompileResult:
    status: str
    goal: Dict[str, Any]
    question: str = ""


NEW_ORDER_DEFAULTS: Dict[str, Any] = {
    "target_node": "order_offered",
    "keyword": "衣服",
    "shop_type": "1688",
    "order_shop_count": 1,
    "order_per_shop": 1,
    "order_item_num": 1,
    "offer_price": "10",
    "order_payment_mode": "balance_first",
    "payment_fallback": "bank",
}
```

- [ ] **Step 4: Implement source-priority compilation**

```python
def resolve_customer_ids(explicit: list[str], context: Dict[str, Any]) -> tuple[list[str], str]:
    if explicit:
        return explicit, "natural_language"
    topbar = [str(item) for item in context.get("topbar_customer_ids") or [] if str(item).isdigit()]
    if topbar:
        return topbar, "topbar"
    bound = [str(item) for item in context.get("bound_customer_ids") or [] if str(item).isdigit()]
    return bound, "bound_account" if bound else ""


def compile_agent_contract(payload, messages, intent_state, context, force_ready=False):
    raw_goal = dict(payload.get("goal") or {}) if isinstance(payload, dict) else {}
    variables = dict(raw_goal.get("variables") or {})
    resolved = dict((intent_state or {}).get("resolved_fields") or {})
    def resolved_value(name: str, fallback: Any = "") -> Any:
        item = resolved.get(name) if isinstance(resolved.get(name), dict) else {}
        return item.get("value", fallback)

    order_sn = str(resolved_value("order_sn", raw_goal.get("order_sn") or "")).strip()
    porder_sn = str(resolved_value("porder_sn", raw_goal.get("porder_sn") or "")).strip()
    if order_sn and porder_sn:
        return ContractCompileResult("clarifying", {}, "同时识别到订单号和配送单号，请明确本次处理哪一种单据。")
    mode = "resume_porder" if porder_sn else "resume_order" if order_sn else "new"
    defaults_used: list[str] = []
    if mode == "new":
        for key, value in NEW_ORDER_DEFAULTS.items():
            if key == "target_node":
                if not resolved_value("target_node", raw_goal.get(key)):
                    raw_goal[key] = value
                    defaults_used.append(key)
                else:
                    raw_goal[key] = resolved_value("target_node", raw_goal.get(key))
            elif key not in variables or variables.get(key) in (None, ""):
                variables[key] = value
                defaults_used.append(key)
    elif resolved_value("target_node", raw_goal.get("target_node")):
        raw_goal["target_node"] = resolved_value("target_node", raw_goal.get("target_node"))
    else:
        raw_goal["target_node"] = ""
    explicit_ids = list((resolved.get("customer_ids") or {}).get("value") or [])
    customer_ids, customer_source = resolve_customer_ids(explicit_ids, context)
    if customer_ids and not explicit_ids:
        defaults_used.append("customer_ids")
    raw_goal.update({
        "mode": mode,
        "order_sn": order_sn,
        "porder_sn": porder_sn,
        "customer_ids": customer_ids,
        "customer_source": customer_source,
        "variables": variables,
        "defaults_used": list(dict.fromkeys(defaults_used)),
    })
    return ContractCompileResult("awaiting_confirmation", raw_goal, "")
```

- [ ] **Step 5: Route `_normalize_goal` through the compiler without changing its public tuple**

```python
compiled = compile_agent_contract(
    payload,
    messages or [],
    conversation_intent,
    compile_context or {},
    force_ready=force_ready,
)
return compiled.status, compiled.goal, compiled.question
```

Add optional `compile_context: dict[str, Any] | None = None` to `_normalize_goal` and `_analyze_turn`; existing callers pass `{}`.

Add `payment_fallback` to `ALLOWED_VARIABLE_KEYS`; it is contract metadata consumed by the agent tool layer and does not change any data-script signature.

- [ ] **Step 6: Run compiler and existing agent tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent_contract.py tests/test_data_factory_agent.py -q`

Expected: PASS.

- [ ] **Step 7: Commit compiler task files**

```powershell
git add app/services/data_factory_agent_contract.py app/services/data_factory_agent.py tests/test_data_factory_agent_contract.py
git commit -m "feat: compile deterministic data agent contracts"
```

---

### Task 3: Pass Top-Bar and Bound-Account Customer Context

**Files:**
- Modify: `app/agent_schemas.py:6-10`
- Modify: `app/routers/data_factory_agent.py:28-42`
- Modify: `app/services/data_factory_agent.py:1567-1633`
- Modify: `static/data-factory-agent.js:501-520`
- Test: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: `DataAgentSessionCreate.topbar_customer_ids`.
- Produces: compiler context with validated `topbar_customer_ids` and `bound_customer_ids`.

- [ ] **Step 1: Write an API priority test**

```python
def test_agent_customer_priority_is_natural_language_then_topbar_then_bound(monkeypatch):
    project, env = _agent_context()
    monkeypatch.setattr(agent_service, "call_local_model_json", lambda *a, **k: _ready_goal())
    with TestClient(app) as client:
        headers = _login(client)
        created = client.post(
            "/api/data-scripts/agent/sessions",
            headers=headers,
            json={
                "project_id": project.id,
                "env_id": env.id,
                "instruction": "客户300002帮我造一个订单",
                "topbar_customer_ids": ["300001"],
            },
        ).json()
    assert created["goal"]["customer_ids"] == ["300002"]
    assert created["goal"]["customer_source"] == "natural_language"
```

- [ ] **Step 2: Verify the request field is currently ignored**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py::test_agent_customer_priority_is_natural_language_then_topbar_then_bound -v`

Expected: FAIL.

- [ ] **Step 3: Extend the request schema and route**

```python
class DataAgentSessionCreate(BaseModel):
    project_id: int
    env_id: int
    instruction: str = Field(min_length=1, max_length=4000)
    topbar_customer_ids: list[str] = Field(default_factory=list, max_length=100)
```

Pass `payload.topbar_customer_ids` as the final argument to `create_agent_session`.

- [ ] **Step 4: Validate page IDs and resolve the bound account**

```python
topbar_ids = []
for value in topbar_customer_ids or []:
    text = str(value or "").strip()
    if not text.isdigit():
        raise HTTPException(status_code=400, detail=f"客户ID只能是数字：{text}")
    topbar_ids.append(text)
bound_ids = bound_customer_ids_for_environment(db, project_id, env_id)
compile_context = {
    "topbar_customer_ids": list(dict.fromkeys(topbar_ids)),
    "bound_customer_ids": bound_ids,
}
```

Implement `bound_customer_ids_for_environment` using the current project account binding and existing decrypted profile variables; return only numeric `customer_id/customer_ids` values.

- [ ] **Step 5: Send the stored top-bar IDs from the frontend**

```javascript
const topbarCustomerIds = String(localStorage.getItem("dataScriptCustomerIds") || "")
  .split(/[\n,，;；]+/)
  .map((item) => item.trim())
  .filter(Boolean);

body: {
  project_id: Number(options.projectId),
  env_id: Number(options.envId),
  instruction: form.get("instruction"),
  topbar_customer_ids: topbarCustomerIds,
},
```

- [ ] **Step 6: Run API, frontend static, and agent tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the context path**

```powershell
git add app/agent_schemas.py app/routers/data_factory_agent.py app/services/data_factory_agent.py static/data-factory-agent.js tests/test_data_factory_agent.py
git commit -m "feat: pass customer context into data agent contracts"
```

---

### Task 4: Make Problem-Goods Contracts Use Order Facts

**Files:**
- Modify: `app/services/data_factory_agent_intent.py`
- Modify: `app/services/data_factory_agent_contract.py`
- Modify: `app/services/data_factory_agent.py:1100-1405`
- Test: `tests/test_data_factory_agent_contract.py`

**Interfaces:**
- Consumes: deterministic `problem_scope`, `problem_changes`, and existing-order facts.
- Produces: exact problem-goods operations or one consolidated clarification.

- [ ] **Step 1: Add failing scope and full-refund tests**

```python
def test_problem_goods_all_refund_keeps_unit_price():
    result = reduce_intent_fields({}, "两番都处理问题产品，全部退")
    fields = result["resolved_fields"]
    assert fields["problem_scope"]["value"] == "all"
    assert fields["problem_refund_quantity"]["value"] == "all"
    assert fields["problem_refund_freight"]["value"] == "all"
    assert fields["problem_preserve_price"]["value"] is True


def test_existing_order_unit_price_change_does_not_request_shape():
    compiled = compile_agent_contract(
        _problem_payload(),
        [{"role": "user", "content": "订单2026071715475684-300001第1番单价改成0"}],
        reduce_intent_fields({}, "订单2026071715475684-300001第1番单价改成0"),
        {},
    )
    assert compiled.status == "awaiting_confirmation"
    assert "商品种类数" not in compiled.question
```

- [ ] **Step 2: Run and verify failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent_contract.py -v -k "problem_goods or existing_order"`

Expected: FAIL.

- [ ] **Step 3: Add exact deterministic expressions**

```python
if re.search(r"(?:全部|所有|每番|各番|分别).{0,8}(?:商品|问题产品)|(?:两|二|2)番都", text):
    resolve("problem_scope", "all", text[:200])
if re.search(r"(?:全部退|全退(?:了)?)", text):
    resolve("problem_refund_quantity", "all", text[:200])
    resolve("problem_refund_freight", "all", text[:200])
    resolve("problem_preserve_price", True, text[:200])
```

- [ ] **Step 4: Enforce only the two agreed clarification gates**

```python
if operation_type == "problem_goods" and known_item_count > 1 and not problem_scope:
    return ContractCompileResult("clarifying", {}, "订单包含多个商品，请说明处理第几番或全部商品。")
if operation_type == "problem_goods" and not problem_changes:
    return ContractCompileResult("clarifying", {}, "请说明问题产品需要修改数量、单价或国内运费，以及目标值。")
```

Remove the resume-order rule that requires user-supplied item count and quantity for an existing order price change. Execution must inspect the order instead.

- [ ] **Step 5: Run intent, contract, and tool tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent_contract.py tests/test_data_factory_agent.py tests/test_problem_goods_script.py -q`

Expected: PASS.

- [ ] **Step 6: Commit problem-goods semantics**

```powershell
git add app/services/data_factory_agent_intent.py app/services/data_factory_agent_contract.py app/services/data_factory_agent.py tests/test_data_factory_agent_contract.py
git commit -m "feat: compile problem goods intent from explicit scope"
```

---

### Task 5: Fall Back from Balance to Bank Only on Insufficient Balance

**Files:**
- Modify: `app/services/data_factory_agent_tools.py:583-611,633-650`
- Test: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: balance runner result and `is_insufficient_balance(result)`.
- Produces: one bank-payment retry with finance confirmation and an auditable fallback summary.

- [ ] **Step 1: Write fallback classification tests**

```python
def test_payment_falls_back_to_bank_only_for_insufficient_balance(monkeypatch):
    calls = []
    monkeypatch.setattr(data_scripts, "run_balance_payment_script", lambda e, v: {"passed": False, "reason": "余额不足"})
    monkeypatch.setattr(data_scripts, "run_bank_payment_script", lambda e, v: calls.append(v) or {"passed": True, "finance_passed": True})
    result = agent_tools._pay_order(_tool_context(), {})
    assert result["passed"] is True
    assert result["summary"]["payment_fallback_reason"] == "insufficient_balance"
    assert calls[0]["finance_confirm"] is True


def test_payment_does_not_fallback_for_authentication_failure(monkeypatch):
    monkeypatch.setattr(data_scripts, "run_balance_payment_script", lambda e, v: {"passed": False, "reason": "Token失效"})
    monkeypatch.setattr(data_scripts, "run_bank_payment_script", lambda *a: pytest.fail("must not fallback"))
    assert agent_tools._pay_order(_tool_context(), {})["passed"] is False
```

- [ ] **Step 2: Run and verify the first test fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -v -k "payment_falls_back or authentication_failure"`

Expected: FAIL.

- [ ] **Step 3: Add strict classification and one retry**

```python
INSUFFICIENT_BALANCE_PATTERNS = ("余额不足", "可用余额不足", "insufficient balance")


def is_insufficient_balance(result: Dict[str, Any]) -> bool:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    text = " ".join(str(value or "") for value in (result.get("reason"), result.get("error"), summary.get("reason"), summary.get("message"))).lower()
    return any(pattern.lower() in text for pattern in INSUFFICIENT_BALANCE_PATTERNS)
```

After the balance call, call the bank runner once only when this function is true. Add `payment_fallback_reason`, `initial_payment_mode`, and `final_payment_mode` to the sanitized summary.

- [ ] **Step 4: Run payment and agent tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py tests/test_data_script_contract.py -q -k "payment or agent or contract"`

Expected: PASS.

- [ ] **Step 5: Commit payment fallback**

```powershell
git add app/services/data_factory_agent_tools.py tests/test_data_factory_agent.py
git commit -m "feat: fallback to bank on insufficient balance"
```

---

### Task 6: Automate and Secure 500-Yuan Permission Recovery

**Files:**
- Modify: `app/agent_schemas.py`
- Modify: `app/routers/data_factory_agent.py`
- Modify: `app/services/data_factory_agent.py:2631-2678`
- Modify: `app/services/data_factory_agent_tools.py:697-718,997-1025`
- Modify: `static/data-factory-agent.js:177-199,442-467`
- Test: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: project-scoped account profiles and optional one-use credentials.
- Produces: automatic Shen Wenni retry, then `awaiting_permission` manual resume without serializing secrets.

- [ ] **Step 1: Add failing automatic and manual-resume tests**

```python
def test_large_refund_automatically_uses_shen_wenni_once(monkeypatch):
    context = _tool_context()
    context.state["permission_retry_count"] = 0
    profile = SimpleNamespace(id=4, profile_name="后台沈文妮账号", status="active")
    monkeypatch.setattr(agent_tools, "find_permission_profile", lambda *a: profile)
    agent_tools.prepare_permission_retry(context)
    assert context.state["backend_account_profile_id"] == 4
    assert context.state["allow_large_refund"] is True
    assert context.state["permission_retry_count"] == 1


def test_temporary_permission_password_is_never_serialized():
    session = _session(status="awaiting_permission")
    agent_service._TEMP_PERMISSION_SECRETS[session.id] = {"backend_password": "secret"}
    payload = agent_service._serialize_session(session)
    assert "secret" not in json.dumps(payload, ensure_ascii=False)
```

- [ ] **Step 2: Run and verify missing helpers**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -v -k "shen_wenni or temporary_permission"`

Expected: FAIL.

- [ ] **Step 3: Add project-scoped automatic account resolution**

```python
def find_permission_profile(db: Session, project_id: int):
    return (
        db.query(TestAccountProfile)
        .filter(
            TestAccountProfile.project_id == project_id,
            TestAccountProfile.status == "active",
            TestAccountProfile.profile_name == "后台沈文妮账号",
        )
        .order_by(TestAccountProfile.id.asc())
        .first()
    )


def prepare_permission_retry(context: AgentToolContext) -> bool:
    if int(context.state.get("permission_retry_count") or 0) >= 1:
        return False
    profile = find_permission_profile(context.db, context.project_id)
    if not profile:
        return False
    context.state.update({
        "backend_account_profile_id": profile.id,
        "allow_large_refund": True,
        "permission_retry_count": 1,
        "awaiting_permission": False,
    })
    return True
```

- [ ] **Step 4: Carry the permission flag into script variables**

```python
if context.state.get("allow_large_refund") is True:
    variables["allow_large_refund"] = True
```

When the first permission pause occurs, call `prepare_permission_retry(context)` and continue the same problem item once. A second identical pause must return `awaiting_permission`.

- [ ] **Step 5: Extend the resume request with mutually exclusive credential sources**

```python
class DataAgentPermissionResume(BaseModel):
    plan_version: int
    backend_account_profile_id: int | None = None
    backend_account: str = Field(default="", max_length=160)
    backend_password: str = Field(default="", max_length=500)
```

Reject a request unless it supplies a profile ID or both temporary fields. Store temporary credentials in `_TEMP_PERMISSION_SECRETS[session_id]`, not `runtime_state`.

- [ ] **Step 6: Clear one-use secrets on every terminal path**

```python
def _clear_permission_secret(session_id: str) -> None:
    secret = _TEMP_PERMISSION_SECRETS.pop(session_id, None)
    if isinstance(secret, dict):
        secret.clear()
```

Call this from finalization, cancellation, session cleanup, failed executor submission, and immediately after `_problem_runtime_variables` copies the values into a local tool invocation.

- [ ] **Step 7: Render project-filtered profiles and temporary inputs**

```javascript
<select name="backend_account_profile_id">
  <option value="">临时输入账号</option>${accountOptions}
</select>
<input name="backend_account" autocomplete="off" placeholder="临时后台账号" />
<input name="backend_password" type="password" autocomplete="new-password" placeholder="临时密码" />
```

Send profile ID or temporary credentials, never both. Clear password inputs after submission regardless of success.

- [ ] **Step 8: Run permission, security, and agent tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py tests/test_problem_goods_script.py tests/test_permissions.py -q`

Expected: PASS.

- [ ] **Step 9: Commit permission recovery**

```powershell
git add app/agent_schemas.py app/routers/data_factory_agent.py app/services/data_factory_agent.py app/services/data_factory_agent_tools.py static/data-factory-agent.js tests/test_data_factory_agent.py
git commit -m "feat: resume large refunds with scoped accounts"
```

---

### Task 7: Build and Run the Hit-Rate Evaluation Gate

**Files:**
- Create: `tests/fixtures/data_agent_intent_cases.json`
- Create: `tests/test_data_agent_hit_rate.py`
- Create: `scripts/evaluate_data_agent_hit_rate.py`
- Modify: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: fixture entries with `instruction`, `expected_status`, and `expected_goal`.
- Produces: deterministic pytest coverage and a live DeepSeek three-round summary without business execution.

- [ ] **Step 1: Add the first explicit and ambiguous fixture cases**

Use a grouped fixture that deterministically expands to 60 explicit cases (`10 targets × 3 shapes × 2 prices`) plus these 20 fixed ambiguity/conflict/capability-gap cases:

```json
{
  "targets": [
    ["做到待付款", "order_offered"],
    ["报价完等付款", "order_offered"],
    ["做到付款前", "order_offered"],
    ["做到待拍下", "pending_purchase"],
    ["做到已付款", "order_paid"],
    ["做到采购待财务付款", "purchase_wait_pay"],
    ["做到上架入库", "shelf_stored"],
    ["做到配送单提出", "warehouse_delivery_created"],
    ["做到配送单报价", "porder_offered"],
    ["做到配送单支付完成", "porder_paid"]
  ],
  "shapes": [
    ["1个店1种商品每种1件", 1, 1, 1],
    ["2个店每店1种商品每种2件", 2, 1, 2],
    ["1个店3种商品每种4件", 1, 3, 4]
  ],
  "prices": [
    ["商品总价60元", "goods_total", "60"],
    ["每种商品单价10元", "uniform_unit", "10"]
  ],
  "ambiguous": [
    ["订单2026071715475684-300001有两番，处理问题产品", "clarifying", "第几番或全部"],
    ["订单2026071715475684-300001第1番处理问题产品", "clarifying", "修改数量、单价或国内运费"],
    ["帮我造订单，价格100元", "clarifying", "总价还是单价"],
    ["订单2026071715475684-300001和配送单P2024-001继续处理", "clarifying", "哪一种单据"],
    ["订单做到待付款又做到待拍下", "clarifying", "目标状态"],
    ["两个商品只处理一个问题产品", "clarifying", "第几番"],
    ["问题产品数量改一下", "clarifying", "目标值"],
    ["问题产品运费调整", "clarifying", "目标值"],
    ["问题产品单价修改", "clarifying", "目标值"],
    ["把订单处理一下", "clarifying", "具体操作"],
    ["帮我", "clarifying", "造数目标"],
    ["继续这个订单", "clarifying", "订单号"],
    ["继续这个配送单", "clarifying", "配送单号"],
    ["订单号ABC和订单号XYZ都继续", "clarifying", "订单号"],
    ["客户300001改成客户300002", "clarifying", "客户"],
    ["每种数量1又改成每种数量2", "clarifying", "数量"],
    ["商品总价100元又说单价100元", "clarifying", "价格"],
    ["删除订单2026071715475684-300001", "blocked", "删除订单"],
    ["执行任意SQL修改订单", "blocked", "SQL"],
    ["调用这个URL帮我造数 https://example.com", "blocked", "URL"]
  ]
}
```

`load_cases()` builds each explicit instruction as `帮我创建订单，{shape}，{price}，{target}` and attaches the exact target, shop count, per-shop count, quantity, and pricing expectations from the fixture.

- [ ] **Step 2: Add deterministic parameterized evaluation**

```python
@pytest.mark.parametrize("case", load_cases(), ids=lambda item: item["id"])
def test_data_agent_contract_fixture(case):
    status, goal, question = analyze_without_execution(case["instruction"])
    assert status == case["expected_status"]
    for key, value in case.get("expected_goal", {}).items():
        assert goal.get(key) == value
    if case.get("question_contains"):
        assert case["question_contains"] in question
```

- [ ] **Step 3: Run the fixture tests and fix only compiler gaps**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_hit_rate.py -v`

Expected: PASS after all fixture cases are represented by explicit compiler behavior.

- [ ] **Step 4: Implement the live analysis-only evaluator**

```python
def main() -> int:
    rounds = 3
    cases = load_cases()
    results = [evaluate_round(cases, round_index) for round_index in range(rounds)]
    explicit_rates = [item["explicit_correct"] / item["explicit_total"] for item in results]
    print(json.dumps({"rounds": results, "explicit_rates": explicit_rates}, ensure_ascii=False, indent=2))
    return 0 if all(rate >= 0.95 for rate in explicit_rates) else 1
```

The evaluator must call `_analyze_turn` only; it must never confirm a session or invoke `execute_agent_tool`.

- [ ] **Step 5: Run all automated gates**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py tests/test_data_factory_agent_contract.py tests/test_data_agent_hit_rate.py tests/test_data_script_contract.py tests/test_problem_goods_script.py -q`

Expected: PASS.

- [ ] **Step 6: Run the real DeepSeek evaluation**

Run: `.venv\Scripts\python.exe scripts/evaluate_data_agent_hit_rate.py`

Expected: exit 0; every round reports explicit first-turn accuracy `>= 0.95`, and no business record with kind `data_agent_tool` is created.

- [ ] **Step 7: Commit evaluation assets**

```powershell
git add tests/fixtures/data_agent_intent_cases.json tests/test_data_agent_hit_rate.py scripts/evaluate_data_agent_hit_rate.py tests/test_data_factory_agent.py
git commit -m "test: gate data agent first-turn hit rate"
```

---

### Task 8: Final Verification and Phase-One Handoff

**Files:**
- No source changes expected.

**Interfaces:**
- Consumes: all phase-one tasks.
- Produces: verified phase-one baseline ready for the controlled-learning plan.

- [ ] **Step 1: Run the complete project test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`

Expected: PASS.

- [ ] **Step 2: Run syntax checks for changed frontend files**

Run: `node --check static/data-factory-agent.js`

Expected: exit 0.

- [ ] **Step 3: Inspect final scope**

Run: `git status --short` and `git diff --stat`

Expected: only phase-one files remain modified; database, logs, reports, temporary credentials, and evaluation outputs are absent.

- [ ] **Step 4: Record the phase-one verification commit if verification required a test-only adjustment**

```powershell
git add tests/test_data_factory_agent.py tests/test_data_factory_agent_contract.py tests/test_data_agent_hit_rate.py
git commit -m "test: verify data agent core upgrade"
```

Skip this step when verification makes no file changes.
