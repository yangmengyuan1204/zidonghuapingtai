# Frontend V3 Functional Fingerprint (BEFORE) — Enterprise AI Workbench UI Redesign (BEFORE)

Generated: 2026-08-12
Branch: codex/frontend-v3-workbench-redesign
Source of truth: live frontend/static source scan (not guessed)

## Scope

- V3 app base: `/v3/`
- Shell menu groups/order: `frontend/src/components/AppShell.vue`
- Routes: `frontend/src/router/index.js`
- Envs / Accounts: panels inside Projects (no separate routes)
- Data Factory / System Regression (live V3): `LegacyEmbedView` → `/?v3_embed=1#/{viewKey}`
- Native Vue `DataScriptsView.vue` / `SystemRegressionView.vue` exist but are NOT routed

## Route / Menu Map

| order | group | key | label | route(s) | adminOnly | component |
|------:|-------|-----|-------|----------|-----------|-----------|
| 1 | 工作空间 | dashboard | 工作台总览 | `/dashboard` | no | DashboardView.vue |
| 2 | 工作空间 | projects | 项目空间 | `/projects` | no | ProjectsView.vue |
| 3 | 测试资产 | apiCases | 接口用例库 | `/api-cases` | no | ApiCasesView.vue |
| 4 | 自动化执行 | dataScripts | 数据工厂 | `/dataScripts` | no | LegacyEmbedView.vue |
| 5 | 自动化执行 | requirementVerification | 需求验证中心 | `/requirementVerification` | no | RequirementVerificationView.vue |
| 6 | 自动化执行 | uiCases | UI自动化 | `/ui-cases` | no | UiCasesView.vue |
| 7 | 自动化执行 | records | 执行报告 | `/records` | no | RecordsView.vue |
| 8 | 系统管理 | systemRegression | 系统回归 | `/systemRegression` | yes | LegacyEmbedView.vue |
| 9 | 系统管理 | users | 权限中心 | `/users` | yes | UsersView.vue |
| — | public | login | — | `/login` | public | LoginView.vue |

Shell extras (admin): 全局 AI 配置 (modal), 模板管理 (`/static/admin/templates.html`), 自愈记录 (`/static/admin/heal-logs.html`), 退出.

Global project filter: `app.filters.projectId` via BaseSelect.

---

## Module: Login

- Route: `/v3/login` (public)
- Buttons: 登录 / 登录中... → handleLogin
- Fields: username, password, remember
- API: POST /api/auth/login
- Forbidden extras: register / forgot password / OAuth

## Module: Dashboard

- Buttons: project dropdown; 查看执行报告; 全部记录; row 日志/报告/截图; 重新加载
- Filters: project dropdown
- Columns (最近执行): ID, 类型, 用例ID, 结果, 执行时间, 操作
- Modal: 执行日志 BaseModal
- APIs: GET /api/dashboard; GET /api/projects; report/screenshot blobs
- Content: metrics rail, trend chart, attention list, recent table, status summary

## Module: Projects (+ Envs + Accounts)

- Buttons: 新增项目(admin); row 账号/编辑/删除(admin); 新增环境(admin); env 编辑/删除; 新增测试账号(admin); account 编辑/删除
- Filters: envFilterProjectId
- Columns:
  - Projects: ID, 项目名称, 描述, 默认测试账号, 创建时间, 操作
  - Envs: ID, 项目, 环境名称, Base URL, 超时, 全局请求头, 全局变量, 操作
  - Accounts: ID, 账号档案, 范围, 变量(masked), 状态, 操作
- Modals: project / env / account / default-account binding AppFormDialogs
- Fields:
  - Project: name, desc
  - Env: project_id, env_name, base_url, global_headers, global_vars, timeout
  - Account: project_id, profile_name, username, password, code, login_url, locators, success_url_contains, success_selector, status
  - Binding: account_profile_id
- APIs: /api/projects, /api/envs, /api/test-accounts, PUT /api/test-account-bindings

## Module: API Cases

- Buttons: 新增接口用例(admin); 批量执行 N; row 执行/复制/编辑/删除
- Filters: filterProjectId, filterEnvId
- Columns: select, ID, 项目, 环境, 用例名称, 方法, URL, 状态, 操作
- Modals: case form; batch execute (variables JSON)
- Fields: project_id, env_id, case_name, method, url, headers, params, body, assert_rule, status; batch variables
- APIs: /api/api-cases CRUD; execute; batch-execute; GET /api/envs

## Module: Data Factory (Legacy embed)

- Route: /dataScripts → iframe /?v3_embed=1#/dataScripts
- Tabs: active / deleted / hidden
- Buttons: 新建脚本; 录制新流程; 实时录制; row edit/run/hide/delete/drag-sort; deleted 恢复
- Context: factoryProjectId, factoryEnvId, factoryVariables, factoryFlowId, factoryCaseIds
- Columns active: drag, 脚本名称, 项目, 环境, 步骤, 操作
- Columns deleted: 脚本名称, 项目, 环境, 类型, 删除时间, 操作
- Agent flows: confirm / risk / cancel / permission
- DO NOT MODIFY: static/app.js, static/full-flow.js, static/data-factory-agent.js

## Module: Requirement Verification

- Buttons: 新建验证任务(admin); 搜索; 生成验证计划/预检并执行/删除任务(admin); 刷新/暂停/继续/取消; modal 取消/创建任务
- Filters: projectId; keyword
- Modal: 新建需求验证任务
- Fields: project_id, name, target_url, requirement_text
- APIs: /api/requirement-verifications*; analyze; preflight; runs; pause/resume/cancel
- Poll: 1.5s

## Module: UI Automation

- Buttons: 录制UI用例/新增UI用例(admin); row 执行/编辑/删除; record cancel/返回录制/保存用例; 可视化执行/关闭; 查看记录/关闭
- Filters: filterProjectId
- Columns: ID, 项目, 用例名称, 页面地址, 超时, 测试账号, 状态, 操作
- Dialogs: UiCaseForm; 录制开始; 录制中; 保存录制; 执行表单; 可视化执行
- Fields: case fields; record start; assertion_text; execute account_mode/profile/headed/variables
- APIs: /api/ui-cases*; ui-executions; ui-record sessions; heal-steps; test-accounts

## Module: Records

- Buttons: 再次执行 (api/ui only); 日志; 报告; 截图; pagination
- Filters: filterProjectId; filterType (api/ui/全部)
- Columns: ID, 类型, 用例ID, 结果, 执行时间, 操作
- Modal: log BaseModal
- APIs: /api/test-records*; re-execute; report/screenshot

## Module: System Regression (Legacy embed)

- Route: /systemRegression adminOnly
- Filters: srSuite, srProject, srEnv, srCustomerId
- Buttons: 选择当前分类; 批量执行; category chips; 编辑; 保存参数/复制用例/恢复默认/单条执行; 新增单番/添加OPTION/删除*; 继续执行
- DO NOT MODIFY: static/system-regression.js

## Module: Users / Permissions

- Buttons: 新增用户; 编辑; 删除
- Columns: ID, 账号, 角色, 创建时间, 操作
- Fields: username, password, role (admin|normal only)
- APIs: /api/users CRUD
- adminOnly route + redirect non-admin

## Module: AI Config

- Shell modal (admin)
- Buttons: 测试连接; 保存配置
- Fields: provider, base_url, model, api_key
- APIs: GET/PUT /api/ai-config; POST /api/ai-config/test

## Module: Templates

- External: /static/admin/templates.html
- Buttons: 新建模板; 编辑/测试运行/删除; +添加步骤/保存/关闭
- Filters: projectFilter
- Fields: name, description, project_id, trigger_keywords, dynamic steps
- APIs: /api/action-templates*

## Module: Heal Logs

- External: /static/admin/heal-logs.html
- Buttons: 查询; 确认应用/驳回/撤销确认; pagination
- Filters: caseIdFilter
- APIs: /api/locator-heal-logs*

## Shared Components (props/emits frozen)

AppTable, AppFormDialog, AppModal, AppPagination, AppToast, AiConfigDialog
BaseButton, BaseIconButton, BaseInput, BaseTextarea, BaseSelect, BaseCheckbox, BaseModal, BaseTable, BasePagination, BaseBadge, BaseChip, BaseCard, BaseDropdown, BaseDropdownItem, BaseEmptyState, BaseErrorState, BaseSkeleton, BaseTooltip
WorkbenchPageHeader, WorkbenchPanel, WorkbenchStatus, WorkbenchMetricRail, WorkbenchAttentionList, WorkbenchTrendChart

## Freeze Rules for this redesign

- Script changes = 0
- Menu/button/field/column/filter/modal/API/permission/event diffs = 0
- No hide via CSS (display:none etc. on business controls)
- Presentation wrappers / CSS / visual class only

