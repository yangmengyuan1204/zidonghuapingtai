# Data Agent Controlled Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn confirmed, successfully verified data-agent tasks and user contract corrections into project-scoped candidate language rules that require regression checks and administrator approval before use.

**Architecture:** Persist sanitized samples, candidates, immutable rule versions, and review events in dedicated tables. Retrieve only approved project/global rules at runtime; hard-coded safety and contract rules always retain priority.

**Tech Stack:** Python 3.11, FastAPI 0.115, SQLAlchemy 2.0, SQLite, vanilla JavaScript, pytest.

## Global Constraints

- Complete and verify the core hit-rate plan before starting this plan.
- Run every Python test with `.venv\Scripts\python.exe`.
- Database changes are limited to dedicated learning tables created through existing SQLAlchemy/bootstrap patterns.
- Passwords, tokens, cookies, authorization headers, temporary permission credentials, and raw encrypted account payloads must never enter learning tables.
- A candidate rule cannot affect runtime behavior until an administrator approves a passing immutable version.
- Learned rules cannot override account permissions, amount thresholds, interface order, or fixed safety rules.

---

### Task 1: Add Dedicated Learning Persistence

**Files:**
- Modify: `app/models.py`
- Modify: `app/core/bootstrap.py`
- Test: `tests/test_data_agent_learning.py`

**Interfaces:**
- Produces: `DataAgentLearningSample`, `DataAgentRuleCandidate`, `DataAgentRuleVersion`, and `DataAgentRuleReview` ORM models.

- [ ] **Step 1: Write model creation and uniqueness tests**

```python
def test_data_agent_learning_tables_are_created():
    inspector = inspect(engine)
    assert {
        "data_agent_learning_sample",
        "data_agent_rule_candidate",
        "data_agent_rule_version",
        "data_agent_rule_review",
    } <= set(inspector.get_table_names())


def test_active_rule_scope_and_key_are_unique(db_session):
    db_session.add(DataAgentRuleVersion(
        candidate_id=1, project_id=1, scope="project", rule_key="quantity.each", version=1,
        rule_json="{}", status="active", create_time=datetime.now(),
    ))
    db_session.commit()
    db_session.add(DataAgentRuleVersion(
        candidate_id=2, project_id=1, scope="project", rule_key="quantity.each", version=1,
        rule_json="{}", status="active", create_time=datetime.now(),
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Run and verify missing models**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py -v -k "tables or unique"`

Expected: FAIL.

- [ ] **Step 3: Add the four focused ORM models**

```python
class DataAgentLearningSample(Base):
    __tablename__ = "data_agent_learning_sample"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    module_key = Column(String(80), nullable=False, index=True)
    intent_key = Column(String(120), nullable=False, index=True)
    instruction_text = Column(Text, nullable=False)
    model_candidate_json = Column(Text, nullable=False, default="{}")
    initial_contract_json = Column(Text, nullable=False, default="{}")
    final_contract_json = Column(Text, nullable=False, default="{}")
    corrections_json = Column(Text, nullable=False, default="[]")
    outcome = Column(String(32), nullable=False, index=True)
    verified = Column(Integer, nullable=False, default=0)
    fingerprint = Column(String(64), nullable=False, unique=True, index=True)
    create_time = Column(DateTime, nullable=False)


class DataAgentRuleCandidate(Base):
    __tablename__ = "data_agent_rule_candidate"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False, index=True)
    module_key = Column(String(80), nullable=False, index=True)
    intent_key = Column(String(120), nullable=False, index=True)
    rule_key = Column(String(160), nullable=False, index=True)
    proposal_json = Column(Text, nullable=False)
    source_sample_ids_json = Column(Text, nullable=False)
    occurrence_count = Column(Integer, nullable=False, default=0)
    regression_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="collecting", index=True)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=True)


class DataAgentRuleVersion(Base):
    __tablename__ = "data_agent_rule_version"
    __table_args__ = (
        UniqueConstraint("project_id", "scope", "rule_key", "version", name="uq_data_agent_rule_version"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False, index=True)
    project_id = Column(Integer, nullable=False, default=0, index=True)
    scope = Column(String(16), nullable=False, index=True)
    rule_key = Column(String(160), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    rule_json = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, index=True)
    create_time = Column(DateTime, nullable=False)
    activated_at = Column(DateTime, nullable=True)


class DataAgentRuleReview(Base):
    __tablename__ = "data_agent_rule_review"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False, index=True)
    rule_version_id = Column(Integer, nullable=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    action = Column(String(24), nullable=False)
    reason = Column(Text, nullable=False, default="")
    create_time = Column(DateTime, nullable=False)
```

- [ ] **Step 4: Use `Base.metadata.create_all` for new tables**

No `ALTER TABLE` entry is needed because all four tables are new. Add indexes only through model declarations and keep `init_app()` calling `Base.metadata.create_all(bind=engine)`.

- [ ] **Step 5: Run model tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py -v -k "tables or unique"`

Expected: PASS.

- [ ] **Step 6: Commit persistence models**

```powershell
git add app/models.py app/core/bootstrap.py tests/test_data_agent_learning.py
git commit -m "feat: add data agent learning persistence"
```

---

### Task 2: Capture Sanitized Success and Correction Samples

**Files:**
- Create: `app/services/data_agent_learning.py`
- Modify: `app/services/data_factory_agent.py:2060-2110,2491-2605`
- Test: `tests/test_data_agent_learning.py`

**Interfaces:**
- Consumes: `capture_learning_sample(db, session, final_status, result)`.
- Produces: one deduplicated sanitized sample per completed session.

- [ ] **Step 1: Write success, failure, and redaction tests**

```python
def test_only_confirmed_verified_success_becomes_positive_sample(db_session):
    sample = capture_learning_sample(db_session, _successful_session(), "succeeded", {"verification": {"passed": True}})
    assert sample.outcome == "success"
    assert sample.verified == 1


def test_learning_sample_redacts_sensitive_values(db_session):
    session = _successful_session()
    session.messages[0]["content"] = "password=secret token=abc 帮我造订单"
    sample = capture_learning_sample(db_session, session, "succeeded", {"verification": {"passed": True}})
    serialized = " ".join((sample.instruction_text, sample.model_candidate_json, sample.final_contract_json))
    assert "secret" not in serialized
    assert "token=abc" not in serialized
```

- [ ] **Step 2: Run and verify missing service**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py -v -k "positive_sample or redacts"`

Expected: FAIL.

- [ ] **Step 3: Implement recursive redaction and stable fingerprinting**

```python
SENSITIVE_KEYS = {"password", "passwd", "pwd", "token", "cookie", "authorization", "secret", "api_key"}


def sanitize_learning_value(value: Any, key: str = "") -> Any:
    lowered = str(key).lower()
    if lowered in SENSITIVE_KEYS or lowered.endswith("_password") or lowered.endswith("_token"):
        return "***"
    if isinstance(value, dict):
        return {str(k): sanitize_learning_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_learning_value(item, key) for item in value[:100]]
    if isinstance(value, str):
        text = re.sub(r"(?i)(password|passwd|pwd|token|secret|authorization|cookie)\s*[:=]\s*[^\s,;]+", r"\1=***", value)
        return text[:4000]
    return value


def sample_fingerprint(project_id: int, instruction: str, final_contract: Dict[str, Any]) -> str:
    raw = json.dumps([project_id, instruction, final_contract], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Capture corrections and outcome without treating failures as truth**

In `update_agent_goal`, capture only the fields the user submitted and store sanitized before/after values in the existing event:

```python
before_values = {
    key: copy.deepcopy(goal.get("target_node") if key == "target_node" else variables.get(key))
    for key, value in updates.items()
    if value is not None
}
# Apply the existing validated updates and rebuild the contract.
after_values = {
    key: copy.deepcopy(goal.get("target_node") if key == "target_node" else variables.get(key))
    for key in before_values
}
correction_items = [
    {"field": key, "before": before_values[key], "after": after_values[key]}
    for key in before_values
    if before_values[key] != after_values[key]
]
session.events.append(
    _event("goal_updated", "用户直接编辑了目标数据", corrections=correction_items)
)
```

Then classify the finalized session:

```python
verified = bool(final_status == "succeeded" and (result.get("verification") or {}).get("passed"))
outcome = "success" if verified else "failure"
corrections = [
    item
    for event in session.events
    if event.get("kind") == "goal_updated"
    for item in event.get("corrections") or []
]
corrections.extend(
    {
        "field": item.get("field"),
        "before": (item.get("before") or {}).get("value") if isinstance(item.get("before"), dict) else item.get("before"),
        "after": (item.get("after") or {}).get("value") if isinstance(item.get("after"), dict) else item.get("after"),
        "source": "clarification",
    }
    for item in session.intent_state.get("revisions") or []
    if item.get("before") is not None and item.get("before") != item.get("after")
)
```

Persist failure samples with `verified=0`; candidate generation queries only `outcome="success"`, `verified=1`, and non-empty corrections.

- [ ] **Step 5: Call capture after the aggregate execution record is saved**

```python
try:
    capture_learning_sample(db, session, final_status, aggregate)
except Exception as exc:
    logger.error(
        "数据智能体学习样本保存失败 session_id=%s error=%s",
        session.id,
        type(exc).__name__,
    )
```

This runs after the aggregate execution record is saved, so learning persistence cannot change the task result.

- [ ] **Step 6: Run learning and agent tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py tests/test_data_factory_agent.py -q`

Expected: PASS.

- [ ] **Step 7: Commit sample capture**

```powershell
git add app/services/data_agent_learning.py app/services/data_factory_agent.py tests/test_data_agent_learning.py
git commit -m "feat: capture verified data agent learning samples"
```

---

### Task 3: Generate Candidates After Three Matching Corrections

**Files:**
- Modify: `app/services/data_agent_learning.py`
- Test: `tests/test_data_agent_learning.py`

**Interfaces:**
- Consumes: `refresh_rule_candidate(db, project_id, module_key, intent_key, rule_key)`.
- Produces: a `collecting` candidate below 3 occurrences or `pending_regression` candidate at 3.

- [ ] **Step 1: Write threshold and forbidden-field tests**

```python
def test_candidate_requires_three_matching_corrections(db_session):
    for index in range(2):
        add_correction_sample(db_session, index, rule_key="quantity.each")
    assert refresh_rule_candidate(db_session, 1, "order", "create", "quantity.each").status == "collecting"
    add_correction_sample(db_session, 3, rule_key="quantity.each")
    assert refresh_rule_candidate(db_session, 1, "order", "create", "quantity.each").status == "pending_regression"


@pytest.mark.parametrize("field", ["allow_large_refund", "backend_password", "permission_threshold", "api_path"])
def test_candidate_rejects_forbidden_fields(field):
    with pytest.raises(ValueError):
        validate_candidate_rule({"set_fields": {field: True}})
```

- [ ] **Step 2: Run and verify failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py -v -k "requires_three or forbidden_fields"`

Expected: FAIL.

- [ ] **Step 3: Define the allowlist and candidate schema**

```python
LEARNABLE_FIELDS = {
    "target_node", "order_shop_count", "order_per_shop", "order_item_num",
    "pricing_mode", "problem_scope", "problem_refund_quantity",
    "problem_refund_freight", "keyword", "shop_type", "order_payment_mode",
}


def validate_candidate_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    set_fields = dict(rule.get("set_fields") or {})
    forbidden = sorted(set(set_fields) - LEARNABLE_FIELDS)
    if forbidden:
        raise ValueError(f"候选规则包含不可学习字段：{', '.join(forbidden)}")
    return {"match_phrases": list(rule.get("match_phrases") or []), "set_fields": set_fields}
```

- [ ] **Step 4: Aggregate exact correction signatures**

```python
samples = (
    db.query(DataAgentLearningSample)
    .filter(
        DataAgentLearningSample.project_id == project_id,
        DataAgentLearningSample.module_key == module_key,
        DataAgentLearningSample.intent_key == intent_key,
        DataAgentLearningSample.outcome == "success",
        DataAgentLearningSample.verified == 1,
    )
    .order_by(DataAgentLearningSample.id.asc())
    .all()
)
matching_ids = [
    row.id for row in samples
    if any(item.get("field") == rule_key for item in _json_load(row.corrections_json, []))
]
candidate.occurrence_count = len(matching_ids)
candidate.source_sample_ids_json = json.dumps(matching_ids, ensure_ascii=False)
candidate.status = "pending_regression" if len(matching_ids) >= 3 else "collecting"
```

- [ ] **Step 5: Run candidate tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py -v -k "candidate or forbidden_fields"`

Expected: PASS.

- [ ] **Step 6: Commit candidate generation**

```powershell
git add app/services/data_agent_learning.py tests/test_data_agent_learning.py
git commit -m "feat: propose data agent rules from repeated corrections"
```

---

### Task 4: Gate Candidates with Regression and Conflict Checks

**Files:**
- Modify: `app/services/data_agent_learning.py`
- Modify: `scripts/evaluate_data_agent_hit_rate.py`
- Test: `tests/test_data_agent_learning.py`

**Interfaces:**
- Consumes: `run_candidate_regression(candidate_id)`.
- Produces: stored pass/fail counts and `pending_review` only on a clean regression.

- [ ] **Step 1: Write pass/fail transition tests**

```python
def test_candidate_enters_review_only_after_clean_regression(db_session, monkeypatch):
    candidate = candidate_with_three_samples(db_session)
    monkeypatch.setattr(learning, "evaluate_candidate", lambda *a: {"passed": 80, "failed": 0, "conflicts": 0})
    updated = run_candidate_regression(db_session, candidate.id)
    assert updated.status == "pending_review"


def test_candidate_stays_blocked_when_regression_changes_existing_contract(db_session, monkeypatch):
    candidate = candidate_with_three_samples(db_session)
    monkeypatch.setattr(learning, "evaluate_candidate", lambda *a: {"passed": 79, "failed": 1, "conflicts": 1})
    assert run_candidate_regression(db_session, candidate.id).status == "regression_failed"
```

- [ ] **Step 2: Run and verify failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py -v -k "clean_regression or stays_blocked"`

Expected: FAIL.

- [ ] **Step 3: Evaluate the candidate as an overlay, never a source edit**

```python
def regression_passed(summary: Dict[str, int]) -> bool:
    return int(summary.get("failed") or 0) == 0 and int(summary.get("conflicts") or 0) == 0


def run_candidate_regression(db: Session, candidate_id: int) -> DataAgentRuleCandidate:
    candidate = db.get(DataAgentRuleCandidate, candidate_id)
    if not candidate or candidate.status != "pending_regression":
        raise ValueError("候选规则当前不可执行回归")
    summary = evaluate_candidate(candidate)
    candidate.regression_json = json.dumps(sanitize_learning_value(summary), ensure_ascii=False)
    candidate.status = "pending_review" if regression_passed(summary) else "regression_failed"
    candidate.update_time = datetime.now()
    db.commit()
    db.refresh(candidate)
    return candidate
```

Load the fixed hit-rate fixture and all historical verified samples for the same project. Apply the candidate in memory to the contract compiler and compare expected keys. Store only sanitized case IDs and counts in `regression_json`.

- [ ] **Step 4: Run learning and hit-rate tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py tests/test_data_agent_hit_rate.py -q`

Expected: PASS.

- [ ] **Step 5: Commit regression gate**

```powershell
git add app/services/data_agent_learning.py scripts/evaluate_data_agent_hit_rate.py tests/test_data_agent_learning.py
git commit -m "feat: regression gate learned data agent rules"
```

---

### Task 5: Add Administrator Review, Scope Promotion, and Rollback APIs

**Files:**
- Modify: `app/agent_schemas.py`
- Modify: `app/routers/data_factory_agent.py`
- Modify: `app/services/data_agent_learning.py`
- Test: `tests/test_data_agent_learning.py`
- Modify: `tests/route_contract_expected.json`

**Interfaces:**
- Produces: list/detail/approve/reject/promote/disable/rollback endpoints under `/api/data-scripts/agent/learning`.

- [ ] **Step 1: Write admin-only lifecycle tests**

```python
def test_candidate_approval_creates_immutable_project_rule(client, admin_headers, pending_candidate):
    response = client.post(
        f"/api/data-scripts/agent/learning/candidates/{pending_candidate.id}/approve",
        headers=admin_headers,
        json={"reason": "三条纠正一致且回归通过"},
    )
    assert response.status_code == 200
    assert response.json()["scope"] == "project"
    assert response.json()["status"] == "active"


def test_non_admin_cannot_promote_rule(client, user_headers, active_rule):
    response = client.post(
        f"/api/data-scripts/agent/learning/rules/{active_rule.id}/promote",
        headers=user_headers,
        json={"reason": "通用规则"},
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Run and verify missing routes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py -v -k "approval or promote_rule"`

Expected: FAIL with 404.

- [ ] **Step 3: Add review request schemas**

```python
class DataAgentRuleReviewRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class DataAgentRuleRollbackRequest(BaseModel):
    target_version_id: int
    reason: str = Field(min_length=1, max_length=1000)
```

- [ ] **Step 4: Implement immutable version transitions**

```python
def activate_rule_version(db, candidate, user_id, reason, scope="project"):
    project_id = candidate.project_id if scope == "project" else 0
    previous = (
        db.query(DataAgentRuleVersion)
        .filter_by(project_id=project_id, scope=scope, rule_key=candidate.rule_key, status="active")
        .all()
    )
    for item in previous:
        item.status = "superseded"
    next_version = max([item.version for item in previous] or [0]) + 1
    row = DataAgentRuleVersion(
        candidate_id=candidate.id,
        project_id=project_id,
        scope=scope,
        rule_key=candidate.rule_key,
        version=next_version,
        rule_json=candidate.proposal_json,
        status="active",
        create_time=datetime.now(),
        activated_at=datetime.now(),
    )
    db.add(row)
    db.flush()
    db.add(DataAgentRuleReview(
        candidate_id=candidate.id, rule_version_id=row.id, user_id=user_id,
        action="approve" if scope == "project" else "promote", reason=reason,
        create_time=datetime.now(),
    ))
    db.commit()
    db.refresh(row)
    return row
```

Disable changes status only. Rollback calls the same transactional activation path with `rule_json` copied from the selected historical version; it never deletes versions.

Use `project_id=0` for global versions so SQLite uniqueness works consistently. Project versions use their real positive project ID. Activating a version first marks the previous active version for the same `(project_id, scope, rule_key)` as `superseded` in the same transaction.

- [ ] **Step 5: Run lifecycle and route-contract tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py tests/test_route_contracts.py -q`

Expected: PASS.

- [ ] **Step 6: Commit review APIs**

```powershell
git add app/agent_schemas.py app/routers/data_factory_agent.py app/services/data_agent_learning.py tests/test_data_agent_learning.py tests/route_contract_expected.json
git commit -m "feat: review and version learned data agent rules"
```

---

### Task 6: Retrieve Approved Project and Global Knowledge

**Files:**
- Modify: `app/services/data_agent_learning.py`
- Modify: `app/services/data_factory_agent.py`
- Modify: `app/services/data_factory_agent_prompts.py`
- Test: `tests/test_data_agent_learning.py`

**Interfaces:**
- Consumes: `learning_context(db, project_id, module_key, instruction, limit=5)`.
- Produces: approved rules and up to five sanitized similar success examples.

- [ ] **Step 1: Write scope and safety priority tests**

```python
def test_project_rules_precede_global_rules_but_not_hard_rules(db_session):
    context = learning_context(db_session, 1, "order", "做到待付款", limit=5)
    assert [item["scope"] for item in context["rules"]][:2] == ["project", "global"]
    final = apply_learning_context({"target_node": "order_offered"}, context, hard_fields={"target_node"})
    assert final["target_node"] == "order_offered"


def test_learning_context_returns_at_most_five_examples(db_session):
    seed_verified_samples(db_session, count=10)
    assert len(learning_context(db_session, 1, "order", "造订单", limit=5)["examples"]) == 5
```

- [ ] **Step 2: Run and verify failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py -v -k "precede_global or at_most_five"`

Expected: FAIL.

- [ ] **Step 3: Implement deterministic token-overlap retrieval**

```python
def _bigrams(value: str) -> set[str]:
    text = re.sub(r"[\s，。；：、,.!?！？]+", "", str(value or "").lower())
    return {text[index:index + 2] for index in range(max(0, len(text) - 1))}


def _similarity(left: str, right: str) -> float:
    a, b = _bigrams(left), _bigrams(right)
    return len(a & b) / len(a | b) if a and b else 0.0
```

Filter by current project or global scope, active status, and matching module; sort by project scope first and similarity second. Return serialized dictionaries, never raw database models.

- [ ] **Step 4: Inject a bounded learning context into analysis**

```python
learning = learning_context(db, project_id, infer_module(messages), messages[-1]["content"], limit=5)
prompt = build_analysis_prompt(messages, intent_state, learning_context=learning)
```

The prompt includes only approved rule JSON and sanitized example instruction/final-contract pairs. The contract compiler applies hard rules after any learned candidate.

- [ ] **Step 5: Run learning, contract, and agent tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py tests/test_data_factory_agent_contract.py tests/test_data_factory_agent.py -q`

Expected: PASS.

- [ ] **Step 6: Commit runtime retrieval**

```powershell
git add app/services/data_agent_learning.py app/services/data_factory_agent.py app/services/data_factory_agent_prompts.py tests/test_data_agent_learning.py
git commit -m "feat: retrieve approved data agent learning context"
```

---

### Task 7: Add the Learning Center UI

**Files:**
- Modify: `static/data-factory-agent.js`
- Test: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: learning list and lifecycle APIs.
- Produces: administrator-only sample, candidate, regression, approval, promotion, disable, and rollback views.

- [ ] **Step 1: Add static UI contract assertions**

```python
def test_data_agent_learning_center_has_required_controls():
    source = Path("static/data-factory-agent.js").read_text(encoding="utf-8")
    for token in (
        "dataAgentLearningCenter", "learning/candidates", "approveLearningRule",
        "promoteLearningRule", "rollbackLearningRule", "回归结果", "来源样本",
    ):
        assert token in source
```

- [ ] **Step 2: Run and verify missing controls**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -v -k "learning_center"`

Expected: FAIL.

- [ ] **Step 3: Render a focused learning-center modal**

```javascript
async function openDataAgentLearningCenter() {
  const data = await options.api("/api/data-scripts/agent/learning/overview");
  modalEl.innerHTML = `<div class="modal-head"><h3>数据智能体学习中心</h3></div>
    <div class="modal-body" id="dataAgentLearningCenter">
      ${renderLearningCandidates(data.candidates || [])}
      ${renderLearningRules(data.rules || [])}
    </div>`;
  if (!modalEl.open) modalEl.showModal();
}

async function approveLearningRule(candidateId, reason) {
  if (!String(reason || "").trim()) throw new Error("请填写审核原因");
  return options.api(`/api/data-scripts/agent/learning/candidates/${candidateId}/approve`, {
    method: "POST", body: { reason: String(reason).trim() },
  });
}
```

Candidate detail shows occurrence count, sanitized sample summaries, affected fields, regression counts, scope, and approve/reject buttons. Active rule detail shows versions and promote/disable/rollback actions.

- [ ] **Step 4: Keep all learning actions admin-only**

Render the entry only when the existing user context is admin; APIs remain protected by `require_admin` regardless of frontend visibility.

- [ ] **Step 5: Run frontend syntax and UI contract tests**

Run: `node --check static/data-factory-agent.js`

Expected: exit 0.

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -q -k "learning_center or progress_ui"`

Expected: PASS.

- [ ] **Step 6: Commit learning UI**

```powershell
git add static/data-factory-agent.js tests/test_data_factory_agent.py
git commit -m "feat: add data agent learning center"
```

---

### Task 8: Verify the Controlled Learning Loop

**Files:**
- No source changes expected.

**Interfaces:**
- Consumes: all controlled-learning tasks.
- Produces: a verified growth loop ready for capability metadata.

- [ ] **Step 1: Run focused learning and agent suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_agent_learning.py tests/test_data_agent_hit_rate.py tests/test_data_factory_agent_contract.py tests/test_data_factory_agent.py -q`

Expected: PASS.

- [ ] **Step 2: Run the full project suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`

Expected: PASS.

- [ ] **Step 3: Inspect sensitive-data and file scope**

Run: `git status --short` and `git diff --stat`

Expected: no database file, log, report, temporary credential, or generated evaluation output is staged or untracked by this work.
