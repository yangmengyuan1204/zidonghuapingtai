# Vue V3 测试工作台全量视觉重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. 每个阶段完成后必须停止，等待人工验收，不得自动进入下一阶段。

**Goal:** 以已确认的“方案 1 + 方案 2 融合稿”为唯一视觉基准，把 `/v3/` 收敛为完整、可回滚、无 legacy iframe 的 Vue 3 测试工作台，同时保持现有 API、权限、路由别名、Storage 和执行语义兼容。

**Architecture:** 采用“Vue V3 Design Tokens → 基础组件 → Workbench 组合组件 → Shell → 业务页”的单向依赖。先完成真实工作区审计，再逐页做功能等价迁移；每页独立通过源码合同、构建、浏览器和 legacy 对照验收后，才更新迁移开关。除非单独批准，不修改后端接口、不新增第三方 UI/图标/图表依赖。

**Tech Stack:** Vue 3.5、Vue Router 4.4、Pinia 2.2、Axios 1.7、Vite 5.4、项目现有 `--v2-*` Token、原生 SVG、Node 校验脚本、Playwright。

## Global Constraints

- 视觉基准：深海军蓝侧栏、冷白内容区、细描边、低饱和蓝、无渐变、无玻璃效果、无夸张阴影。
- 信息密度：桌面优先，1920×1080 与 1440×900 为主验收尺寸；1080、1240、1440、1920 四档不得横向溢出。
- 功能兼容：API URL/method/payload/response、Router path/name/alias/viewKey、permission key、Pinia 结构、Storage key、登录退出语义均保持兼容。
- 数据真实性：趋势图和待处理区只能由现有真实接口数据派生，不允许硬编码演示数据。
- 依赖限制：不引入 Element Plus、Ant Design、Tailwind、ECharts、Lucide 或其他新运行时依赖。
- 隔离限制：V2 Token 仅作用于 `.frontend-v2` 与 `.frontend-v2-portal`，不得污染 legacy。
- Git 安全：执行前隔离工作树；禁止覆盖当前未提交的 Frontend V2、系统回归和支付回归改动；禁止 `git add -A`。
- GitNexus：修改任何函数/类/方法前必须执行 upstream impact；出现 HIGH/CRITICAL 时停止并提示；提交前执行 `detect_changes()`。
- 阶段闸门：每阶段先输出理解摘要和预计文件，获得人工批准后才修改；阶段完成后写入 `docs/frontend-v2/phase-reports/` 并停止。

---

## Skill 执行组合

1. 主审美 Skill：安装并使用 [Anthropic frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design)。职责是约束视觉意图、排除模板化装饰、在每阶段截图后做一次自我批评。
2. 不默认安装 [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)。它适合从零生成设计系统，但本项目已经有确认稿和现有 Token，继续叠加 84 套风格会增加视觉漂移风险；仅当响应式或可访问性清单不足时作为备选参考。
3. 流程 Skill：`test-driven-development` → `executing-plans` → `playwright`/`webapp-testing` → `verification-before-completion`。
4. Skill 安装必须单独获得人工批准；不得在计划阶段执行全局 npm 安装。

---

## 目标文件结构

### 继续作为公共基础

- `frontend/src/styles/v2/tokens.foundation.css`：原子色值、间距、圆角、字体、阴影。
- `frontend/src/styles/v2/tokens.semantic.css`：背景、边框、文字、状态语义。
- `frontend/src/styles/v2/tokens.component.css`：Shell、表格、表单、Dropdown、Modal 等组件 Token。
- `frontend/src/components/v2/base/`：无业务状态的基础组件。

### 新增 Workbench 组合层

- `frontend/src/components/v2/workbench/WorkbenchPageHeader.vue`：页面标题、说明、筛选和主操作插槽。
- `frontend/src/components/v2/workbench/WorkbenchMetricRail.vue`：运行状态与指标栏。
- `frontend/src/components/v2/workbench/WorkbenchPanel.vue`：统一面板标题、工具栏和内容区。
- `frontend/src/components/v2/workbench/WorkbenchTrendChart.vue`：无依赖 SVG 趋势图。
- `frontend/src/components/v2/workbench/WorkbenchAttentionList.vue`：真实数据派生的待处理队列。
- `frontend/src/components/v2/workbench/WorkbenchStatus.vue`：状态点、文本和辅助说明。
- `frontend/src/components/v2/workbench/index.js`：唯一导出入口。

### 新增业务 API 与页面

- `frontend/src/api/modules/apiHarvester.js` + `frontend/src/views/ApiHarvesterView.vue`
- `frontend/src/api/modules/dataScripts.js` + `frontend/src/views/DataScriptsView.vue`
- `frontend/src/api/modules/requirementVerification.js` + `frontend/src/views/RequirementVerificationView.vue`
- `frontend/src/api/modules/systemRegression.js` + `frontend/src/views/SystemRegressionView.vue`

### 校验脚本

- `frontend/scripts/validate-v3-visual-contract.mjs`
- `frontend/scripts/validate-v3-shell-contract.mjs`
- `frontend/scripts/validate-v3-workbench-components.mjs`
- `frontend/scripts/validate-v3-route-parity.mjs`
- `frontend/scripts/validate-v3-page-parity.mjs`

---

### Task 1: 真实状态与改动所有权审计

**Files:**
- Modify: `docs/frontend-v2/handoff/STATE.json`
- Modify: `docs/frontend-v2/handoff/CURRENT-TASK.md`
- Create: `docs/frontend-v2/phase-reports/frontend-v3-redesign-baseline-audit-2026-08-10.md`

**Interfaces:**
- Consumes: 当前 `git status`、`git diff`、Vue 路由、migration-config、legacy 菜单。
- Produces: 每个未提交文件的 owner、完成度、允许修改阶段和保护规则。

- [ ] 记录 `git status --short`、当前分支、HEAD、`git diff --name-status`。
- [ ] 对 `AppShell.vue`、`DashboardView.vue`、`ApiCasesView.vue`、V2 Base 组件和 validators 做逐文件完成度审计。
- [ ] 更新已失真的 handoff：明确 5.2B2 组件已存在，HEAD 为执行时真实值，不再写“NOT STARTED”。
- [ ] 建立保护清单：系统回归、支付回归、后端 Agent、数据库、日志和报告均不属于本次任务。
- [ ] 运行现有全部 V2 validators 与 `npm run build`，把结果作为视觉重构基线。
- [ ] 写审计报告并停止，等待人工批准 Task 2。

**Expected verification:** 只改 3 个文档/状态文件；生产代码零改动。

---

### Task 2: 固化融合稿与视觉合同

**Files:**
- Create: `docs/frontend-v2/visual-baseline/workbench-v1-v2-hybrid.png`
- Create: `docs/frontend-v2/visual-baseline/VISUAL-CONTRACT.md`
- Create: `frontend/scripts/validate-v3-visual-contract.mjs`

**Interfaces:**
- Consumes: 已批准的 1920×1080 融合稿。
- Produces: 可机器检查的颜色、间距、圆角、阴影、字体和禁用项合同。

- [ ] 将融合稿复制为仓库内唯一基准图，不改动图片内容。
- [ ] 在视觉合同中锁定：sidebar `232px`、topbar `62px`、内容背景 `#f5f8fc`、sidebar `#132238`、primary `#2457ad`、panel border `#dbe3ed`、panel radius `8px`。
- [ ] 写 RED validator，检查禁止渐变、backdrop-filter、超大阴影、散落品牌色和非 `--v2-*` 组件变量。
- [ ] 运行 validator，确认当前样式合同未满足并记录 RED。
- [ ] 不修改生产 CSS；停止等待 Task 3 批准。

**Expected verification:** `node frontend/scripts/validate-v3-visual-contract.mjs` 以明确的缺失 Token/违规选择器失败。

---

### Task 3: Token 与基础组件视觉收敛

**Files:**
- Modify: `frontend/src/styles/v2/tokens.foundation.css`
- Modify: `frontend/src/styles/v2/tokens.semantic.css`
- Modify: `frontend/src/styles/v2/tokens.component.css`
- Modify only when contract mismatch is proven: `frontend/src/components/v2/base/*.vue`

**Interfaces:**
- Consumes: `VISUAL-CONTRACT.md`。
- Produces: Shell 和业务页只能消费的稳定 `--v2-*` Token。

- [ ] 对计划修改的每个组件 symbol 运行 GitNexus upstream impact。
- [ ] 添加融合稿 Token，颜色只在 Token 层出现一次。
- [ ] 让 BaseButton、BaseCard、BaseTable、BaseSelect、BaseDropdown、BaseModal、BaseTextarea 的尺寸、focus-visible、disabled 和 danger 状态对齐合同。
- [ ] 先扩展现有 validator 形成 RED，再做最小 CSS/SFC 修改形成 GREEN。
- [ ] 验证 12 个既有基础组件公共 props/emits 不变。
- [ ] 运行 foundation、base、support、dropdown、modal、resource validators 与 build。
- [ ] 在 Component Lab 对 1080/1240/1440/1920 截图，console error 必须为 0。
- [ ] 写阶段报告并停止。

---

### Task 4: Workbench 组合组件

**Files:**
- Create: `frontend/src/components/v2/workbench/WorkbenchPageHeader.vue`
- Create: `frontend/src/components/v2/workbench/WorkbenchMetricRail.vue`
- Create: `frontend/src/components/v2/workbench/WorkbenchPanel.vue`
- Create: `frontend/src/components/v2/workbench/WorkbenchTrendChart.vue`
- Create: `frontend/src/components/v2/workbench/WorkbenchAttentionList.vue`
- Create: `frontend/src/components/v2/workbench/WorkbenchStatus.vue`
- Create: `frontend/src/components/v2/workbench/index.js`
- Create: `frontend/scripts/validate-v3-workbench-components.mjs`
- Modify: `frontend/src/dev/V2BaseComponentsLab.vue`

**Interfaces:**
- `WorkbenchTrendChart` consumes `{ labels: string[], passed: number[], failed: number[] }`，只绘制 SVG。
- `WorkbenchAttentionList` consumes `Array<{ id, tone, title, detail, actionLabel }>`，emit `action(id)`。
- `WorkbenchMetricRail` consumes `Array<{ key, label, value, trend, progress, tone }>`。

- [ ] 写 RED validator，检查组件文件、导出、props/emits、无 API/Router/Pinia/Storage 依赖、无硬编码品牌色。
- [ ] 实现无业务状态的组合组件；每个文件只负责一个视觉单元。
- [ ] 在 Lab 覆盖正常、loading、empty、error、长文本、0 值、窄屏和键盘焦点。
- [ ] 对 SVG chart 加 `role="img"`、可访问标题和无数据状态；尊重 `prefers-reduced-motion`。
- [ ] 运行组件 validator、既有 validators 与 build。
- [ ] 截图与融合稿对照，自审后至少删除一个无功能装饰（若不存在则报告“无可删除项”）。
- [ ] 写阶段报告并停止。

---

### Task 5: AppShell 与全局导航

**Files:**
- Modify: `frontend/src/components/AppShell.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/services/navigation.js`
- Create: `frontend/scripts/validate-v3-shell-contract.mjs`

**Interfaces:**
- Consumes: `menuViews`、auth/theme/toast stores、`navigateToView()`。
- Produces: 深色分组侧栏、项目切换、breadcrumb、全局搜索占位、AI 配置和账号操作区域。

- [ ] 对 `AppShell`、`menuViews`、`navigateToView` 运行 upstream impact 并报告风险。
- [ ] 写 RED validator：菜单顺序、adminOnly、route active、logout、移动端折叠、禁止隐藏 `apiHarvester`。
- [ ] 将侧栏按“工作空间 / 测试资产 / 自动化执行 / 系统管理”分组，保持 viewKey 不变。
- [ ] 使用现有 project store/filter 实现项目切换，不新增 Storage key。
- [ ] 1080 以下使用可关闭侧栏抽屉；桌面保持 232px，不用纯图标导航。
- [ ] 保持登录页独立、admin 权限过滤、legacy 未迁移跳转语义。
- [ ] 验证键盘导航、active、刷新恢复、退出、非管理员菜单。
- [ ] 写阶段报告并停止。

---

### Task 6: Dashboard 真实数据版

**Files:**
- Modify: `frontend/src/views/DashboardView.vue`
- Modify: `frontend/src/api/modules/dashboard.js`
- Reuse: `frontend/src/api/modules/records.js`
- Create: `frontend/scripts/validate-v3-dashboard-contract.mjs`

**Interfaces:**
- Consumes: `GET /api/dashboard` 与 `GET /api/test-records?page_size=200`。
- Produces: 指标栏、最近 7 天趋势、待处理队列、最近执行表格。

- [ ] 写 RED validator：禁止 mock 数组，要求真实 API、loading/empty/error、项目筛选和记录操作合同。
- [ ] 用最近最多 200 条真实记录按日期聚合 passed/failed；数据不足时显示真实范围，不伪造 7 天。
- [ ] 待处理项仅由失败记录、环境缺失、UI 用例为 0、需求验证未完成等可证明状态派生；不能证明的项目不显示。
- [ ] 保留日志、报告、截图和跳转执行报告功能。
- [ ] 对比旧版 Dashboard 的五项计数、项目筛选和最近记录，保证数值一致。
- [ ] 通过 dashboard validator、build、四档 viewport 和键盘验收。
- [ ] 写阶段报告并停止。

---

### Task 7: 核心 CRUD 页面统一

**Files:**
- Modify: `frontend/src/views/ProjectsView.vue`
- Modify: `frontend/src/views/ApiCasesView.vue`
- Modify: `frontend/src/views/RecordsView.vue`
- Modify: `frontend/src/views/UsersView.vue`
- Modify: `frontend/src/components/AppFormDialog.vue`
- Modify: `frontend/src/components/AppTable.vue`
- Modify: `frontend/src/components/AppPagination.vue`
- Create: `frontend/scripts/validate-v3-core-pages-parity.mjs`

**Interfaces:**
- Consumes: 现有 projects/envs/testAccounts/apiCases/records/users API modules。
- Produces: 同一套 PageHeader、filter toolbar、BaseTable、状态和 action menu 交互。

- [ ] 按页面分别运行 impact；一次只改一个业务页，每页单独 RED/GREEN/验收。
- [ ] Projects：项目、环境、测试账号三块保持新增/编辑/删除/绑定和非管理员只读。
- [ ] API Cases：保持项目/环境筛选、选择、批量执行、新增、复制、编辑、删除、单条执行。
- [ ] Records：保持筛选、分页、日志、报告、截图、恢复孤儿报告、再次执行确认。
- [ ] Users：保持 adminOnly、新增、编辑、删除和普通用户不可达。
- [ ] 统一表格密度、空状态、错误状态、危险操作确认和表单字段布局，不改 API payload。
- [ ] 每个页面做 legacy 功能清单逐项对照，缺一项即阻塞。
- [ ] 写阶段报告并停止。

---

### Task 8: UI 自动化页面拆分与重构

**Files:**
- Modify: `frontend/src/views/UiCasesView.vue`
- Create: `frontend/src/components/ui-cases/UiCaseForm.vue`
- Create: `frontend/src/components/ui-cases/UiExecutionPanel.vue`
- Create: `frontend/src/components/ui-cases/UiRecordingPanel.vue`
- Create: `frontend/scripts/validate-v3-ui-cases-parity.mjs`

**Interfaces:**
- Consumes: 现有 `uiCasesApi`、test account API 和 timer/session lifecycle。
- Produces: 用例列表、编辑、可视化执行、录制、保存四个清晰单元。

- [ ] 先锁定 `UiCasesView.vue` 现有全部 API 调用、timer 和 onBeforeUnmount 清理合同。
- [ ] 写 RED validator 覆盖 937 行页面的执行、轮询、取消、录制、事件读取、保存和卸载清理。
- [ ] 只拆 UI 子组件，业务状态仍由 View 编排，避免跨组件复制 session 状态。
- [ ] 保持账号绑定、视觉执行、状态轮询、录制取消和保存语义。
- [ ] 浏览器验证快速切路由、重复执行和卸载后无残留 timer/请求。
- [ ] 写阶段报告并停止。

---

### Task 9: 数据工厂原生 Vue 迁移

**Files:**
- Create: `frontend/src/api/modules/dataScripts.js`
- Create: `frontend/src/views/DataScriptsView.vue`
- Create: `frontend/src/components/data-scripts/DataScriptCatalog.vue`
- Create: `frontend/src/components/data-scripts/DataScriptRunner.vue`
- Create: `frontend/src/components/data-scripts/DataAgentWorkspace.vue`
- Modify: `frontend/src/router/index.js`
- Create: `frontend/scripts/validate-v3-data-scripts-parity.mjs`

**Interfaces:**
- Consumes: `/api/data-scripts/**`、`/api/data-scripts/agent/**`、现有 data factory Storage keys。
- Produces: 脚本目录、动态参数表单、执行结果和 Agent 会话工作区。

- [ ] 从 `static/app.js`、`static/full-flow.js`、`static/data-factory-agent.js` 建立完整功能与 Storage 合同表。
- [ ] 先迁移目录和单脚本执行，再迁移动态表单/组合流程，最后迁移 Agent 确认/风险/权限/取消循环。
- [ ] 每个子阶段独立 RED/GREEN，不同时改其他业务页。
- [ ] 保持脚本入参、返回、执行记录 kind、会话状态和 LocalStorage key 完全兼容。
- [ ] 通过 legacy/Vue 同数据对照后，将路由组件从 `LegacyEmbedView` 切为 `DataScriptsView`。
- [ ] 不在本阶段移除 legacy 实现；写阶段报告并停止。

---

### Task 10: 需求验证中心原生 Vue 迁移

**Files:**
- Create: `frontend/src/api/modules/requirementVerification.js`
- Create: `frontend/src/views/RequirementVerificationView.vue`
- Create: `frontend/src/components/requirement-verification/RequirementTaskList.vue`
- Create: `frontend/src/components/requirement-verification/RequirementWorkspace.vue`
- Create: `frontend/src/components/requirement-verification/RequirementRunPanel.vue`
- Modify: `frontend/src/router/index.js`
- Create: `frontend/scripts/validate-v3-requirement-verification-parity.mjs`

**Interfaces:**
- Consumes: `/api/requirement-verifications/**` 与 case-generation workspace API。
- Produces: 任务、材料、澄清、条目、公式、数据源、记忆、预检、运行和学习会话。

- [ ] 把 legacy `caseGeneration` 与 `functionalTests` alias 合并规则固化为测试。
- [ ] 按“任务资料 → AI 分析与澄清 → 验证条目 → 运行控制 → 学习沉淀”五段迁移。
- [ ] 保持 upload/OCR、confirm/defer、pause/resume/cancel/retry 和 browser open 语义。
- [ ] 所有轮询都具备路由卸载清理、重复请求保护和错误恢复。
- [ ] parity 通过后替换 `LegacyEmbedView`；保留 legacy 回滚入口。
- [ ] 写阶段报告并停止。

---

### Task 11: 接口抓取原生 Vue 页面

**Files:**
- Create: `frontend/src/api/modules/apiHarvester.js`
- Create: `frontend/src/views/ApiHarvesterView.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/components/AppShell.vue`
- Create: `frontend/scripts/validate-v3-api-harvester-parity.mjs`

**Interfaces:**
- Consumes: extract、crawl、task polling、analyze 四组现有接口。
- Produces: 可访问菜单页、抓取任务状态、结果预览和分析入口。

- [ ] 删除 `HIDDEN_SIDEBAR_KEYS` 对 apiHarvester 的隐藏，但保留权限规则。
- [ ] 新增 route path/name/alias/viewKey，不改 API。
- [ ] 对抓取轮询实现卸载清理和终态停止。
- [ ] 验证抽取、爬取、轮询、分析、错误和空结果。
- [ ] 写阶段报告并停止。

---

### Task 12: 系统回归原生 Vue 页面

**Files:**
- Create: `frontend/src/api/modules/systemRegression.js`
- Create: `frontend/src/views/SystemRegressionView.vue`
- Create: `frontend/src/components/system-regression/RegressionCaseTable.vue`
- Create: `frontend/src/components/system-regression/RegressionBatchPanel.vue`
- Modify: `frontend/src/router/index.js`
- Create: `frontend/scripts/validate-v3-system-regression-parity.mjs`

**Interfaces:**
- Consumes: `/api/system-regression/suites/**`、cases、batches、runs 现有合同。
- Produces: 套件用例、覆盖编辑/复制/重置、批次执行/停止、失败续跑。

- [ ] 读取系统回归未提交改动的 owner，确认不会覆盖后再开始。
- [ ] 固化 customer/project/env Storage key 与批次轮询合同。
- [ ] 保持 copy/reset、stop、rerun、resume-account 和报告证据入口。
- [ ] 验证长批次、刷新恢复、停止竞态、账号恢复和权限边界。
- [ ] parity 通过后把 systemRegression 加入 Vue Router、Shell 与 migration config。
- [ ] 写阶段报告并停止。

---

### Task 13: 路由、迁移开关与 legacy 退场

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/services/navigation.js`
- Modify: `static/migration-config.json`
- Modify: `static/migration-bridge.js`
- Delete only after separate human confirmation: `frontend/src/views/LegacyEmbedView.vue`
- Create: `frontend/scripts/validate-v3-route-parity.mjs`
- Create: `frontend/scripts/validate-v3-page-parity.mjs`

**Interfaces:**
- Consumes: 每个页面已签字的 parity 报告。
- Produces: `/v3/` 全原生 Vue 导航与页面级可回滚开关。

- [ ] 建立 legacy views、menuViews、Router、migration-config 四方真值表。
- [ ] 写 RED validator 检查 key/path/name/alias/adminOnly 和每个菜单均有可达页面。
- [ ] 一次只切换一个 viewKey；每切一个都执行 smoke、build 和刷新/后退/前进测试。
- [ ] 保留 `/` legacy 直到全页面签字完成；禁止一次性删除 legacy JS/CSS。
- [ ] `LegacyEmbedView.vue` 的删除属于破坏性动作，必须单独获得人工确认。
- [ ] 写阶段报告并停止。

---

### Task 14: 全量验收与发布准备

**Files:**
- Create: `docs/frontend-v2/phase-reports/frontend-v3-workbench-final-acceptance-YYYY-MM-DD.md`
- Modify: `docs/frontend-v2/handoff/STATE.json`
- Modify: `docs/frontend-v2/handoff/CODEX-HANDOFF.md`
- Modify: `docs/frontend-v2/handoff/CURRENT-TASK.md`

**Interfaces:**
- Consumes: 全部阶段报告与最终代码。
- Produces: 可交接、可回滚、可发布的 Vue V3 状态。

- [ ] 运行全部 frontend validators、`npm run build`、`git diff --check`。
- [ ] 使用项目 `.venv` 运行权限、路由合同、系统回归前端和本次相关最小 pytest 集合。
- [ ] Playwright 验收 `/v3/login` 与全部业务路由：1080/1240/1440/1920、键盘、ARIA、loading/empty/error、console error 0。
- [ ] 与融合稿做截图差异审查：布局、颜色、密度和层级通过；真实业务页面不要求像素级复制演示数据。
- [ ] 对 `/` legacy 做登录、菜单和核心执行 smoke，确认未被 V2 Token 污染。
- [ ] 执行 GitNexus `detect_changes(scope="compare", base_ref="main")`，确认只影响预期符号和流程。
- [ ] 输出准备提交与不会提交文件清单；默认不 commit、不 push。
- [ ] 更新 handoff 和 STATE，最终报告必须包含 Remaining Risks 与回滚步骤。

## 最终验收标准

- `/v3/` 所有菜单项都有原生 Vue 页面，不再依赖 iframe。
- 融合稿的视觉合同在 Shell、Dashboard 和全部业务页保持一致。
- 所有 legacy 功能都有 parity 证据，API/权限/Storage/路由语义无破坏。
- 4 档 viewport 无横向溢出，键盘和 focus-visible 可用，console error 为 0。
- 新增依赖为 0，legacy 全局样式污染为 0，演示假数据为 0。
- 每阶段报告、状态和回滚点齐全；未经批准不删除 legacy、不提交、不推送。

## 执行节奏

- 推荐使用当前会话的 `executing-plans`，每次只执行一个 Task，并在阶段报告后等待用户批准。
- Task 1–6 建立视觉与核心工作台；Task 7–8 完成已原生 Vue 页面；Task 9–12 解决四个 legacy/缺失页面；Task 13–14 才做全量切换与验收。
- 预计 14 个阶段，任何阶段出现 HIGH/CRITICAL impact、功能 parity 缺口或未明确的改动所有权，都立即停止，不通过“顺手修复”扩大范围。
