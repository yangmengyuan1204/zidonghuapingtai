# UI 自动化验证式录制与双轮回放 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 UI 录制升级为包含目标上下文和动作结果的验证式录制，在每轮数据重置后完成两次独立回放，并仅将连续两轮通过的用例保存为 `active`。

**Architecture:** 在现有 `locator_profile` 兼容路径旁新增 `target_profile`、`effect_profile` 和控件适配层；项目级配置选择现有数据脚本作为每轮重置入口。现有 `ui_record_preflight` 继续承担运行持久化，新的验证编排器负责数据重置、第一轮修复验证、人工重新选点和第二轮冻结验证。

**Tech Stack:** Python 3.11、FastAPI 0.115、SQLAlchemy 2.0、SQLite、Playwright 1.60、Vue 3、Vite 5、pytest。

## Global Constraints

- 实施必须在独立 `codex/` worktree 中进行，保留根工作区已有未提交改动，不覆盖、不提交。
- 测试必须使用项目 `.venv\Scripts\python.exe`，不能使用系统 Python。
- 修改任何现有函数、类或方法前，先执行 GitNexus upstream impact；HIGH/CRITICAL 风险先报告并停止等待确认。
- 每次提交前执行 `node .gitnexus/run.cjs detect-changes`、`git status --short`、`git diff --stat` 和 `git diff --check`。
- 每次只暂存任务列出的文件，不使用 `git add -A`，不提交数据库、日志、报告、截图、缓存或用户文件。
- 不增加第三方依赖，不修改 `.secret_key`、环境配置、启动脚本或现有数据脚本的入参、返回值和执行流程。
- `locator`、`fallback_locators`、`locator_profile` 和旧步骤 JSON 必须继续兼容。
- 匹配多个元素、候选置信度不足、危险动作结果不明确时必须安全停止，禁止 `.first` 和坐标兜底点击。
- `data-testid` 存在时优先，但不得要求被测系统必须增加该属性。
- 密码、Token、Cookie 和敏感数据不得写入步骤、预检报告或前端页面。
- 默认不做真实浏览器业务验收；30 条真实流程验收需测试账号、登录态和用户单独确认。

---

## File Structure

### New backend files

- `app/services/ui_recording_config.py`：项目级录制验证配置的读取、验证、保存和序列化。
- `app/services/ui_recording_reset.py`：调用现有数据脚本、生成每轮动态变量并脱敏报告。
- `app/services/ui_recording_capture.py`：录制注入脚本、页面状态采集和重新选点脚本。
- `app/services/ui_target_profile.py`：从录制事件编译页面、frame、容器和元素目标描述。
- `app/services/ui_action_effects.py`：推断动作结果及安全重试策略。
- `app/services/ui_target_resolver.py`：运行时统一候选评分、页面/frame/容器解析和安全唯一化。
- `app/executors/ui_adapters.py`：原生、Element Plus 和 Ant Design 常用组件交互适配。
- `app/executors/ui_effects_runtime.py`：动作结果预检查和等待验证。
- `app/services/ui_recording_verification.py`：双轮验证、暂停修复、重新选点和运行控制。

### Modified backend files

- `app/models.py`：新增独立 `UiRecordProjectConfig` 表。
- `app/routers/ui_record.py`：项目配置、双轮预检、重新选点、重启验证和保存规则。
- `app/routers/projects.py`：删除项目时清理录制配置。
- `app/services/ui_recording_session.py`：使用独立采集脚本，合并动作前后状态并应用重新选点结果。
- `app/services/ui_locator_engine.py`：保留旧定位器能力，并把页面/frame 解析委托给新解析器。
- `app/services/ui_recording_preflight.py`：保留序列化和兼容入口，转交双轮验证编排器。
- `app/executors/actions.py`：新步骤走目标解析、控件适配和结果验证，旧步骤继续原路径。
- `app/executors/runtime.py`：支持冻结验证、禁用 AI 自愈、运行轮次和失败上下文。
- `tests/route_contract_expected.json`：登记新增接口。

### New frontend file

- `frontend/src/components/ui-cases/UiRecordingStartDialog.vue`：项目、账号、数据重置脚本、环境和录制参数配置。

### Modified frontend files

- `frontend/src/api/modules/uiCases.js`：新增配置、重新选点和重启验证 API。
- `frontend/src/components/ui-cases/UiRecordingPanel.vue`：显示目标描述和动作结果采集状态。
- `frontend/src/components/ui-cases/UiRecordingPreflightPanel.vue`：显示轮次、重置、结果验证和重新选点状态。
- `frontend/src/views/UiCasesView.vue`：接入新的开始弹窗、双轮轮询和修复流程。
- `frontend/scripts/validate-v3-ui-cases-parity.mjs`：扩充 V3 契约校验。

### New tests

- `tests/test_ui_recording_config.py`
- `tests/test_ui_recording_reset.py`
- `tests/test_ui_target_profile.py`
- `tests/test_ui_action_effects.py`
- `tests/test_ui_target_resolver.py`
- `tests/test_ui_adapters.py`
- `tests/test_ui_recording_verification.py`

---

### Task 1: 项目级录制验证配置

**Files:**
- Modify: `app/models.py:398-449`
- Create: `app/services/ui_recording_config.py`
- Modify: `app/routers/ui_record.py:1-55`
- Modify: `app/routers/projects.py`（项目删除函数）
- Test: `tests/test_ui_recording_config.py`
- Test: `tests/route_contract_expected.json`

**Interfaces:**
- Produces: `UiRecordProjectConfig` ORM 模型。
- Produces: `get_recording_config(db: Session, project_id: int) -> UiRecordProjectConfig | None`。
- Produces: `save_recording_config(db: Session, project_id: int, payload: dict[str, Any]) -> UiRecordProjectConfig`。
- Produces: `serialize_recording_config(db: Session, project_id: int) -> dict[str, Any]`。
- Produces: `GET/PUT /api/ui-record/projects/{project_id}/config`。

- [ ] **Step 1: 对现有修改符号执行 upstream impact**

Run:

```powershell
node .gitnexus/run.cjs impact Project --direction upstream
node .gitnexus/run.cjs impact delete_project --direction upstream
```

Expected: 记录直接调用者、受影响流程和风险等级；HIGH/CRITICAL 时先报告。

- [ ] **Step 2: 编写失败测试，锁定表结构、权限语义和项目归属校验**

在 `tests/test_ui_recording_config.py` 写入：

```python
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Env, Project, UiRecordProjectConfig
from app.services.ui_recording_config import save_recording_config, serialize_recording_config


def test_recording_config_table_is_independent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    assert "ui_record_project_config" in inspect(engine).get_table_names()


def test_recording_config_rejects_env_from_other_project():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Project(id=1, name="A", desc="", create_time=datetime.now()),
            Project(id=2, name="B", desc="", create_time=datetime.now()),
            Env(id=9, project_id=2, env_name="B测试", base_url="https://b.test"),
        ])
        db.commit()
        with pytest.raises(ValueError, match="环境不存在或不属于当前项目"):
            save_recording_config(db, 1, {
                "reset_script_key": "shopping_cart",
                "reset_env_id": 9,
                "reset_variables": {},
                "max_repair_attempts": 3,
            })


def test_recording_config_serialization_hides_sensitive_values(monkeypatch):
    monkeypatch.setattr(
        "app.services.ui_recording_config.data_script_catalog",
        lambda _db, _project_id: [{"script_type": "shopping_cart", "name": "购物车", "risk_level": "normal"}],
    )
    # 创建项目、环境和配置后，断言 response 只返回允许保存的非敏感 reset_variables。
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_recording_config.py
```

Expected: FAIL，提示 `UiRecordProjectConfig` 或配置服务不存在。

- [ ] **Step 4: 新增独立模型**

在 `app/models.py` 的 UI 录制模型区域新增：

```python
class UiRecordProjectConfig(Base):
    __tablename__ = "ui_record_project_config"

    project_id = Column(Integer, primary_key=True)
    reset_script_key = Column(String(80), nullable=False)
    reset_env_id = Column(Integer, nullable=False, index=True)
    reset_variables_json = Column(Text, nullable=False, default="{}")
    verification_rounds = Column(Integer, nullable=False, default=2)
    max_repair_attempts = Column(Integer, nullable=False, default=3)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=True)
```

新表由现有 `Base.metadata.create_all()` 创建，不修改 `Project` 或 `UiCase` 字段。

- [ ] **Step 5: 实现配置服务**

`app/services/ui_recording_config.py` 的公开接口固定为：

```python
SENSITIVE_KEY_PARTS = ("password", "token", "cookie", "secret", "authorization")


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            any(part in str(key).strip().lower() for part in SENSITIVE_KEY_PARTS)
            or _contains_sensitive_key(nested)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def get_recording_config(db: Session, project_id: int) -> UiRecordProjectConfig | None:
    return db.get(UiRecordProjectConfig, project_id)

def save_recording_config(
    db: Session,
    project_id: int,
    payload: dict[str, Any],
) -> UiRecordProjectConfig:
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("项目不存在")
    reset_script_key = str(payload.get("reset_script_key") or "").strip()
    reset_env_id = int(payload.get("reset_env_id") or 0)
    reset_variables = payload.get("reset_variables") or {}
    if not isinstance(reset_variables, dict):
        raise ValueError("重置参数必须是对象")
    if _contains_sensitive_key(reset_variables):
        raise ValueError("重置参数不能保存密码、令牌或Cookie")
    validate_data_setup_for_project(db, project_id, {
        "steps": [{
            "script_type": reset_script_key,
            "env_id": reset_env_id,
            "variables": reset_variables,
            "enabled": True,
        }]
    })
    row = db.get(UiRecordProjectConfig, project_id)
    if row is None:
        row = UiRecordProjectConfig(project_id=project_id, create_time=datetime.now())
        db.add(row)
    row.reset_script_key = reset_script_key
    row.reset_env_id = reset_env_id
    row.reset_variables_json = json.dumps(reset_variables, ensure_ascii=False)
    row.verification_rounds = 2
    row.max_repair_attempts = max(1, min(5, int(payload.get("max_repair_attempts") or 3)))
    row.update_time = datetime.now()
    db.commit()
    db.refresh(row)
    return row

def serialize_recording_config(db: Session, project_id: int) -> dict[str, Any]:
    row = get_recording_config(db, project_id)
    return {
        "project_id": project_id,
        "config": None if row is None else {
            "reset_script_key": row.reset_script_key,
            "reset_env_id": row.reset_env_id,
            "reset_variables": json.loads(row.reset_variables_json or "{}"),
            "verification_rounds": 2,
            "max_repair_attempts": row.max_repair_attempts,
        },
        "available_scripts": data_script_catalog(db, project_id),
    }
```

实现要求：

```python
setup = validate_data_setup_for_project(db, project_id, {
    "steps": [{
        "script_type": reset_script_key,
        "env_id": reset_env_id,
        "variables": reset_variables,
        "enabled": True,
    }]
})
if contains_sensitive_key(reset_variables):
    raise ValueError("重置参数不能保存密码、令牌或Cookie")
verification_rounds = 2
max_repair_attempts = max(1, min(5, int(payload.get("max_repair_attempts") or 3)))
```

序列化返回 `config` 和当前项目可用的 `available_scripts`，脚本列表复用 `data_script_catalog(db, project_id)`。

- [ ] **Step 6: 增加配置路由和项目删除清理**

在 `app/routers/ui_record.py` 增加：

```python
@router.get("/projects/{project_id}/config")
def get_ui_record_project_config(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    ensure_project_exists(db, project_id)
    return serialize_recording_config(db, project_id)

@router.put("/projects/{project_id}/config")
def put_ui_record_project_config(
    project_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        save_recording_config(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return serialize_recording_config(db, project_id)
```

两个接口均使用 `require_admin`。在项目删除事务中增加：

```python
db.query(UiRecordProjectConfig).filter(UiRecordProjectConfig.project_id == project_id).delete()
```

- [ ] **Step 7: 更新路由契约并运行测试**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_recording_config.py tests/test_route_contract.py
```

Expected: PASS。

- [ ] **Step 8: 检查并提交**

Run:

```powershell
node .gitnexus/run.cjs detect-changes
git status --short
git diff --stat
git diff --check
git add app/models.py app/services/ui_recording_config.py app/routers/ui_record.py app/routers/projects.py tests/test_ui_recording_config.py tests/route_contract_expected.json
git commit -m "feat: add UI recording verification config"
```

Expected: 仅提交本任务文件。

---

### Task 2: 数据重置适配与 `${reset.xxx}` 动态变量

**Files:**
- Create: `app/services/ui_recording_reset.py`
- Test: `tests/test_ui_recording_reset.py`

**Interfaces:**
- Consumes: `UiRecordProjectConfig`。
- Produces: `ResetExecutionResult(passed, raw_outputs, runtime_variables, public_report, error)`。
- Produces: `execute_recording_reset(db, config) -> ResetExecutionResult`。
- Produces: `resolve_reset_templates(value, outputs) -> Any`。

- [ ] **Step 1: 编写数据脚本调用和变量替换失败测试**

```python
def test_reset_executes_registered_script_and_flattens_outputs(monkeypatch, db, config, env):
    monkeypatch.setitem(SCRIPT_REGISTRY, "shopping_cart", {
        "name": "购物车",
        "func": lambda _env, _vars: (True, "ok", "", {"order": {"sn": "A100"}}),
    })
    result = execute_recording_reset(db, config)
    assert result.passed is True
    assert result.runtime_variables["reset.order.sn"] == "A100"
    assert resolve_reset_templates("订单 ${reset.order.sn}", result.raw_outputs) == "订单 A100"


def test_reset_failure_stops_before_browser_execution(monkeypatch, db, config):
    monkeypatch.setitem(SCRIPT_REGISTRY, "shopping_cart", {
        "name": "购物车",
        "func": lambda _env, _vars: (False, "业务初始化失败", "", {}),
    })
    result = execute_recording_reset(db, config)
    assert result.passed is False
    assert "业务初始化失败" in result.error


def test_reset_report_masks_sensitive_outputs(monkeypatch, db, config):
    # runner 返回 token/password 时，raw_outputs 可供当轮内部使用，但 public_report 中必须为 ***。
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_recording_reset.py
```

Expected: FAIL，提示模块不存在。

- [ ] **Step 3: 实现独立重置适配器**

核心类型：

```python
@dataclass
class ResetExecutionResult:
    passed: bool
    raw_outputs: dict[str, Any]
    runtime_variables: dict[str, Any]
    public_report: dict[str, Any]
    error: str = ""
```

执行顺序固定为：

```python
definition = SCRIPT_REGISTRY.get(config.reset_script_key)
env = db.get(Env, config.reset_env_id)
prepared = data_script_variables(db, reset_variables, config.project_id)
passed, log_text, evidence_path, outputs = definition["func"](env, prepared)
```

只把 `mask_sensitive_data(outputs)` 和 `redact_sensitive_text(log_text)`写入 `public_report`。使用递归扁平化生成 `reset.order.sn` 形式的运行变量。

`resolve_reset_templates`只替换严格格式：

```python
RESET_PATTERN = re.compile(r"\$\{reset\.([A-Za-z0-9_.-]+)\}")
```

缺失变量时抛出 `ValueError("缺少数据重置变量：reset.xxx")`，不能替换为空字符串。

- [ ] **Step 4: 运行测试**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_recording_reset.py
```

Expected: PASS。

- [ ] **Step 5: 检查并提交**

```powershell
node .gitnexus/run.cjs detect-changes
git status --short
git diff --stat
git diff --check
git add app/services/ui_recording_reset.py tests/test_ui_recording_reset.py
git commit -m "feat: add UI recording data reset adapter"
```

---

### Task 3: 目标描述采集与编译

**Files:**
- Create: `app/services/ui_recording_capture.py`
- Create: `app/services/ui_target_profile.py`
- Modify: `app/services/ui_recording_session.py:21-291,298-520,656-712`
- Test: `tests/test_ui_target_profile.py`
- Test: `tests/test_ui_record_and_execution.py`

**Interfaces:**
- Produces: `recording_init_script() -> str`。
- Produces: `repick_script(step_index: int) -> str`。
- Produces: `build_target_profile(event: dict[str, Any]) -> dict[str, Any]`。
- Produces: 录制步骤字段 `target_profile.schema_version == 1`。

- [ ] **Step 1: 对录制符号执行 upstream impact**

```powershell
node .gitnexus/run.cjs impact _sanitize_event --direction upstream
node .gitnexus/run.cjs impact _event_to_step --direction upstream
node .gitnexus/run.cjs impact _attach_page_recorder --direction upstream
```

- [ ] **Step 2: 编写目标描述测试**

```python
def test_target_profile_keeps_dialog_table_row_and_element_semantics():
    profile = build_target_profile({
        "url": "https://example.test/orders?ts=123",
        "page_title": "订单管理",
        "frame_chain": [],
        "scope_chain": [
            {"kind": "dialog", "role": "dialog", "name": "删除订单"},
            {"kind": "table_row", "headers": {"订单号": "A100"}},
        ],
        "tag": "button",
        "role": "button",
        "accessible_name": "删除",
        "stable_attrs": {"data-testid": "delete-order"},
        "capabilities": {"click": True, "input": False},
    })
    assert profile["page"]["title"] == "订单管理"
    assert profile["scope_chain"][1]["headers"]["订单号"] == "A100"
    assert profile["element"]["accessible_name"] == "删除"
    assert profile["quality"] == "stable"


def test_target_profile_marks_unscoped_repeated_text_as_risk():
    profile = build_target_profile({
        "tag": "button", "role": "button", "accessible_name": "删除",
        "recorded_match_count": 4, "scope_chain": [], "stable_attrs": {},
    })
    assert profile["quality"] == "risk"
```

- [ ] **Step 3: 运行测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_target_profile.py tests/test_ui_record_and_execution.py
```

- [ ] **Step 4: 抽出录制注入脚本**

`ui_recording_capture.py` 中的脚本必须公开并采集：

```javascript
window.__uiRecorderCaptureTarget = (el) => ({
  page_title: document.title || '',
  frame_chain: buildFrameChain(),
  scope_chain: buildScopeChain(el),
  neighbor_texts: buildNeighborTexts(el),
  stable_class_tokens: stableClassTokens(el),
  capabilities: {
    click: isClickable(el),
    input: ['input', 'textarea'].includes(el.tagName.toLowerCase()),
    select: el.tagName.toLowerCase() === 'select',
    check: ['checkbox', 'radio'].includes((el.getAttribute('type') || '').toLowerCase()),
  },
  recorded_match_count: candidateMatchCount(el),
})
```

`buildScopeChain`只记录最近的 `dialog/drawer/form/table_row/card/menu/listbox`，最多 6 层；每层文字最多 160 字符。

- [ ] **Step 5: 实现目标描述编译器并接入步骤生成**

`build_target_profile()` 返回：

```python
{
    "schema_version": 1,
    "page": {
        "url_pattern": "https://example.test/orders*",
        "title": "订单管理",
        "opener_interaction_id": "interaction-12",
    },
    "frame_chain": [],
    "scope_chain": [{"kind": "table_row", "headers": {"订单号": "A100"}}],
    "element": {"tag": "button", "role": "button", "accessible_name": "删除"},
    "neighbor_texts": ["订单号", "A100"],
    "quality": "stable" | "weak" | "risk",
}
```

在 `_event_to_step()` 中保留 `locator_profile`，并加入：

```python
step["target_profile"] = build_target_profile(event)
```

- [ ] **Step 6: 运行测试**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_target_profile.py tests/test_ui_record_and_execution.py tests/test_ui_recording.py
```

Expected: PASS。

- [ ] **Step 7: 检查并提交**

```powershell
node .gitnexus/run.cjs detect-changes
git status --short
git diff --stat
git diff --check
git add app/services/ui_recording_capture.py app/services/ui_target_profile.py app/services/ui_recording_session.py tests/test_ui_target_profile.py tests/test_ui_record_and_execution.py
git commit -m "feat: capture semantic UI target profiles"
```

---

### Task 4: 动作前后状态与结果编译

**Files:**
- Create: `app/services/ui_action_effects.py`
- Modify: `app/services/ui_recording_capture.py`
- Modify: `app/services/ui_recording_session.py:361-460,534-606`
- Test: `tests/test_ui_action_effects.py`

**Interfaces:**
- Produces: `infer_effect_profile(event: dict[str, Any]) -> dict[str, Any]`。
- Produces: `build_retry_policy(step: dict[str, Any]) -> dict[str, Any]`。
- Produces: 步骤字段 `effect_profile` 和 `retry_policy`。

- [ ] **Step 1: 编写效果推断和危险动作测试**

```python
def test_infer_effect_profile_detects_dialog_and_url_change():
    profile = infer_effect_profile({
        "before_state": {"url": "https://x.test/orders", "dialogs": []},
        "after_state": {"url": "https://x.test/orders/1", "dialogs": ["订单详情"]},
    })
    assert {item["type"] for item in profile["effects"]} == {"url_change", "dialog_visible"}


def test_input_effect_requires_value_change():
    profile = infer_effect_profile({
        "action": "input", "value": "张三",
        "before_state": {"target": {"value": ""}},
        "after_state": {"target": {"value": "张三"}},
    })
    assert profile["effects"] == [{"type": "target_value", "expected": "张三"}]


def test_delete_submit_and_payment_are_not_automatically_retried():
    for text in ("删除", "提交订单", "确认支付"):
        policy = build_retry_policy({"action": "click", "name": text})
        assert policy == {"safe_retry": False, "max_attempts": 1, "reason": "dangerous_action"}
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_action_effects.py
```

- [ ] **Step 3: 录制交互关联 ID 和页面状态**

每次动作生成 `interaction_id`，发送动作事件前采集 `before_state`；在 400ms 和 1200ms 采集两次，取变化更完整的一次作为 `after_state`：

```javascript
const interactionId = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`
const beforeState = capturePageState(target)
send({ ...actionPayload, interaction_id: interactionId, before_state: beforeState })
setTimeout(() => send({ action: 'effect_observation', interaction_id: interactionId, after_state: capturePageState(target) }), 400)
setTimeout(() => send({ action: 'effect_observation', interaction_id: interactionId, after_state: capturePageState(target), final: true }), 1200)
```

`_append_event()` 遇到 `effect_observation` 时按 `interaction_id` 合并到原事件，不生成额外业务步骤。

- [ ] **Step 4: 编译 effect_profile 和 retry_policy**

`effect_profile` 至少包含：

```python
{
    "schema_version": 1,
    "effects": [{"type": "dialog_hidden", "name": "提交订单"}],
    "required": True,
    "confidence": 90,
}
```

若无法推断业务结果，输入/选择/勾选使用控件值结果；普通点击标记 `required=False` 和低置信度，双轮验证时作为高风险步骤处理。

- [ ] **Step 5: 运行测试并提交**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_action_effects.py tests/test_ui_record_and_execution.py tests/test_ui_recording.py
node .gitnexus/run.cjs detect-changes
git status --short
git diff --stat
git diff --check
git add app/services/ui_action_effects.py app/services/ui_recording_capture.py app/services/ui_recording_session.py tests/test_ui_action_effects.py tests/test_ui_record_and_execution.py
git commit -m "feat: record and compile UI action effects"
```

---

### Task 5: 上下文约束的统一目标解析器

**Files:**
- Create: `app/services/ui_target_resolver.py`
- Modify: `app/services/ui_locator_engine.py:150-206`
- Test: `tests/test_ui_target_resolver.py`
- Test: `tests/test_ui_locator_engine.py`

**Interfaces:**
- Produces: `ResolvedTarget(target, used_locator, score, reasons, matched_count, page_identity)`。
- Produces: `resolve_target(page, step, timeout_ms, memory=(), frozen=False) -> ResolvedTarget`。
- Produces: `select_profile_page(page, step, timeout_ms) -> Any`。
- Produces: `select_profile_scope(page, step, timeout_ms) -> Any`。

- [ ] **Step 1: 对旧页面/frame选择符号执行 impact**

```powershell
node .gitnexus/run.cjs impact select_step_page --direction upstream
node .gitnexus/run.cjs impact select_step_scope --direction upstream
node .gitnexus/run.cjs impact _impl__resolve_locator --direction upstream
```

- [ ] **Step 2: 编写安全解析测试**

```python
def test_resolver_constrains_duplicate_delete_button_to_order_row(fake_page):
    step = {
        "action": "click",
        "target_profile": {
            "page": {"url_pattern": "*/orders"},
            "frame_chain": [],
            "scope_chain": [{"kind": "table_row", "headers": {"订单号": "A100"}}],
            "element": {"role": "button", "accessible_name": "删除", "capabilities": {"click": True}},
        },
    }
    result = resolve_target(fake_page, step, 1000)
    assert result.matched_count == 1
    assert result.reasons[-1] == "目标在订单号=A100的表格行中唯一匹配"


def test_resolver_rejects_close_scores_instead_of_clicking(fake_page):
    with pytest.raises(TargetResolutionError, match="候选分差不足"):
        resolve_target(fake_page, ambiguous_step, 1000)


def test_resolver_uses_page_identity_before_page_index(fake_context):
    selected = select_profile_page(fake_context.pages[0], step_for_popup_title, 1000)
    assert selected.title() == "支付结果"


def test_resolver_requires_each_frame_chain_level_to_be_unique(fake_page):
    with pytest.raises(TargetResolutionError, match="iframe第2层匹配不唯一"):
        select_profile_scope(fake_page, nested_frame_step, 1000)
```

- [ ] **Step 3: 运行测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_target_resolver.py tests/test_ui_locator_engine.py
```

- [ ] **Step 4: 实现统一候选池和阈值**

固定评分原则：

```python
MIN_CONFIDENCE = 80
MIN_SCORE_GAP = 10
```

候选来源按设计统一生成，但最终按分数排序后一次判断；不得逐个候选等待完整超时。每个候选最多使用总超时的 `min(1500, remaining_ms)`。

解析成功必须检查：

```python
count == 1
visible is True
enabled is True
action_compatible is True
not_obscured is True
stable_box is True
top_score >= MIN_CONFIDENCE
top_score - second_score >= MIN_SCORE_GAP
```

在 `frozen=True` 时不加入 AI 候选，也不加入当轮产生的新定位记忆。

- [ ] **Step 5: 保留旧步骤兼容入口**

`select_step_page()` 和 `select_step_scope()` 对存在 `target_profile` 的步骤委托新解析器；没有新字段时保持旧逻辑和现有异常语义。

- [ ] **Step 6: 运行测试并提交**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_target_resolver.py tests/test_ui_locator_engine.py
node .gitnexus/run.cjs detect-changes
git status --short
git diff --stat
git diff --check
git add app/services/ui_target_resolver.py app/services/ui_locator_engine.py tests/test_ui_target_resolver.py tests/test_ui_locator_engine.py
git commit -m "feat: resolve UI targets by semantic context"
```

---

### Task 6: 控件适配、动作结果验证和防重复提交

**Files:**
- Create: `app/executors/ui_adapters.py`
- Create: `app/executors/ui_effects_runtime.py`
- Modify: `app/executors/actions.py:49-245`
- Modify: `app/executors/runtime.py:85-344`
- Test: `tests/test_ui_adapters.py`
- Test: `tests/test_ui_record_and_execution.py`

**Interfaces:**
- Consumes: `resolve_target()`。
- Produces: `execute_adapted_action(page, resolved, step, timeout_ms) -> dict[str, Any]`。
- Produces: `effect_already_satisfied(page, step) -> bool`。
- Produces: `wait_for_effect_profile(page, step, timeout_ms) -> dict[str, Any]`。
- Changes: `_impl__run_ui_step(..., execution_context: dict[str, Any] | None = None)`，wrapper 使用同一参数并保持默认兼容。

- [ ] **Step 1: 对执行器现有符号执行 impact**

```powershell
node .gitnexus/run.cjs impact _impl__perform_ui_action --direction upstream
node .gitnexus/run.cjs impact _impl__run_ui_step --direction upstream
node .gitnexus/run.cjs impact _impl_execute_ui_case_in_page --direction upstream
```

- [ ] **Step 2: 编写适配器和结果验证测试**

```python
def test_element_plus_select_uses_visible_listbox_option(fake_page, resolved):
    detail = execute_adapted_action(fake_page, resolved, {
        "action": "select", "value": "上海", "target_profile": {"element": {"framework": "element_plus"}},
    }, 1000)
    assert detail["adapter"] == "element_plus_select"
    assert fake_page.clicked_option == "上海"


def test_effect_precheck_prevents_duplicate_submit(fake_page):
    step = {"action": "click", "effect_profile": {"effects": [{"type": "dialog_hidden", "name": "提交订单"}]}}
    fake_page.dialog_visible = False
    assert effect_already_satisfied(fake_page, step) is True


def test_dangerous_action_timeout_is_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(actions, "execute_adapted_action", lambda *_args: calls.append(1) or {})
    with pytest.raises(UiStepExecutionError):
        actions._impl__run_ui_step(page, dangerous_step_without_effect, [], 5)
    assert len(calls) == 1
```

- [ ] **Step 3: 运行测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_adapters.py tests/test_ui_record_and_execution.py
```

- [ ] **Step 4: 实现控件适配注册表**

公开注册表：

```python
ADAPTERS = (
    NativeInputAdapter(),
    NativeSelectAdapter(),
    NativeCheckAdapter(),
    ElementPlusSelectAdapter(),
    ElementPlusDialogAdapter(),
    ElementPlusDateAdapter(),
    AntSelectAdapter(),
    AntModalAdapter(),
    AntDateAdapter(),
    GenericClickAdapter(),
)
```

下拉适配器只在当前可见 popup/listbox 内精确选择选项；匹配多个 popup 或多个选项时抛错。

- [ ] **Step 5: 实现结果预检查和等待**

`ui_effects_runtime.py` 支持设计中的 URL、标签页、dialog、元素、值、勾选、表格行、toast 和网络结果。等待策略使用同一个总 deadline，每 100ms 检查一次，不能为每个 effect 重新使用完整超时。

- [ ] **Step 6: 在新步骤路径接入执行器**

在 `_impl__run_ui_step()` 中：

```python
if isinstance(step.get("target_profile"), dict):
    resolved = resolve_target(page, step, timeout_ms, memory_candidates, frozen=freeze_resolution)
    if effect_already_satisfied(page, step):
        return {**detail, "status": "passed", "effect_pre_satisfied": True}
    action_detail = execute_adapted_action(page, resolved, step, timeout_ms)
    effect_detail = wait_for_effect_profile(page, step, timeout_ms)
else:
    # 原有 locator/fallback 执行路径保持不变
```

`freeze_resolution`、`disable_ai_heal` 从 `execution_context` 传入步骤执行。第二轮不得调用 `auto_heal` 或写入 locator memory。

- [ ] **Step 7: 运行测试并提交**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_adapters.py tests/test_ui_record_and_execution.py tests/test_ui_locator_learning.py tests/test_ui_recording_preflight.py
node .gitnexus/run.cjs detect-changes
git status --short
git diff --stat
git diff --check
git add app/executors/ui_adapters.py app/executors/ui_effects_runtime.py app/executors/actions.py app/executors/runtime.py tests/test_ui_adapters.py tests/test_ui_record_and_execution.py
git commit -m "feat: verify UI action effects safely"
```

---

### Task 7: 双轮验证编排与暂停重新选点

**Files:**
- Create: `app/services/ui_recording_verification.py`
- Modify: `app/services/ui_recording_preflight.py:1-240`
- Modify: `app/services/ui_recording_session.py:613-655`
- Modify: `app/services/ui_recording_capture.py`
- Test: `tests/test_ui_recording_verification.py`
- Test: `tests/test_ui_recording_preflight.py`

**Interfaces:**
- Produces: `launch_verification(row, case_data, storage_state) -> None`。
- Produces: `request_repick(run_id, step_index) -> dict[str, Any]`。
- Produces: `restart_verification(db, row, case_data, storage_state) -> None`。
- Produces: `cleanup_verification(run_id) -> None`。
- Produces statuses: `queued/resetting/round_1_running/repair_required/repick_waiting/repair_ready/round_2_running/passed/failed`。

- [ ] **Step 1: 对预检符号执行 impact**

```powershell
node .gitnexus/run.cjs impact create_preflight --direction upstream
node .gitnexus/run.cjs impact launch_preflight --direction upstream
node .gitnexus/run.cjs impact determine_recorded_case_status --direction upstream
```

- [ ] **Step 2: 编写状态机测试**

```python
def test_each_round_resets_data_before_browser(monkeypatch, runner):
    calls = []
    monkeypatch.setattr(runner, "execute_recording_reset", lambda *_: calls.append("reset") or passed_reset())
    monkeypatch.setattr(runner, "execute_round", lambda round_no, *_: calls.append(f"round-{round_no}") or passed_round())
    runner.run()
    assert calls == ["reset", "round-1", "reset", "round-2"]


def test_second_round_is_frozen(monkeypatch, runner):
    contexts = []
    monkeypatch.setattr(runner, "execute_round", lambda _round, context: contexts.append(context) or passed_round())
    runner.run()
    assert contexts[1]["freeze_resolution"] is True
    assert contexts[1]["disable_ai_heal"] is True


def test_locator_failure_pauses_first_round_for_repick(runner):
    runner.execute_round = lambda *_: failed_round("locator_error", step_index=3)
    runner.run()
    assert runner.row.status == "repair_required"
    assert runner.browser_is_open is True


def test_repair_limit_prevents_infinite_loop(runner):
    runner.row.report_json = json.dumps({"repair_attempts": 3})
    with pytest.raises(ValueError, match="已达到最大重新选点次数"):
        request_repick(runner.row.run_id, 3)
```

- [ ] **Step 3: 运行测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_recording_verification.py tests/test_ui_recording_preflight.py
```

- [ ] **Step 4: 实现验证控制对象**

```python
@dataclass
class VerificationControl:
    run_id: str
    repick_requested: threading.Event
    stop_requested: threading.Event
    requested_step_index: int = 0
```

全局控制表只保存运行中的控制对象，并受 `threading.Lock` 保护。运行结束、取消、保存或超时后必须清理。

- [ ] **Step 5: 实现双轮 worker**

每轮：

1. 设置 `resetting` 并执行 `execute_recording_reset()`。
2. 使用 `resolve_reset_templates()` 生成当轮步骤快照。
3. worker 自己持有 Playwright、browser、context 和 page。
4. 第一轮使用 `headless=False`，调用 `execute_ui_case_in_page()`，避免运行结束前自动关闭失败页面。
5. 第一轮定位、交互或效果失败进入 `repair_required`；环境、登录、重置和断言失败直接 `failed`。
6. 第一轮通过后关闭上下文，重新重置并创建第二个 `headless=True` 上下文。
7. 第二轮设置 `freeze_resolution=True`、`disable_ai_heal=True`、`retry_count=0`。

- [ ] **Step 6: 实现重新选点脚本**

`repick_script(step_index)` 注入全屏提示和 hover 高亮，下一次左键点击后阻止业务动作并返回：

```javascript
{
  step_index,
  locator_candidates,
  target_profile_source: window.__uiRecorderCaptureTarget(target),
}
```

worker 在自己的线程中执行该脚本，收到结果后调用：

```python
ui_recording_session.override_session_step_target(
    session_id,
    step_index,
    locator_candidates,
    build_target_profile(target_profile_source),
)
```

状态改为 `repair_ready` 后关闭验证浏览器。重启必须从数据重置和第一步开始。

- [ ] **Step 7: 保持 preflight 兼容入口**

`ui_recording_preflight.launch_preflight()` 保留原函数名，但内部调用 `launch_verification()`；`serialize_preflight()` 保留现有响应字段并增加轮次、重置和修复信息。

- [ ] **Step 8: 运行测试并提交**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_recording_verification.py tests/test_ui_recording_preflight.py tests/test_ui_recording.py
node .gitnexus/run.cjs detect-changes
git status --short
git diff --stat
git diff --check
git add app/services/ui_recording_verification.py app/services/ui_recording_preflight.py app/services/ui_recording_session.py app/services/ui_recording_capture.py tests/test_ui_recording_verification.py tests/test_ui_recording_preflight.py tests/test_ui_recording.py
git commit -m "feat: add two-round UI recording verification"
```

---

### Task 8: 预检、重新选点、重启和保存 API

**Files:**
- Modify: `app/routers/ui_record.py:102-227`
- Modify: `app/services/ui_recording_preflight.py`
- Test: `tests/test_ui_recording.py`
- Test: `tests/route_contract_expected.json`

**Interfaces:**
- Produces: `POST /api/ui-record/preflights/{run_id}/steps/{step_index}/repick/start`。
- Produces: `POST /api/ui-record/preflights/{run_id}/restart`。
- Strengthens: `POST /api/ui-record/sessions/{session_id}/preflight`。
- Strengthens: `POST /api/ui-record/sessions/{session_id}/save`。
- Changes: `determine_recorded_case_status(preflight_status, steps, preflight_report=None) -> str`。

- [ ] **Step 1: 对路由和保存判定执行 impact**

```powershell
node .gitnexus/run.cjs impact start_ui_record_preflight --direction upstream
node .gitnexus/run.cjs impact save_ui_record_session --direction upstream
node .gitnexus/run.cjs impact determine_recorded_case_status --direction upstream
```

- [ ] **Step 2: 编写路由和保存规则失败测试**

```python
def test_start_preflight_without_config_uses_legacy_single_round(monkeypatch):
    result = asyncio.run(ui_record.start_ui_record_preflight(
        "session",
        payload={},
        db=db,
        current_user=admin,
    ))
    assert result["report"]["verification_mode"] == "legacy"
    assert result["report"]["required_rounds"] == 1


def test_repick_requires_matching_failed_step(monkeypatch):
    with pytest.raises(HTTPException, match="只能重新选择当前失败步骤"):
        ui_record.start_ui_record_repick("run", 4, db=db, current_user=admin)


def test_case_is_active_only_after_two_frozen_rounds(monkeypatch):
    preflight.status = "passed"
    preflight.report_json = json.dumps({
        "verified_rounds": 2,
        "rounds": [{"status": "passed"}, {"status": "passed", "frozen": True}],
        "steps_snapshot_hash": expected_hash,
    })
    result = asyncio.run(ui_record.save_ui_record_session(
        "session",
        payload={"preflight_run_id": "run"},
        db=db,
        current_user=admin,
    ))
    assert result["case"].status == "active"


def test_legacy_single_preflight_can_only_save_draft(monkeypatch):
    preflight.status = "passed"
    preflight.report_json = json.dumps({"verified_rounds": 1})
    result = asyncio.run(ui_record.save_ui_record_session(
        "session",
        payload={"preflight_run_id": "run"},
        db=db,
        current_user=admin,
    ))
    assert result["case"].status == "draft"
```

- [ ] **Step 3: 运行测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_recording.py tests/test_route_contract.py
```

- [ ] **Step 4: 接入项目配置和新控制接口**

开始预检时服务端读取 `UiRecordProjectConfig`，将配置快照写入 `report_json`。没有配置时运行一次现有兼容预检，写入 `verification_mode="legacy"` 和 `required_rounds=1`，但保存时只能得到 `draft`。重新选点和重启接口验证管理员权限、run/session/project 一致性和状态机合法性。

- [ ] **Step 5: 强化 active 判定**

`determine_recorded_case_status(preflight_status, steps, preflight_report=None)` 必须同时检查：

```python
report.get("verified_rounds") == 2
report["rounds"][0]["status"] == "passed"
report["rounds"][1]["status"] == "passed"
report["rounds"][1]["frozen"] is True
report.get("steps_snapshot_hash") == steps_snapshot_hash(steps)
all(step target/effect quality is not risk)
```

任何条件不满足均返回 `draft`。

- [ ] **Step 6: 更新契约、运行测试并提交**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_recording.py tests/test_ui_recording_preflight.py tests/test_route_contract.py
node .gitnexus/run.cjs detect-changes
git status --short
git diff --stat
git diff --check
git add app/routers/ui_record.py app/services/ui_recording_preflight.py tests/test_ui_recording.py tests/route_contract_expected.json
git commit -m "feat: expose verified recording repair APIs"
```

---

### Task 9: V3 录制配置、双轮进度和重新选点界面

**Files:**
- Create: `frontend/src/components/ui-cases/UiRecordingStartDialog.vue`
- Modify: `frontend/src/api/modules/uiCases.js:45-92`
- Modify: `frontend/src/components/ui-cases/UiRecordingPanel.vue`
- Modify: `frontend/src/components/ui-cases/UiRecordingPreflightPanel.vue`
- Modify: `frontend/src/views/UiCasesView.vue:57-143,697-978`
- Modify: `frontend/scripts/validate-v3-ui-cases-parity.mjs`

**Interfaces:**
- Consumes: 项目配置、可用脚本、环境列表、预检状态和修复 API。
- Produces: `saveUiRecordProjectConfig()`、`startUiRecordRepick()`、`restartUiRecordPreflight()`。
- Produces events: `repick`、`restart`、`save-draft`。

- [ ] **Step 1: 阅读 V3 迁移上下文并检查现有改动**

Read:

```text
docs/frontend-v2/README.md
docs/frontend-v2/handoff/CODEX-HANDOFF.md
docs/frontend-v2/handoff/CURRENT-TASK.md
docs/migration/frontend-v2-vue-migration-plan.md
```

Run `git status --short`，确认不覆盖并行 V3 改动。

- [ ] **Step 2: 先扩充 V3 契约校验并确认失败**

在 validator 中要求以下字符串和组件存在：

```javascript
for (const contract of [
  'getUiRecordProjectConfig',
  'saveUiRecordProjectConfig',
  'startUiRecordRepick',
  'restartUiRecordPreflight',
  'verified_rounds',
  'repair_required',
  'round_2_running',
]) {
  if (!apiModule.includes(contract) && !view.includes(contract) && !preflightPanel.includes(contract)) {
    failures.push(`missing verified recording contract ${contract}`)
  }
}
```

Run:

```powershell
node frontend/scripts/validate-v3-ui-cases-parity.mjs
```

Expected: FAIL，列出缺失契约。

- [ ] **Step 3: 新增 API 方法**

```javascript
export function getUiRecordProjectConfig(projectId) {
  return api(`/api/ui-record/projects/${projectId}/config`)
}

export function saveUiRecordProjectConfig(projectId, data) {
  return api(`/api/ui-record/projects/${projectId}/config`, { method: 'PUT', body: data })
}

export function startUiRecordRepick(runId, stepIndex) {
  return api(`/api/ui-record/preflights/${runId}/steps/${stepIndex}/repick/start`, { method: 'POST' })
}

export function restartUiRecordPreflight(runId) {
  return api(`/api/ui-record/preflights/${runId}/restart`, { method: 'POST' })
}
```

- [ ] **Step 4: 实现专用录制开始弹窗**

`UiRecordingStartDialog.vue` 负责：

- 项目改变时加载配置、可用数据脚本和当前项目环境。
- 必填：项目、用例名称、起始 URL、重置脚本、重置环境。
- 可选：测试账号、JSON 格式的非敏感重置参数。
- 提交时先保存项目配置，再发出 `start` 事件。
- JSON 错误、未选环境或敏感键在前端直接提示，但服务端仍做最终校验。

- [ ] **Step 5: 扩充预检面板**

状态文案固定映射：

```javascript
const STATUS_TEXT = {
  queued: '排队中',
  resetting: '正在重置测试数据',
  round_1_running: '第一轮修复验证',
  repair_required: '需要重新选择元素',
  repick_waiting: '请在验证浏览器中点击正确元素',
  repair_ready: '已重新选择，可从头验证',
  round_2_running: '第二轮冻结验证',
  passed: '双轮验证通过',
  failed: '验证失败',
}
```

只有 `repair_required` 显示“重新选点”，只有 `repair_ready` 显示“从头重新验证”。失败分类、动作预期结果、实际结果、截图和 URL 必须展示。

- [ ] **Step 6: 更新 UiCasesView 状态机和轮询清理**

保留 `recordPreflightGeneration` 和 `recordPreflightPollInFlight`。终态为 `passed/failed`，`repair_required/repick_waiting/repair_ready` 是暂停态：停止定时轮询，但不清空 `run_id`；点击重新选点或重启后恢复轮询。

`passed` 后调用 `finalizeRecordSave(runId)`；保存草稿继续传空 `preflight_run_id`。

- [ ] **Step 7: 运行前端校验和构建**

```powershell
node frontend/scripts/validate-v3-ui-cases-parity.mjs
Set-Location frontend
npm run build
Set-Location ..
```

Expected: 均 PASS；仅允许既有静态资源 warning。

- [ ] **Step 8: 检查并提交**

```powershell
node .gitnexus/run.cjs detect-changes
git status --short
git diff --stat
git diff --check
git add frontend/src/components/ui-cases/UiRecordingStartDialog.vue frontend/src/api/modules/uiCases.js frontend/src/components/ui-cases/UiRecordingPanel.vue frontend/src/components/ui-cases/UiRecordingPreflightPanel.vue frontend/src/views/UiCasesView.vue frontend/scripts/validate-v3-ui-cases-parity.mjs
git commit -m "feat: add verified recording workflow to V3"
```

---

### Task 10: 回归验证、代码审查和真实验收准备

**Files:**
- Modify only if failures prove necessary: files from Tasks 1-9
- Test: all UI recording/locator tests

**Interfaces:**
- Produces: 完整自动化验证证据。
- Produces: 真实 30 条业务流程验收清单，不启动浏览器。

- [ ] **Step 1: 运行相关测试集合**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ui_recording_config.py tests/test_ui_recording_reset.py tests/test_ui_target_profile.py tests/test_ui_action_effects.py tests/test_ui_target_resolver.py tests/test_ui_adapters.py tests/test_ui_recording_verification.py tests/test_ui_locator_engine.py tests/test_ui_locator_learning.py tests/test_ui_record_and_execution.py tests/test_ui_recording_preflight.py tests/test_ui_recording.py
```

Expected: PASS。

- [ ] **Step 2: 运行路由、权限和项目删除回归**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_route_contract.py tests/test_permissions.py -k "ui or project"
```

Expected: PASS。

- [ ] **Step 3: 运行完整测试**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/
```

Expected: 全部 PASS；只记录既有 collection warning。

- [ ] **Step 4: 运行前端验证**

```powershell
node frontend/scripts/validate-v3-ui-cases-parity.mjs
Set-Location frontend
npm run build
Set-Location ..
```

Expected: PASS。

- [ ] **Step 5: 请求独立代码审查**

使用 `superpowers:requesting-code-review` 检查：

- 是否存在错误点击路径。
- 第二轮是否真的冻结 AI、自愈和写回。
- 数据重置失败是否会阻止浏览器启动。
- 重新选点是否可能修改错误步骤。
- 敏感数据是否可能进入 report JSON。
- 所有线程、浏览器和轮询是否清理。

Critical/Important 问题必须修复并重跑最小测试。

- [ ] **Step 6: 最终 GitNexus 和 Git 检查**

```powershell
node .gitnexus/run.cjs detect-changes
git status --short
git diff --stat
git diff --check
```

Expected: 仅包含本功能文件；受影响流程符合录制、预检、执行器、项目删除和 V3 UI Cases 范围。

- [ ] **Step 7: 如有最终修复，回到对应任务提交**

若 Step 5 没有产生代码修改，不创建额外提交。若代码审查要求修复，回到问题所属 Task，使用该 Task 已列明的精确 `git add` 文件列表，提交信息使用 `fix: harden verified UI recording replay`，并重新执行该 Task 的测试和 Step 6 全部检查。

- [ ] **Step 8: 准备真实业务验收，不自动执行**

在最终汇报中请求用户提供或确认：

- 测试账号和有效登录态。
- 30 条业务流程清单。
- 每个项目的数据重置脚本和环境。
- 允许启动人工可见浏览器。

验收执行标准：每条流程先双轮验证，再独立干净执行 3 次；统计成功率不低于 97%、错误点击率为 0、危险动作无重复提交。

---

## Completion Criteria

- 新录制步骤包含 `target_profile`、`effect_profile` 和 `retry_policy`。
- 重复文本通过弹窗、表格行、表单或卡片上下文唯一化。
- 每轮浏览器开始前都执行项目配置的数据重置脚本。
- 第一轮失败可在保留现场的验证浏览器中重新选点。
- 重新选点后从数据重置和第一步重新执行。
- 第二轮使用全新上下文，冻结定位结果并禁用 AI 自愈和写回。
- 只有两轮通过、步骤快照一致且无高风险步骤才保存为 `active`。
- 旧格式用例仍走原执行路径。
- 相关 pytest、完整 pytest、V3 validator 和 production build 均通过。
- 根工作区已有未提交改动保持原样。
