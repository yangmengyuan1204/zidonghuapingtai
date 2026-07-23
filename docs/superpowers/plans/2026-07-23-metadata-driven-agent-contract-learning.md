# Metadata-Driven Agent Contract Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有订单、配送单、问题产品、支付和权限切换核心流程的前提下，让脚本元数据驱动首次执行合同、完整合同编辑和可度量的学习闭环。

**Architecture:** 保留现有核心专用编译器为最高优先级，在其后增加受 `DataScriptCapability` 约束的通用合同编译器；DeepSeek 只产出候选能力与字段，所有字段进入合同前必须经过元数据白名单、类型、来源和跨字段校验。最终确认合同作为标准答案，在确认时保存 `pending` 样本，执行校验成功后升级为 `verified`；学习中心展示样本、候选、规则和 7/30 天命中率。

**Tech Stack:** Python 3.11、FastAPI 0.115、Pydantic、SQLAlchemy 2.0、SQLite、原生 JavaScript、pytest。

## Global Constraints

- 所有测试必须使用 `.venv\Scripts\python.exe`，不得使用系统 Python。
- 修改前执行 `git status --short`；当前工作区存在用户未提交改动，逐文件核对并保留，禁止覆盖或回退。
- 执行前必须用 `using-git-worktrees` 技能从用户确认的基线创建隔离工作区；当前未提交的配送单发货等改动不属于本计划，未经用户确认不得混入功能提交，集成时逐文件解决重叠。
- 每个任务只暂存该任务明确列出的文件，禁止 `git add -A`，禁止提交 `*.db`、日志、报告、缓存和临时脚本。
- 不修改现有脚本 runner 的入参、返回值或执行顺序；元数据只决定识别、合同、编辑与学习，不绕过工具注册、结果校验、合同哈希或二次确认。
- 客户 ID 来源优先级固定为：自然语言明确值 → 顶部栏客户 ID → 当前项目环境绑定测试账号客户 ID，并在合同中标注推断来源。
- 支付策略固定为余额优先；接口明确返回余额不足时降级银行支付。
- 问题产品金额触发 500 限制时，先按当前项目选择“后台沈文妮账号”；仍受限时显示系统账号下拉框与临时账号密码输入，并在原界面续跑。
- 业务字段、客户 ID、订单号、配送单号和账号选择策略允许项目级学习；密码、Token、Cookie、授权头和加密凭据永不进入样本、规则或模型提示词。
- 核心订单、配送单和问题产品实际样本首次合同命中率发布门槛为 95%；其他启用元数据编译的脚本为 90%；任何分类不得低于上一发布基线，并必须同时报告样本量。
- 新前端功能放入独立 JS 文件，不向 `static/app.js` 堆积实现；默认只做代码和自动化回归，不启动浏览器。

## File Map

- Create `app/services/data_agent_contracts.py`: 合同字段解析、规范化、差异、结构化更新与编辑器 schema。
- Create `app/services/data_agent_contract_compiler.py`: 能力匹配和受元数据约束的通用合同编译。
- Create `static/data-agent-contract-editor.js`: 方案 A 分组合同编辑器、草稿、字段错误和自然语言纠正交互。
- Create `static/data-agent-learning-center.js`: 样本、候选、规则和命中率四视图。
- Create `tests/test_data_agent_contracts.py`: 合同元数据与合同服务单元测试。
- Create `tests/test_data_agent_learning_metrics.py`: 样本状态与命中率统计测试。
- Modify `app/data_scripts/capabilities.py`: 扩展合同字段和学习元数据，保持旧能力注册兼容。
- Modify `app/services/data_factory_agent_prompts.py`: 要求模型仅返回候选能力键和元数据允许字段。
- Modify `app/services/data_factory_agent.py`: 接入专用/通用编译优先级、通用编辑 schema、合同反馈和学习状态升级。
- Modify `app/services/data_agent_learning.py`: pending/verified/invalid 样本、去重、候选刷新和命中率统计。
- Modify `app/agent_schemas.py`: 通用字段更新与合同反馈请求结构。
- Modify `app/routers/data_factory_agent.py`: 合同反馈和学习样本接口。
- Modify `static/data-factory-agent.js`: 仅保留会话编排，委托新编辑器和学习中心模块。
- Modify `static/index.html`: 挂载两个独立 JS 模块。
- Modify `tests/test_data_script_capabilities.py`, `tests/test_data_factory_agent_contract.py`, `tests/test_data_factory_agent.py`, `tests/test_data_agent_learning.py`, `tests/test_data_agent_hit_rate.py`, `tests/test_route_contracts.py`: 分阶段回归。

---

### Task 1: Contract and learning metadata primitives

**Files:**
- Modify: `app/data_scripts/capabilities.py:22-92`
- Modify: `tests/test_data_script_capabilities.py`

**Interfaces:**
- Produces: `ContractFieldSpec.validate() -> ContractFieldSpec`
- Produces: `DataScriptCapability.contract_fields: tuple[ContractFieldSpec, ...]`
- Produces: `effective_contract_fields(capability: DataScriptCapability) -> tuple[ContractFieldSpec, ...]`
- Compatibility: capabilities that only declare `parameters` continue to validate and receive synthesized editable fields.

- [ ] **Step 1: Write failing metadata compatibility tests**

```python
from app.data_scripts.capabilities import (
    ContractFieldSpec,
    DataScriptCapability,
    ParameterSpec,
    RiskSpec,
    effective_contract_fields,
)


def test_contract_field_rejects_secret_learning():
    field = ContractFieldSpec(
        name="backend_password",
        label="后台密码",
        path="variables.backend_password",
        group="execution",
        value_type="str",
        learnable=True,
    )
    with pytest.raises(ValueError, match="sensitive"):
        field.validate()


def test_legacy_parameters_are_synthesized_as_contract_fields():
    capability = DataScriptCapability(
        key="demo",
        name="演示",
        module="order",
        projects=("日本站测试",),
        intents=("演示",),
        examples=("执行演示",),
        parameters=(ParameterSpec("order_sn", "订单号", "str", required=True),),
        risk=RiskSpec(level="low", mutating=False, second_confirmation=False),
        runner=lambda **_: {},
        result_validator=None,
    ).validate()
    field = effective_contract_fields(capability)[0]
    assert (field.name, field.path, field.editor) == (
        "order_sn", "variables.order_sn", "text"
    )
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py -v -k "contract_field or synthesized"`

Expected: FAIL because `ContractFieldSpec` and `effective_contract_fields` do not exist.

- [ ] **Step 3: Add validated, backward-compatible metadata types**

```python
ALLOWED_EDITORS = {"text", "number", "decimal", "select", "checkbox", "id_list", "readonly"}
ALLOWED_LEARNING_MODES = {"none", "value", "pattern", "strategy"}
ALLOWED_LEARNING_SCOPES = {"project", "global"}
SENSITIVE_FIELD_PARTS = {"password", "token", "cookie", "authorization", "secret", "ciphertext"}


@dataclass(frozen=True)
class ContractFieldSpec:
    name: str
    label: str
    path: str
    group: str
    value_type: str
    required: bool = False
    default: Any = None
    sources: tuple[str, ...] = (
        "natural_language", "page_context", "environment", "default"
    )
    aliases: tuple[str, ...] = ()
    editor: str = "text"
    choices: tuple[tuple[str, str], ...] = ()
    readonly: bool = False
    execution_field: bool = True
    learnable: bool = True
    learning_mode: str = "value"
    learning_scope: str = "project"

    def validate(self) -> "ContractFieldSpec":
        if not all(str(item).strip() for item in (self.name, self.label, self.path, self.group, self.value_type)):
            raise ValueError("contract field identity is required")
        if self.editor not in ALLOWED_EDITORS:
            raise ValueError("contract field editor is invalid")
        if not self.sources or set(self.sources) - ALLOWED_PARAMETER_SOURCES:
            raise ValueError("contract field contains invalid sources")
        if self.learning_mode not in ALLOWED_LEARNING_MODES:
            raise ValueError("contract field learning mode is invalid")
        if self.learning_scope not in ALLOWED_LEARNING_SCOPES:
            raise ValueError("contract field learning scope is invalid")
        normalized = self.name.casefold().replace("-", "_")
        if self.learnable and any(part in normalized for part in SENSITIVE_FIELD_PARTS):
            raise ValueError("sensitive contract field cannot be learnable")
        if self.readonly and self.editor != "readonly":
            raise ValueError("readonly contract field must use readonly editor")
        return self
```

Add `contract_fields: tuple[ContractFieldSpec, ...] = ()` after the existing defaulted fields on `DataScriptCapability`, validate unique names/paths, and implement synthesis:

```python
def effective_contract_fields(
    capability: DataScriptCapability,
) -> tuple[ContractFieldSpec, ...]:
    if capability.contract_fields:
        return tuple(field.validate() for field in capability.contract_fields)
    return tuple(
        ContractFieldSpec(
            name=item.name,
            label=item.label,
            path=f"variables.{item.name}",
            group="task_scope" if item.name.endswith("_sn") else "business",
            value_type=item.value_type,
            required=item.required,
            default=item.default,
            sources=item.sources,
            editor="number" if item.value_type == "int" else (
                "decimal" if item.value_type == "decimal" else "text"
            ),
            learning_mode="pattern" if item.name.endswith("_sn") else "value",
        ).validate()
        for item in capability.parameters
    )
```

- [ ] **Step 4: Run capability tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_script_capabilities.py -v`

Expected: PASS, including all existing capability registrations.

- [ ] **Step 5: Commit only Task 1 files**

```powershell
git status --short
git diff --stat -- app/data_scripts/capabilities.py tests/test_data_script_capabilities.py
git add app/data_scripts/capabilities.py tests/test_data_script_capabilities.py
git commit -m "feat: add contract field metadata"
```

### Task 2: Contract normalization, diff, editor schema, and generic updates

**Files:**
- Create: `app/services/data_agent_contracts.py`
- Create: `tests/test_data_agent_contracts.py`

**Interfaces:**
- Consumes: `effective_contract_fields(DataScriptCapability)` from Task 1.
- Produces: `build_contract_editor_schema(capability, goal) -> list[dict[str, Any]]`
- Produces: `normalize_execution_contract(goal, capability) -> dict[str, Any]`
- Produces: `diff_execution_contract(initial, final, capability, source) -> list[dict[str, Any]]`
- Produces: `apply_contract_updates(goal, updates, capability) -> tuple[dict, list[dict]]`
- Error contract: raises `ContractValidationError(errors: dict[str, str])`; caller maps this to HTTP 400 without discarding the browser draft.

- [ ] **Step 1: Write failing normalization and update tests**

```python
from app.data_scripts.capabilities import capability_catalog
from app.services.data_agent_contracts import (
    ContractValidationError,
    apply_contract_updates,
    build_contract_editor_schema,
    diff_execution_contract,
    normalize_execution_contract,
)

FULL_FLOW = capability_catalog()["full_flow"]


def test_display_only_change_does_not_reduce_first_hit():
    initial = {"target_node": "order_offered", "target_label": "订单待付款", "variables": {"order_item_num": 1}}
    final = {"target_node": "order_offered", "target_label": "待付款", "variables": {"order_item_num": 1}}
    assert normalize_execution_contract(initial, FULL_FLOW) == normalize_execution_contract(final, FULL_FLOW)
    assert diff_execution_contract(initial, final, FULL_FLOW, "direct_edit") == []


def test_apply_updates_rejects_unknown_field():
    with pytest.raises(ContractValidationError) as exc_info:
        apply_contract_updates(
            {"variables": {}}, {"backend_password": "secret"}, FULL_FLOW
        )
    assert exc_info.value.errors == {"backend_password": "字段不属于当前脚本合同"}


def test_editor_schema_marks_inferred_customer_source():
    goal = {
        "customer_ids": ["300001"],
        "field_sources": {"customer_ids": "environment"},
        "inferred_fields": ["customer_ids"],
        "variables": {},
    }
    customer = next(
        item for item in build_contract_editor_schema(FULL_FLOW, goal)
        if item["name"] == "customer_ids"
    )
    assert customer["inferred"] is True
    assert customer["source"] == "environment"
```

- [ ] **Step 2: Run the new test module and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_contracts.py -v`

Expected: FAIL because `app.services.data_agent_contracts` does not exist.

- [ ] **Step 3: Implement the focused contract service**

Implement these exact public objects; keep path access and conversion private:

```python
class ContractValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("合同字段校验失败")
        self.errors = dict(errors)


def build_contract_editor_schema(
    capability: DataScriptCapability, goal: dict[str, Any]
) -> list[dict[str, Any]]:
    inferred = set(goal.get("inferred_fields") or [])
    sources = goal.get("field_sources") if isinstance(goal.get("field_sources"), dict) else {}
    return [
        {
            "name": field.name,
            "label": field.label,
            "group": field.group,
            "value_type": field.value_type,
            "editor": field.editor,
            "choices": [{"value": value, "label": label} for value, label in field.choices],
            "required": field.required,
            "readonly": field.readonly,
            "learnable": field.learnable,
            "value": copy.deepcopy(_get_path(goal, field.path, field.default)),
            "source": str(sources.get(field.name) or ""),
            "inferred": field.name in inferred,
        }
        for field in effective_contract_fields(capability)
    ]


def normalize_execution_contract(
    goal: dict[str, Any], capability: DataScriptCapability
) -> dict[str, Any]:
    return {
        field.name: _normalize_value(field, _get_path(goal, field.path, field.default))
        for field in effective_contract_fields(capability)
        if field.execution_field
    }


def diff_execution_contract(
    initial: dict[str, Any],
    final: dict[str, Any],
    capability: DataScriptCapability,
    source: str,
) -> list[dict[str, Any]]:
    before = normalize_execution_contract(initial, capability)
    after = normalize_execution_contract(final, capability)
    return [
        {"field": name, "before": before.get(name), "after": after.get(name), "source": source}
        for name in sorted(set(before) | set(after))
        if before.get(name) != after.get(name)
    ]
```

`apply_contract_updates` must reject unknown/readonly fields, coerce `int`/`decimal`/`list[str]`/`bool`, validate choices, write only declared paths, recompute dependent price totals through a callback-free deterministic helper, refresh `summary` and `contract_hash`, and return only execution-field diffs.

- [ ] **Step 4: Run contract service tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_contracts.py -v`

Expected: PASS.

- [ ] **Step 5: Commit only the new service and tests**

```powershell
git add app/services/data_agent_contracts.py tests/test_data_agent_contracts.py
git commit -m "feat: add metadata driven contract service"
```

### Task 3: Core capability field declarations and session editor contract

**Files:**
- Modify: `app/data_scripts/capabilities.py:180-299`
- Modify: `app/services/data_factory_agent.py:287-419,3244-3376`
- Modify: `app/agent_schemas.py:35-42`
- Modify: `app/routers/data_factory_agent.py:133-142`
- Modify: `tests/test_data_factory_agent_contract.py`
- Modify: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: Task 2 contract service.
- Produces in session payload: `capability_key: str`, `contract_editor: {groups: list[dict], fields: list[dict]}`.
- Produces: `resolve_goal_capability(goal: dict[str, Any]) -> str`, mapping existing core goals deterministically before the generic compiler is introduced.
- Changes `PATCH /api/data-scripts/agent/sessions/{session_id}/goal` request to `{plan_version: int, fields: dict[str, Any]}` while accepting the six legacy top-level fields for compatibility.
- Produces preview endpoints: `POST /sessions/{id}/contract-preview` with `{plan_version, message}` and `POST /sessions/{id}/contract-preview/apply` with `{plan_version, preview_hash}`. Preview never mutates the active goal; apply mutates only if the base version still matches.
- Version rule: stale `plan_version` returns HTTP 409; valid change increments exactly once.

- [ ] **Step 1: Write failing API tests**

Append this API block to `tests/test_data_factory_agent.py`, which already provides `_agent_context`, `_login`, `_ready_goal`, `TestClient`, `app`, and runtime reset:

```python
class AuthorizedAgentClient:
    def __init__(self, client, headers, project_id, env_id):
        self.client = client
        self.headers = headers
        self.project_id = project_id
        self.env_id = env_id

    def get(self, path):
        return self.client.get(path, headers=self.headers)

    def post(self, path, json):
        return self.client.post(path, headers=self.headers, json=json)

    def patch(self, path, json):
        return self.client.patch(path, headers=self.headers, json=json)


@pytest.fixture
def agent_client(monkeypatch):
    project, env = _agent_context()
    monkeypatch.setattr(
        agent_service, "call_local_model_json", lambda *args, **kwargs: _ready_goal()
    )
    with TestClient(app) as client:
        yield AuthorizedAgentClient(client, _login(client), project.id, env.id)


def create_ready_session(agent_client, instruction):
    response = agent_client.post(
        "/api/data-scripts/agent/sessions",
        json={
            "project_id": agent_client.project_id,
            "env_id": agent_client.env_id,
            "instruction": instruction,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_session_exposes_grouped_contract_editor(agent_client):
    created = create_ready_session(agent_client, "订单待付款")
    names = {item["name"] for item in created["contract_editor"]["fields"]}
    assert {"customer_ids", "order_shop_count", "order_per_shop", "order_item_num", "target_node"} <= names
    assert created["capability_key"] == "full_flow"


def test_goal_patch_updates_declared_fields_and_checks_version(agent_client):
    created = create_ready_session(agent_client, "订单待付款")
    response = agent_client.patch(
        f"/api/data-scripts/agent/sessions/{created['id']}/goal",
        json={
            "plan_version": created["plan_version"],
            "fields": {"customer_ids": ["300003"], "order_item_num": 2},
        },
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["goal"]["customer_ids"] == ["300003"]
    assert updated["goal"]["variables"]["order_item_num"] == 2
    assert updated["plan_version"] == created["plan_version"] + 1


def test_goal_patch_returns_field_errors_without_mutating_session(agent_client):
    created = create_ready_session(agent_client, "订单待付款")
    response = agent_client.patch(
        f"/api/data-scripts/agent/sessions/{created['id']}/goal",
        json={"plan_version": created["plan_version"], "fields": {"order_item_num": 0}},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["fields"]["order_item_num"]
    current = agent_client.get(f"/api/data-scripts/agent/sessions/{created['id']}").json()
    assert current["plan_version"] == created["plan_version"]


def test_natural_language_correction_is_previewed_before_apply(agent_client):
    created = create_ready_session(agent_client, "订单待付款")
    preview = agent_client.post(
        f"/api/data-scripts/agent/sessions/{created['id']}/contract-preview",
        json={"plan_version": created["plan_version"], "message": "客户改成300003"},
    ).json()
    assert preview["diff"] == [{
        "field": "customer_ids",
        "before": created["goal"]["customer_ids"],
        "after": ["300003"],
        "source": "natural_language_correction",
    }]
    unchanged = agent_client.get(f"/api/data-scripts/agent/sessions/{created['id']}").json()
    assert unchanged["goal"] == created["goal"]
    applied = agent_client.post(
        f"/api/data-scripts/agent/sessions/{created['id']}/contract-preview/apply",
        json={"plan_version": created["plan_version"], "preview_hash": preview["preview_hash"]},
    ).json()
    assert applied["goal"]["customer_ids"] == ["300003"]
    assert applied["plan_version"] == created["plan_version"] + 1
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent_contract.py tests/test_data_factory_agent.py -v -k "contract_editor or goal_patch"`

Expected: FAIL because the session has no editor schema and the patch request is still a fixed six-field model.

- [ ] **Step 3: Declare core fields and wire generic updates**

Add explicit `contract_fields` to `full_flow`, `resume_order_flow`, `resume_porder_flow`, and `problem_goods`. Use these paths and policies:

```python
CORE_FIELDS = (
    ContractFieldSpec("customer_ids", "客户ID", "customer_ids", "task_scope", "list[str]", aliases=("客户", "客户id"), editor="id_list", learning_mode="pattern"),
    ContractFieldSpec("order_sn", "订单号", "order_sn", "task_scope", "str", aliases=("订单", "订单编号"), editor="text", learning_mode="pattern"),
    ContractFieldSpec("porder_sn", "配送单号", "porder_sn", "task_scope", "str", aliases=("配送单", "配送单编号"), editor="text", learning_mode="pattern"),
    ContractFieldSpec("target_node", "目标状态", "target_node", "task_scope", "node", aliases=("做到", "执行到"), editor="select", choices=tuple(FULL_FLOW_NODE_CHOICES), learning_mode="value"),
    ContractFieldSpec("order_shop_count", "店铺数", "variables.order_shop_count", "goods_price", "int", default=1, aliases=("店铺", "店"), editor="number"),
    ContractFieldSpec("order_per_shop", "每店商品种类", "variables.order_per_shop", "goods_price", "int", default=1, aliases=("每店商品", "商品种类"), editor="number"),
    ContractFieldSpec("order_item_num", "每种购买数量", "variables.order_item_num", "goods_price", "int", default=1, aliases=("购买数量", "每种数量"), editor="number"),
    ContractFieldSpec("offer_price", "统一单价", "variables.offer_price", "goods_price", "decimal", default="10", aliases=("单价", "价格"), editor="decimal"),
)
```

Capability-specific fields append payment strategy, problem scope/refund amount/freight/add-on service, or resume identifiers. Add read-only execution information fields for inferred items, operation order, plan version and contract hash with `execution_field=False`, `learnable=False`.

Replace the fixed update loop with:

```python
updated_goal, corrections = apply_contract_updates(
    session.goal, updates, capability_catalog()[session.capability_key]
)
session.goal = updated_goal
session.plan_version += 1
session.events.append(
    _event("goal_updated", "用户直接编辑了目标数据", corrections=corrections)
)
```

Add `capability_key: str = ""` and `pending_contract_preview: dict[str, Any] = field(default_factory=dict)` to `AgentSessionState`; serialize the grouped schema from `build_contract_editor_schema`. Map `ContractValidationError` to `HTTPException(400, detail={"message": "合同字段校验失败", "fields": exc.errors})`.

```python
def resolve_goal_capability(goal: dict[str, Any]) -> str:
    explicit = str(goal.get("capability_key") or "")
    if explicit in capability_catalog():
        return explicit
    operations = [item for item in goal.get("operations") or [] if isinstance(item, dict)]
    types = {str(item.get("type") or "") for item in operations}
    if types == {"problem_goods"}:
        return "problem_goods"
    if "advance_porder" in types or goal.get("mode") == "resume_porder":
        return "resume_porder_flow"
    if goal.get("mode") == "resume_order":
        return "resume_order_flow"
    return "full_flow"
```

Set this key whenever analysis produces an awaiting-confirmation goal and persist it on the session before `_serialize_session` builds the editor.

Implement correction preview by running the existing turn analyzer against a copied message list and current goal baseline, then storing only `{base_plan_version, goal, diff, preview_hash}` in memory. Applying verifies `preview_hash`, compares `base_plan_version` to the active `plan_version`, replaces the goal, appends a `goal_updated` event with source `natural_language_correction`, clears the preview, and increments the version once. Any direct edit or new clarification invalidates the pending preview.

- [ ] **Step 4: Run focused backend tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_contracts.py tests/test_data_factory_agent_contract.py tests/test_data_factory_agent.py -v -k "contract or goal_patch or customer_id_priority or balance or permission"`

Expected: PASS.

- [ ] **Step 5: Commit exact files after reconciling pre-existing edits**

```powershell
git diff --stat -- app/data_scripts/capabilities.py app/services/data_factory_agent.py app/agent_schemas.py app/routers/data_factory_agent.py tests/test_data_factory_agent_contract.py tests/test_data_factory_agent.py
git add app/data_scripts/capabilities.py app/services/data_factory_agent.py app/agent_schemas.py app/routers/data_factory_agent.py tests/test_data_factory_agent_contract.py tests/test_data_factory_agent.py
git commit -m "feat: expose editable execution contracts"
```

### Task 4: Pending learning sample and terminal verification upgrade

**Files:**
- Modify: `app/agent_schemas.py`
- Modify: `app/routers/data_factory_agent.py`
- Modify: `app/services/data_factory_agent.py`
- Modify: `app/services/data_agent_learning.py:1072-1142`
- Modify: `tests/test_data_agent_learning.py`

**Interfaces:**
- Produces schema: `DataAgentContractFeedback(plan_version: int, verdict: Literal["correct", "invalid"])`.
- Produces endpoint: `POST /api/data-scripts/agent/sessions/{session_id}/contract-feedback`.
- Produces: `record_contract_feedback(db, session, verdict) -> DataAgentLearningSample`.
- Existing `confirm_agent_session` also records `pending` before dispatch, so “合同正确” is optional and “确认并执行” never skips learning ingestion.
- Changes: `capture_learning_sample` upserts the session sample; successful verified execution upgrades `pending -> verified`, failed execution leaves `pending`, explicit invalidation sets `invalid`.

- [ ] **Step 1: Write failing learning lifecycle tests**

```python
def test_contract_correct_creates_pending_sample(learning_db):
    session = _agent_session(status="awaiting_confirmation")
    sample = learning_service.record_contract_feedback(learning_db, session, "correct")
    assert sample.outcome == "pending"
    assert sample.verified == 0
    assert json.loads(sample.final_contract_json)["target_node"] == "order_offered"


def test_confirm_records_pending_before_execution(monkeypatch, learning_db):
    session = _agent_session(status="awaiting_confirmation")
    calls = []
    monkeypatch.setattr(
        learning_service,
        "record_contract_feedback",
        lambda db, current, verdict: calls.append((current.id, verdict)),
    )
    agent_service._record_pending_contract_feedback(learning_db, session)
    assert calls == [(session.id, "correct")]


def test_successful_execution_upgrades_pending_sample(learning_db):
    session = _agent_session()
    pending = learning_service.record_contract_feedback(learning_db, session, "correct")
    upgraded = learning_service.capture_learning_sample(
        learning_db, session, "succeeded", _verified_result()
    )
    assert upgraded.id == pending.id
    assert upgraded.outcome == "verified"
    assert upgraded.verified == 1


def test_execution_failure_does_not_turn_recognition_into_failure(learning_db):
    session = _agent_session()
    pending = learning_service.record_contract_feedback(learning_db, session, "correct")
    same = learning_service.capture_learning_sample(learning_db, session, "failed", {})
    assert same.id == pending.id
    assert same.outcome == "pending"


def test_invalid_feedback_marks_sample_invalid(learning_db):
    sample = learning_service.record_contract_feedback(
        learning_db, _agent_session(status="awaiting_confirmation"), "invalid"
    )
    assert sample.outcome == "invalid"
    assert sample.verified == 0


def test_order_identifier_candidate_learns_pattern_not_task_value(learning_db):
    session = _agent_session(
        instruction="把订单2026071715475684-300001继续到待付款",
        goal={
            "capability_key": "resume_order_flow",
            "order_sn": "2026071715475684-300001",
            "target_node": "order_offered",
            "variables": {},
            "operations": [{"id": "operation_1", "type": "advance_order"}],
        },
    )
    sample = learning_service.capture_learning_sample(
        learning_db, session, "succeeded", _verified_result()
    )
    proposal = learning_service.correction_rule_proposal(
        sample, {"field": "order_sn", "before": "", "after": session.goal["order_sn"]}
    )
    assert proposal["learning_mode"] == "pattern"
    assert "2026071715475684-300001" not in json.dumps(proposal, ensure_ascii=False)


def test_account_strategy_is_learnable_but_credentials_are_rejected():
    safe = learning_service.validate_candidate_rule({
        "signature": "permission_account_strategy:abc1234567890def",
        "field": "permission_account_strategy",
        "learning_mode": "strategy",
        "match_phrases": ["问题产品超过500"],
        "set_strategy": {"profile_name": "后台沈文妮账号"},
        "source_count": 3,
    })
    assert safe["set_strategy"]["profile_name"] == "后台沈文妮账号"
    with pytest.raises(ValueError, match="禁止字段"):
        learning_service.validate_candidate_rule({
            **safe,
            "set_strategy": {"backend_password": "secret"},
        })
```

- [ ] **Step 2: Run lifecycle tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py -v -k "pending or upgrades or invalid_feedback"`

Expected: FAIL because feedback recording and pending state do not exist.

- [ ] **Step 3: Implement idempotent feedback and upgrade**

Use the existing table; do not add or migrate database columns. Identify the current sample by `(project_id, session_id)` before fingerprint fallback. Store statuses in `outcome` as `pending`, `verified`, or `invalid`; retain read compatibility for historical `success`/`failure` rows.

```python
def record_contract_feedback(
    db: Session, session: Any, verdict: str
) -> DataAgentLearningSample:
    if verdict not in {"correct", "invalid"}:
        raise LearningInputError("合同反馈无效")
    sample = _upsert_session_sample(db, session)
    sample.outcome = "pending" if verdict == "correct" else "invalid"
    sample.verified = 0
    db.commit()
    db.refresh(sample)
    return sample


def capture_learning_sample(db, session, final_status, result):
    if session is None or final_status not in TERMINAL_STATUSES:
        return None
    sample = _upsert_session_sample(db, session)
    if sample.outcome == "invalid":
        return sample
    verified = bool(
        final_status == "succeeded"
        and _confirmed(session)
        and _operations_verified(session, result if isinstance(result, dict) else {})
    )
    if verified:
        sample.outcome = "verified"
        sample.verified = 1
        db.commit()
        db.refresh(sample)
        if _load_json_list(sample.corrections_json):
            _refresh_candidates_with_retry(db, sample)
    return sample
```

Candidate generation must resolve the field through the sample's `capability_key`/`intent_key` metadata. `learnable=False` produces no candidate; `learning_mode="value"` produces the existing `set_fields`; `learning_mode="pattern"` stores only a normalized identifier shape and extraction aliases, never the task's exact order or delivery number; `learning_mode="strategy"` produces `set_strategy`. Candidate validation uses an explicit credential denylist, permits declared `customer_ids`, identifier patterns and `permission_account_strategy` only at project scope, and still requires three verified samples before `collecting -> candidate`.

```python
def correction_rule_proposal(sample, correction):
    capability = capability_catalog().get(str(sample.intent_key))
    field = next(
        (item for item in effective_contract_fields(capability) if item.name == correction["field"]),
        None,
    ) if capability else None
    if field is None or not field.learnable:
        raise ValueError("字段未声明为可学习")
    base = {
        "field": field.name,
        "learning_mode": field.learning_mode,
        "learning_scope": "project",
        "match_phrases": _instruction_phrases(sample.instruction_text, field.aliases),
        "source_count": 1,
    }
    if field.learning_mode == "pattern":
        base["extract_pattern"] = identifier_shape(correction.get("after"), field.name)
    elif field.learning_mode == "strategy":
        base["set_strategy"] = sanitize_learning_value(correction.get("after"))
    else:
        base["set_fields"] = {field.name: sanitize_learning_value(correction.get("after"))}
    base["signature"] = candidate_signature(base)
    return base
```

The feedback endpoint checks ownership, editable status and `plan_version`, records the sample, appends a non-sensitive event, and does not execute the task. `confirm_agent_session` invokes `_record_pending_contract_feedback(db, session)` before submitting `_run_agent_session`; a learning write error appends `learning_error` and logs the exception type but must not change the execution status.

- [ ] **Step 4: Run learning and confirmation regression tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py tests/test_data_factory_agent.py -v -k "learning or contract_feedback or confirm"`

Expected: PASS.

- [ ] **Step 5: Commit exact files**

```powershell
git add app/agent_schemas.py app/routers/data_factory_agent.py app/services/data_factory_agent.py app/services/data_agent_learning.py tests/test_data_agent_learning.py
git commit -m "feat: capture confirmed contract samples"
```

### Task 5: Metadata compiler with protected core priority

**Files:**
- Create: `app/services/data_agent_contract_compiler.py`
- Modify: `app/services/data_factory_agent_prompts.py:75-130`
- Modify: `app/services/data_factory_agent.py:2103-2188`
- Modify: `tests/test_data_factory_agent_contract.py`
- Modify: `tests/test_data_agent_hit_rate.py`

**Interfaces:**
- Produces: `select_capability(candidate_key, instruction, capabilities) -> DataScriptCapability | None`.
- Produces: `compile_metadata_contract(capability, candidate_fields, compile_context) -> tuple[dict, list[str]]`.
- Priority: rollback/core deterministic compiler → core existing `_normalize_goal` → metadata compiler for non-core capability → minimal clarification.
- Model candidate keys outside metadata are discarded and recorded in analysis trace as `rejected_fields`.

- [ ] **Step 1: Write failing compiler boundary tests**

```python
def test_metadata_compiler_rejects_undeclared_model_fields():
    order_quote = capability_catalog()["order_quote"]
    goal, rejected = compile_metadata_contract(
        order_quote,
        {"order_sn": "20260701-1", "backend_password": "secret"},
        {"project_id": 1},
    )
    assert "backend_password" in rejected
    assert "backend_password" not in json.dumps(goal, ensure_ascii=False)


def test_core_full_flow_still_uses_specialized_compiler(monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "compile_metadata_contract",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    monkeypatch.setattr(
        agent_service, "call_local_model_json", lambda *args, **kwargs: _ready_goal()
    )
    project, env = _agent_context()
    with TestClient(app) as client:
        headers = _login(client)
        created = client.post(
            "/api/data-scripts/agent/sessions",
            headers=headers,
            json={"project_id": project.id, "env_id": env.id, "instruction": "订单待付款"},
        ).json()
    assert created["status"] == "awaiting_confirmation"
    assert created["goal"]["target_node"] == "order_offered"


def test_non_core_capability_compiles_from_declared_metadata(monkeypatch):
    candidate = {
        "status": "ready",
        "capability_key": "order_quote",
        "fields": {"order_sn": "20260701-1"},
        "evidence": {"order_sn": "订单20260701-1"},
        "question": "",
    }
    monkeypatch.setattr(
        agent_service, "call_local_model_json", lambda *args, **kwargs: candidate
    )
    project, env = _agent_context()
    with TestClient(app) as client:
        headers = _login(client)
        created = client.post(
            "/api/data-scripts/agent/sessions",
            headers=headers,
            json={"project_id": project.id, "env_id": env.id, "instruction": "给订单20260701-1报价"},
        ).json()
    assert created["status"] == "awaiting_confirmation"
    assert created["goal"]["capability_key"] == "order_quote"
    assert created["goal"]["variables"]["order_sn"] == "20260701-1"
```

- [ ] **Step 2: Run compiler tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent_contract.py tests/test_data_agent_hit_rate.py -v -k "metadata_compiler or specialized_compiler or non_core"`

Expected: FAIL because the generic compiler and capability-key response contract do not exist.

- [ ] **Step 3: Implement selection and compilation boundaries**

```python
CORE_SPECIALIZED_CAPABILITIES = {
    "full_flow", "resume_order_flow", "resume_porder_flow", "problem_goods"
}


def select_capability(
    candidate_key: str,
    instruction: str,
    capabilities: Sequence[DataScriptCapability],
) -> DataScriptCapability | None:
    by_key = {item.key: item for item in capabilities if item.agent_enabled}
    if candidate_key in by_key:
        return by_key[candidate_key]
    normalized = normalize_match_text(instruction)
    matches = [
        item for item in by_key.values()
        if any(normalize_match_text(term) in normalized for term in (*item.intents, *item.examples))
    ]
    return matches[0] if len(matches) == 1 else None


def compile_metadata_contract(
    capability: DataScriptCapability,
    candidate_fields: dict[str, Any],
    compile_context: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    declared = {field.name for field in effective_contract_fields(capability)}
    rejected = sorted(set(candidate_fields) - declared)
    seed = new_contract_seed(capability, compile_context)
    goal, _ = apply_contract_updates(
        seed,
        {key: value for key, value in candidate_fields.items() if key in declared},
        capability,
    )
    goal["capability_key"] = capability.key
    goal["risk"] = capability_risk_payload(capability)
    return goal, rejected
```

Update the analysis prompt JSON response contract to include only:

```json
{
  "status": "ready|clarifying",
  "capability_key": "metadata capability key",
  "fields": {"declared_field_name": "candidate value"},
  "evidence": {"declared_field_name": "source phrase"},
  "question": "only when required data cannot be defaulted"
}
```

For core keys, continue invoking existing `_normalize_goal`; for other uniquely selected enabled keys, invoke `compile_metadata_contract`. Store `capability_key`, `rejected_fields`, model candidate and field evidence in the analysis trace.

- [ ] **Step 4: Run compiler and hit-rate regression tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent_contract.py tests/test_data_agent_hit_rate.py tests/test_data_factory_agent.py -v -k "compiler or recognition or hit_rate or customer_id_priority or payment or permission"`

Expected: PASS.

- [ ] **Step 5: Commit exact files**

```powershell
git add app/services/data_agent_contract_compiler.py app/services/data_factory_agent_prompts.py app/services/data_factory_agent.py tests/test_data_factory_agent_contract.py tests/test_data_agent_hit_rate.py
git commit -m "feat: compile contracts from capability metadata"
```

### Task 6: Grouped contract editor and natural-language correction

**Files:**
- Create: `static/data-agent-contract-editor.js`
- Modify: `static/data-factory-agent.js:140-190,380-460`
- Modify: `static/index.html:16`
- Modify: `tests/test_route_contracts.py`

**Interfaces:**
- Produces browser global: `window.DataAgentContractEditor.render(session, options) -> string`.
- Produces: `window.DataAgentContractEditor.bind(container, session, options) -> void`.
- `options` contains `escapeHtml`, `save(fields, planVersion)`, `previewCorrection(message, planVersion)`, `applyPreview(previewHash, planVersion)`, `markCorrect(planVersion)`, and `confirm(planVersion)`.
- Draft rule: validation error preserves all input values and maps `detail.fields` beside matching `data-contract-field` controls.

- [ ] **Step 1: Add failing frontend contract smoke tests**

```python
def test_contract_editor_module_is_loaded_before_agent_module():
    html = Path("static/index.html").read_text(encoding="utf-8")
    editor = html.index("/static/data-agent-contract-editor.js")
    agent = html.index("/static/data-factory-agent.js")
    assert editor < agent


def test_contract_editor_has_required_actions_and_no_fixed_field_whitelist():
    source = Path("static/data-agent-contract-editor.js").read_text(encoding="utf-8")
    for text in ("重新生成合同", "合同正确", "保存修改", "确认并执行", "恢复推断值"):
        assert text in source
    assert "session.contract_editor.fields" in source
    assert "order_shop_count,order_per_shop" not in source
```

- [ ] **Step 2: Run smoke tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_route_contracts.py -v -k "contract_editor"`

Expected: FAIL because the new module is not present.

- [ ] **Step 3: Implement the independent grouped editor**

Use metadata groups `task_scope`, `goods_price`, `payment`, `problem_goods`, and `execution`. Render controls exclusively from field schema:

```javascript
(function () {
  const drafts = new Map();

  function renderField(field, escapeHtml) {
    const value = drafts.has(field.name) ? drafts.get(field.name) : field.value;
    const inferred = field.inferred ? '<span class="tag warning">推断项</span>' : "";
    const source = field.source ? `<small>来源：${escapeHtml(field.source)}</small>` : "";
    const attrs = `data-contract-field="${escapeHtml(field.name)}" ${field.readonly ? "disabled" : ""}`;
    if (field.editor === "select") {
      return `<label>${escapeHtml(field.label)}${inferred}<select ${attrs}>${field.choices.map((item) => `<option value="${escapeHtml(item.value)}" ${String(item.value) === String(value) ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}</select>${source}<span data-field-error="${escapeHtml(field.name)}"></span></label>`;
    }
    const type = field.editor === "number" || field.editor === "decimal" ? "number" : "text";
    return `<label>${escapeHtml(field.label)}${inferred}<input type="${type}" ${attrs} value="${escapeHtml(Array.isArray(value) ? value.join(",") : value ?? "")}" />${source}<button type="button" data-restore-field="${escapeHtml(field.name)}">恢复推断值</button><span data-field-error="${escapeHtml(field.name)}"></span></label>`;
  }

  window.DataAgentContractEditor = { render, bind };
})();
```

`bind` must collect typed values without converting empty strings into zero, save drafts before awaiting API calls, apply field-level errors, submit natural-language correction through `/contract-preview`, display returned execution-field diffs, and require a second click through `/contract-preview/apply` before replacing the active contract. `data-factory-agent.js` delegates goal rendering and button binding to this module; it keeps polling, permission takeover, risk confirmation and cancellation logic unchanged.

- [ ] **Step 4: Run frontend smoke and backend route tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_route_contracts.py tests/test_data_factory_agent_contract.py -v`

Expected: PASS.

- [ ] **Step 5: Commit exact frontend files**

```powershell
git add static/data-agent-contract-editor.js static/data-factory-agent.js static/index.html tests/test_route_contracts.py
git commit -m "feat: add grouped agent contract editor"
```

### Task 7: Learning samples and hit-rate metrics API

**Files:**
- Modify: `app/services/data_agent_learning.py:1619-1813`
- Modify: `app/routers/data_factory_agent.py:174-195`
- Create: `tests/test_data_agent_learning_metrics.py`
- Modify: `tests/test_data_agent_learning.py`

**Interfaces:**
- Produces: `serialize_learning_sample(sample) -> dict` with normalized `status`, `first_hit`, contracts, corrections, scope, and session ID.
- Produces: `learning_metrics(db, project_id, days) -> dict` for `days in {7, 30}`.
- Extends `GET /learning/overview` with `samples` and `metrics`, without removing current keys.
- Produces: `GET /learning/samples/{sample_id}` with project visibility check.

- [ ] **Step 1: Write failing metric tests**

```python
@pytest.fixture
def learning_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def sample_factory(learning_db):
    counter = itertools.count(1)

    def create(*, intent_key="full_flow", first_hit=None, outcome="verified", initial=None, final=None):
        index = next(counter)
        initial_contract = initial or {"variables": {"order_item_num": 1}}
        final_contract = final or copy.deepcopy(initial_contract)
        corrections = [] if first_hit is not False else [
            {"field": "order_item_num", "before": 1, "after": 2, "source": "direct_edit"}
        ]
        sample = models.DataAgentLearningSample(
            project_id=1,
            session_id=f"metric-session-{index}",
            module_key="order",
            intent_key=intent_key,
            instruction_text=f"metric sample {index}",
            model_candidate_json="{}",
            initial_contract_json=json.dumps(initial_contract, ensure_ascii=False),
            final_contract_json=json.dumps(final_contract, ensure_ascii=False),
            corrections_json=json.dumps(corrections, ensure_ascii=False),
            outcome=outcome,
            verified=1 if outcome == "verified" else 0,
            fingerprint=f"{index:064x}",
            create_time=datetime.now(),
        )
        learning_db.add(sample)
        learning_db.commit()
        learning_db.refresh(sample)
        return sample

    return create


def test_first_hit_uses_normalized_execution_contract(sample_factory):
    sample = sample_factory(
        initial={"variables": {"order_item_num": 1}, "target_label": "订单待付款"},
        final={"variables": {"order_item_num": 1}, "target_label": "待付款"},
        outcome="verified",
    )
    assert learning_service.serialize_learning_sample(sample)["first_hit"] is True


def test_metrics_report_sample_count_pending_and_per_script(learning_db, sample_factory):
    sample_factory(intent_key="full_flow", first_hit=True, outcome="verified")
    sample_factory(intent_key="full_flow", first_hit=False, outcome="verified")
    sample_factory(intent_key="full_flow", first_hit=True, outcome="pending")
    metrics = learning_service.learning_metrics(learning_db, project_id=1, days=30)
    assert metrics["verified_count"] == 2
    assert metrics["pending_count"] == 1
    assert metrics["first_hit_count"] == 1
    assert metrics["first_hit_rate"] == 0.5
    assert metrics["by_script"][0]["script_key"] == "full_flow"


def test_overview_preserves_existing_keys_and_adds_learning_views(learning_db):
    overview = learning_service.get_learning_overview(learning_db, 1)
    assert {"candidates", "active_rules", "recent_versions", "recent_reviews", "samples", "metrics"} <= set(overview)
    assert set(overview["metrics"]) == {"days_7", "days_30"}
```

- [ ] **Step 2: Run metric tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning_metrics.py tests/test_data_agent_learning.py -v -k "first_hit or metrics or overview"`

Expected: FAIL because samples and metrics are not serialized by overview.

- [ ] **Step 3: Implement exact comparison and aggregates**

```python
def serialize_learning_sample(sample: DataAgentLearningSample) -> dict:
    initial = _load_json_object(sample.initial_contract_json)
    final = _load_json_object(sample.final_contract_json)
    corrections = _load_json_list(sample.corrections_json)
    status_value = {"success": "verified", "failure": "pending"}.get(sample.outcome, sample.outcome)
    execution_corrections = [item for item in corrections if item.get("before") != item.get("after")]
    return {
        "id": sample.id,
        "project_id": sample.project_id,
        "session_id": sample.session_id,
        "module_key": sample.module_key,
        "script_key": sample.intent_key,
        "instruction": sample.instruction_text,
        "initial_contract": initial,
        "final_contract": final,
        "corrections": execution_corrections,
        "status": status_value,
        "first_hit": not execution_corrections,
        "verified": bool(sample.verified),
        "create_time": sample.create_time.strftime("%Y-%m-%d %H:%M:%S"),
    }
```

`learning_metrics` counts only `verified`/historical `success` in the denominator; pending and invalid are separate counts. It groups by `intent_key` and correction field, returns decimal rates in `[0, 1]`, and returns `None` rate when the verified denominator is zero so the UI cannot imply 100% from no samples.

- [ ] **Step 4: Run learning API tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning_metrics.py tests/test_data_agent_learning.py tests/test_permissions.py -v -k "learning or permissions"`

Expected: PASS.

- [ ] **Step 5: Commit exact files**

```powershell
git add app/services/data_agent_learning.py app/routers/data_factory_agent.py tests/test_data_agent_learning_metrics.py tests/test_data_agent_learning.py
git commit -m "feat: report agent learning samples and hit rates"
```

### Task 8: Four-view learning center UI

**Files:**
- Create: `static/data-agent-learning-center.js`
- Modify: `static/data-factory-agent.js:620-803`
- Modify: `static/index.html:16`
- Modify: `tests/test_route_contracts.py`

**Interfaces:**
- Produces browser global: `window.DataAgentLearningCenter.open(options) -> Promise<void>`.
- Views: `samples`, `candidates`, `rules`, `metrics`.
- Existing candidate regression/approve/reject and rule promote/disable/rollback actions keep their current endpoints and reason prompts.

- [ ] **Step 1: Write failing learning-center smoke tests**

```python
def test_learning_center_module_has_all_four_views():
    source = Path("static/data-agent-learning-center.js").read_text(encoding="utf-8")
    for key in ("samples", "candidates", "rules", "metrics"):
        assert f'data-learning-view="{key}"' in source
    for text in ("学习样本", "规则候选", "生效规则", "命中率"):
        assert text in source


def test_learning_center_displays_rate_with_denominator():
    source = Path("static/data-agent-learning-center.js").read_text(encoding="utf-8")
    assert "verified_count" in source
    assert "pending_count" in source
    assert "first_hit_rate" in source
```

- [ ] **Step 2: Run smoke tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_route_contracts.py -v -k "learning_center"`

Expected: FAIL because the independent learning center module does not exist.

- [ ] **Step 3: Move learning presentation into the new module**

```javascript
(function () {
  const VIEW_LABELS = {
    samples: "学习样本",
    candidates: "规则候选",
    rules: "生效规则",
    metrics: "命中率",
  };

  function rateText(metric) {
    if (metric.first_hit_rate == null) return `暂无已验证样本（待验证 ${metric.pending_count || 0}）`;
    return `${(metric.first_hit_rate * 100).toFixed(1)}%（${metric.first_hit_count}/${metric.verified_count}，待验证 ${metric.pending_count || 0}）`;
  }

  async function open(options) {
    const overview = await options.api(`/api/data-scripts/agent/learning/overview?project_id=${encodeURIComponent(options.projectId)}`);
    options.dialog.innerHTML = renderShell(overview, options);
    bindViews(options.dialog);
    bindExistingRuleActions(options.dialog, overview, options);
  }

  window.DataAgentLearningCenter = { open };
})();
```

Samples view shows instruction, initial/final contract diff, correction source, pending/verified/invalid state and source session. Metrics view shows 7-day and 30-day totals, per-script rates and per-field correction counts. `data-factory-agent.js` removes duplicated presentation helpers and delegates opening; it retains its public initialization function.

- [ ] **Step 4: Run route smoke tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_route_contracts.py -v`

Expected: PASS.

- [ ] **Step 5: Commit exact frontend files**

```powershell
git add static/data-agent-learning-center.js static/data-factory-agent.js static/index.html tests/test_route_contracts.py
git commit -m "feat: add agent learning center views"
```

### Task 9: Release gates and full regression

**Files:**
- Modify: `tests/test_data_agent_hit_rate.py`
- Modify: `tests/test_data_factory_agent.py`
- Modify: `tests/test_permissions.py`
- Modify: `tests/test_data_agent_learning.py`

**Interfaces:**
- Produces a repeatable actual-sample report helper: `build_hit_rate_report(samples, baseline) -> dict`.
- Gate semantics: core rate `>= 0.95`, other metadata-enabled rate `>= 0.90`, verified denominator reported, every category rate `>= baseline`.

- [ ] **Step 1: Add failing release-gate tests**

```python
def test_hit_rate_gate_requires_threshold_denominator_and_no_regression():
    report = build_hit_rate_report(
        [
            {"script_key": "full_flow", "core": True, "first_hit": True, "verified": True}
            for _ in range(19)
        ] + [
            {"script_key": "full_flow", "core": True, "first_hit": False, "verified": True}
        ],
        baseline={"full_flow": 0.94},
    )
    assert report["categories"]["full_flow"]["rate"] == 0.95
    assert report["categories"]["full_flow"]["sample_count"] == 20
    assert report["passed"] is True


def test_hit_rate_gate_fails_when_metadata_script_is_below_ninety_percent():
    samples = [
        {"script_key": "order_quote", "core": False, "first_hit": index < 8, "verified": True}
        for index in range(10)
    ]
    assert build_hit_rate_report(samples, baseline={"order_quote": 0.75})["passed"] is False
```

- [ ] **Step 2: Run release-gate tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_hit_rate.py -v -k "gate"`

Expected: FAIL because `build_hit_rate_report` does not exist.

- [ ] **Step 3: Implement deterministic release report and protected regressions**

```python
def build_hit_rate_report(samples: list[dict], baseline: dict[str, float]) -> dict:
    categories = {}
    for sample in samples:
        if not sample.get("verified"):
            continue
        key = str(sample["script_key"])
        item = categories.setdefault(key, {"core": bool(sample.get("core")), "sample_count": 0, "hit_count": 0})
        item["sample_count"] += 1
        item["hit_count"] += int(bool(sample.get("first_hit")))
    passed = True
    for key, item in categories.items():
        item["rate"] = item["hit_count"] / item["sample_count"]
        threshold = 0.95 if item["core"] else 0.90
        item["threshold"] = threshold
        item["baseline"] = baseline.get(key)
        item["passed"] = item["rate"] >= threshold and (
            item["baseline"] is None or item["rate"] >= item["baseline"]
        )
        passed = passed and item["passed"]
    return {"passed": passed and bool(categories), "categories": categories}
```

Add explicit regression cases for natural-language customer ID priority, topbar fallback, environment-account fallback, balance-insufficient bank fallback, the 500-limit Shen Wenni switch, second permission prompt continuation, temporary credential redaction, high-risk contract hash, second confirmation, and candidate threshold `3`.

- [ ] **Step 4: Run the staged regression suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_contracts.py tests/test_data_factory_agent_contract.py tests/test_data_agent_learning.py tests/test_data_agent_learning_metrics.py tests/test_data_agent_hit_rate.py tests/test_data_script_capabilities.py -v`

Expected: PASS.

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py tests/test_permissions.py tests/test_route_contracts.py -v`

Expected: PASS. If SQLite reports a transient lock/conflict, rerun the single failing test in isolation; only accept the suite when the isolated test passes and no deterministic failure remains.

- [ ] **Step 5: Verify repository state and commit only release-gate tests**

```powershell
git status --short
git diff --stat
git add tests/test_data_agent_hit_rate.py tests/test_data_factory_agent.py tests/test_permissions.py tests/test_data_agent_learning.py
git commit -m "test: enforce agent contract learning gates"
```

- [ ] **Step 6: Run final full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -v`

Expected: PASS. Report only the pass/fail summary and any isolated deterministic failure; do not paste full logs.

## Execution Checkpoints

- Checkpoint A after Task 4: core contracts are fully editable, “合同正确” creates a visible pending sample, and existing execution behavior is unchanged.
- Checkpoint B after Task 6: non-core scripts can compile from metadata and the grouped editor is usable without adding per-script frontend fields.
- Checkpoint C after Task 8: learning center exposes the complete feedback loop and denominators.
- Checkpoint D after Task 9: release gates prove recognition improvement without regressions in payment, permission takeover, account switching or high-risk confirmation.
