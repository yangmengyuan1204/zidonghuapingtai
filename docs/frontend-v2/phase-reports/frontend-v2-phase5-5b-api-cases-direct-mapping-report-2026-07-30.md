# Frontend V2 Phase 5.5B — API Cases Direct Component Mapping

## Status

- Implementation: **PASS**
- Verification: **PASS**
- Phase: **PASS**
- Date: 2026-07-30

普通用户浏览器权限矩阵受环境条件限制：当前 `/api/users` 仅返回 `admin`，没有可用于登录的普通用户账号。本阶段没有创建、重置或绕过普通用户认证；此条件按阶段验收要求明确记录，不伪造验证结果。

## Git Baseline

- Branch: `codex/safe-refactor-preserve-features`
- HEAD: `a4c5764a759720707b34d65caddce7661d54e13d`
- Staged changes: none
- Stash: none
- 开始前工作区已混有 Frontend V2、payment regression、system regression、backend 与 tests 改动。本阶段未执行 add、reset、restore、checkout、clean、stash、commit 或 push，也未处理无关改动。

## Scope

本阶段只对 `ApiCasesView.vue` 中已有 UI 做一对一映射：Toolbar Button、Row Action Button、Method/Status Badge、Row Checkbox、Pagination。Project/Environment Select、Toolbar/Field/Actions 布局、AppTable、AppFormDialog、CRUD/Batch Form、Router、Store、API、Permission 与业务生命周期保持原样。

## Component Mapping

| Existing UI | V2 mapping | Result |
|---|---|---|
| Toolbar Batch/Create buttons | `BaseButton` | PASS |
| Execute/Copy/Edit/Delete actions | `BaseButton` | PASS |
| Method/Status badge | `BaseBadge` | PASS |
| Row native checkbox | controlled `BaseCheckbox` | PASS |
| Manual pagination | `BasePagination` | PASS |

Delete 使用 `danger`；主次操作、文案、handler、admin 可见性和 disabled 条件未改变。Method 保留真实方法文本，Status 保留真实状态文本，不仅依赖颜色。

## Protected Contracts

- API module、Router、auth/app/toast Store、AppTable、AppFormDialog、AppModal、AppToast 的 SHA-256 基线由阶段 Validator 校验。
- `loadApiCases`、项目/环境切换、`goPage`、`toggleSelect`、CRUD、单条/批量执行与 mounted 生命周期的已有实现由阶段 Validator 校验。
- `pageSize = 20`、`selectedIds = ref(new Set())`、项目/环境 Select 片段与两个 AppFormDialog 声明保持不变。
- 未新增 Dropdown、Search、全选、Loading、Error、Skeleton、EmptyState、`v-html` 或业务功能。

## Validator Changes

- 新增 `frontend/scripts/validate-v2-api-cases-direct-mapping.mjs`，作为 Phase 5.5B 的页面边界 Validator；包含真实违规样本 self-check。
- `validate-v2-support-components.mjs` 新增 `BasePagination -> src/views/ApiCasesView.vue` Approved Production Usage，并引入 Fully/Partially Migrated 两类页面边界。
- 所有既有 Primitive、Supporting、Component Lab、Portal Isolation 与 Legacy Isolation 断言均保留。

## Validator Boundary Model

### Fully Migrated Page

`src/views/DashboardView.vue` 仍执行原有整页 legacy isolation，禁止项和检查强度没有降低。

### Partially Migrated Page

当前仅 `src/views/ApiCasesView.vue`。明确批准 `BaseButton`、`BaseBadge`、`BaseCheckbox`、`BasePagination`；已经迁移的区域禁止 `.btn`、`.badge`、`.pagination`。尚未迁移的 Toolbar/Filter/Field/Compact/Actions 布局 class 可继续存在，但不承担已迁移组件的视觉合同。

这不是全局跳过 legacy isolation：页面必须存在显式边界配置，Supporting Component 仍必须通过 Approved Production Usage；非批准页面继续 FAIL。Phase 5.5C 如扩大迁移，只应扩展该页面的边界配置与专属阶段 Validator，不应放宽 Fully Migrated 页面或重写 Validator 核心逻辑。

## RED / GREEN

- RED：Supporting Validator 在边界架构调整后通过，不再误报允许保留的未迁移布局 class；Phase 5.5B Validator 因 Button、Badge、Checkbox、Pagination 尚未迁移及 `.btn/.badge/.pagination` 仍存在而失败。
- GREEN：完成四类真实组件映射后，Phase 5.5B Validator 与 Supporting Validator 均通过。

## Automated Verification

| Command | Result |
|---|---|
| `node frontend/scripts/validate-v2-foundation.mjs` | PASS |
| `node frontend/scripts/validate-login-redirect.mjs` | PASS (9/9) |
| `node frontend/scripts/validate-v2-base-components.mjs` | PASS |
| `node frontend/scripts/validate-v2-support-components.mjs` | PASS (5 support components, 14 exports) |
| `node frontend/scripts/validate-v2-dropdown.mjs` | PASS |
| `node frontend/scripts/validate-v2-api-cases-direct-mapping.mjs` | PASS |
| `npm --prefix frontend run build` | PASS (155 modules) |
| `git diff --check` | PASS；仅工作区既有 LF/CRLF 提示，无 whitespace error |

项目没有可声明为已执行的独立 frontend lint/test script；本报告不虚构相关结果。

## Browser Verification

- 实际地址：`http://127.0.0.1:8000/v3/api-cases`（production build）；alias `/v3/apiCases` 同样加载 20 行、总计 82 条。
- 管理员使用真实账号完成登录；canonical/alias、刷新、返回、前进均通过。
- 首屏：80 个 Row Action Button、40 个 Badge、20 个 Checkbox；目标 `.btn/.badge/.pagination` 为 0；Portal 为 0。
- 新开干净 V2 页面：Console 0 error / 0 warning；首屏只有 1 次 API Cases list 请求，没有迁移引入的新 endpoint。
- Dashboard 回归：5 个 V2 Card 正常，Console 仍为 0；返回 API Cases 正常。
- 受控空列表响应显示现有 AppTable `暂无数据`，摘要为 `共 0 条，第 1/1 页`；解除受控响应后恢复真实列表。
- legacy `/`：V2 Token 0、`.frontend-v2` 0、`.frontend-v2-portal` 0、Console 0 error / 0 warning。

## Permission Matrix

| Capability | Admin | Normal user |
|---|---|---|
| Read / Execute | PASS | 环境无账号，未伪造 |
| Create | Visible and exercised | 环境无账号，未伪造 |
| Copy / Edit / Delete | Visible and exercised | 环境无账号，未伪造 |
| Backend permission contract | 未修改 | 未修改 |

当前用户接口仅存在 `admin`。本阶段没有创建临时普通用户或绕过认证。

## Selection Regression

- Checkbox accessible name 包含用例名称；Space 可选择和取消。
- 多选两行后 Batch 文案为 `批量执行 2`，disabled 正确解除。
- 按现有受保护逻辑，翻页保留选择；项目/环境切换清空选择并重置第 1 页。
- 真实 Batch 请求 payload 的 `case_ids: [83]` 与勾选的临时用例 ID 83 一致；完成后进入 `/records`。

## Pagination Regression

- 第一、中间、最后页及 Previous/Next 均通过；最后页 Next disabled，第一页 Previous disabled。
- `aria-current="page"` 正确；Enter 切换至第 2 页，Space 切换至第 3 页。
- 当前页点击产生 0 次 list 请求；disabled Previous 产生 0 次请求；每次有效切页只产生 1 次请求。
- 受控 page 5 / total 20 响应触发现有越界恢复：依次请求 page 5、page 1，最终恢复真实第 1 页。
- 摘要与 total 正确；page size 仍为 20，`siblingCount` 为 2。

## CRUD / Execution Regression

- 使用现有 AppFormDialog 完成临时用例 Create (200)、Edit (200)、Copy (200)、Delete；临时 API Cases 最终剩余 0。
- Delete 仍使用现有 native confirm。
- 单条 Execute (200) 与 Batch Execute (200) 均进入 `/records`。
- 执行专用临时用例使用空 assertion contract，使现有执行器在外部 HTTP 请求前安全失败；没有请求配置中的真实 Japan/OEM 外部站点。单条结果为 failed，Batch 返回 1 条记录且 `passed=false`，符合该专用输入。
- Browser 验证产生的两条执行记录按平台既有行为保留；没有将数据库、reports 或运行产物加入 Git。

## Accessibility Audit

- 每行 Checkbox 具有包含 Case 名称或 ID 的 accessible name；Space 行为正常。
- Pagination 为命名 nav，当前页使用 `aria-current="page"`，边界按钮原生 disabled。
- BaseButton 均为显式 `type="button"`；Row actions 保留清晰文字名称。
- Method/Status Badge 保留可读文本。

## Responsive Verification

| Width | Document overflow | AppTable overflow-x | Toolbar/actions | Pagination |
|---:|---|---|---|---|
| 1080 | none | auto；内容宽 986 / 容器 752 | visible / reachable | visible |
| 1240 | none | auto；内容宽 986 / 容器 912 | visible / reachable | visible |
| 1440 | none | auto | visible / reachable | visible |
| 1920 | none | auto | visible / reachable | visible |

Toolbar 顺序未变；每档均保留 2 个 Toolbar Button、80 个首屏 Row Action Button，AppTable 原有横向滚动合同保留。

## Diff Audit

- 本阶段创建：阶段 Validator、阶段报告。
- 本阶段修改：`ApiCasesView.vue`、Supporting Validator。
- `tokens.component.css` 当前存在其他 Frontend V2 阶段的未提交改动，但 Phase 5.5B 未修改该文件。
- API、Router、Store、AppTable、AppFormDialog、AppModal、AppToast、package/lockfile 均未被本阶段修改。
- 未暂存、未提交、未推送；无关 payment/system/backend/test 改动保持原样。

## Contract Gaps

继续保留到后续阶段：BaseSelect、BaseTextarea、BaseTable/ResourceTable、BaseModal、BaseToast、Form Contract、Confirm Contract。AppTable、Project/Environment Select 与 Dialog/Form 本阶段仍为合法 legacy/既有结构。

## Remaining Risks

- 环境没有普通用户账号，因此 normal 用户真实登录矩阵只能明确记录为环境条件缺失。
- 空结果和页码越界使用浏览器内受控 API 响应验证 UI/生命周期；当前真实数据的两个项目均有用例，无法通过真实筛选自然得到空结果。
- GitNexus 对整个混合未提交工作区报告 `critical`：31 个 tracked 文件、52 个符号、290 条受影响流程。该结果包含 payment/system/backend/tests 等本阶段未触碰改动，不能解释为 Phase 5.5B 独立风险；在工作区拆分前禁止整体暂存或提交。
- 工作区仍混有大量其他任务未提交改动，后续暂存时必须精确列文件，禁止 `git add .`。
