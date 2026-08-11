# System Regression Real Regression Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复日本站系统回归真实执行中的分批尾款、配送单金额/超时、问题产品前置单和重启残留状态问题。

**Architecture:** 金额证据修复限定在 `payment_amount_regression` 执行器；问题产品流程修复限定在日本站 `ProblemGoodsRunner`；启动恢复复用现有批次服务函数。共享支付脚本和问题产品脚本的对外契约保持不变。

**Tech Stack:** Python 3.11、FastAPI lifespan、SQLAlchemy 2.0、pytest、Decimal、现有数据脚本 HTTP 客户端。

## Global Constraints

- 测试必须使用 `.venv\Scripts\python.exe`。
- 退款实际证据只允许客户余额流水，不允许银行退款。
- 禁止使用支付请求参数冒充实际金额。
- 保留所有生成业务数据并使用系统回归批次备注追踪。
- 不修改数据库结构、密钥、环境配置或启动脚本。
- 不提交、不推送；保留工作区全部既有改动。

---

### Task 1: 分批尾款响应取证

**Files:**
- Modify: `app/data_scripts/payment_amount_regression/runner.py:407-452`
- Test: `tests/test_payment_amount_regression.py`

**Interfaces:**
- Consumes: `LivePaymentRegressionExecutor._tail_summary(payload) -> dict[str, Any]`
- Produces: `LivePaymentRegressionExecutor._tail_expected_amount(payload) -> str`

- [ ] **Step 1: 写失败测试**

```python
def test_tail_expected_amount_reads_flattened_response_amount():
    payload = {"order_tail_payment": {"data.pay_amount": 422, "request": {"pay_amount": "999"}}}
    assert LivePaymentRegressionExecutor._tail_expected_amount(payload) == "422"
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_payment_amount_regression.py::test_tail_expected_amount_reads_flattened_response_amount -v`

Expected: FAIL，当前类没有 `_tail_expected_amount`。

- [ ] **Step 3: 实现最小响应解析**

```python
@staticmethod
def _tail_expected_amount(payload: Any) -> str:
    tail = LivePaymentRegressionExecutor._tail_summary(payload)
    return str(
        tail.get("pay_amount")
        or tail.get("data.pay_amount")
        or LivePaymentRegressionExecutor._recursive_amount(
            tail.get("pay_data") or {},
            ("pay_amount_jpy", "total_amount", "pay_amount"),
        )
        or ""
    )
```

- [ ] **Step 4: 在 `_execute_part_pay` 使用新解析器并运行定点测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_payment_amount_regression.py -v`

Expected: PASS。

### Task 2: 配送单币种与日元预期证据

**Files:**
- Modify: `app/data_scripts/payment_amount_regression/runner.py:345-353,486-508`
- Test: `tests/test_payment_amount_regression.py`

**Interfaces:**
- Consumes: 配送单详情 `data.porder_amount.pay_amount/pay_amount_jpy/exchange_rate`
- Produces: `LivePaymentRegressionExecutor._porder_expected_evidence(variables, porder_sn) -> MoneyEvidence`

- [ ] **Step 1: 写失败测试**

```python
def test_porder_expected_evidence_converts_cny_to_jpy(monkeypatch):
    executor = LivePaymentRegressionExecutor(object(), {})
    payload = {"code": 0, "data": {"porder_amount": {
        "pay_amount": "775.02", "pay_amount_jpy": "16353", "exchange_rate": "21.10"
    }}}
    monkeypatch.setattr(executor, "_client", lambda variables: StubClient(payload))
    evidence = executor._porder_expected_evidence({}, "P1")
    assert evidence.currency == "CNY"
    assert evidence.amount == Decimal("775.02")
    assert evidence.exchange_rate == Decimal("21.10")
    assert to_jpy(evidence.amount, evidence.currency, evidence.exchange_rate) == 16353
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_payment_amount_regression.py::test_porder_expected_evidence_converts_cny_to_jpy -v`

Expected: FAIL，当前实现返回字符串并按 JPY 对账。

- [ ] **Step 3: 实现详情证据和交叉校验**

```python
def _porder_expected_evidence(self, variables: dict[str, Any], porder_sn: str) -> MoneyEvidence:
    payload = self._client(variables).post_form(
        self._scripts()._api_path(variables, "client_porder_detail", "/client/porder.porderDetail"),
        {"porder_sn": porder_sn},
    )
    amount_data = ((payload.get("data") or {}).get("porder_amount") or {})
    evidence = MoneyEvidence(
        "porder_pay_detail",
        _decimal(amount_data.get("pay_amount"), "配送单应付金额"),
        "CNY",
        "debit",
        exchange_rate=_decimal(amount_data.get("exchange_rate"), "配送单汇率"),
        reference=porder_sn,
        raw=dict(amount_data),
    )
    if to_jpy(evidence.amount, evidence.currency, evidence.exchange_rate) != int(amount_data["pay_amount_jpy"]):
        raise ScenarioBlocked("配送单人民币金额、汇率与日元应付金额不一致")
    return evidence
```

- [ ] **Step 4: 调整 `_execute_porder` 直接使用 `MoneyEvidence` 并运行定点测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_payment_amount_regression.py -v`

Expected: PASS。

### Task 3: 配送单银行支付等待上限

**Files:**
- Modify: `app/data_scripts/payment_amount_regression/runner.py:486-508`
- Test: `tests/test_payment_amount_regression.py`

**Interfaces:**
- Produces: `_bounded_porder_payment_variables(variables) -> dict[str, Any]`
- Default values: `timeout=8`、`finance_confirm_retries=2`、`finance_confirm_initial_delay=1`、`finance_confirm_delay=1`

- [ ] **Step 1: 写失败测试，覆盖默认值和用户覆盖值**

```python
def test_porder_bank_defaults_are_bounded_but_explicit_values_win():
    executor = LivePaymentRegressionExecutor(type("Env", (), {"timeout": 25})(), {})
    assert executor._bounded_porder_payment_variables({})["timeout"] == 8
    assert executor._bounded_porder_payment_variables({"timeout": 12})["timeout"] == 12
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_payment_amount_regression.py::test_porder_bank_defaults_are_bounded_but_explicit_values_win -v`

Expected: FAIL，当前没有回归专用等待边界。

- [ ] **Step 3: 实现边界变量并仅在配送单银行场景合并**

```python
def _bounded_porder_payment_variables(self, variables: dict[str, Any]) -> dict[str, Any]:
    values = dict(variables)
    values.setdefault("timeout", 8)
    values.setdefault("finance_confirm_retries", 2)
    values.setdefault("finance_confirm_initial_delay", 1)
    values.setdefault("finance_confirm_delay", 1)
    return values
```

- [ ] **Step 4: 运行支付回归测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_payment_amount_regression.py tests/test_system_regression_japan_runner.py -v`

Expected: PASS。

### Task 4: 问题产品前置订单停点与恢复

**Files:**
- Modify: `app/system_regression/projects/japan/problem_runner.py:192-250`
- Test: `tests/test_system_regression_japan_runner.py`

**Interfaces:**
- Consumes: `run_full_flow_script(...)` 和 `run_resume_order_flow_script(...)`
- Produces: `_prepare_candidate(...)` 在 `checking_started` 返回未上架且 `can_submit=true` 的采购明细上下文

- [ ] **Step 1: 写失败测试，断言前置停点为 `purchase_paid`**

```python
def test_problem_candidate_stops_before_storage(monkeypatch):
    captured = {}
    monkeypatch.setattr(data_scripts, "run_full_flow_script", lambda env, variables: (
        captured.update(variables) or True, "", "", {"order_sn": "O1"}
    ))
    # inspect_problem_goods 返回 possible_num=3、storage_num=0、can_submit=true
    assert captured["stop_after_node"] == "checking_started"
```

- [ ] **Step 2: 写失败测试，已创建订单发生状态竞争时改用恢复流程**

```python
def test_problem_candidate_resumes_created_order_after_quote_state_race(monkeypatch):
    full = (False, "", "", {"order_sn": "O1", "reason": "订单翻译提交失败"})
    resumed = (True, "", "", {"order_sn": "O1", "stopped_after_node": "checking_started"})
    # 断言恢复调用携带 order_sn=O1，且完整流程只调用一次
```

- [ ] **Step 3: 运行两个测试并确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_japan_runner.py -k "candidate and (storage or resumes)" -v`

Expected: FAIL，当前停在 `shelf_stored` 且失败后直接抛错。

- [ ] **Step 4: 实现 `purchase_paid` 停点、按订单号恢复和候选诊断信息**

```python
variables["stop_after_node"] = "checking_started"
passed, log, report, summary = run_full_flow_script(self.env, variables)
if not passed and str((summary or {}).get("order_sn") or ""):
    resume_variables = {**variables, "order_sn": summary["order_sn"], "stop_after_node": "checking_started"}
    passed, log, report, summary = run_resume_order_flow_script(self.env, resume_variables)
```

- [ ] **Step 5: 运行日本站执行器测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_japan_runner.py tests/test_problem_goods_script.py -v`

Expected: PASS。

### Task 5: 服务启动恢复遗留运行状态

**Files:**
- Modify: `app/main.py:237-243`
- Test: `tests/test_system_regression_batch.py`

**Interfaces:**
- Consumes: `reconcile_interrupted_runs(db: Session) -> int`
- Produces: lifespan 启动阶段把旧 `running` 用例标记为 `blocked / unknown_write_state`

- [ ] **Step 1: 写失败测试验证启动恢复包装器关闭数据库会话**

```python
def test_recover_system_regression_runs_on_startup(monkeypatch):
    events = []
    monkeypatch.setattr(main, "SessionLocal", lambda: StubSession(events))
    monkeypatch.setattr(main, "reconcile_interrupted_runs", lambda db: events.append("reconciled"))
    main.recover_system_regression_runs_on_startup()
    assert events == ["reconciled", "closed"]
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_batch.py::test_recover_system_regression_runs_on_startup -v`

Expected: FAIL，当前 lifespan 未调用系统回归恢复。

- [ ] **Step 3: 添加小型启动包装器并接入 lifespan**

```python
def recover_system_regression_runs_on_startup() -> int:
    db = SessionLocal()
    try:
        return reconcile_interrupted_runs(db)
    finally:
        db.close()
```

- [ ] **Step 4: 运行批次与路由测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_batch.py tests/test_system_regression_batch_api.py -v`

Expected: PASS。

### Task 6: 静态、集成与真实验证

**Files:**
- Verify only: all files modified in Tasks 1-5

**Interfaces:**
- Consumes: Tasks 1-5 的最终实现
- Produces: 测试结果和真实批次证据

- [ ] **Step 1: 运行相关自动化测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_payment_amount_regression.py tests/test_system_regression_japan_runner.py tests/test_system_regression_batch.py tests/test_system_regression_batch_api.py tests/test_problem_goods_script.py -v`

Expected: PASS。

- [ ] **Step 2: 停止本项目服务并确认没有其他 pytest 进程后运行完整测试**

Run: `.venv\Scripts\python.exe -m pytest tests/ -v`

Expected: PASS；避免服务与 pytest 并发写 SQLite。

- [ ] **Step 3: 重启服务并依次执行真实场景**

执行顺序：`JP-PAY-003`、`JP-PAY-004`、`JP-PAY-005`、`JP-PAY-006`、`JP-PG-AMT-001`。

Expected: 前四条金额/方向一致；问题产品首条取得可提交采购明细并完成余额退款验证。

- [ ] **Step 4: 执行问题产品完整组合矩阵**

Expected: 每条独立执行并保留订单、问题产品 ID、预览证据、余额实际流水和差值；单条失败不影响后续场景。

- [ ] **Step 5: 检查改动范围**

Run: `git status --short`

Run: `git diff --stat`

Run: `node .gitnexus/run.cjs detect-changes -r "D:\A_zidonghuapingtai" --scope compare --base-ref master`

Expected: 本轮变更仅映射到支付回归、日本站问题产品执行、启动恢复及对应测试；不提交任何文件。
