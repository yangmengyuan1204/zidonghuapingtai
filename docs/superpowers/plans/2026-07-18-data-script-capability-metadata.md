# Data Script Capability Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make data-script capabilities discoverable through project/module-scoped metadata so new natural-language abilities can be enabled incrementally without changing existing script interfaces.

**Architecture:** Replace the registry's name/function-only entries with validated immutable capability specifications while preserving `SCRIPT_REGISTRY[key]["func"]` compatibility. Filter capabilities before prompt construction and expose only explicitly enabled tools with risk and confirmation metadata.

**Tech Stack:** Python 3.11, dataclasses, FastAPI 0.115, existing data scripts, pytest.

## Global Constraints

- Complete and verify the core hit-rate and controlled-learning plans first.
- Run every Python test with `.venv\Scripts\python.exe`.
- Preserve every existing public `run_*_script(env, variables)` signature and script return contract.
- Metadata is code-versioned; do not add another database table for capability definitions.
- Capabilities are disabled for agent use until their metadata, contract tests, risk gates, and result validator pass.
- High-risk money, batch, and OEM operations require explicit risk confirmation.

---

### Task 1: Define and Validate Capability Specifications

**Files:**
- Create: `app/data_scripts/capabilities.py`
- Modify: `app/data_scripts/registry.py`
- Modify: `app/data_scripts/__init__.py`
- Test: `tests/test_data_script_capabilities.py`

**Interfaces:**
- Produces: `ParameterSpec`, `RiskSpec`, `DataScriptCapability`, `register_capability`, and `capability_catalog`.
- Preserves: `SCRIPT_REGISTRY[key]["func"]` and `registered_script_keys()`.

- [ ] **Step 1: Write registry compatibility and validation tests**

```python
def test_register_capability_projects_runner_into_legacy_registry():
    original = dict(SCRIPT_REGISTRY["shopping_cart"])
    runner = lambda env, variables: {"passed": True}
    try:
        register_capability(DataScriptCapability(
            key="shopping_cart", name="购物车", module="order", projects=("日本站测试",),
            intents=("加入购物车",), examples=("加入购物车",), parameters=(),
            risk=RiskSpec(level="low", mutating=False, second_confirmation=False),
            runner=runner, result_validator=None, agent_enabled=False,
        ))
        assert SCRIPT_REGISTRY["shopping_cart"]["func"] is runner
        assert capability_catalog()["shopping_cart"].runner is runner
    finally:
        SCRIPT_REGISTRY["shopping_cart"] = original
        CAPABILITIES.pop("shopping_cart", None)


def test_mutating_capability_requires_result_validator():
    with pytest.raises(ValueError, match="result_validator"):
        DataScriptCapability(
            key="bad", name="错误能力", module="order", projects=("日本站测试",),
            intents=("造订单",), examples=("帮我造订单",), parameters=(),
            risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
            runner=lambda env, variables: {}, result_validator=None, agent_enabled=True,
        ).validate()
```

- [ ] **Step 2: Run and verify missing module**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py -v`

Expected: FAIL.

- [ ] **Step 3: Add immutable metadata types**

```python
@dataclass(frozen=True)
class ParameterSpec:
    name: str
    label: str
    value_type: str
    required: bool = False
    default: Any = None
    sources: tuple[str, ...] = ("natural_language", "page_context", "environment", "default")


@dataclass(frozen=True)
class RiskSpec:
    level: str
    mutating: bool
    second_confirmation: bool


@dataclass(frozen=True)
class DataScriptCapability:
    key: str
    name: str
    module: str
    projects: tuple[str, ...]
    intents: tuple[str, ...]
    examples: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]
    risk: RiskSpec
    runner: Callable[[Any, Dict[str, Any]], Any]
    result_validator: Callable[[Dict[str, Any]], tuple[bool, str]] | None
    account_role: str = ""
    preconditions: tuple[str, ...] = ()
    result_state: str = ""
    resume_key: str = ""
    idempotency_key: str = ""
    agent_enabled: bool = False

    def validate(self) -> "DataScriptCapability":
        if not self.key or not callable(self.runner):
            raise ValueError("capability key and runner are required")
        if self.risk.mutating and not callable(self.result_validator):
            raise ValueError("mutating capability requires result_validator")
        if self.risk.level not in {"low", "medium", "high", "critical"}:
            raise ValueError("invalid risk level")
        return self
```

- [ ] **Step 4: Keep the legacy dictionary as a compatibility projection**

```python
CAPABILITIES: Dict[str, DataScriptCapability] = {}


def register_capability(spec: DataScriptCapability) -> None:
    CAPABILITIES[spec.key] = spec.validate()
    SCRIPT_REGISTRY.setdefault(spec.key, {})
    SCRIPT_REGISTRY[spec.key].update({"name": spec.name, "func": spec.runner, "capability": spec})
```

Existing `register_script` continues to work during migration and updates the matching capability runner when present.

Keep module initialization acyclic by importing and calling `register_builtin_capabilities()` at the end of `app/data_scripts/__init__.py`, after every runner import and legacy `register_script` call:

```python
from .capabilities import register_builtin_capabilities

register_builtin_capabilities()
```

Inside `register_builtin_capabilities`, import the initialized package lazily before referencing runners:

```python
def register_builtin_capabilities() -> None:
    import app.data_scripts as data_scripts
    if CAPABILITIES:
        return
    return None
```

Later tasks add their registration blocks inside this function before its final return.

- [ ] **Step 5: Run capability and existing registry contract tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py tests/test_data_script_contract.py -q`

Expected: PASS.

- [ ] **Step 6: Commit metadata types**

```powershell
git add app/data_scripts/capabilities.py app/data_scripts/registry.py app/data_scripts/__init__.py tests/test_data_script_capabilities.py
git commit -m "feat: define data script capability metadata"
```

---

### Task 2: Register the Existing Core Agent Capabilities

**Files:**
- Modify: `app/data_scripts/capabilities.py`
- Modify: `app/services/data_factory_agent_tools.py:51-143`
- Test: `tests/test_data_script_capabilities.py`

**Interfaces:**
- Consumes: current core runners and tool validators.
- Produces: enabled metadata for `full_flow`, `resume_order_flow`, `resume_porder_flow`, and `problem_goods`.

- [ ] **Step 1: Write core metadata completeness tests**

```python
@pytest.mark.parametrize("key", ["full_flow", "resume_order_flow", "resume_porder_flow", "problem_goods"])
def test_core_agent_capability_is_complete(key):
    spec = capability_catalog()[key]
    assert spec.agent_enabled is True
    assert spec.projects == ("日本站测试",)
    assert spec.intents
    assert spec.examples
    assert callable(spec.result_validator)
```

- [ ] **Step 2: Run and verify missing specs**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py -v -k "core_agent"`

Expected: FAIL.

- [ ] **Step 3: Register the full-flow specification**

```python
register_capability(DataScriptCapability(
    key="full_flow",
    name="日本站订单全流程",
    module="order",
    projects=("日本站测试",),
    intents=("新建订单", "造订单", "订单做到指定状态"),
    examples=("帮我造一个订单到待付款", "创建两种商品各一件做到上架"),
    parameters=(
        ParameterSpec("customer_ids", "客户ID", "list[str]"),
        ParameterSpec("order_shop_count", "店铺数", "int", default=1),
        ParameterSpec("order_per_shop", "每店商品数", "int", default=1),
        ParameterSpec("order_item_num", "每种购买数量", "int", default=1),
        ParameterSpec("offer_price", "统一单价", "decimal", default="10"),
        ParameterSpec("stop_after_node", "目标节点", "node", default="order_offered"),
    ),
    risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
    runner=data_scripts.run_full_flow_script,
    result_validator=validate_full_flow_result,
    account_role="frontend_and_backend",
    resume_key="order_sn",
    idempotency_key="contract_hash",
    agent_enabled=True,
))
```

Register the three other core specs with concrete examples, required identifiers, current validators, and exact risk levels.

```python
def validate_script_result(result: Dict[str, Any]) -> tuple[bool, str]:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    passed = bool(result.get("passed") or result.get("result") == "passed")
    return passed, "" if passed else str(summary.get("reason") or result.get("reason") or "脚本未返回成功证据")


CORE_CONFIGS = (
    ("resume_order_flow", "已有订单续跑", "order", ("继续订单", "订单续跑"), ("订单2026071715475684-300001继续到待拍下",),
     (ParameterSpec("order_sn", "订单号", "str", required=True), ParameterSpec("stop_after_node", "目标节点", "node")), data_scripts.run_resume_order_flow_script, "order_sn"),
    ("resume_porder_flow", "已有配送单续跑", "porder", ("继续配送单", "配送单续跑"), ("配送单P2024-001继续到支付完成",),
     (ParameterSpec("porder_sn", "配送单号", "str", required=True), ParameterSpec("stop_after_node", "目标节点", "node")), data_scripts.run_resume_porder_flow_script, "porder_sn"),
    ("problem_goods", "日本站问题产品处理", "problem_goods", ("提出问题产品", "处理问题产品", "问题产品退款"), ("订单2026071715475684-300001第1番单价改成0",),
     (ParameterSpec("order_sn", "订单号", "str", required=True), ParameterSpec("problem_scope", "处理范围", "scope", required=True)), data_scripts.run_problem_goods_script, "problem_goods_id"),
)
for key, name, module, intents, examples, parameters, runner, resume_key in CORE_CONFIGS:
    register_capability(DataScriptCapability(
        key=key, name=name, module=module, projects=("日本站测试",),
        intents=intents, examples=examples, parameters=parameters,
        risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
        runner=runner, result_validator=validate_script_result,
        account_role="frontend_and_backend", resume_key=resume_key,
        idempotency_key="contract_hash", agent_enabled=True,
    ))

STANDARD_STEP_CONFIGS = (
    ("order_quote", "订单报价", data_scripts.run_order_quote_script, "medium", False, True),
    ("balance_payment", "订单余额支付", data_scripts.run_balance_payment_script, "high", True, False),
    ("bank_payment", "订单银行支付", data_scripts.run_bank_payment_script, "high", True, False),
    ("purchase_to_shelf", "待拍下到上架", data_scripts.run_purchase_to_shelf_script, "medium", False, True),
    ("purchase_to_shelf_chain", "待拍下到上架组合流程", data_scripts.run_purchase_to_shelf_chain, "medium", False, True),
    ("porder_balance_payment", "配送单余额支付", data_scripts.run_porder_balance_payment_script, "high", True, False),
    ("porder_bank_payment", "配送单银行支付", data_scripts.run_porder_bank_payment_script, "high", True, False),
)
for key, name, runner, risk_level, second_confirmation, enabled in STANDARD_STEP_CONFIGS:
    identifier = "porder_sn" if key.startswith("porder_") else "order_sn"
    register_capability(DataScriptCapability(
        key=key, name=name, module="porder" if key.startswith("porder_") else "order",
        projects=("日本站测试",), intents=(name,), examples=(f"{name}，单号由当前任务取得",),
        parameters=(ParameterSpec(identifier, "配送单号" if identifier == "porder_sn" else "订单号", "str", required=True),),
        risk=RiskSpec(level=risk_level, mutating=True, second_confirmation=second_confirmation),
        runner=runner, result_validator=validate_script_result,
        account_role="frontend_and_backend", resume_key=identifier,
        idempotency_key="contract_hash", agent_enabled=enabled,
    ))
```

- [ ] **Step 4: Project legacy `TOOL_SPECS` from capability metadata**

```python
for tool_name, capability_key in {
    "run_full_flow": "full_flow",
    "resume_order_flow": "resume_order_flow",
    "resume_porder_flow": "resume_porder_flow",
    "process_problem_goods": "problem_goods",
}.items():
    capability = capability_catalog()[capability_key]
    TOOL_SPECS[tool_name] = AgentToolSpec(
        tool_name,
        f"{capability.name}：{'；'.join(capability.intents)}",
        capability.risk.mutating,
        "组合脚本",
    )
```

Retain atomic tools that do not map one-to-one to a script as explicit tool specs.

- [ ] **Step 5: Run core agent, registry, and capability tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py tests/test_data_script_contract.py tests/test_data_factory_agent.py -q`

Expected: PASS.

- [ ] **Step 6: Commit core capability specs**

```powershell
git add app/data_scripts/capabilities.py app/services/data_factory_agent_tools.py tests/test_data_script_capabilities.py
git commit -m "feat: register core data agent capabilities"
```

---

### Task 3: Filter Capabilities by Project, Module, and Risk

**Files:**
- Modify: `app/data_scripts/capabilities.py`
- Modify: `app/services/data_factory_agent_prompts.py`
- Modify: `app/services/data_factory_agent.py`
- Test: `tests/test_data_script_capabilities.py`

**Interfaces:**
- Consumes: `available_capabilities(project_name, modules, max_risk=None)`.
- Produces: a bounded prompt catalog containing only enabled applicable capabilities.

- [ ] **Step 1: Write filtering and prompt-size tests**

```python
def test_available_capabilities_excludes_other_projects_and_disabled_specs():
    specs = available_capabilities("日本站测试", {"order"})
    assert all("日本站测试" in spec.projects for spec in specs)
    assert all(spec.agent_enabled for spec in specs)
    assert all(spec.module == "order" for spec in specs)


def test_analysis_prompt_does_not_include_unrelated_oem_capabilities():
    prompt = build_analysis_prompt(_order_messages(), capability_specs=available_capabilities("日本站测试", {"order"}))
    assert "OEM大货" not in prompt
```

- [ ] **Step 2: Run and verify failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py -v -k "available_capabilities or unrelated_oem"`

Expected: FAIL.

- [ ] **Step 3: Implement stable filtering**

```python
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def available_capabilities(project_name: str, modules: set[str], max_risk: str | None = None):
    limit = RISK_ORDER[max_risk] if max_risk else 3
    return [
        spec for spec in CAPABILITIES.values()
        if spec.agent_enabled
        and project_name in spec.projects
        and spec.module in modules
        and RISK_ORDER[spec.risk.level] <= limit
    ]
```

Sort by module, risk, and key before prompt serialization.

- [ ] **Step 4: Serialize only intent-facing metadata**

```python
def public_capability_catalog(specs):
    return [
        {
            "key": spec.key,
            "name": spec.name,
            "module": spec.module,
            "intents": list(spec.intents),
            "examples": list(spec.examples),
            "parameters": [
                {"name": item.name, "label": item.label, "required": item.required, "default": item.default}
                for item in spec.parameters
            ],
            "preconditions": list(spec.preconditions),
            "result_state": spec.result_state,
            "risk": {"level": spec.risk.level, "second_confirmation": spec.risk.second_confirmation},
        }
        for spec in specs
    ]
```

This excludes runner objects, account secrets, URLs, and implementation details.

- [ ] **Step 5: Run capability, prompt, and agent tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py tests/test_data_factory_agent.py -q`

Expected: PASS.

- [ ] **Step 6: Commit scoped discovery**

```powershell
git add app/data_scripts/capabilities.py app/services/data_factory_agent_prompts.py app/services/data_factory_agent.py tests/test_data_script_capabilities.py
git commit -m "feat: scope data agent capabilities by project"
```

---

### Task 4: Preserve Read-Only Tools and Add the Low-Risk Shopping-Cart Capability

**Files:**
- Modify: `app/data_scripts/capabilities.py`
- Modify: `app/services/data_factory_agent_tools.py`
- Test: `tests/test_data_script_capabilities.py`

**Interfaces:**
- Produces: unchanged explicit read-only tool specs plus metadata-driven shopping-cart preparation.

- [ ] **Step 1: Write low-risk activation tests**

```python
@pytest.mark.parametrize("key", ["inspect_order_state", "inspect_porder_state", "inspect_problem_goods"])
def test_read_only_tools_remain_explicit_non_mutating_specs(key):
    assert TOOL_SPECS[key].mutating is False
    assert TOOL_SPECS[key].category == "查询接口"


def test_shopping_cart_capability_is_enabled_without_second_confirmation():
    spec = capability_catalog()["shopping_cart"]
    assert spec.agent_enabled is True
    assert spec.risk.mutating is True
    assert spec.risk.second_confirmation is False
```

- [ ] **Step 2: Run and verify missing metadata**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py -v -k "low_risk"`

Expected: FAIL because shopping-cart capability metadata is not registered; the existing inspection assertions continue to pass.

- [ ] **Step 3: Keep inspections outside the script registry**

Keep `inspect_order_state`, `inspect_porder_state`, and `inspect_problem_goods` in `TOOL_SPECS`; do not add them to `SCRIPT_REGISTRY` or the script capability catalog. Their current non-mutating contract remains covered by the test in Step 1.

- [ ] **Step 4: Register shopping-cart preparation**

```python
register_capability(DataScriptCapability(
    key="shopping_cart", name="购物车准备", module="order", projects=("日本站测试",),
    intents=("加入购物车", "准备购物车商品"), examples=("搜索衣服，准备1个店1种商品",),
    parameters=(
        ParameterSpec("keyword", "商品关键词", "str", default="衣服"),
        ParameterSpec("shop_type", "店铺类型", "str", default="1688"),
        ParameterSpec("target_shops", "目标店铺数", "int", default=1),
        ParameterSpec("per_shop", "每店商品数", "int", default=1),
    ),
    risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
    runner=data_scripts.run_shopping_cart_script,
    result_validator=validate_script_result,
    account_role="frontend", idempotency_key="contract_hash", agent_enabled=True,
))
```

- [ ] **Step 5: Run capability and tool tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py tests/test_data_factory_agent.py -q -k "capability or inspect or cart"`

Expected: PASS.

- [ ] **Step 6: Commit low-risk capabilities**

```powershell
git add app/data_scripts/capabilities.py app/services/data_factory_agent_tools.py tests/test_data_script_capabilities.py
git commit -m "feat: enable low risk data agent capabilities"
```

---

### Task 5: Add Warehouse and Materials Capabilities

**Files:**
- Modify: `app/data_scripts/capabilities.py`
- Modify: `app/services/data_factory_agent_tools.py`
- Test: `tests/test_data_script_capabilities.py`

**Interfaces:**
- Produces: metadata-driven warehouse delivery, direct box-to-shelf, material order, and material generation tools.

- [ ] **Step 1: Write required-parameter and result-validator tests**

```python
@pytest.mark.parametrize("key,required", [
    ("warehouse_delivery", {"warehouse_sku_count", "send_num"}),
    ("direct_box_to_shelf", {"order_sn"}),
    ("material_order", {"customer_ids"}),
    ("material_generation", {"customer_ids"}),
])
def test_warehouse_material_metadata_declares_required_inputs(key, required):
    spec = capability_catalog()[key]
    actual = {item.name for item in spec.parameters if item.required}
    assert required <= actual
    assert callable(spec.result_validator)
```

- [ ] **Step 2: Run and verify failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py -v -k "warehouse_material"`

Expected: FAIL.

- [ ] **Step 3: Register medium-risk specs disabled by default**

```python
MEDIUM_RISK_CONFIGS = (
    ("warehouse_delivery", "仓库提出配送单", data_scripts.run_warehouse_delivery_script,
     (ParameterSpec("warehouse_sku_count", "仓库提出番数", "int", required=True), ParameterSpec("send_num", "每番提出数量", "int", required=True))),
    ("direct_box_to_shelf", "直接装箱上架", data_scripts.run_direct_box_to_shelf_script,
     (ParameterSpec("order_sn", "订单号", "str", required=True),)),
    ("material_order", "辅料单", data_scripts.run_material_order_script,
     (ParameterSpec("customer_ids", "客户ID", "list[str]", required=True),)),
    ("material_generation", "辅料生成", data_scripts.run_material_generation_script,
     (ParameterSpec("customer_ids", "客户ID", "list[str]", required=True),)),
)
for key, name, runner, parameters in MEDIUM_RISK_CONFIGS:
    register_capability(DataScriptCapability(
        key=key, name=name, module="warehouse" if "warehouse" in key or "box" in key else "material",
        projects=("日本站测试",), intents=(name,), examples=(f"执行{name}",), parameters=parameters,
        risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
        runner=runner, result_validator=validate_script_result,
        account_role="frontend_and_backend", resume_key="order_sn",
        idempotency_key="contract_hash", agent_enabled=False,
    ))
```

- [ ] **Step 4: Enable one capability at a time after focused verification**

Run each script's existing focused tests, then flip only that spec to `agent_enabled=True`. Do not enable the next spec when the current validator is incomplete.

- [ ] **Step 5: Run warehouse/material and agent tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py tests/test_data_script_contract.py tests/test_data_factory_agent.py -q -k "warehouse or material or capability or contract"`

Expected: PASS.

- [ ] **Step 6: Commit warehouse/material capabilities**

```powershell
git add app/data_scripts/capabilities.py app/services/data_factory_agent_tools.py tests/test_data_script_capabilities.py
git commit -m "feat: add warehouse and material agent capabilities"
```

---

### Task 6: Add High-Risk Confirmation Gates for Money Capabilities

**Files:**
- Modify: `app/data_scripts/capabilities.py`
- Modify: `app/services/data_factory_agent.py`
- Modify: `app/agent_schemas.py`
- Modify: `app/routers/data_factory_agent.py`
- Modify: `static/data-factory-agent.js`
- Test: `tests/test_data_script_capabilities.py`

**Interfaces:**
- Produces: `awaiting_risk_confirmation` for recharge, balance adjustment, and direct money mutations.

- [ ] **Step 1: Write risk-gate tests**

```python
@pytest.mark.parametrize("key", ["balance_recharge", "balance_adjustment"])
def test_money_capabilities_require_second_confirmation(key):
    spec = capability_catalog()[key]
    assert spec.risk.level in {"high", "critical"}
    assert spec.risk.second_confirmation is True


def test_money_tool_cannot_run_before_matching_risk_confirmation():
    session = _session_for_capability("balance_adjustment")
    with pytest.raises(HTTPException) as exc:
        confirm_agent_session(_db(), session.id, session.user_id, session.plan_version)
    assert exc.value.status_code == 409
```

- [ ] **Step 2: Run and verify failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py -v -k "money_capabilities or risk_confirmation"`

Expected: FAIL.

- [ ] **Step 3: Register money specs and add the risk-confirmation request**

```python
for key, name, runner in (
    ("balance_recharge", "客户余额充值", data_scripts.run_balance_recharge_script),
    ("balance_adjustment", "客户出入金调整", data_scripts.run_balance_adjustment_script),
):
    register_capability(DataScriptCapability(
        key=key, name=name, module="funds", projects=("日本站测试",),
        intents=(name,), examples=(f"客户300001{name}100元",),
        parameters=(
            ParameterSpec("customer_ids", "客户ID", "list[str]", required=True),
            ParameterSpec("amount", "金额", "decimal", required=True),
        ),
        risk=RiskSpec(level="critical", mutating=True, second_confirmation=True),
        runner=runner, result_validator=validate_script_result,
        account_role="backend_finance", idempotency_key="contract_hash", agent_enabled=True,
    ))

for key in ("balance_payment", "bank_payment", "porder_balance_payment", "porder_bank_payment"):
    spec = capability_catalog()[key]
    CAPABILITIES[key] = replace(spec, agent_enabled=True)
    SCRIPT_REGISTRY[key]["capability"] = CAPABILITIES[key]
```

```python
class DataAgentRiskConfirm(BaseModel):
    plan_version: int
    contract_hash: str = Field(min_length=16, max_length=64)
    acknowledged: bool
```

The first contract confirmation moves a high-risk session to `awaiting_risk_confirmation`. The second endpoint requires `acknowledged=True`, matching plan version, and matching contract hash before execution.

- [ ] **Step 4: Render an explicit Chinese risk summary**

```javascript
function riskConfirmationHtml(session) {
  const risk = session.goal?.risk || {};
  return `<form id="dataAgentRiskConfirmForm" class="panel">
    <div class="panel-title"><h3>高风险操作二次确认</h3></div>
    <div class="panel-body">
      <p>操作：${escapeHtml(risk.operation || "-")}</p>
      <p>客户范围：${escapeHtml(risk.customer_scope || "-")}</p>
      <p>金额与方向：${escapeHtml(risk.amount_direction || "-")}</p>
      <p>执行账号：${escapeHtml(risk.account_role || "-")}</p>
      <p class="danger-text">该操作会修改真实测试业务数据，请核对后确认。</p>
      <label><input type="checkbox" name="acknowledged" required /> 我已核对上述范围</label>
    </div><button class="btn danger" type="submit">确认执行</button>
  </form>`;
}
```

Do not use a generic browser confirm dialog.

- [ ] **Step 5: Run risk, route, and frontend syntax tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py tests/test_route_contracts.py tests/test_data_factory_agent.py -q`

Expected: PASS.

Run: `node --check static/data-factory-agent.js`

Expected: exit 0.

- [ ] **Step 6: Commit money risk gates**

```powershell
git add app/data_scripts/capabilities.py app/services/data_factory_agent.py app/agent_schemas.py app/routers/data_factory_agent.py static/data-factory-agent.js tests/test_data_script_capabilities.py tests/route_contract_expected.json
git commit -m "feat: gate high risk data agent capabilities"
```

---

### Task 7: Add OEM and Batch Capabilities Last

**Files:**
- Modify: `app/data_scripts/capabilities.py`
- Modify: `app/services/data_factory_agent_tools.py`
- Test: `tests/test_data_script_capabilities.py`

**Interfaces:**
- Produces: independently enabled OEM inquiry, sample, bulk, and payment capabilities with strict scope contracts.

- [ ] **Step 1: Write OEM completeness and batch-scope tests**

```python
@pytest.mark.parametrize("key", [
    "oem_new_inquiry", "oem_sample_order", "oem_sample_admin_flow",
    "oem_full_inquiry_flow", "oem_sample_full_flow", "oem_bulk_order", "oem_balance_pay",
])
def test_oem_capability_declares_scope_account_and_validator(key):
    spec = capability_catalog()[key]
    assert spec.module == "oem"
    assert spec.account_role
    assert spec.idempotency_key
    assert callable(spec.result_validator)
    assert spec.risk.second_confirmation is True
```

- [ ] **Step 2: Run and verify failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py -v -k "oem_capability"`

Expected: FAIL.

- [ ] **Step 3: Register OEM specs disabled by default**

```python
OEM_CONFIGS = (
    ("oem_new_inquiry", "OEM创建询价单", data_scripts.run_oem_new_inquiry_script, "inquiry_id"),
    ("oem_sample_order", "OEM提出样品单", data_scripts.run_oem_sample_order_script, "sample_order_id"),
    ("oem_sample_admin_flow", "OEM样品单后台流程", data_scripts.run_oem_sample_admin_flow_script, "sample_order_id"),
    ("oem_full_inquiry_flow", "OEM询价单全流程", data_scripts.run_oem_full_inquiry_flow_script, "inquiry_id"),
    ("oem_sample_full_flow", "OEM样品单全流程", data_scripts.run_oem_sample_full_flow_script, "sample_order_id"),
    ("oem_bulk_order", "OEM大货单下单", data_scripts.run_oem_bulk_order_script, "bulk_order_id"),
    ("oem_balance_pay", "OEM样品单余额支付", data_scripts.run_oem_sample_balance_pay_script, "sample_order_id"),
)
for key, name, runner, resume_key in OEM_CONFIGS:
    register_capability(DataScriptCapability(
        key=key, name=name, module="oem", projects=("oem-测试",),
        intents=(name,), examples=(f"执行{name}，数量1",),
        parameters=(
            ParameterSpec("customer_ids", "客户ID", "list[str]", required=True),
            ParameterSpec("operation_count", "操作数量", "int", required=True),
        ),
        risk=RiskSpec(level="high", mutating=True, second_confirmation=True),
        runner=runner, result_validator=validate_script_result,
        account_role="oem_frontend_and_backend", resume_key=resume_key,
        idempotency_key="contract_hash", agent_enabled=False,
    ))
```

Bulk order requires an explicit positive bounded `operation_count`; enforce the project limit before confirmation.

- [ ] **Step 4: Enable each OEM capability only after its existing script tests pass**

Use the existing OEM test files present in the working tree or their maintained replacements. If an OEM runner lacks a reliable result validator, leave that capability disabled and report the specific missing evidence.

- [ ] **Step 5: Run OEM, capability, and agent tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q -k "oem or capability or data_factory_agent"`

Expected: PASS.

- [ ] **Step 6: Commit enabled OEM capabilities**

```powershell
git add app/data_scripts/capabilities.py app/services/data_factory_agent_tools.py tests/test_data_script_capabilities.py
git commit -m "feat: add verified OEM agent capabilities"
```

---

### Task 8: Verify Metadata Coverage and Compatibility

**Files:**
- Modify: `tests/test_data_script_contract.py`
- Modify: `tests/test_data_script_capabilities.py`

**Interfaces:**
- Consumes: all registered scripts and capabilities.
- Produces: proof that every script has metadata and all legacy runners remain identical.

- [ ] **Step 1: Require metadata for every registry key**

```python
def test_every_registered_script_has_valid_capability_metadata():
    assert set(data_scripts.SCRIPT_REGISTRY) == set(capability_catalog())
    for key, item in data_scripts.SCRIPT_REGISTRY.items():
        spec = capability_catalog()[key]
        assert item["func"] is spec.runner
        spec.validate()
```

- [ ] **Step 2: Require disabled status when validation evidence is incomplete**

```python
def test_agent_enabled_capabilities_are_fully_executable():
    for spec in capability_catalog().values():
        if not spec.agent_enabled:
            continue
        assert callable(spec.result_validator)
        assert spec.examples
        assert spec.intents
        assert spec.projects
```

- [ ] **Step 3: Run all script and agent tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_contract.py tests/test_data_script_capabilities.py tests/test_data_factory_agent.py -q`

Expected: PASS.

- [ ] **Step 4: Run the complete project suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`

Expected: PASS.

- [ ] **Step 5: Inspect final repository scope**

Run: `git status --short` and `git diff --stat`

Expected: no database, logs, reports, generated evaluation output, or temporary files are included.

- [ ] **Step 6: Commit final metadata contract tests**

```powershell
git add tests/test_data_script_contract.py tests/test_data_script_capabilities.py
git commit -m "test: enforce data script capability contracts"
```
