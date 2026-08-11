# 系统回归——日本站 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建成独立“系统回归”菜单和日本站 77 条可编辑回归用例，支持单条/批量异步执行、三方金额核对、预期业务拦截和大额退款部长账号续跑。

**Architecture:** 新增 `app/system_regression/` 领域模块、`app/services/system_regression/` 持久化与批次编排服务、独立 FastAPI 路由和 legacy 前端模块。日本站目录只声明日本业务参数、计算和执行适配；现有造单、支付、配送和问题产品脚本继续作为底层业务动作，不改变其公开契约。

**Tech Stack:** Python 3.11、FastAPI 0.115、SQLAlchemy 2.0、SQLite、原生 JavaScript/CSS、pytest。

## Global Constraints

- 所有测试必须使用 `.venv\Scripts\python.exe`。
- 当前分支为 `codex/safe-refactor-preserve-features`；在现有工作区就地实施，保留全部未提交改动。
- 不修改旧数据脚本的入参、返回值和执行流程；旧 `payment_amount_regression` 保留兼容。
- 前端新增独立 `static/system-regression.js` 和 `static/system-regression.css`，不向 `static/app.js` 堆业务逻辑。
- 所有用户参数使用输入框、下拉框、复选框和可增删表格；不提供 JSON 编辑框。
- 临时账号密码不得落库、进入日志或报告。
- 默认不启动浏览器，不提交、不推送。
- 修改任何现有符号前必须先运行 GitNexus impact；当前会话无 GitNexus MCP 时使用项目 CLI，若仍不可用则报告并只做最小入口改动。
- 每个生产行为先写失败测试并确认 RED，再写最小实现确认 GREEN。

---

### Task 1: 日本站目录与纯领域类型

**Files:**
- Create: `app/system_regression/__init__.py`
- Create: `app/system_regression/common/__init__.py`
- Create: `app/system_regression/common/catalog.py`
- Create: `app/system_regression/projects/__init__.py`
- Create: `app/system_regression/projects/japan/__init__.py`
- Create: `app/system_regression/projects/japan/catalog.py`
- Test: `tests/test_system_regression_catalog.py`

**Interfaces:**
- Produces: `RegressionCaseDefinition`, `CaseExpectation`, `japan_case_definitions() -> tuple[RegressionCaseDefinition, ...]`。
- Case fields: `key`, `name`, `category`, `runner_kind`, `parameters`, `expectation`, `tags`, `sort_order`。

- [ ] **Step 1: 写失败测试，锁定 77 条目录和分类计数**

```python
def test_japan_catalog_has_stable_unique_matrix():
    cases = japan_case_definitions()
    assert len(cases) == 77
    assert len({case.key for case in cases}) == 77
    assert Counter(case.category for case in cases) == {
        "payment": 10,
        "problem_amount": 12,
        "problem_service_fee": 6,
        "problem_option_manual": 15,
        "problem_option_auto": 6,
        "problem_mixed": 3,
        "problem_flow": 10,
        "problem_guard": 15,
    }
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_catalog.py -v`  
Expected: FAIL，原因是 `app.system_regression` 或 `japan_case_definitions` 不存在。

- [ ] **Step 3: 实现不可变目录类型和表驱动目录**

```python
@dataclass(frozen=True)
class CaseExpectation:
    outcome: Literal["success", "guard"]
    direction: Literal["credit", "debit", "none"] = "none"
    error_codes: tuple[str, ...] = ()
    error_keywords: tuple[str, ...] = ()

@dataclass(frozen=True)
class RegressionCaseDefinition:
    key: str
    name: str
    category: str
    runner_kind: str
    parameters: Mapping[str, Any]
    expectation: CaseExpectation
    tags: tuple[str, ...]
    sort_order: int
```

目录用 `JP-PAY-001..010`、`JP-PG-AMT-001..012`、`JP-PG-SVC-001..006`、`JP-PG-OPT-M-001..015`、`JP-PG-OPT-A-001..006`、`JP-PG-MIX-001..003`、`JP-PG-FLOW-001..010`、`JP-PG-GUARD-001..015` 生成，逐条写入设计文档规定的参数和预期。

- [ ] **Step 4: 运行目录测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_catalog.py -v`  
Expected: PASS。

- [ ] **Step 5: 检查本任务范围**

Run: `git diff --check -- app/system_regression tests/test_system_regression_catalog.py`

---

### Task 2: 参数表单 Schema 与联动校验

**Files:**
- Create: `app/system_regression/schemas.py`
- Create: `app/system_regression/projects/japan/parameters.py`
- Test: `tests/test_system_regression_parameters.py`

**Interfaces:**
- Consumes: Task 1 case definition parameters。
- Produces: `JapanCaseParameters`, `MoneyInput`, `OrderItemInput`, `OptionInput`, `validate_case_parameters()`。

- [ ] **Step 1: 写失败测试覆盖普通输入字段和 OPTION 约束**

```python
def test_quantity_increase_rejects_auto_option():
    payload = valid_problem_payload(pre_num=4, option_deal_suggest=2)
    with pytest.raises(ParameterValidationError, match="数量增加"):
        validate_case_parameters("problem_goods", payload, current_num=3)

def test_existing_option_cannot_change_price_type():
    with pytest.raises(ParameterValidationError, match="计价类型"):
        validate_option_changes(original=[fixed_option()], updated=[rate_option()])
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_parameters.py -v`  
Expected: FAIL，缺少参数模型和校验函数。

- [ ] **Step 3: 实现结构化 Pydantic 输入模型**

`MoneyInput` 必须包含 `value: Decimal`、`currency: Literal["CNY", "JPY"]`；`OptionInput` 包含名称、计价类型、价格、数量、选中和自动计算；`OrderItemInput` 包含采购/确认/报价数量、价格、三类国内运费和 OPTION 列表；`JapanCaseParameters` 包含整单默认、单番覆盖、支付、配送、问题产品与期望字段。

- [ ] **Step 4: 实现后端一致的联动校验**

校验数量增加与自动 OPTION、OPTION 数量超过商品数、多个百分比 OPTION、已有 OPTION 计价类型变化、其他回复/其他采购处理备注、非负金额和整数数量。

- [ ] **Step 5: 运行参数测试确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_parameters.py -v`  
Expected: PASS。

---

### Task 3: 独立金额计算、汇率与三方核对

**Files:**
- Create: `app/system_regression/common/reconciliation.py`
- Create: `app/system_regression/common/evidence.py`
- Create: `app/system_regression/projects/japan/calculators.py`
- Test: `tests/test_system_regression_calculators.py`
- Test: `tests/test_system_regression_evidence.py`

**Interfaces:**
- Produces: `MoneyEvidence`, `ProblemAmountBreakdown`, `calculate_problem_amount()`, `reconcile_three_way()`。

- [ ] **Step 1: 写公式失败测试**

```python
def test_problem_total_uses_goods_freight_service_and_option():
    result = calculate_problem_amount(problem_fixture())
    assert result.goods_delta == Decimal("-20")
    assert result.freight_delta == Decimal("-3")
    assert result.service_delta == Decimal("-2")
    assert result.option_delta == Decimal("-5")
    assert result.total_cny == Decimal("-30")
```

- [ ] **Step 2: 写汇率、方向、误差和唯一流水失败测试**

覆盖 HALF_UP、差值 0/1/2、退款入账、补款出账、零金额无流水、缺汇率和重复歧义。

- [ ] **Step 3: 运行两个测试文件确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_calculators.py tests/test_system_regression_evidence.py -v`

- [ ] **Step 4: 按 PHP 公式实现计算器**

```python
goods_delta = (old_total_num + diff_num) * new_price - old_total_num * old_price
service_should = (goods_delta * service_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
total_cny = goods_delta + freight_delta + service_delta + option_delta
bill_jpy = (-total_cny * exchange_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
```

手续费优惠、已收不退、实际未支付手续费、固定/百分比 OPTION、检品已完成数量保护分别实现为可测试分支。

- [ ] **Step 5: 实现三方证据核对**

要求独立预期与后台预览、后台预览与实际流水两段差值都在容差内；问题产品只接受余额证据；支付按用例接受余额或已财务确认银行证据。

- [ ] **Step 6: 运行测试确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_calculators.py tests/test_system_regression_evidence.py -v`

---

### Task 4: 四张数据表与系统用例持久化

**Files:**
- Create: `app/system_regression/models.py`
- Create: `app/services/system_regression/__init__.py`
- Create: `app/services/system_regression/case_service.py`
- Test: `tests/test_system_regression_persistence.py`

**Interfaces:**
- Produces SQLAlchemy models: `SystemRegressionSuite`, `SystemRegressionCase`, `SystemRegressionBatch`, `SystemRegressionCaseRun`。
- Produces service functions: `ensure_japan_suite()`, `list_cases()`, `update_case()`, `copy_case()`, `reset_case()`。

- [x] **Step 1: 对待修改模型符号执行 impact 分析并报告风险**

GitNexus 对 `TestRecord` 和 `TestAccountBinding` 返回 CRITICAL（73 个上游、57 个直接引用），已暂停并获得用户批准：四张表改放独立 `app/system_regression/models.py`，不修改 `app/models.py` 现有符号。

- [ ] **Step 2: 写失败测试，在临时 SQLite 中建表并种入 77 条用例**

断言系统预置不可删除、修改增加版本、复制产生自定义用例、恢复默认不删除执行历史。

- [ ] **Step 3: 运行持久化测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_persistence.py -v`

- [ ] **Step 4: 在独立模型模块新增四个模型**

表名固定为 `system_regression_suite`、`system_regression_case`、`system_regression_batch`、`system_regression_case_run`；run 冗余保存 `case_key` 和 `case_version` 作为执行快照索引；JSON 数据用 `Text` 存储并由服务统一序列化；为 suite/key、batch/status 和 run/batch/status 建索引。

- [ ] **Step 5: 实现幂等种子和用例服务**

用 `suite_key + case_key` 唯一定位；系统默认副本单独保存；种子升级只更新未被用户修改的系统默认版本。

- [ ] **Step 6: 运行测试确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_persistence.py -v`

---

### Task 5: 用例管理 API

**Files:**
- Create: `app/routers/system_regression.py`
- Modify: `app/routers/__init__.py`
- Test: `tests/test_system_regression_api.py`

**Interfaces:**
- Produces design-specified suite/case endpoints under `/api/system-regression`。

- [ ] **Step 1: 对 `register_routers` 执行 impact 并报告风险**
- [ ] **Step 2: 写失败路由契约测试**

覆盖列出、详情、普通表单结构化更新、复制、恢复默认和启停；验证密码字段不属于用例持久化请求模型。

- [ ] **Step 3: 运行 API 测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_api.py -v`

- [ ] **Step 4: 实现独立路由并最小注册**

所有写接口使用现有鉴权依赖；返回结构包含 `form_schema` 和结构化 `parameters`，前端无需解析或编辑 JSON 文本。

- [ ] **Step 5: 运行 API 测试和路由契约测试确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_api.py tests/test_route_contract.py -v`

---

### Task 6: 日本站支付与问题产品实时执行适配

**Files:**
- Create: `app/system_regression/projects/japan/payment_runner.py`
- Create: `app/system_regression/projects/japan/problem_runner.py`
- Create: `app/system_regression/projects/japan/guard_runner.py`
- Create: `app/system_regression/projects/japan/runner.py`
- Test: `tests/test_system_regression_japan_runner.py`

**Interfaces:**
- Produces: `JapanRegressionRunner.execute(case_snapshot, context) -> CaseRunResult`。
- Consumes existing `run_full_flow_script`, payment scripts, `inspect_problem_goods`, `run_problem_goods_script` and real evidence gateways。

- [ ] **Step 1: 写失败执行器测试**

覆盖 10 条支付类型分派、通用问题产品参数映射、预期拦截匹配、失败继续所需的结构化结果，以及请求参数不能成为实际证据。

- [ ] **Step 2: 运行执行器测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_japan_runner.py -v`

- [ ] **Step 3: 实现支付适配**

普通订单、分批付款、配送单分别调用现有脚本；余额用前后账单差集，银行只接受唯一匹配且财务确认流水；全费用用例把表单参数映射到现有 full-flow variables。

- [ ] **Step 4: 实现问题产品适配**

每条用例先造独立订单到安全前置节点，再查真实采购候选，提交问题产品、预览、采购处理和配货确认；退款与补款都从客户余额差集取证。

- [ ] **Step 5: 实现拦截适配**

只在出现配置错误码或关键词时返回 passed；发生其他错误、未拦截或产生不应有的写入时返回 failed。

- [ ] **Step 6: 运行执行器测试确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_japan_runner.py -v`

---

### Task 7: 批次状态机、异步执行与账号恢复

**Files:**
- Create: `app/system_regression/common/execution.py`
- Create: `app/services/system_regression/batch_service.py`
- Create: `app/services/system_regression/account_service.py`
- Test: `tests/test_system_regression_batch.py`
- Test: `tests/test_system_regression_account_resume.py`

**Interfaces:**
- Produces: `create_batch()`, `request_stop()`, `resume_run_with_account()`, `rerun_case()`。

- [ ] **Step 1: 写失败状态机测试**

覆盖顺序执行、失败继续、停止未开始用例、等待账号但继续其他用例、服务重启后的状态核对和不确定写操作禁止重试。

- [ ] **Step 2: 写沈文妮账号恢复安全测试**

断言退款 CNY `>= 500` 时优先查项目内 `profile_name == "沈文妮"`；自动登录失败进入 `waiting_account`；临时 password 不出现在数据库字段、日志和序列化结果中。

- [ ] **Step 3: 运行测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_batch.py tests/test_system_regression_account_resume.py -v`

- [ ] **Step 4: 实现 DB 驱动状态机和单进程后台执行器**

创建批次接口只落库并提交后台任务；每条 run 使用独立数据库会话；同 suite/env/customer 使用互斥锁串行执行；应用重启将遗留 running 进入状态核对而非直接重跑。

- [ ] **Step 5: 实现部长账号与临时凭证恢复**

临时凭证只作为函数参数传给登录流程，使用后立即释放引用；恢复前读取 problem_goods 状态、订单状态和余额流水决定下一安全动作。

- [ ] **Step 6: 运行测试确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_batch.py tests/test_system_regression_account_resume.py -v`

---

### Task 8: 批次、停止、恢复和重跑 API

**Files:**
- Modify: `app/routers/system_regression.py`
- Test: `tests/test_system_regression_batch_api.py`

- [ ] **Step 1: 对将修改的路由函数逐个执行 impact**
- [ ] **Step 2: 写失败 API 测试**

创建批次必须立即返回 ID；查询返回批次和明细统计；停止只标记未开始项；resume 请求接收 password 但响应、日志和数据库不包含明文；rerun 创建新 run 并关联来源。

- [ ] **Step 3: 运行测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_batch_api.py -v`

- [ ] **Step 4: 实现批次接口并只向服务层传递结构化命令**

```python
@router.post("/batches", status_code=202)
def create_regression_batch(request: BatchCreateRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return batch_service.create_batch(db, request, actor_id=user.id)

@router.post("/runs/{run_id}/resume-account", status_code=202)
def resume_regression_run(run_id: int, request: AccountResumeRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return batch_service.resume_run_with_account(db, run_id, request.username, request.password, actor_id=user.id)
```

`AccountResumeRequest` 不实现 `model_dump()` 日志，不将 password 传给任何持久化函数。
- [ ] **Step 5: 运行测试确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_batch_api.py -v`

---

### Task 9: 独立 legacy 系统回归页面

**Files:**
- Create: `static/system-regression.js`
- Create: `static/system-regression.css`
- Modify: `static/index.html`
- Test: `tests/test_system_regression_frontend.py`

**Interfaces:**
- Exposes: `window.renderSystemRegression()`。
- Consumes: `/api/system-regression/*` structured API。

- [ ] **Step 1: 对 `static/index.html` 脚本入口影响执行 impact 或入口依赖审计**
- [ ] **Step 2: 写失败静态契约测试**

断言菜单名为“系统回归”、独立 JS/CSS 被加载、没有参数 JSON textarea、存在数字/文本/密码/select/checkbox 和 OPTION 可增删表格、支持单选和批量按钮。

- [ ] **Step 3: 运行前端契约测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_frontend.py -v`

- [ ] **Step 4: 实现菜单注入与 renderCurrentView 扩展**

仿照 `requirement-verification.js` 在 `views` 中插入 `{key: "systemRegression", label: "系统回归"}`，包装 `renderCurrentView`，不修改 `static/app.js`。

- [ ] **Step 5: 实现三栏页面和普通表单控件**

左侧分类、中间用例表、右侧参数抽屉；OPTION 和单番使用可增删行；后台轮询批次；`waiting_account` 使用 password 输入框续跑；不渲染可编辑 JSON。

- [ ] **Step 6: 运行前端契约测试确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_frontend.py -v`

---

### Task 10: 兼容记录、全集成验证和影响检查

**Files:**
- Modify: `app/services/system_regression/batch_service.py`
- Test: `tests/test_system_regression_integration.py`
- Modify: `tests/route_contract_expected.json`

- [ ] **Step 1: 写失败集成测试**

验证批次主 `TestRecord`、每条明细 `TestRecord`、batch/run 关联、原支付金额回归路由仍存在、旧脚本注册和返回契约不变。

- [ ] **Step 2: 运行集成测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_integration.py -v`

- [ ] **Step 3: 实现 TestRecord 兼容写入并更新路由契约快照**

```python
def save_compat_record(db: Session, *, batch: SystemRegressionBatch, run: SystemRegressionCaseRun | None) -> TestRecord:
    payload = {
        "script_key": "system_regression",
        "batch_id": batch.id,
        "batch_no": batch.batch_no,
        "run_id": run.id if run else None,
        "case_key": run.case_key if run else None,
    }
    record = TestRecord(
        case_type="data_script",
        case_id=run.case_id if run else batch.id,
        project_id=batch.project_id,
        result=(run.status if run else batch.status),
        log=json.dumps(payload, ensure_ascii=False),
        execute_time=datetime.now(),
    )
    db.add(record)
    db.flush()
    return record
```
- [ ] **Step 4: 运行系统回归最小全集**

Run: `.venv\Scripts\python.exe -m pytest tests/test_system_regression_*.py -v`  
Expected: PASS。

- [ ] **Step 5: 运行相邻既有测试**

Run: `.venv\Scripts\python.exe -m pytest tests/test_payment_amount_reconciliation.py tests/test_payment_amount_scenarios.py tests/test_payment_amount_regression.py tests/test_problem_goods_script.py tests/test_data_script_contract.py tests/test_route_contract.py -v`  
Expected: PASS。

- [ ] **Step 6: 运行静态和语法检查**

Run: `.venv\Scripts\python.exe -m compileall app/system_regression app/services/system_regression app/routers/system_regression.py`  
Run: `git diff --check`

- [ ] **Step 7: 运行 GitNexus 变更影响检查**

Run: `detect_changes(scope="compare", base_ref="main")`；MCP 不可用时使用 GitNexus CLI 等价命令，并记录工具不可用风险。

- [ ] **Step 8: 输出最终工作区审计**

Run: `git status --short`  
Run: `git diff --stat`

只汇报本次系统回归文件与未触碰的既有脏文件；不提交、不推送。
