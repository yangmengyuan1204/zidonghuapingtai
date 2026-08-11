# Frontend V2 Phase 5.5D — API Cases Foundation Integration

## Status

- Implementation: **PASS**
- Verification: **PASS**
- PHASE 5.5D: **PASS**
- Date: 2026-07-30

本阶段只将已经冻结的 `BaseSelect`、`BaseTextarea`、`BaseTable` 接入真实生产路径；没有重新设计组件，也没有进入 Modal、Toast、Confirm 或 Form Framework。

## Git Baseline

- Branch: `codex/safe-refactor-preserve-features`
- HEAD: `a4c5764a759720707b34d65caddce7661d54e13d`
- Staged changes: none
- 开始前工作区已混有 Frontend V2、payment regression、system regression、backend、static 与 tests 改动。
- 本阶段未执行 `git add`、`reset`、`checkout`、`restore`、`clean`、`stash`、`commit` 或 `push`，无关改动保持原样。

## Component Mapping

| Existing production UI | V2 mapping | Production usage point | Result |
|---|---|---|---|
| Project native select | `BaseSelect` | `src/views/ApiCasesView.vue` | PASS |
| Environment native select | `BaseSelect` | `src/views/ApiCasesView.vue` | PASS |
| `AppTable` | `BaseTable` | `src/views/ApiCasesView.vue` | PASS |
| AppFormDialog native textarea branch | `BaseTextarea` | `src/components/AppFormDialog.vue` | PASS |

`BaseTable` 保留 `columns`、`rows`、`rowKey`、named cell slots、Method/Status Badge、Action Buttons、loading、empty 与 responsive overflow；没有加入 sorting、filtering、selection model、virtual scroll、resize、drag 或业务字段。

两个 `BaseSelect` 保留原有受控 value/change、项目/环境数据来源、watch、mounted 与切换 handler；原筛选器没有 disabled 绑定，本阶段也没有新增。`BaseTextarea` 是共享渲染分支的一对一替换，不是 ApiCasesView 专属分支。

`BaseTable` 的 ID、Case Name 与 URL 通过页面级 named slot 保留 `AppTable` 原有 `short(value, 140)` 普通文本截断合同，不修改冻结的 BaseTable。

## Protected Contracts

- Phase Validator 固定校验 API module、Router、Store、`AppTable.vue`、`AppModal.vue`、`AppToast.vue` 与三个非目标消费者页面的 SHA-256。
- `loadApiCases`、Project/Environment 切换、分页、CRUD、Copy、Delete、Execute、Batch Execute、selection 与 mounted 生命周期保持 Phase 5.5B 基线。
- `pageSize = 20` 与 `selectedIds = ref(new Set())` 保持不变。
- API Cases 的 headers、params、body、assert_rule 与 batch variables 五个 textarea 字段按 name、type、default、rows 精确校验；Projects、Users、UiCases 继续由整文件散列保护。
- `AppFormDialog` 的 props、emits、watch、submit/reset、field schema、model/update 与 consumer 数据格式保持不变。
- 未修改 API、Router、Store、Permission、CRUD handler、Batch handler、API response、package、lockfile、Base Component API 或 Design Token。

## RED

先创建并运行 `frontend/scripts/validate-v2-api-cases-foundation-integration.mjs`。在实现生产接入前，Validator 按预期因以下真实缺口失败：

- ApiCasesView 缺少 `BaseSelect` 与 `BaseTable` import/usage，仍存在 native Project/Environment select 与 `AppTable`。
- AppFormDialog 缺少 `BaseTextarea` import/usage，仍存在 native textarea 分支。
- Supporting/Resource Approved Production Usage 尚未批准三个真实使用点。

Validator 自身的基线散列与函数提取问题在只修改 Validator 后先修正；修正后的 RED 仍只由上述尚未迁移合同触发，没有提前 GREEN。

独立审查后又补充一次定向 RED：Validator 因 BaseTable 缺少 ID/Case Name/URL 三个 `short(value, 140)` slot 而失败；补回原 AppTable 普通文本合同后重新 GREEN。

## GREEN

- `validate-v2-api-cases-foundation-integration.mjs`: PASS
- `validate-v2-support-components.mjs`: PASS；Approved Production Usage 精确增加：
  - `BaseSelect` → `src/views/ApiCasesView.vue`
  - `BaseTable` → `src/views/ApiCasesView.vue`
  - `BaseTextarea` → `src/components/AppFormDialog.vue`
- 非批准 production usage 继续 FAIL；Dashboard Fully Migrated 与 ApiCases Partially Migrated 边界未放宽。
- Phase 5.5B Validator 保留直接映射合同，同时将 Select/Table/AppFormDialog 的新合法边界交给 Phase 5.5D Validator。

## Shared Consumer Impact

| Consumer | 实际 textarea 路径 | 真实验证 | 调用方修改 | 差异 |
|---|---|---|---|---|
| `AppFormDialog.vue` | 唯一 `field.type === "textarea"` 分支 | import、binding、submit/reset 与无 native textarea | 仅共享渲染分支替换 | 无行为差异 |
| `ApiCasesView.vue` | headers、params、body、assert_rule（rows 3）；batch variables（rows 8） | Create/Edit/Copy、初值、输入、提交、取消/重开、Batch dialog | 无 | 无；冻结后的 V2 textarea 视觉进入现有 Dialog |
| `ProjectsView.vue` | description；global_headers/global_vars；username/password/submit locator，共 6 个字段 | Create/Edit、初值、必填校验、输入、提交、取消/重开 | 无 | 无；当前字段无 readonly/disabled 合同 |
| `UsersView.vue` | 当前 field schema 中没有 textarea | 打开 Create Dialog，确认 BaseTextarea 0、native textarea 0 | 无 | 共享消费者但当前无 textarea 渲染路径 |
| `UiCasesView.vue` | steps（rows 8） | Create/Edit、默认值回填、长 JSON、校验、提交、取消/重开 | 无 | 无 |

审计未发现消费者依赖原生 textarea DOM、class、ref 或原生事件。当前四个消费者的 textarea 字段均未设置 maxlength、required、disabled、readonly、error 或 help；共享组件仍透传这些既有 field contract，未新增 schema。

## Shared Contract Proof

- 调用 API 未变化：四个页面的 `AppFormDialog` props 与事件调用均未修改。
- Form schema 未变化：消费者 field 数量、type、name/key、rows、placeholder 与默认值保持原样。
- Business handler 未变化：submit、reset、create/edit 生命周期及各页面 handler 保持原函数内容。
- BaseTextarea 为原生 textarea 分支的一对一替换；页面消费者没有新增 import 或调用。
- 没有新增 consumer-specific branch、route condition、feature flag、prop 或 schema 字段。
- `BaseTextarea` 只批准到真实使用点 `src/components/AppFormDialog.vue`，没有分别批准四个页面。

## Browser Verification

实际生产地址：`http://127.0.0.1:8000/v3/api-cases`。

- 管理员完成真实登录、刷新与退出/重新登录。
- 真实数据总数 82，首屏 20 行；Project/Environment 切换、依赖选项刷新与恢复全量均通过。
- Pagination 第 1/2 页往返通过，page size 仍为 20。
- Loading：项目切换时捕获 loading 状态，响应完成后消失。
- Empty：创建无用例临时项目后得到真实 `共 0 条` 空态；验证后通过现有 UI 删除，最终项目列表恢复。
- CRUD：临时 API Case 完成 Create、Edit、Copy、Delete，最终总数恢复 82。
- Execute / Batch Execute：均进入现有 Records 路径；专用临时用例使用不可达本地地址安全失败，没有访问 Japan/OEM 外部业务站点。
- Dialog：ApiCases 的 4 个 rows=3 Textarea 与 Batch rows=8 Textarea 均由 `BaseTextarea` 渲染。
- UI Cases 临时数据完成 Create/Edit/Delete 并清理；临时 Project 与 API Cases 数据也已清理。
- In-app Browser 的最终干净标签：Console **0 Error / 0 Warning**。
- Phase 5.5D.1 使用单一共享 ICO、显式根路径引用、Vite favicon 专属 build hook 与 FastAPI 精确静态映射修复 `/favicon.ico` 404。独立 headed Playwright CLI 全新浏览器上下文再次登录并访问 Dashboard、API Cases、刷新与 Component Lab；浏览器 Resource Timing 只出现 `/favicon.ico`，Console **0 Error / 0 Warning**，Page Error **0**，因此 Verification 更新为 PASS。
- Network/contract：所有交互仅走现有页面 API；Validator 的模块散列与 handler 散列证明没有新增 endpoint、请求参数或请求路径。实际列表、CRUD、Execute、Batch 与删除后的 UI 响应均返回到预期页面状态。

## Regression

- Login：退出后回到 `/v3/login`，真实账号重新登录后进入 Dashboard。
- Dashboard：首次进入与刷新均正常。
- AppShell：主导航、API Cases 导航、退出按钮与 admin 信息正常；1080/1240/1440/1920 均可用。
- Projects：共享 Textarea 的 Create/Edit/validation/submit/cancel/reopen 通过。
- Users：共享 Dialog 可打开；当前没有 textarea 渲染路径，未伪造 textarea 测试。
- UI Cases：共享 Textarea 的默认值、长文本、validation/submit/cancel/reopen 通过。
- Legacy `/`：`.frontend-v2` 0、`--v2-*` Token 规则 0、`.frontend-v2-portal` 0、Console 0 Error / 0 Warning。

## Accessibility

- 两个 `BaseSelect` 保留显式 label/id 关联与 native keyboard contract；ArrowDown/Home 操作正常。
- `BaseTable` 为 `role="region"`、`tabindex="0"`、`aria-label="接口用例列表可滚动区域"`；semantic table/thead/tbody 与各列文本保留。
- Checkbox、Method/Status 文本、Action Button accessible name 保持 Phase 5.5B 合同。
- `BaseTextarea` 通过 AppFormDialog label/id 映射；Project 与 UI Cases 的键盘输入、Tab 离开与长文本均正常。

## Responsive

| Width | Document overflow | BaseTable internal overflow | Client / scroll width | Result |
|---:|---|---|---:|---|
| 1080 | none | yes | 751 / 986 | PASS |
| 1240 | none | yes | 911 / 986 | PASS |
| 1440 | none | no | 1111 / 1111 | PASS |
| 1920 | none | no | 1591 / 1591 | PASS |

四档均保留两个 Filter、20 行真实数据与完整操作列；窄视口通过 BaseTable 内部滚动访问右侧列，没有造成 document 级横向滚动。

## Automated Verification

| Command | Result |
|---|---|
| `node frontend/scripts/validate-v2-foundation.mjs` | PASS |
| `node frontend/scripts/validate-login-redirect.mjs` | PASS (9/9) |
| `node frontend/scripts/validate-v2-base-components.mjs` | PASS |
| `node frontend/scripts/validate-v2-support-components.mjs` | PASS |
| `node frontend/scripts/validate-v2-dropdown.mjs` | PASS |
| `node frontend/scripts/validate-v2-resource-foundation.mjs` | PASS |
| `node frontend/scripts/validate-v2-api-cases-direct-mapping.mjs` | PASS |
| `node frontend/scripts/validate-v2-api-cases-foundation-integration.mjs` | PASS |
| `npm --prefix frontend run build` | PASS (161 modules) |
| `git diff --check` | PASS；仅既有 LF/CRLF 提示，无 whitespace error |

## Diff Audit

本阶段创建：

- `frontend/scripts/validate-v2-api-cases-foundation-integration.mjs`
- 本报告

本阶段修改：

- `frontend/src/views/ApiCasesView.vue`
- `frontend/src/components/AppFormDialog.vue`
- `frontend/scripts/validate-v2-support-components.mjs`
- `frontend/scripts/validate-v2-resource-foundation.mjs`
- `frontend/scripts/validate-v2-api-cases-direct-mapping.mjs`

未修改 BaseSelect、BaseTextarea、BaseTable、Token、任何其他业务页面、AppTable、AppModal、AppToast、API、Router、Store、Prototype、package 或 lockfile。

## Known Risks

- 工作区仍混有大量其他任务未提交改动；后续暂存必须精确列文件，禁止 `git add .`。
- GitNexus `detect-changes` 对整个混合工作区报告 `critical`（32 个 tracked 文件、87 个索引符号、292 条受影响流程）；它同时包含 payment/system/backend/tests 等无关改动，不能解释为 Phase 5.5D 的独立影响，但进一步确认当前工作区不得整体提交。
- 浏览器执行 Execute/Batch Execute 按平台既有行为留下执行记录；未修改或直接清理数据库。
- Projects 与 Users 当前没有真实 readonly/disabled textarea 字段，因此按真实 schema 记录为不适用，没有构造不存在的路径。
- AppFormDialog 是共享生产组件；未来修改 BaseTextarea contract 时仍需同时回归 ApiCases、Projects、Users 与 UI Cases。
- 本阶段没有迁移 Modal、Toast、Confirm、其他页面 Table/Select 或 Form Framework。
- Phase 5.5D.1 已解除 `/favicon.ico` 404；单一 source/build asset、根路径引用和 FastAPI 映射由独立 Validator 持续保护。
