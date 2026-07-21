# Data Agent Conversation Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make DeepSeek data-agent conversations preserve correct fields across follow-ups, resolve explicit Chinese instructions deterministically, persist failed analysis attempts, and keep execution progress visible without permanent loading overlays.

**Architecture:** Add a focused intent-state module that extracts a field-level patch from the latest message, merges it with prior evidence, and applies deterministic corrections to the model candidate before the existing goal normalizer runs. Keep the current in-memory session and execution APIs compatible, but persist each analysis turn as a sanitized `data_agent_analysis` test record and expose pending fields/revisions through existing session JSON.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, SQLite, vanilla JavaScript, pytest.

## Global Constraints

- Use `.venv\\Scripts\\python.exe` for every Python test command.
- Preserve all existing workspace changes; do not reset, delete, commit, or push.
- Do not change the database schema or data-script business interfaces.
- Keep user-visible data-agent field names and statuses in Simplified Chinese.
- A known operation may never be silently ignored.
- Ambiguous or contradictory instructions must not call mutating business tools.

---

### Task 1: Field-level intent state and deterministic latest-message patch

**Files:**
- Create: `app/services/data_factory_agent_intent.py`
- Modify: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: latest user message, previous JSON-compatible `intent_state`, and optional model candidate goal.
- Produces: `extract_intent_patch(message, message_index) -> dict`, `merge_intent_state(state, patch) -> dict`, `apply_intent_state(payload, state) -> dict`, and `build_pending_question(state) -> str`.

- [ ] **Step 1: Write failing tests for latest-message precedence and preservation**

```python
def test_follow_up_patch_preserves_existing_fields_and_updates_refund_scope():
    state = merge_intent_state({}, extract_intent_patch("订单到待拍下，全部数量退款", 0))
    updated = merge_intent_state(state, extract_intent_patch("国内运费也全部退，其他不变", 1))
    assert updated["resolved_fields"]["target_node"]["value"] == "pending_purchase"
    assert updated["resolved_fields"]["problem_refund_quantity"]["value"] == "all"
    assert updated["resolved_fields"]["problem_refund_freight"]["value"] == "all"
    assert updated["revisions"][-1]["message_index"] == 1

def test_explicit_all_goods_and_freight_refund_clears_option_ambiguity():
    state = merge_intent_state({}, extract_intent_patch("全部商品金额和国内运费这些都给退了", 0))
    assert state["resolved_fields"]["problem_refund_quantity"]["value"] == "all"
    assert state["resolved_fields"]["problem_refund_freight"]["value"] == "all"
    assert "problem_goods" not in state["pending_fields"]
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_data_factory_agent.py -v -k "follow_up_patch or all_goods_and_freight"`

Expected: FAIL because the new intent-state functions do not exist.

- [ ] **Step 3: Implement the JSON-compatible state helpers**

```python
def merge_intent_state(state: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(state) if isinstance(state, dict) else {}
    result.setdefault("resolved_fields", {})
    result.setdefault("pending_fields", {})
    result.setdefault("evidence", {})
    result.setdefault("revisions", [])
    for name, item in (patch.get("fields") or {}).items():
        previous = copy.deepcopy(result["resolved_fields"].get(name))
        result["resolved_fields"][name] = copy.deepcopy(item)
        result["evidence"][name] = copy.deepcopy(item.get("evidence") or {})
        result["pending_fields"].pop(name, None)
        if previous != item:
            result["revisions"].append({"field": name, "before": previous, "after": item, "message_index": patch["message_index"]})
    return result
```

Implement deterministic patterns for target state, item count, per-item quantity, goods-total/unit-price mode, all/half/fixed problem quantity, all/keep freight, explicit cancellation, and “其他不变”. Store value, Chinese source text, message index, and source=`deterministic` for each field.

- [ ] **Step 4: Apply state to a copied model payload**

`apply_intent_state` must override only fields with deterministic evidence, preserve the existing goal when the latest message says “其他不变”, and ensure that quantity refund plus freight refund both remain present in the `problem_goods` operation.

- [ ] **Step 5: Run the focused tests**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_data_factory_agent.py -v -k "follow_up_patch or all_goods_and_freight"`

Expected: PASS.

### Task 2: Incremental analysis integration and consolidated clarification

**Files:**
- Modify: `app/services/data_factory_agent.py:245-537, 1016-1440`
- Modify: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: Task 1 intent-state helpers.
- Produces: `_analyze_turn(db, messages, intent_state) -> (status, goal, question, next_state, trace)` while preserving `_analyze_messages(db, messages) -> (status, goal, question)` for existing callers/tests.

- [ ] **Step 1: Replace the old second-question regression test with desired behavior**

```python
def test_same_clarification_field_can_be_answered_more_than_once_without_blocking():
    session = AgentSessionState(id="s", user_id=1, project_id=1, env_id=1, status="clarifying")
    first = _bounded_clarification(session, "pricing", "请说明价格口径")
    second = _bounded_clarification(session, "pricing", "仍缺少价格口径")
    assert first["blocked"] is False
    assert second["blocked"] is False
    assert second["count"] == 2
```

Add a mocked two-turn test in which the first model answer correctly resolves target and quantity, the second model answer omits them, and the final contract still contains them while accepting the latest refund-freight correction.

- [ ] **Step 2: Run the tests and verify the old logic fails**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_data_factory_agent.py -v -k "clarification_field or two_turn"`

Expected: FAIL because `_bounded_clarification` blocks count 2 and full re-analysis discards fields.

- [ ] **Step 3: Add incremental prompt and merge pipeline**

The prompt must contain the existing resolved fields and ask for a latest-message patch with `set_fields`, `clear_fields`, `pending_fields`, `operation_updates`, and evidence. `_analyze_turn` must:

```python
patch = extract_intent_patch(messages[-1]["content"], len(messages) - 1)
state = merge_intent_state(intent_state, patch)
payload = call_local_model_json(config, _incremental_analysis_prompt(messages, state), timeout=120)
candidate = apply_intent_state(payload, state)
status, goal, question = _normalize_goal(candidate, messages)
state = reconcile_goal_state(state, goal, question, len(messages) - 1)
question = build_pending_question(state) or question
return status, goal, question, state, trace
```

Keep the initial model contract schema compatible and apply deterministic evidence after the model candidate. Never accept a model change without evidence from the latest message.

- [ ] **Step 4: Remove mechanical blocking and update session serialization**

`_bounded_clarification` continues counting for diagnostics but always returns `blocked=False`. Add `intent_state`, `pending_fields`, and the latest revisions to `_serialize_session`. `create_agent_session` and `add_agent_message` store `next_state`; they do not replace an existing correct goal with `{}` unless the user explicitly cancels the operation or the request becomes contradictory.

- [ ] **Step 5: Run conversation regression tests**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_data_factory_agent.py -v -k "clarification or follow_up or refund or intent_state"`

Expected: PASS.

### Task 3: Persist every analysis turn without a schema change

**Files:**
- Modify: `app/services/data_factory_agent.py:1352-1440, 1825-1881`
- Modify: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: `_analyze_turn` trace and existing `save_record`/`sanitize_observation`.
- Produces: `_save_analysis_record(db, session, trace, result) -> int | None` and session `analysis_record_ids`.

- [ ] **Step 1: Write failing persistence and redaction tests**

```python
def test_clarifying_turn_is_persisted_as_sanitized_analysis_record(monkeypatch, db, project, env):
    captured = []
    def fake_clarifying_turn(_db, messages, state):
        trace = {"message": messages[-1], "request_headers": {"Authorization": "secret"}}
        return "clarifying", {}, "请说明总价还是单价", state, trace
    monkeypatch.setattr(agent_service, "save_record", lambda *args, **kwargs: captured.append(kwargs) or SimpleNamespace(id=91))
    monkeypatch.setattr(agent_service, "_analyze_turn", fake_clarifying_turn)
    agent_service.create_agent_session(db, 1, project.id, env.id, "价格1000")
    assert captured[-1]["kind"] == "data_agent_analysis"
    saved_text = json.dumps(captured[-1], ensure_ascii=False).lower()
    assert "authorization" not in saved_text
    assert "api_key" not in saved_text
    assert "cookie" not in saved_text
```

Also assert that a second message creates a second analysis record and that record IDs are returned in session JSON even when confirmation never occurs.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_data_factory_agent.py -v -k "analysis_record or sanitized_analysis"`

Expected: FAIL because pre-confirmation analysis is not persisted.

- [ ] **Step 3: Implement safe analysis persistence**

Build a compact log containing session ID, turn index, sanitized message, model name, deterministic patch, model patch summary, rejected corrections, resolved/pending fields, status, question, and error category. Use `kind="data_agent_analysis"`, `script_key="data_factory_agent_analysis"`, and existing project/env IDs. Catch persistence errors, log them server-side, and never fail the user request because the audit write failed.

- [ ] **Step 4: Include analysis record IDs in the aggregate record**

Add the IDs to the final aggregate `child_record_ids`, preserving current tool record behavior.

- [ ] **Step 5: Run persistence tests**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_data_factory_agent.py -v -k "analysis_record or sanitized_analysis"`

Expected: PASS.

### Task 4: Visible, non-blocking execution progress

**Files:**
- Modify: `static/data-factory-agent.js:211-490`
- Modify: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: existing session `current_state.progress`, status, question, and events.
- Produces: mutually exclusive polling, local submit states, and a persistent progress panel that survives modal close/minimize.

- [ ] **Step 1: Add source-contract tests**

Assert the JavaScript contains a `pollInFlight` guard, clears submit loading in `finally`, no longer displays “同一信息最多追问一次”, and never calls `showModal()` from polling updates.

- [ ] **Step 2: Run source-contract tests and verify they fail**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_data_factory_agent.py -v -k "progress_ui or poll_guard"`

Expected: FAIL.

- [ ] **Step 3: Implement request-local loading and polling guard**

Use `let pollInFlight = false`. `refreshSession` exits when already running and resets the flag in `finally`. `sendMessage`, `confirmGoal`, and `createSession` disable only their initiating button, change its Chinese text, and restore it in `finally`. Polling calls `updateModal` only when the dialog is already open and always updates the background “继续查看任务” button.

- [ ] **Step 4: Keep progress readable**

Replace the obsolete one-question hint with “请直接补充或纠正，已确认内容会保留”. Render pending fields as one Chinese list and keep current operation, node, timestamp, and recent event visible. Closing/minimizing the dialog must not stop polling or restart the session.

- [ ] **Step 5: Run UI source tests and JavaScript syntax check**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_data_factory_agent.py -v -k "progress_ui or poll_guard"`

Run: `node --check static/data-factory-agent.js`

Expected: PASS and no syntax errors.

### Task 5: Full regression, live recognition matrix, and low-risk execution verification

**Files:**
- Modify: `tests/test_agent_accuracy.py`
- Modify: `tests/test_data_factory_agent.py`

**Interfaces:**
- Consumes: final incremental analysis pipeline.
- Produces: a no-report, exit-code-based live recognition matrix with at least 20 user-style cases and three rounds.

- [ ] **Step 1: Convert the live matrix into read-only recognition checks**

Remove absolute paths and report-file writes. Define at least 20 UTF-8 cases covering order states, total/unit price, item quantity, continuation, all/half refund, freight handling, combined refund, multiple operations, ambiguity, contradiction, and two-turn correction. Run each case three times and print only failed case summaries.

- [ ] **Step 2: Run the complete data-agent unit suite**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_data_factory_agent.py -v`

Expected: PASS.

- [ ] **Step 3: Run the live model matrix**

Run: `.venv\\Scripts\\python.exe tests/test_agent_accuracy.py`

Expected: all explicit cases produce complete contracts in all three rounds; ambiguous/contradictory cases remain clarifying; no business tools are called.

- [ ] **Step 4: Run low-risk real execution cases**

Use the platform’s configured Japanese test environment and customer `300001`. Execute only low-value cases for two-item goods total, order-to-pending-purchase plus all goods/freight refund, purchase-wait-pay without payment, and resume-with-other-data-unchanged. Validate actual order/problem-goods data through existing inspection tools. Do not delete test orders.

- [ ] **Step 5: Final engineering checks**

Run: `git diff --check`

Run: `git status --short`

Run: `git diff --stat`

Expected: no whitespace errors; only intended files are changed in addition to preserved pre-existing workspace changes.
