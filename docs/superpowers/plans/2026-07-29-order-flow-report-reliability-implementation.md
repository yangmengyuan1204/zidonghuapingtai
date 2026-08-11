# Order Flow And Report Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复订单续跑账号误用、翻译超时假失败、执行报告丢失风险及支付流水方向误判。

**Architecture:** 账号档案解析放在数据脚本路由边界，订单写操作对账放在订单业务模块，报告恢复放在独立服务，支付方向修复限定在新支付回归模块。所有行为先用定点失败测试锁定，再做最小实现。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2.0、SQLite、pytest、原生 JavaScript。

## Global Constraints

- 测试必须使用 `.venv\Scripts\python.exe`。
- 不修改数据库文件、密钥、环境配置和启动脚本。
- 保留当前工作区已有改动，不提交无关文件。
- 不扫描或删除 Allure 报告之外的文件。
- 有副作用请求不能在状态未知时盲目重复提交。

---

### Task 1: 后台账号档案解析

**Files:**
- Modify: `app/routers/data_scripts.py`
- Modify: `static/full-flow.js`
- Test: `tests/test_permissions.py`
- Test: `tests/test_data_script_contract.py`

**Interfaces:**
- Produces: `_resolve_backend_account_variables(db, variables, project_id) -> Dict[str, Any]`
- Consumes: `account_profile_variables`、`default_account_profile_for_target`

- [ ] 编写失败测试：显式档案覆盖硬编码账号；项目唯一档案自动解析；没有档案且没有显式账号时返回明确 400；前端内置续跑不包含 `Y001`。
- [ ] 运行上述测试并确认因解析函数或行为缺失而失败。
- [ ] 实现统一解析函数，并应用于 `full-flow`、`resume-order-flow`、`payment-amount-regression` 三个路由。
- [ ] 删除 `static/full-flow.js` 中相关内置流程的固定后台凭据，保留显式运行变量兼容。
- [ ] 运行定点测试并确认通过。

### Task 2: 订单确认字段与翻译超时对账

**Files:**
- Modify: `app/data_scripts/order_support.py`
- Modify: `app/data_scripts/full_flow.py`
- Test: `tests/test_permissions.py`
- Test: `tests/test_data_factory_agent.py`

**Interfaces:**
- Produces: `_submit_order_translate_with_reconciliation(session, base_url, variables, order_sn, fields, timeout) -> tuple[Dict[str, Any], Dict[str, Any]]`
- Consumes: `_impl__post_admin_form`、`_order_detail_data`、订单状态字段 `status`

- [ ] 保留并测试当前未提交的 `confirm_freight = "0"` 必传修复。
- [ ] 编写失败测试：首次翻译超时但回查状态大于 20 时成功且只提交一次；回查仍为 20 时最多受控重试；始终未知时返回明确错误。
- [ ] 运行测试并确认旧代码因直接抛出 `RuntimeError` 而失败。
- [ ] 实现翻译专用提交与状态对账，替换订单恢复流程中的通用盲重试。
- [ ] 在恢复流程进入节点前记录当前节点，异常摘要使用真实节点。
- [ ] 运行订单恢复和数据智能体运费定点测试并确认通过。

### Task 3: 项目删除报告保护

**Files:**
- Modify: `app/routers/projects.py`
- Test: `tests/test_permissions.py`

**Interfaces:**
- Produces: 删除前 `TestRecord` 计数保护；存在记录时 HTTP 409。

- [ ] 编写失败测试：项目存在直属或用例关联执行记录时删除返回 409，记录和项目均保留。
- [ ] 运行测试并确认旧代码会删除记录。
- [ ] 在任何删除语句之前计算关联记录数量并拒绝危险删除。
- [ ] 运行项目权限和删除定点测试并确认通过。

### Task 4: 孤立 Allure 报告索引恢复

**Files:**
- Create: `app/services/test_record_recovery.py`
- Modify: `app/routers/test_records.py`
- Test: `tests/test_record_recovery.py`

**Interfaces:**
- Produces: `recover_orphan_test_records(db, report_dir, project_id) -> Dict[str, int]`
- Produces: `POST /api/test-records/recover-orphan-reports?project_id=<id>`，仅管理员可调用。

- [ ] 编写失败测试：扫描有效 Allure result、跳过损坏文件、忽略已引用文件、二次执行不重复。
- [ ] 运行测试并确认恢复服务不存在。
- [ ] 使用 `json.load` 解析结果文件，根据 Allure `status/name/start/stop/description` 建立最小 `TestRecord`；`report_path` 作为幂等键。
- [ ] 新增管理员恢复接口并验证项目存在，不自动执行真实数据库恢复。
- [ ] 运行恢复服务、权限和路由契约测试并确认通过。

### Task 5: 支付余额流水方向归一化

**Files:**
- Modify: `app/data_scripts/payment_amount_regression/runner.py`
- Test: `tests/test_payment_amount_reconciliation.py`
- Test: `tests/test_payment_amount_regression.py`

**Interfaces:**
- Produces: `money_evidence_from_record(..., direction="debit")` 对余额支付显式采用业务方向。
- Consumes: `_aggregate_evidence`、`MoneyEvidence`、订单或配送单业务引用。

- [ ] 编写失败测试：接口返回正数和 `credit` 展示标签时，余额支付证据仍按客户扣款 `debit`；退款场景继续为 `credit`。
- [ ] 运行测试并确认当前自动方向推断导致失败。
- [ ] 仅在订单及配送单余额支付调用点显式传入 `debit`，不改变问题商品退款方向规则。
- [ ] 运行全部支付回归测试并确认通过。

### Task 6: 集成验证与影响检查

**Files:**
- Verify only: all modified files

- [ ] 运行订单、权限、报告恢复、支付回归和数据脚本契约测试。
- [ ] 运行 `git diff --check`、`git status --short`、`git diff --stat`。
- [ ] 运行 `node .gitnexus/run.cjs detect-changes --scope unstaged --repo zidonghuapingtai`，核对只影响预期符号和流程。
- [ ] 不调用真实远端写操作；报告恢复只在临时测试数据库和临时目录验证。
