# 日本站系统回归拦截规则与费用证据 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让日本站 15 条问题产品拦截用例按真实业务阶段执行并可恢复，同时让 `JP-PAY-009/010` 以真实费用分项而非碰巧相等的总额通过。

**Architecture:** 新增统一执行协议、声明式 guard 场景目录和真实 guard 执行器；现有 `GuardRunner` 只负责分阶段判定，批次服务负责参数冻结、checkpoint 和恢复。支付侧新增独立费用证据模块，按稳定业务 ID 校验组件集合和 Decimal 公式。所有批次默认串行，不修改数据库结构。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2.0、SQLite、Decimal、pytest、原生 JavaScript。

## Global Constraints

- 测试命令必须使用 `.venv\Scripts\python.exe`。
- 不修改数据库结构、密钥、环境配置、启动脚本和其他数据脚本契约。
- 退款实际金额只取客户余额入账，不设计银行退款。
- 用例结果状态只使用 `passed`、`failed`、`blocked`、`waiting`；具体原因使用 `reason_code`。
- 批次默认串行，只有显式 `parallel_safe=true` 才允许并行；本计划不实现并行调度。
- OPTION 以 `option_id` 唯一识别，名称只用于展示。
- 当前工作区包含用户已有改动；不提交、不推送、不回退无关文件。

---

### Task 1: 统一执行协议与结构化业务差异

**Files:**
- Create: `app/system_regression/projects/japan/execution_contract.py`
- Modify: `app/system_regression/projects/japan/runner.py`
- Test: `tests/test_system_regression_execution_contract.py`

**Interfaces:**
- Produces: `ExecutionResultPayload`, `BusinessEffect`, `classify_business_diffs()`, `CaseRunResult.reason_code`。
- Consumes: 现有 `CaseRunResult` 调用方。

- [ ] **Step 1: 为固定状态、完整结果字段和未分类差异写失败测试**

```python
def test_execution_payload_rejects_non_contract_status():
    with pytest.raises(ValueError):
        ExecutionResultPayload(status="waiting_account", reason_code="account_required")

def test_unclassified_business_diff_prevents_pass():
    payload = ExecutionResultPayload(status="passed", business_diffs=[{"entity": "problem", "field": "amount", "before": "0", "after": "1"}])
    checked = classify_business_diffs(payload, allowed_rules=[])
    assert checked.status == "failed"
    assert checked.reason_code == "unclassified_business_effect"
```

- [ ] **Step 2: 运行测试并确认因模块或接口不存在而失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_execution_contract.py -v`

Expected: FAIL，原因是 `execution_contract` 或 `reason_code` 尚不存在。

- [ ] **Step 3: 实现最小协议**

```python
RESULT_STATUSES = frozenset({"passed", "failed", "blocked", "waiting"})

@dataclass
class ExecutionResultPayload:
    execution_id: str = ""
    batch_id: str = ""
    case_id: str = ""
    status: str = "blocked"
    reason_code: str = ""
    guard_kind: str = ""
    expected_stage: str = ""
    actual_stage: str = ""
    actor: dict[str, Any] = field(default_factory=dict)
    order_sn: str = ""
    problem_goods_id: str = ""
    purchase_record_ids: list[str] = field(default_factory=list)
    parameter_snapshot: dict[str, Any] = field(default_factory=dict)
    precondition_evidence: dict[str, Any] = field(default_factory=dict)
    attempted_actions: list[dict[str, Any]] = field(default_factory=list)
    response_evidence: list[dict[str, Any]] = field(default_factory=list)
    before_evidence: dict[str, Any] = field(default_factory=dict)
    after_evidence: dict[str, Any] = field(default_factory=dict)
    required_effects: list[dict[str, Any]] = field(default_factory=list)
    forbidden_effects: list[dict[str, Any]] = field(default_factory=list)
    allowed_effects: list[dict[str, Any]] = field(default_factory=list)
    unclassified_effects: list[dict[str, Any]] = field(default_factory=list)
    business_diffs: list[dict[str, Any]] = field(default_factory=list)
    failure_reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in RESULT_STATUSES:
            raise ValueError(f"无效结果状态：{self.status}")
```

`CaseRunResult` 增加 `reason_code`，保留 `error_code` 作为兼容镜像；新逻辑以 `reason_code` 为准。

- [ ] **Step 4: 运行协议测试和现有 runner 测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_execution_contract.py tests/test_system_regression_japan_runner.py -v`

Expected: PASS。

### Task 2: 参数冻结、execution_id、checkpoint 与重启恢复

**Files:**
- Modify: `app/services/system_regression/batch_service.py`
- Modify: `app/routers/system_regression.py`
- Modify: `static/system-regression.js`
- Test: `tests/test_system_regression_batch.py`
- Test: `tests/test_system_regression_account_resume.py`
- Test: `tests/test_system_regression_batch_api.py`

**Interfaces:**
- Produces: `checkpoint_run(db: Session, run_id: int, checkpoint: Mapping[str, Any])`、`recover_run_state(run: SystemRegressionCaseRun, probe: Callable) -> str`。
- Stores: `snapshot_json._execution` 与 `result_json.execution_state`。

- [ ] **Step 1: 写失败测试覆盖参数冻结、两个批次隔离和 execution_id 唯一性**

```python
def test_create_batch_freezes_per_case_parameters(db_session):
    suite, case = seed_suite_and_case(db_session, parameters={"pre_num": 1})
    batch = create_batch(db_session, suite_key=suite.suite_key, case_ids=[case.id], project_id=1, env_id=1, actor_id=1, context={"case_parameters": {str(case.id): {"pre_num": 2}}})
    run = db_session.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id).one()
    snapshot = json.loads(run.snapshot_json)
    assert snapshot["parameters"]["pre_num"] == 2
    assert snapshot["_execution"]["execution_id"]

def test_batches_do_not_share_execution_or_parameters(db_session):
    suite, case = seed_suite_and_case(db_session, parameters={"pre_num": 1})
    first = create_batch(db_session, suite_key=suite.suite_key, case_ids=[case.id], project_id=1, env_id=1, actor_id=1, context={"case_parameters": {str(case.id): {"pre_num": 2}}})
    second = create_batch(db_session, suite_key=suite.suite_key, case_ids=[case.id], project_id=1, env_id=1, actor_id=1, context={"case_parameters": {str(case.id): {"pre_num": 3}}})
    first_run_execution_id = json.loads(first.runs[0].snapshot_json)["_execution"]["execution_id"]
    second_run_execution_id = json.loads(second.runs[0].snapshot_json)["_execution"]["execution_id"]
    assert first_run_execution_id != second_run_execution_id
```

- [ ] **Step 2: 写失败测试覆盖 waiting 重启恢复和 running 超时三态**

```python
def test_restart_preserves_waiting_account_checkpoint(db_session):
    run.status = "waiting"
    run.error_code = "account_required"
    reconcile_interrupted_runs(db_session)
    assert run.status == "waiting"

@pytest.mark.parametrize("write_state,expected_status", [("confirmed_written", "pending"), ("confirmed_not_written", "pending"), ("indeterminate", "blocked")])
def test_restart_recovery_uses_write_state_probe(write_state, expected_status):
    run = interrupted_run(last_write={"state": "started", "idempotent": False})
    assert recover_run_state(run, lambda _run: write_state) == expected_status
```

- [ ] **Step 3: 运行测试并确认当前共享 context、`waiting_account` 和一律 unknown 的逻辑导致失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_batch.py tests/test_system_regression_account_resume.py tests/test_system_regression_batch_api.py -v`

Expected: FAIL 于新断言。

- [ ] **Step 4: 实现参数快照和 checkpoint**

创建 run 时生成 `uuid4().hex`，把目录参数与 `context.case_parameters[case_id]` 合并后写入 `snapshot_json`。每次动作前调用 `checkpoint_run` 持久化：

```python
{
  "execution_id": "49c13df1b9284eaab0fc0c26fc9c3845",
  "current_step": "guard.purchase_deal.before",
  "completed_actions": [],
  "order_sn": "20260730-300001-1",
  "problem_goods_id": "901",
  "purchase_record_ids": ["701"],
  "before_evidence": {"problem_status": 4, "balance_row_ids": [1001]},
  "last_write": {"state": "not_started", "idempotent": False}
}
```

序列化接口返回 `execution_id`、`reason_code` 和执行状态。前端把 `waiting` 且 `reason_code=account_required` 识别为账号恢复入口。

- [ ] **Step 5: 实现重启恢复三态，不重放不确定写请求**

`reconcile_interrupted_runs` 保留 `waiting`；对 `running` 根据 checkpoint 调用只读探针：`confirmed_written` 进入结果验证，`confirmed_not_written` 仅对显式安全动作回到 `pending`，`indeterminate` 转 `blocked / unknown_write_state`。

- [ ] **Step 6: 运行批次、API 和账号恢复测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_batch.py tests/test_system_regression_account_resume.py tests/test_system_regression_batch_api.py -v`

Expected: PASS。

### Task 3: 声明 15 条真实拦截场景

**Files:**
- Create: `app/system_regression/projects/japan/guard_scenarios.py`
- Modify: `app/system_regression/projects/japan/catalog.py`
- Modify: `app/system_regression/projects/japan/parameters.py`
- Test: `tests/test_system_regression_guard_scenarios.py`
- Test: `tests/test_system_regression_parameters.py`

**Interfaces:**
- Produces: `GuardScenarioSpec`, `guard_scenario(guard_kind)`。

- [ ] **Step 1: 写失败测试要求 15 个 guard_kind 都有唯一阶段、动作和参数 schema**

```python
def test_all_catalog_guards_have_executable_specs():
    guards = [case for case in japan_case_definitions() if case.runner_kind == "problem_guard"]
    assert len(guards) == 15
    for case in guards:
        spec = guard_scenario(case.parameters["guard_kind"])
        assert spec.expected_stage
        assert spec.target_action
        assert spec.precondition_builder
```

- [ ] **Step 2: 写失败测试确认候选不可见不能作为通过策略**

```python
def test_guard_specs_require_real_target_submission():
    assert all(spec.requires_target_call for spec in guard_scenarios())
```

- [ ] **Step 3: 运行并确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_guard_scenarios.py tests/test_system_regression_parameters.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 4: 实现场景目录和普通表单字段**

`GuardScenarioSpec` 明确 `expected_stage`、`precondition_builder`、`target_action`、错误码/HTTP/正则匹配、效果规则、可安全重试标记和 `parallel_safe=False`。15 条规则按提出、业务决策、OPTION、采购处理、预处理和配货直完阶段登记。

- [ ] **Step 5: 运行目录与参数测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_guard_scenarios.py tests/test_system_regression_catalog.py tests/test_system_regression_parameters.py -v`

Expected: PASS。

### Task 4: 真实 GuardExecutor 与分阶段错误判定

**Files:**
- Create: `app/system_regression/projects/japan/guard_executor.py`
- Modify: `app/system_regression/projects/japan/guard_runner.py`
- Modify: `app/routers/system_regression.py`
- Test: `tests/test_system_regression_guard_executor.py`
- Test: `tests/test_system_regression_japan_runner.py`

**Interfaces:**
- Consumes: `GuardScenarioSpec`、`ProblemGoodsGateway`、checkpoint callback。
- Produces: `GuardExecutor.execute(case, context) -> Mapping[str, Any]`。

- [ ] **Step 1: 写失败测试覆盖匹配优先级和阶段一致性**

```python
def test_guard_prefers_business_code_over_message():
    response = {"business_code": "PART_TAIL_UNPAID", "http_status": 400, "message": "其他文案"}
    assert match_guard_error(response, expected_codes={"PART_TAIL_UNPAID"}, expected_http={422}, patterns=[]) == "business_code"

def test_guard_uses_http_status_before_message_regex():
    response = {"http_status": 422, "message": "没有预期文案"}
    assert match_guard_error(response, expected_codes=set(), expected_http={422}, patterns=[r"尾款"]) == "http_status"
def test_same_error_at_precondition_stage_does_not_pass():
    result = runner.execute(case, {"actual_stage": "precondition", "error_message": expected_text})
    assert result.status == "failed"
    assert result.reason_code == "unexpected_guard_stage"
```

- [ ] **Step 2: 写失败测试覆盖服务端无规则、目标不可用和副作用分类**

```python
def test_successful_target_call_without_guard_is_backend_defect():
    assert result.status == "failed"
    assert result.reason_code == "backend_guard_missing"

def test_missing_target_endpoint_is_blocked():
    assert result.reason_code == "target_action_unavailable"

def test_guard_cannot_pass_with_unclassified_effects():
    result = evaluate_guard_effects(unclassified_effects=[{"entity": "bill", "field": "amount", "before": "0", "after": "10"}])
    assert result.status == "failed"
    assert result.reason_code == "unclassified_business_effect"
```

- [ ] **Step 3: 写失败测试覆盖超时实际已写入和历史数据误命中**

```python
def test_timeout_confirmed_written_continues_verification_without_replay():
    gateway = TimeoutGateway(probe_state="confirmed_written")
    result = execute_write_once(gateway.submit, gateway.probe, verify=lambda: {"passed": True})
    assert gateway.submit_calls == 1
    assert result["verification"]["passed"] is True

def test_evidence_query_requires_execution_business_ids():
    rows = [{"id": 1, "batch_no": "OLD", "problem_goods_id": 9}, {"id": 2, "batch_no": "NEW", "problem_goods_id": 10}]
    assert select_execution_rows(rows, batch_no="NEW", problem_goods_id="10") == [rows[1]]
```

- [ ] **Step 4: 运行测试并确认旧统一普通流程导致失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_guard_executor.py tests/test_system_regression_japan_runner.py -v`

Expected: FAIL 于新行为。

- [ ] **Step 5: 实现真实阶段执行**

`GuardExecutor` 为每条规则调用对应真实接口。前置构造失败使用 `precondition_capability_missing`；目标接口缺失使用 `target_action_unavailable`。每次写动作只执行一次，并保存业务码、结构化错误、HTTP 状态、响应文案、阶段和查询证据。

- [ ] **Step 6: 替换路由接线**

`_build_japan_runner` 注入 `GuardExecutor`，删除 `guard_gateway -> problem_runner.execute` 的统一普通流程接线。

- [ ] **Step 7: 运行 guard 和路由契约测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_guard_executor.py tests/test_system_regression_japan_runner.py tests/test_system_regression_integration.py -v`

Expected: PASS。

### Task 5: 大额退款普通账号＋部长账号复合续跑

**Files:**
- Modify: `app/system_regression/projects/japan/guard_executor.py`
- Modify: `app/services/system_regression/batch_service.py`
- Modify: `app/routers/system_regression.py`
- Test: `tests/test_system_regression_large_refund_guard.py`
- Test: `tests/test_system_regression_account_resume.py`

**Interfaces:**
- Produces: `execute_large_refund_guard(case: Mapping[str, Any], context: Mapping[str, Any])` 和 `resume_large_refund_with_minister(checkpoint: Mapping[str, Any], credentials: Mapping[str, str])`。

- [ ] **Step 1: 写失败测试验证普通账号必须拦截且余额无变化**

```python
def test_large_refund_first_step_requires_permission_error_and_no_balance_effect():
    result = executor.execute(case, context)
    assert result.status == "waiting"
    assert result.reason_code == "account_required"
    assert result.forbidden_effects == []
    assert result.attempted_actions[0]["actor"]["role"] == "normal"
```

- [ ] **Step 2: 写失败测试验证部长使用同一业务对象续跑**

```python
def test_minister_resume_reuses_same_problem_and_validates_balance_credit():
    resumed = resume_large_refund_with_minister(checkpoint, credentials)
    assert resumed.execution_id == checkpoint.execution_id
    assert resumed.problem_goods_id == checkpoint.problem_goods_id
    assert resumed.status == "passed"
    assert resumed.required_effects[0]["kind"] == "balance_credit"
```

- [ ] **Step 3: 运行并确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_large_refund_guard.py tests/test_system_regression_account_resume.py -v`

Expected: FAIL。

- [ ] **Step 4: 实现复合步骤和持久化续跑**

普通账号采购处理后保存权限错误、问题状态差异和余额差集；任何退款、余额变化或状态越级均失败。第一步通过后自动尝试默认部长账号，失败则 `waiting / account_required`。恢复时读取 checkpoint，只执行部长采购处理和最终余额轮询。

- [ ] **Step 5: 运行复合场景测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_large_refund_guard.py tests/test_system_regression_account_resume.py -v`

Expected: PASS。

### Task 6: 费用公式、组件集合与防碰巧一致

**Files:**
- Create: `app/system_regression/projects/japan/fee_evidence.py`
- Modify: `app/system_regression/projects/japan/payment_runner.py`
- Test: `tests/test_system_regression_fee_evidence.py`
- Test: `tests/test_system_regression_japan_runner.py`

**Interfaces:**
- Produces: `FeeComponent`, `FeeEvidenceContract`, `reconcile_fee_components()`。

- [ ] **Step 1: 写失败测试覆盖固定和百分比 OPTION 公式**

```python
def test_rate_option_uses_rate_times_option_quantity_times_goods_unit_price():
    component = rate_option_amount(rate="5", option_quantity=2, goods_unit_price_cny="10")
    assert component == Decimal("1.00")

def test_jpy_rounding_happens_after_cny_components_are_summed():
    components = [Decimal("0.03"), Decimal("0.03")]
    assert cny_components_to_jpy(components, Decimal("21.10")) == 1
```

- [ ] **Step 2: 写失败测试覆盖稳定 ID、重复和互相抵消**

```python
def test_duplicate_option_id_fails_even_when_total_matches():
    result = reconcile_fee_components(required=[fixed_option("7", "2.00")], actual=[fixed_option("7", "1.00"), fixed_option("7", "1.00")])
    assert result.reason_code == "duplicate_fee_component"

def test_same_total_with_offsetting_wrong_components_fails():
    result = reconcile_fee_components(required=[goods("10.00"), freight("5.00")], actual=[goods("11.00"), freight("4.00")])
    assert result.reason_code == "fee_component_amount_mismatch"

def test_option_name_match_without_option_id_fails():
    result = reconcile_fee_components(required=[fixed_option("7", "2.00")], actual=[{"kind": "option_fixed", "name": "检品", "amount_cny": "2.00"}])
    assert result.reason_code == "fee_component_identity_missing"
```

- [ ] **Step 3: 运行并确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_fee_evidence.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 4: 实现 Decimal 公式与组件分类**

人民币分项 `ROUND_HALF_UP` 到 2 位；总人民币乘报价汇率后统一 `ROUND_HALF_UP` 到整数日元；容差 1 日元。实现 `required_components`、`optional_components`、`forbidden_components`、`system_generated_components`，按组件 ID、类型和番号唯一匹配。

- [ ] **Step 5: 让 PAY-009/010 真正选择 OPTION 并保存订单详情证据**

从真实 OPTION 目录选择不同 `option_id` 的固定金额和百分比项，写入 `order_option_counts`；若环境没有所需类型则 `blocked / precondition_capability_missing`。`PAY-010` 同时构造单番国内运费和其他费用，并从报价/订单详情反查分项。

- [ ] **Step 6: 运行费用和支付 runner 测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_fee_evidence.py tests/test_system_regression_japan_runner.py tests/test_payment_amount_regression.py -v`

Expected: PASS。

### Task 7: 前端参数与统一证据展示

**Files:**
- Modify: `static/system-regression.js`
- Modify: `static/system-regression.css`
- Test: `tests/test_system_regression_frontend.py`

**Interfaces:**
- Consumes: 新的统一结果结构和 guard 参数 schema。

- [ ] **Step 1: 写失败测试覆盖普通表单、独立快照、全选和 waiting 恢复**

```python
def test_frontend_posts_per_case_parameter_snapshots():
    source = Path("static/system-regression.js").read_text(encoding="utf-8")
    assert "case_parameters" in source

def test_frontend_waiting_account_uses_status_and_reason_code():
    source = Path("static/system-regression.js").read_text(encoding="utf-8")
    assert 'run.status === "waiting"' in source
    assert 'run.reason_code === "account_required"' in source

def test_frontend_renders_structured_effect_groups():
    source = Path("static/system-regression.js").read_text(encoding="utf-8")
    for field in ("required_effects", "forbidden_effects", "allowed_effects", "unclassified_effects", "business_diffs"):
        assert field in source
```

- [ ] **Step 2: 运行并确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_frontend.py -v`

Expected: FAIL。

- [ ] **Step 3: 实现参数快照提交与证据展示**

批次请求提交 `context.case_parameters`；OPTION 行仍为普通表格输入，不显示 JSON。结果展开显示 execution、阶段、账号、响应证据、五类副作用和费用组件。保持单选、筛选全选、全部全选和批量串行。

- [ ] **Step 4: 运行前端契约测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_frontend.py tests/test_system_regression_batch_api.py -v`

Expected: PASS。

### Task 8: 集成、真实环境与完整验证

**Files:**
- Modify only if a failing test proves a scoped defect in files listed above.

**Interfaces:**
- Verifies all preceding tasks as one execution flow.

- [ ] **Step 1: 运行系统回归相关测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_execution_contract.py tests/test_system_regression_guard_scenarios.py tests/test_system_regression_guard_executor.py tests/test_system_regression_large_refund_guard.py tests/test_system_regression_fee_evidence.py tests/test_system_regression_batch.py tests/test_system_regression_account_resume.py tests/test_system_regression_batch_api.py tests/test_system_regression_japan_runner.py tests/test_system_regression_frontend.py tests/test_system_regression_integration.py -v`

Expected: PASS。

- [ ] **Step 2: 使用 `admin`、客户 `300001` 逐条执行 15 条 guard**

Expected: 每条记录都有真实目标接口响应和阶段证据；能力不足为 `blocked / precondition_capability_missing`，目标接口不可调用为 `blocked / target_action_unavailable`，后端规则缺失为 `failed / backend_guard_missing`。

- [ ] **Step 3: 真实执行 PAY-009/010**

Expected: 报价/订单详情能按 `option_id` 证明固定 OPTION、百分比 OPTION；PAY-010 还证明商品、单番国内运费和其他费用。总额与实际支付相差不超过 1 日元。

- [ ] **Step 4: 批量执行全部 77 条**

Expected: 默认串行、失败继续、参数与业务数据按 execution/batch 隔离；不能误命中历史记录。

- [ ] **Step 5: 运行完整测试**

Run: `.venv\Scripts\python.exe -m pytest tests/ -v`

Expected: PASS。

- [ ] **Step 6: 重启服务并确认恢复行为**

Expected: `waiting / account_required` 保持可恢复；`running` 根据 checkpoint 三态处理；不重新造单或重放不确定写动作。

- [ ] **Step 7: 最终变更检查**

Run: `git status --short`

Run: `git diff --stat`

Run: `node .gitnexus/run.cjs detect-changes --scope compare --base-ref master --repo zidonghuapingtai`

Expected: 只解释本次目标文件的新增影响；不暂存、不提交、不推送。
