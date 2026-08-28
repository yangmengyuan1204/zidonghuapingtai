# 日本站系统回归真实数据对齐 — Cursor 交接文档

日期：2026-08-26
仓库：D:\A_zidonghuapingtai

## 目标与约束

继续修改、测试并真实执行，直到 catalog 配置、真实订单/配送详情、精确状态、支付证据和真实增量客户账本全部一致，最终对照 BAD []。

禁止 git add/commit/push、reset、checkout；不得覆盖现有 staged/unstaged 改动。修改现有函数前按 AGENTS.md 做 GitNexus impact；必须 TDD；不能只凭 pytest 绿色交付。

必读：

1. D:\AppCache\Temp\sr_batch137_codex_brief.md
2. D:\AppCache\Temp\sr_compare_137.json
3. D:\AppCache\Temp\sr_compare.py
4. D:\A_zidonghuapingtai\AGENTS.md

## 工作区保护

本任务相关主要文件：

- app/data_scripts/order_support.py
- app/data_scripts/payment_amount_regression/runner.py
- app/data_scripts/porder_flow_support.py
- app/services/system_regression/ticket_service.py
- app/system_regression/common/amount_oracle.py
- app/system_regression/projects/japan/catalog.py
- app/system_regression/projects/japan/panel.py
- app/system_regression/projects/japan/payment_runner.py
- app/system_regression/projects/japan/problem_runner.py
- tests/test_data_factory_agent.py
- tests/test_payment_amount_regression.py
- tests/test_system_regression_amount_oracle.py
- tests/test_system_regression_catalog.py
- tests/test_system_regression_japan_runner.py
- tests/test_system_regression_tickets.py

部分文件为 MM，绝对不要回退。无关内容不要动：static/index.html、static/system-regression.js、.pnpm-store、docs/oem-flow-recon、docs/文档造数-页面示意.html、ui-prototype、ui-reference。

## 已完成修复

- 商品数量、逐番号运费按配置写入。
- 支付 OPTION 79/78 精确映射和数量写入。
- 配送线路不再降级为 14；附加费走真实接口；线路/运费/附加费核验。
- 全部订单反查详情，核验 sorting、quantity、price、freight、OPTION ID/数量。
- 全额订单状态精确 50，分批订单精确 70，配送精确 50。
- 缺 order_sn/porder_sn 直接 evidence_incomplete。
- 配送详情、支付、客户账本和证据完整性硬校验。
- 券保留 type、discounts_amount_jpy、fee_waiver。
- discounts_amount_jpy=1 的手续费券不再当固定减 1 JPY。
- SERVICE 哨兵精确选手续费券；ACCOUNT 优先金额券，无金额券时使用真实手续费券语义。
- 问题件 service_discount 时手续费增量为 0。
- 问题件手动 OPTION 金额使用“新总额 - 旧总额”，不按名称合并，允许新增项提交前无 ID。

## 自动化测试

最后两项修改前：95 passed + 217 passed = 312 passed。
最后修改账号券回退和 OPTION oracle 后：定点 9 passed。

必须重新跑完整相关测试。项目 venv 启动器损坏，使用：

~~~powershell
$env:PYTHONPATH='D:\A_zidonghuapingtai\.venv\Lib\site-packages'
& 'C:\Users\刘礼鹏\AppData\Local\Programs\Python\Python311\python.exe' -m pytest -q -p no:cacheprovider tests/test_system_regression_amount_oracle.py tests/test_system_regression_tickets.py tests/test_system_regression_japan_runner.py tests/test_system_regression_catalog.py tests/test_payment_amount_regression.py tests/test_data_factory_agent.py
~~~

## 真实批次

原始 Batch 137：SYSREG-20260825131625-1BA061，61 passed / 6 failed / 1 blocked。

Batch 146：67 passed / 1 blocked。Batch 147 单独重跑支付-004 passed。合并曾得到 68 条 BAD []，但发生在最后硬校验修改前，不能作为最终交付。

### Batch 148

SYSREG-20260826113331-DE8435，关键 10 条 6 passed / 4 blocked。

通过：

- 支付-004：order 2026082611333237-300001，状态70；账本180+106=286 JPY，冻结285，差1。
- 支付-007：order 2026082611342527-300001，状态50，账本558 JPY。
- 支付-008：order 2026082611345295-300001，2番号，状态50，账本1242 JPY。
- 支付-009：order 2026082611352786-300001，状态50，毛额285，手续费券后账本275 JPY。
- 配送-003：porder P2026082611363094-300001，线路25，775+8 CNY，状态50，账本16600 JPY。
- 配送-005：porder P2026082611402205-300001，线路30，2777 CNY，状态50，账本58872 JPY。

### Batch 149

SYSREG-20260826114520-4460C5，4 passed / 0 failed / 0 blocked。

- 配送-004：P2026082611460686-300001；线路25；775 CNY；状态50；账本记录3238251，16430 JPY。
- 支付-016：2026082611465096-300001；状态50；券180935；毛额285；账本记录3238252，275 JPY。
- 支付-017：2026082611472742-300001；状态50；券180936；毛额285；账本记录3238254，275 JPY。
- 手动OPTION-001：order 2026082611480421-300001；problem_goods_id 896969；oracle/预览/账本均21 JPY，三方差异0。

Batch 148+149 的关键 10 条最新结果已全部真实通过。

## 必须继续

### P0 完整测试

执行上述完整相关测试，失败继续按 RED -> 最小修复 -> GREEN。

### P0 最终全量 68 条

创建新真实批次：

- suite_key=japan
- project_id=1
- env_id=1
- admin_profile_id=2
- customer_id=300001

保持执行进程存活并轮询终态。瞬时网络 blocked 可安全单独 rerun。最终每个 case_key 必须有真实证据：订单有 order_sn/详情/精确状态；配送有 porder_sn/线路/运费/附加费/状态50；金额变化有增量客户账本。

### P0 最终对照

运行或修正 D:\AppCache\Temp\sr_compare.py：

- catalog 冻结参数 vs 真实详情。
- expected/preview/payment vs 增量账本。
- 精确状态。
- OPTION 按 ID/数量，不按中文名。
- CNY/JPY 分开。
- 银行入金和订单出金分开，不机械相加。

BAD 不为空就继续修，直到 BAD []。

### P1 自动配送独立报价

当前要求 porder_detail、exchange_rate、报价/支付 check、账本齐全。但要确认 expected_source=porder_pay_detail 是支付前独立冻结报价，不是支付后落库自证。若不是，补：

预测报价 CNY -> 配送详情 CNY -> 支付 JPY -> 增量账本 JPY

四段缺失或不一致必须失败。

### P1 银行支付

复核支付-004、支付-017：

- 银行/财务确认记录证明支付渠道。
- 客户账本可能记余额订单出金，这是账务模型，不能简单要求 bill_method_name=银行。
- 分批混合按阶段核验。
- 禁止把银行入金和余额出金机械相加。
- 纯银行用例不能只凭余额账本通过。

### P1 问题件 OPTION 身份

oracle 只负责金额，新增项提交前无 ID 合理；完成后仍要证明写入正确 OPTION。已有项按 ID；新增项按返回 ID、名称翻译、price_type、price、num。先检查 business_diffs/guard，缺失才补最小硬校验。

## 最终验证

~~~powershell
git status --short
git diff --stat
git diff --check
node .gitnexus/run.cjs detect-changes --scope compare --base-ref HEAD
~~~

不要提交。最终汇报测试数、最终68条批次、重跑记录、订单/配送/问题件ID、详情状态、账本记录ID和金额、银行渠道证据、BAD []、剩余风险。

## 一键复制提示词

~~~text
你在仓库 D:\A_zidonghuapingtai 继续完成“日本站系统回归 vs 真实订单/配送/出入金完全一致”任务。

先完整阅读：
1. D:\A_zidonghuapingtai\docs\system-regression-cursor-handoff-2026-08-26.md
2. D:\AppCache\Temp\sr_batch137_codex_brief.md
3. D:\AppCache\Temp\sr_compare_137.json
4. D:\AppCache\Temp\sr_compare.py
5. D:\A_zidonghuapingtai\AGENTS.md

强制要求：
- 继续修改、测试、真实执行，直到配置、订单/配送详情、精确状态、支付证据和增量客户账本全部一致。
- 不要 git add/commit/push，不要 reset/checkout，不要覆盖 staged/unstaged 改动。
- 不要碰 static/index.html、static/system-regression.js、.pnpm-store、docs/oem-flow-recon、ui-prototype、ui-reference。
- 修改现有函数前做 GitNexus impact；HIGH/CRITICAL 先说明。
- 必须 TDD；不能只凭 pytest 绿色交付。

当前证据：
- Batch 148：SYSREG-20260826113331-DE8435，关键10条中6 passed/4 blocked。
- Batch 149：SYSREG-20260826114520-4460C5，4条重跑全部passed。
- 合并关键10条全部真实通过。
- 配送-004：线路25/775CNY/状态50/账本16430JPY。
- 支付-016、017：毛额285JPY、真实手续费券后账本275JPY、状态50。
- 手动OPTION-001：oracle/预览/账本均21JPY。
- 最后修改前相关测试312 passed；最后修改后定点9 passed，所以完整测试必须重跑。

立即执行：
1. git status --short，保护全部现有改动。
2. 重跑交接文档的完整相关测试，失败继续根因修复。
3. 审查自动配送是否有独立支付前报价；必要时补“预测报价CNY -> 配送详情CNY -> 支付JPY -> 增量账本JPY”。
4. 审查支付-004/017银行支付，分别核验支付渠道和客户账本，禁止机械混加。
5. 审查问题件OPTION最终ID/数量/价格详情；oracle允许新增项提交前无ID，但最终必须证明写入正确。
6. 创建最终全量68条真实批次：suite_key=japan、project_id=1、env_id=1、admin_profile_id=2、customer_id=300001，轮询到终态。
7. blocked可在确认无重复写风险后安全rerun；最终按case_key取最新真实证据。
8. 运行/修正D:\AppCache\Temp\sr_compare.py，逐条对照配置、详情、精确状态和增量账本。
9. BAD不为空就继续RED、最小修复、测试、真实重跑，直到BAD []。
10. 最终运行git status --short、git diff --stat、git diff --check、GitNexus detect-changes。

只有完整测试通过、最终68条都有真实证据、详情/状态/账本一致、银行渠道证据正确、BAD []且未提交代码时才交付。最终总结给出批次号、68条汇总、重跑记录、订单/配送/问题件ID、详情状态、账本记录ID和金额、测试数、剩余风险。不要贴大段日志。
~~~

