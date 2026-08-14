# Frontend V3 Light Workbench Visual Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. 每个 Task 开始前先报告预计修改文件与 GitNexus impact 结果；每个 Task 完成后写入同一份阶段报告并停止，等待人工确认，不自动进入下一 Task。

**Goal:** 只通过 CSS、Design Tokens、现有组件的 `<style>` 区域和 legacy 页面的既有样式入口，把当前项目统一升级为已确认的浅色 Frontend V3 Workbench 视觉；所有源码中现存的功能、字段、按钮、入口、接口、权限、状态、流程和操作习惯保持不变，功能变化为 0。

**Architecture:** 以“源码决定功能，UI 图决定视觉”为最高原则，建立“新 V3 浅色视觉合同 → 公共 Token → 基础组件 → Workbench 组合组件 → Shell → 逐页面样式”的单向视觉依赖。Vue 原生页只允许修改 `<style>`；legacy 内嵌页只允许修改已加载 CSS 或 HTML 内的 `<style>`；Router、API、Store、事件、props、emits、v-model、watcher、生命周期、Storage、轮询、权限和后端全部冻结。通过机器可读的 style-only 校验器比较修改前后的非样式区域，防止任何业务漂移。

**Tech Stack:** Vue 3.5、Vue Router 4.4、Pinia 2.2、Vite 5.4、现有 `--v2-*`/legacy CSS Tokens、静态 HTML/CSS、Node 校验脚本、FastAPI 0.115、项目 Python 3.11 venv。

## Global Constraints

- **最高优先级：** 源码决定功能，11 张新 UI 图和 `docs/ui-redesign/README-CODEX.md` 只决定视觉。
- **新旧视觉优先级：** 本次 Frontend V3 Workbench Redesign 中，`docs/ui-redesign/` 的新图在视觉层面优先于旧的深色 `232px / 62px` 合同；不得用旧合同覆盖新设计。
- **旧规范保留：** 不删除、不覆盖、不改写 `docs/frontend-v2/visual-baseline/VISUAL-CONTRACT.md` 与 `docs/frontend-v2/visual-baseline/workbench-v1-v2-hybrid.png`。它们作为历史基线保留；旧代码中的业务行为仍全部保留。
- **冲突处理：** 新图与源码在功能上冲突时，以源码为准；新图与旧视觉合同在颜色、尺寸、排版上冲突时，以新图为准。
- **视觉说明板边界：** 11 张图右侧的“状态设计 / 关键弹窗 / 真实交互流程”是设计注释，不是要新增的产品区域；示例数据不是种子数据，也不得写入运行时代码。
- **禁止行为：** 不新增、删除、隐藏、合并、重命名或移动任何已有功能、按钮、字段、列、菜单、弹窗、状态和流程；不新增图中但源码不存在的搜索、指标、筛选、图表、快捷入口和操作。
- **生产代码修改白名单：** CSS 文件、Vue SFC 的 `<style>` 区域、静态管理页的 `<style>` 区域。非样式区域必须逐字节保持与实施前 HEAD 一致。
- **冻结区：** `app/`、数据库、`frontend/src/api/`、`frontend/src/router/`、`frontend/src/stores/`、`frontend/src/services/`、`static/*.js`、`static/migration-config.json`、Vue 的 template/script、HTML 的 DOM/script、配置和依赖清单全部禁止修改。
- **现有显示条件不变：** `v-if`、adminOnly、normal/admin、disabled、loading、empty、error、permission、polling、recording、execution、retry 条件均保持源码原样；CSS 不得用 `display:none`、`visibility:hidden`、零尺寸、移出视口等方式隐藏现有能力。
- **无新依赖：** 不安装 UI 框架、字体包、图标包、图表库或动画库；不使用远程资源替代现有资源。
- **Git 安全：** 每个 Task 前后运行 `git status --short`；保留当前用户未跟踪的 `.pytest_cache/` 与 `docs/ui-redesign/`；不使用 `git add -A`，不 commit、不 push，除非用户另行明确授权。
- **GitNexus：** 若修改组件样式前可用，对组件名执行 upstream impact；HIGH/CRITICAL 必须先警告并停止。纯 CSS 无符号结果记录为“无业务符号影响”。提交前如未来获准提交，必须运行 `detect_changes()`。
- **阶段报告：** 所有 Task 结果追加到 `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`；不创建散落截图、临时文件或调试文件。
- **浏览器边界：** 本计划的强制验证使用源码冻结、现有 parity validator、构建、pytest 和服务 HTTP smoke。除非用户在执行阶段另行明确授权，不启动或控制浏览器；获授权后才执行 1080/1240/1440/1920 的视觉截图验收。

---

## Active Visual Contract

新图中重复出现且由 `README-CODEX.md` 明确支持的视觉常量：

```css
--v3-workspace: #e8eef5;
--v3-sidebar: #c9d9e7;
--v3-primary: #245fa8;
--v3-section: #dde7f0;
--v3-panel: #ffffff;
--v3-border: #b9c8d6;
--v3-text: #172b3f;
--v3-sidebar-width: 220px;
--v3-topbar-height: 56px;
--v3-panel-radius: 8px;
```

实现时继续使用项目既有 Token 命名和加载顺序，将上述值映射到 `--v2-*` 与 legacy semantic tokens；业务组件不得直接散落硬编码颜色。视觉限制为：冷灰蓝工作区、浅灰蓝侧栏、白色 Panel、钴蓝主操作、细边框、轻微或无阴影、无渐变、无玻璃拟态、无霓虹、无重阴影、无无意义动画。

## New Reference Integrity

新视觉校验器必须锁定以下 SHA-256，防止实施过程中参考图被替换：

| Reference | SHA-256 |
|---|---|
| `01-dashboard.png` | `20d9b7fa26414accb62ebf99e3f9fc95f5cba9b13abf3abe3a4de56232730613` |
| `02-projects.png` | `7623c651cb6c50bb4f5a3e0d3c16ab32dfa7ece5604c1f3ddddf4cf1282f468d` |
| `03-api-cases.png` | `18e2c6ecf4b1a70f9507ab5b9dbe3ab23b268424d9fb58bc2a3b602e4ef19b60` |
| `04-data-factory.png` | `9d6011275f7836c7bba4aa9713fb5aa7f02dba9cf7bbff8aca65ebf96c49d410` |
| `05-requirement-verification.png` | `4fc6f7132412b4387b213d2c4e7cd37687b16c7fc7d91d40534feaf75f6a97b8` |
| `06-ui-automation.png` | `4b22908b924e9cf98be20b0c55ba7935031da081065fa9634a7dcd8508ecd5a1` |
| `07-records.png` | `77601b0bf4cffec1d748ea106af9ccab6b8c68179caef30c22b061553c307d0f` |
| `08-system-regression.png` | `9de7600cd6a04103064a065ef7536ca03ae512650b007d79fe5f8da20c756bd1` |
| `09-users-ai.png` | `eafe8ff34a9fe362263b44b582a73bf130035af35d9cee08cb82cee2f1d35fbc` |
| `10-admin-utilities.png` | `931199bbe79ac14d316118ac9bc7a4db1e172b74e90c04c3db3a86c3364f805b` |
| `11-login.png` | `f58673304cd0c5d6b15d582b448e3ec0e1b379125106821a24cd8eaf05af7544` |

旧视觉资产也必须保持字节不变：

- `VISUAL-CONTRACT.md`: `894aa143521a1c8b9b9155629fcdcbb2a59c25a35364ab5e37ddc1bf4b74fd03`
- `workbench-v1-v2-hybrid.png`: `369c441945cee1afa3e3295a01951ec2e281369825668bdbacf3b8e2e1472263`

---

## Source-of-Truth Route and Surface Inventory

| Surface | Current live implementation | Functional contract that must remain |
|---|---|---|
| 登录 | `frontend/src/views/LoginView.vue` + `static/login.css` | 账号、密码、记住密码、登录 loading/error、token、redirect/migration 跳转；不新增注册/忘记密码 |
| 工作台 | `frontend/src/views/DashboardView.vue` | 项目筛选、真实统计、趋势/关注/最近记录、日志/报告/截图/跳转以及真实 loading/empty/error |
| 项目空间 | `frontend/src/views/ProjectsView.vue` | 项目、环境、测试账号档案、项目默认账号绑定；admin CRUD、normal 只读；全部原字段和弹窗 |
| 接口用例库 | `frontend/src/views/ApiCasesView.vue` | 项目/环境筛选、checkbox、批量执行、运行变量、分页、执行；admin 新增/复制/编辑/删除；全部列和表单字段 |
| 数据工厂 | `/v3/data-scripts` 实际路由为 `LegacyEmbedView.vue`，业务 DOM/事件由 `static/app.js`、`static/full-flow.js`、`static/data-factory-agent.js` 等提供 | 活跃/隐藏/已删除脚本、编辑、动态参数、组合流程、录制、执行、结果、Agent 确认/风险/权限/取消/状态、现有 Storage/API 全部保留 |
| 需求验证中心 | `frontend/src/views/RequirementVerificationView.vue` | 任务列表/搜索/项目、新建、分析、预检、执行、暂停/继续/取消、删除、运行状态与源码已有错误/空态 |
| UI 自动化 | `frontend/src/views/UiCasesView.vue` + `components/ui-cases/*` | UI 用例筛选/CRUD/执行、账号、录制生命周期、步骤、轮询、进度、截图、变量提取、日志/结果、卸载清理 |
| 执行报告 | `frontend/src/views/RecordsView.vue` | 项目/类型筛选、分页、再次执行 api/ui、日志/报告/截图、结果与权限边界 |
| 系统回归 | `/v3/system-regression` 实际路由为 `LegacyEmbedView.vue`，业务由 `static/system-regression.js` 提供 | adminOnly、分类/用例/参数、选择、保存/复制/恢复默认、单条/批量、停止、失败重跑、账号补充后继续、证据 |
| 权限中心 | `frontend/src/views/UsersView.vue` | adminOnly、用户新增/编辑/删除、username/password/role，角色仅 admin/normal |
| 全局 AI 配置 | `frontend/src/components/AiConfigDialog.vue` | adminOnly、读取/保存/测试连接、现有服务类型/API 地址/模型/API Key 字段和接口 |
| 管理员辅助页 | `static/admin/templates.html`、`static/admin/heal-logs.html` | 模板项目筛选/CRUD/步骤编辑/测试运行；自愈记录筛选/分页/展开/截图/确认应用/拒绝/撤销及 token/登录校验 |
| legacy `/` | `static/index.html` + `static/*.css` + 现有 JS | legacy 应用继续可用；不得删除它因新图未展示的入口或能力 |

`frontend/src/views/DataScriptsView.vue` 与 `frontend/src/views/SystemRegressionView.vue` 当前不是上述两个路由的 live 渲染实现。本次不切换路由、不迁移业务、不修改这两个 dormant view；实际视觉改造必须落在 legacy embed 的真实 CSS 表面。

---

### Task 1: 建立视觉优先级合同与 style-only 防线

**Files:**
- Create: `docs/ui-redesign/V3-LIGHT-VISUAL-CONTRACT.md`
- Create: `frontend/scripts/validate-v3-light-visual-contract.mjs`
- Create: `frontend/scripts/validate-v3-style-only-scope.mjs`
- Modify: `frontend/scripts/validate-v3-visual-contract.mjs`
- Modify: `docs/frontend-v2/handoff/CURRENT-TASK.md`
- Modify: `docs/frontend-v2/handoff/STATE.json`
- Create/append: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`
- Read-only, hash-locked: `docs/frontend-v2/visual-baseline/VISUAL-CONTRACT.md`
- Read-only, hash-locked: `docs/frontend-v2/visual-baseline/workbench-v1-v2-hybrid.png`

**Visual changes:** 此 Task 不改生产样式。新合同记录 220px 浅灰蓝侧栏、56px 顶栏、`#E8EEF5/#C9D9E7/#245FA8`、白色 Panel、8px、细边框和禁用效果；明确新图仅在视觉层面优先，旧合同作为历史资料保留。

**Functional protection checks:**
- `validate-v3-style-only-scope.mjs` 以实施开始时 HEAD 为基线：CSS 文件允许变化；Vue/HTML 文件剥离所有 `<style>` 后必须完全一致；Router/API/Store/Service/static JS/backend/config/db 不得出现在 diff。
- 校验所有既有路由名、path、viewKey、adminOnly、菜单项、接口模块、Storage key 和 static JS 文件未变化。
- 管理页 HTML 仅允许 `<style>` 内容变化，DOM、script、远程调用和按钮文本冻结。
- 新旧 13 个视觉参考资产（11 张新图 + 2 个旧资产）均锁定哈希。

**Steps and verification:**
- [ ] 运行 `git status --short`、`git branch --show-current`、`git rev-parse HEAD`，记录工作树中用户已有内容。
- [ ] 创建 style-only validator，并先运行 `node frontend/scripts/validate-v3-style-only-scope.mjs`，期望 PASS。
- [ ] 创建新视觉 validator；在 Token 未切换前运行，期望以缺少 active light declarations 的明确原因 RED。
- [ ] 调整旧 `validate-v3-visual-contract.mjs`：继续验证旧合同/旧图哈希，但把“当前活动视觉”的判定委托给新 validator；不得修改旧合同文件本身。
- [ ] 运行所有现有 parity validator，记录当前基线，不为修复既有失败而改业务代码。
- [ ] 将结果写入阶段报告并停止，等待 Task 2 确认。

---

### Task 2: 统一 Vue 与 legacy Design Tokens

**Files:**
- Modify: `frontend/src/styles/v2/tokens.foundation.css`
- Modify: `frontend/src/styles/v2/tokens.semantic.css`
- Modify: `frontend/src/styles/v2/tokens.component.css`
- Modify: `frontend/src/styles/v2/base.css`
- Modify: `static/design-tokens.css`
- Modify: `static/design-system-base.css`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`

**Why more than two files:** Vue 与 legacy 同时加载两套既有 Token 命名；必须在各自唯一的 Token/基础层同步映射，才能避免页面内散落硬编码和互相覆盖。

**Visual changes:** 将活动工作区、侧栏、主操作、边框、Panel、字体、间距、控件高度、表格密度、焦点环、disabled、状态色、阴影和布局映射到新合同；活动 Shell 固定 220px/56px，Panel 8px；保留历史 dark/forest token 声明但不再作为本次 V3 活动映射。

**Functional protection checks:**
- 所有 CSS selector 仍指向已有 DOM；不新增/删除 HTML、Vue template、script。
- 保持已有 theme lock 和 disabled/hidden 的源码条件原样；不得用 CSS 新增隐藏。
- 不改变 z-index 语义导致 Modal、Dropdown、Toast、录制/执行浮层不可用。
- 不改变日志等价宽内容的可滚动性，不通过裁切删除信息。

**Steps and verification:**
- [ ] 对 Token 使用点做定点 `rg`，记录 legacy 与 Vue 消费关系；若 GitNexus 可用，对受影响组件执行 upstream impact。
- [ ] 先修改 foundation/semantic token，再修改 component mapping，最后调整两套 base 样式；禁止页面级硬编码新主色。
- [ ] `node frontend/scripts/validate-v3-light-visual-contract.mjs` 从 RED 变为 GREEN。
- [ ] `node frontend/scripts/validate-v3-visual-contract.mjs` PASS，并确认旧合同哈希仍一致。
- [ ] `node frontend/scripts/validate-v3-style-only-scope.mjs` PASS。
- [ ] `node frontend/scripts/validate-v2-foundation.mjs` 与 `npm run build` PASS。
- [ ] 写阶段报告并停止。

---

### Task 3: 公共基础组件视觉统一

**Files — modify `<style>` only:**
- `frontend/src/components/v2/base/BaseBadge.vue`
- `frontend/src/components/v2/base/BaseButton.vue`
- `frontend/src/components/v2/base/BaseCard.vue`
- `frontend/src/components/v2/base/BaseCheckbox.vue`
- `frontend/src/components/v2/base/BaseChip.vue`
- `frontend/src/components/v2/base/BaseDropdown.vue`
- `frontend/src/components/v2/base/BaseDropdownItem.vue`
- `frontend/src/components/v2/base/BaseEmptyState.vue`
- `frontend/src/components/v2/base/BaseErrorState.vue`
- `frontend/src/components/v2/base/BaseIconButton.vue`
- `frontend/src/components/v2/base/BaseInput.vue`
- `frontend/src/components/v2/base/BaseModal.vue`
- `frontend/src/components/v2/base/BasePagination.vue`
- `frontend/src/components/v2/base/BaseSelect.vue`
- `frontend/src/components/v2/base/BaseSkeleton.vue`
- `frontend/src/components/v2/base/BaseTable.vue`
- `frontend/src/components/v2/base/BaseTextarea.vue`
- `frontend/src/components/v2/base/BaseTooltip.vue`
- `frontend/src/components/AppFormDialog.vue`
- `frontend/src/components/AppModal.vue`
- `frontend/src/components/AppPagination.vue`
- `frontend/src/components/AppTable.vue`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`

**Why grouped:** 这些是同一公共视觉层的原子组件；拆开会在中间阶段产生 Button/Input/Table/Modal 不一致。所有文件仍只改 style，不触碰公共接口。

**Visual changes:** 统一 32/40px 控件、6–8px 圆角、细冷色边框、钴蓝 focus/selected/primary、克制 hover/pressed、浅色 disabled、紧凑表头/行高、分页、Badge、Skeleton、Empty/Error/Permission 容器、Dropdown 与 Modal；仅 Skeleton 保留轻量加载动画，不加入装饰动画。

**Functional protection checks:**
- props、emits、slots、v-model、键盘行为、focus trap、scroll lock、portal、点击遮罩关闭、确认/取消、loading/disabled 条件逐字节不变。
- 表格列、checkbox selection、排序、分页事件、操作插槽不变。
- Empty/Error/Permission 只美化现有 slot/文案，不新增 CTA；Retry 仅保留原有 emit。
- Modal 表单字段、required、validator、默认值、提交按钮行为不变。

**Steps and verification:**
- [ ] 对每个拟修改组件名运行 upstream impact；HIGH/CRITICAL 时停止报告。
- [ ] 按 Button/Form → Table/Pagination/Badge → Overlay/State 的顺序只改 style。
- [ ] `node frontend/scripts/validate-v2-base-components.mjs`、`validate-v2-dropdown.mjs`、`validate-v2-modal-foundation.mjs`、`validate-v2-support-components.mjs` PASS。
- [ ] `node frontend/scripts/validate-v3-workbench-components.mjs`、`validate-v3-style-only-scope.mjs`、`npm run build` PASS。
- [ ] 写阶段报告并停止。

---

### Task 4: Workbench 页面构件视觉统一

**Files — modify `<style>` only:**
- `frontend/src/components/v2/workbench/WorkbenchPageHeader.vue`
- `frontend/src/components/v2/workbench/WorkbenchPanel.vue`
- `frontend/src/components/v2/workbench/WorkbenchMetricRail.vue`
- `frontend/src/components/v2/workbench/WorkbenchTrendChart.vue`
- `frontend/src/components/v2/workbench/WorkbenchAttentionList.vue`
- `frontend/src/components/v2/workbench/WorkbenchStatus.vue`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`

**Visual changes:** 统一图中浅蓝页面 Header（左侧钴蓝识别条、eyebrow/title/description/action）、白色 Panel、紧凑 section toolbar、指标条、趋势 SVG、关注列表和状态块；右侧设计说明板不进入产品 DOM。

**Functional protection checks:**
- 组件 props/emits/slots、真实数据数组、SVG 数据映射、点击 action emit、loading/empty/error 分支全部不变。
- 不硬编码图中示例指标、趋势或记录；无真实数据时只使用源码已有 empty。
- 不增加 Header 操作按钮，不把现有操作折叠进“更多”。

**Steps and verification:**
- [ ] 运行各组件 upstream impact。
- [ ] 仅修改 style，让所有页面可通过现有 slot 获得统一外观。
- [ ] `node frontend/scripts/validate-v3-workbench-components.mjs`、`validate-v3-light-visual-contract.mjs`、`validate-v3-style-only-scope.mjs` PASS。
- [ ] `npm run build` PASS，写阶段报告并停止。

---

### Task 5: 全局 Shell 与登录页

**Files — modify style only:**
- `frontend/src/components/AppShell.vue`
- `static/login.css`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`

**Visual changes:** AppShell 使用 220px 浅灰蓝侧栏、56px 白色顶栏、冷灰蓝工作区、分组菜单、浅蓝 active 与 3px 钴蓝指示条、底部账号区；保留并按新图显示现有 Q 品牌标识。登录页改为冷灰蓝画布、白色紧凑卡片、钴蓝按钮、细边框和现有 Toast 错误样式。

**Functional protection checks:**
- 菜单完整保留 dashboard/projects/apiCases/dataScripts/requirementVerification/uiCases/records/systemRegression/users；顺序、route、viewKey、adminOnly 不变。
- 当前项目选择器、面包屑、全局 AI 配置、退出、角色、模板管理、自愈记录入口全部保留；不新增搜索/通知。
- 登录账号/密码/记住密码、loading、错误、token 和 redirect/migration 跳转不变；不新增注册/忘记密码。
- 不用 CSS 隐藏 normal/admin 已有能力；系统回归、用户、AI 配置继续由源码权限控制。

**Steps and verification:**
- [ ] 对 `AppShell` 和 `LoginView` 执行 upstream impact，记录 route/auth 影响但只改样式。
- [ ] 修改 `AppShell.vue` 的 `<style scoped>` 和 `static/login.css`，不改 template/script。
- [ ] `node frontend/scripts/validate-v3-shell-contract.mjs`、`validate-login-redirect.mjs`、`validate-v3-style-only-scope.mjs` PASS。
- [ ] `npm run build` PASS，写阶段报告并停止。

---

### Task 6: 工作台视觉升级

**Files — modify `<style>` only:**
- `frontend/src/views/DashboardView.vue`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`

**Visual changes:** 对齐 `01-dashboard.png` 的 Header、项目筛选、统计条、趋势/关注双列区和最近执行表；提高信息密度并保持白色 Panel、浅蓝分区、克制状态色。

**Functional protection checks:** 项目筛选、真实 dashboard/records 请求、计数、趋势数据、关注项、最近记录、日志/报告/截图/跳转、loading/empty/error 全部保留；不引入图中示例数据或新指标。

**Steps and verification:**
- [ ] 对 `DashboardView` 执行 upstream impact。
- [ ] 仅改 `<style scoped>`，禁止改变已有 Workbench 组件、数据派生或事件。
- [ ] `node frontend/scripts/validate-v3-dashboard-style-only.mjs`、`validate-v3-dashboard-contract.mjs`、`validate-v3-style-only-scope.mjs` PASS。
- [ ] `npm run build` PASS；对照功能清单确认所有入口仍在；写阶段报告并停止。

---

### Task 7: 项目空间视觉升级

**Files — modify `<style>` only:**
- `frontend/src/views/ProjectsView.vue`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`

**Visual changes:** 对齐 `02-projects.png`，把项目、环境配置、测试账号档案作为三个清晰但不合并的 section；统一 toolbar、表格、Badge、账号变量块和新增/编辑/删除/绑定弹窗视觉。

**Functional protection checks:**
- 项目列、环境列、账号列全部保留；空间不足通过宽度/换行/滚动解决，不删列。
- admin 的新增/编辑/删除/账号绑定与 normal 只读保持；默认账号绑定、全局/项目账号范围不变。
- 项目、环境、账号所有表单字段、默认值、required、JSON、提交 API 不变。
- loading/empty/error/permission 与删除确认保持原逻辑。

**Steps and verification:**
- [ ] 对 `ProjectsView` 执行 upstream impact。
- [ ] 仅改 style，并逐项对照三张表、三个 CRUD 域和绑定弹窗。
- [ ] `node frontend/scripts/validate-v3-core-pages-parity.mjs`、`validate-v3-style-only-scope.mjs` PASS。
- [ ] `npm run build` PASS，写阶段报告并停止。

---

### Task 8: 接口用例库视觉升级

**Files — modify `<style>` only:**
- `frontend/src/views/ApiCasesView.vue`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`

**Visual changes:** 对齐 `03-api-cases.png`，使用紧凑筛选工具栏、密集表格、方法/状态 Badge、清晰操作列、分页、运行变量和执行结果弹窗；不改变列或操作分布。

**Functional protection checks:**
- 项目/环境筛选、checkbox、批量选择、批量执行、分页、单条执行保持。
- admin 新增/复制/编辑/删除，normal 可执行权限保持。
- project/env/name/method/url/headers/params/body/assert/status 全字段保持；JSON、required、默认值和 payload 不变。
- disabled 仅由现有选中数量/请求状态决定；不新增搜索、排序或筛选。

**Steps and verification:**
- [ ] 对 `ApiCasesView` 执行 upstream impact。
- [ ] 仅改 style；操作按钮不得隐藏到新菜单。
- [ ] `node frontend/scripts/validate-v2-api-cases-direct-mapping.mjs`、`validate-v2-api-cases-foundation-integration.mjs`、`validate-v3-core-pages-parity.mjs`、`validate-v3-style-only-scope.mjs` PASS。
- [ ] `npm run build` PASS，写阶段报告并停止。

---

### Task 9: 数据工厂 legacy embed 视觉升级

**Files — modify CSS only:**
- `static/styles.css`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`
- Read-only business sources: `frontend/src/views/LegacyEmbedView.vue`, `static/app.js`, `static/full-flow.js`, `static/data-factory-agent.js`, `frontend/src/views/DataScriptsView.vue`

**Visual changes:** 对齐 `04-data-factory.png`，只用已有 `.factory-*`、脚本目录、editor、runner、agent、flow、result、modal 等 selector 调整目录表、编辑区、执行区、日志/结果、状态、Agent 对话/确认/风险/权限视觉。对 embed 使用 `html.v3-embed` 和数据工厂专属 class 限定，避免污染其它页。

**Functional protection checks:**
- 活跃/隐藏/已删除脚本、内置/自定义/组合流程、编辑/恢复/删除、动态字段、录制、执行全部保留。
- Agent 创建会话、目标理解、确认、风险、权限、工具执行、取消、轮询、完成/失败状态全部保留。
- 所有 API、Storage key、事件绑定、动态 DOM 字符串、执行记录 kind、参数/返回值不变。
- 不把 `DataScriptsView.vue` 接入路由，不做 Vue 迁移，不用设计图示例脚本新增业务。

**Steps and verification:**
- [ ] 对 legacy 数据工厂相关 render symbol 执行 read-only context/impact；只报告 blast radius，不编辑 JS。
- [ ] 在 `static/styles.css` 的既有 data factory / `html.v3-embed` 样式区做最小覆盖，禁止改 JS/HTML。
- [ ] `node frontend/scripts/validate-v3-data-scripts-parity.mjs`、`validate-v2-legacy-embed.mjs`、`validate-v3-style-only-scope.mjs` PASS。
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py tests/test_data_factory_agent_contract.py -v` PASS。
- [ ] `npm run build` PASS，写阶段报告并停止。

---

### Task 10: 需求验证中心视觉升级

**Files — modify `<style>` only:**
- `frontend/src/views/RequirementVerificationView.vue`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`

**Visual changes:** 对齐 `05-requirement-verification.png`，在现有 DOM 上形成任务列表与工作区、状态 Badge、阶段/运行面板、操作区和日志/错误块的高密度浅色布局。

**Functional protection checks:** 任务列表、搜索、项目选择、新建、分析、预检、执行、暂停/继续/取消、删除、运行状态、轮询、错误/空态全部以当前源码为准；图中源码不存在的材料、澄清、公式或 CTA 不得新增。

**Steps and verification:**
- [ ] 对 `RequirementVerificationView` 执行 upstream impact。
- [ ] 仅改 style，不改变任务状态机、API、timer 或按钮条件。
- [ ] `node frontend/scripts/validate-v3-requirement-verification-parity.mjs`、`validate-v3-style-only-scope.mjs` PASS。
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_requirement_verification_v2.py tests/test_requirement_verifications.py -v` PASS。
- [ ] `npm run build` PASS，写阶段报告并停止。

---

### Task 11: UI 自动化视觉升级

**Files — modify `<style>` only:**
- `frontend/src/views/UiCasesView.vue`
- `frontend/src/components/ui-cases/UiCaseForm.vue`
- `frontend/src/components/ui-cases/UiExecutionPanel.vue`
- `frontend/src/components/ui-cases/UiRecordingPanel.vue`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`

**Visual changes:** 对齐 `06-ui-automation.png`，统一用例表、筛选/操作栏、录制面板、执行进度、步骤、日志、截图、变量提取、结果状态和现有表单/弹窗；四个文件属于同一现有 UI 自动化页面，不拆业务。

**Functional protection checks:**
- 项目筛选、admin 录制/新增/编辑/删除、登录用户执行、账号选择和表单字段全部保留。
- recording session 创建/读取/停止/取消/保存、execution 创建/轮询/终态/取消、截图和变量提取不变。
- timer、watcher、onBeforeUnmount 清理、错误重试、disabled 条件和权限不变。
- 不增加图中示例步骤、进度或截图；不调整事件和 props/emits。

**Steps and verification:**
- [ ] 对 View 与三个子组件执行 upstream impact。
- [ ] 仅改各自 style，保证长步骤/JSON/日志通过滚动与换行完整可见。
- [ ] `node frontend/scripts/validate-v3-ui-cases-parity.mjs`、`validate-v3-style-only-scope.mjs` PASS。
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_ui_recording.py -v` PASS。
- [ ] `npm run build` PASS，写阶段报告并停止。

---

### Task 12: 执行报告视觉升级

**Files — modify `<style>` only:**
- `frontend/src/views/RecordsView.vue`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`

**Visual changes:** 对齐 `07-records.png`，统一筛选、执行记录表、结果 Badge、分页、脚本结构化摘要、日志/报告/截图证据入口和弹窗。

**Functional protection checks:** 项目/类型筛选、全部列、分页、api/ui 再次执行、日志、报告、截图、结果/时间、现有 permission/loading/empty/error 保持；data_agent 等记录只展示源码真实支持的操作，不新增再次执行。

**Steps and verification:**
- [ ] 对 `RecordsView` 执行 upstream impact。
- [ ] 仅改 style，不改变 record type 分支、action 条件或详情内容。
- [ ] `node frontend/scripts/validate-v3-core-pages-parity.mjs`、`validate-v3-style-only-scope.mjs` PASS。
- [ ] `npm run build` PASS，写阶段报告并停止。

---

### Task 13: 系统回归 legacy embed 视觉升级

**Files — modify CSS only:**
- `static/system-regression.css`
- `static/styles.css`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`
- Read-only business sources: `frontend/src/views/LegacyEmbedView.vue`, `static/system-regression.js`, `frontend/src/views/SystemRegressionView.vue`

**Visual changes:** 对齐 `08-system-regression.png`，使用既有 `.sr-*` selector 调整顶部项目/环境/客户参数、分类列表、用例列表、参数编辑、批次进度、证据与账号补充弹窗；保持与全局浅色 Token 一致。

**Functional protection checks:**
- adminOnly 与 normal 不可达保持；不改变 Router 守卫和 legacy 权限判断。
- 分类/选择、参数字段、保存、复制、恢复默认、单条/批量、停止、失败重跑、waiting_account、补充账号继续、轮询与证据保持。
- 不切换到 dormant `SystemRegressionView.vue`，不改 `system-regression.js`、API、Storage 或状态机。

**Steps and verification:**
- [ ] 对 system regression render/batch symbol 做 read-only impact；只改 CSS。
- [ ] 以 `.sr-*` 和 `html.v3-embed` 限定覆盖，避免影响数据工厂和其它 legacy 页。
- [ ] `node frontend/scripts/validate-v3-system-regression-parity.mjs`、`validate-v2-legacy-embed.mjs`、`validate-v3-style-only-scope.mjs` PASS。
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_system_regression_frontend.py tests/test_system_regression_execution_contract.py tests/test_system_regression_account_resume.py -v` PASS。
- [ ] `npm run build` PASS，写阶段报告并停止。

---

### Task 14: 权限中心与全局 AI 配置视觉升级

**Files — modify `<style>` only:**
- `frontend/src/views/UsersView.vue`
- `frontend/src/components/AiConfigDialog.vue`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`

**Visual changes:** 对齐 `09-users-ai.png`，统一用户表、admin/normal Badge、用户表单、全局 AI 配置表单、警告/说明、测试连接与保存按钮；仍作为当前独立页面和 Shell 顶栏弹窗，不把图中并排示意改成新业务页面。

**Functional protection checks:**
- Users 与 AI 配置继续 adminOnly；normal 菜单/路由/接口能力不变。
- 用户新增/编辑/删除、username/password/role 字段、角色枚举 admin/normal 不变。
- AI 配置读取、测试、保存与服务类型/API 地址/模型/API Key 字段、密钥掩码、运行中配置提示不变。
- 不合并两个模块，不新增模型选项或角色。

**Steps and verification:**
- [ ] 对 `UsersView`、`AiConfigDialog` 执行 upstream impact。
- [ ] 仅改 style；逐字节校验 template/script。
- [ ] `node frontend/scripts/validate-v3-core-pages-parity.mjs`、`validate-v3-shell-contract.mjs`、`validate-v3-style-only-scope.mjs` PASS。
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_permissions.py -v` PASS。
- [ ] `npm run build` PASS，写阶段报告并停止。

---

### Task 15: 管理员辅助页视觉升级

**Files — modify inline `<style>` only:**
- `static/admin/templates.html`
- `static/admin/heal-logs.html`
- Append report: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`

**Visual changes:** 对齐 `10-admin-utilities.png`，统一独立管理页的 Header、项目筛选、模板卡片/列表、步骤编辑表、自愈记录卡片、状态 Badge、详情/截图/确认弹窗和返回平台入口；仍保持两个独立页面，不合并。

**Functional protection checks:**
- 模板：项目筛选、新建/编辑/删除、步骤编辑、测试运行、保存全部保留。
- 自愈：case ID 筛选、分页、展开、AI 详情、截图、确认应用、拒绝、撤销全部保留。
- token/登录/admin 校验、fetch URL/method/payload、DOM id/data attribute、事件监听与按钮文本逐字节不变。
- 不删除现有外链入口，不把操作收进“更多”。

**Steps and verification:**
- [ ] 对两个页面涉及的后端接口只做 read-only 查询，不修改任何 router/service。
- [ ] 仅修改现有 inline `<style>`；`validate-v3-style-only-scope.mjs` 对剥离 style 后的 HTML 做字节对比。
- [ ] `node frontend/scripts/validate-v3-style-only-scope.mjs`、`validate-v3-light-visual-contract.mjs` PASS。
- [ ] `npm run build` PASS，写阶段报告并停止。

---

### Task 16: 全局响应式、状态与功能保护总验收

**Files:**
- Modify only if a verified visual defect remains, style regions only: Task 2–15 已列出的 CSS/SFC/HTML 文件
- Modify: `docs/frontend-v2/handoff/CURRENT-TASK.md`
- Modify: `docs/frontend-v2/handoff/STATE.json`
- Finalize: `docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md`
- No backend/API/router/store/static JS/database/config changes

**Visual changes:** 只修复已证实的溢出、遮挡、焦点、disabled、loading、empty、error、permission、Modal/Drawer/Dialog、日志/JSON、表格和窄视口问题；禁止在总验收阶段顺手重构或扩大范围。

**Functional protection matrix:**
- 路由：所有页面还能进入；login redirect、legacy embed、adminOnly、normal/admin 保持。
- 页面：源码已有按钮、字段、列、菜单、下拉、分页、checkbox、弹窗、Empty/Loading/Error/Permission/Disabled 全部存在。
- CRUD：项目/环境/账号/API 用例/UI 用例/用户/模板/自愈操作的事件与 API 合同不变。
- 执行：接口单条/批量、数据脚本/Agent、需求执行、UI 录制/执行、报告再次执行、系统回归批次/停止/重跑/补账号继续保持。
- 证据：日志、报告、截图、变量提取、执行进度、状态标签、分页均不被裁切或隐藏。

**Mandatory verification commands:**

```powershell
node frontend/scripts/validate-v3-style-only-scope.mjs
node frontend/scripts/validate-v3-light-visual-contract.mjs
node frontend/scripts/validate-v3-visual-contract.mjs
Get-ChildItem frontend/scripts/validate-*.mjs | Sort-Object Name | ForEach-Object { node $_.FullName; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
Push-Location frontend; npm run build; Pop-Location
.venv\Scripts\python.exe -m pytest tests/ -v
git status --short
git diff --stat
git diff --check
```

**Service smoke without browser:**

```powershell
$v3Process = Start-Process .venv\Scripts\python.exe -ArgumentList 'run_server.py','--host','127.0.0.1','--port','8000' -PassThru -WindowStyle Hidden
try {
  Invoke-RestMethod http://127.0.0.1:8000/health
  Invoke-WebRequest http://127.0.0.1:8000/v3/ -UseBasicParsing
  Invoke-WebRequest http://127.0.0.1:8000/ -UseBasicParsing
} finally {
  Stop-Process -Id $v3Process.Id
}
```

**Steps and completion gate:**
- [ ] 运行全部 validator；任何失败优先恢复业务不变约束，不修改被冻结区域绕过校验。
- [ ] 构建、完整 pytest、health、`/v3/`、legacy `/` smoke 全部 PASS。
- [ ] 运行 `git diff --check`，确认无格式错误；运行 style-only validator，确认功能区零改动。
- [ ] 汇总实际修改文件，明确 `.pytest_cache/`、`docs/ui-redesign/` 原始参考包及其它用户改动未被提交或覆盖。
- [ ] 若用户另行授权浏览器，再在 1080/1240/1440/1920 验收：无横向丢列、无按钮遮挡、Modal 可滚动、日志/JSON 可读、focus/hover/active/disabled 清晰；不得为适配窄屏隐藏功能。
- [ ] 最终报告明确：新图为活动视觉基准；旧深色规范仍原样保留；源码业务行为全部保留；生产功能改动为 0。
- [ ] 停止并等待用户决定是否提交；不得自动 stage、commit 或 push。

---

## Plan Self-Review Checklist

- [ ] 计划没有删除或覆盖旧深色视觉合同，而是将其标记为历史基线并锁定哈希。
- [ ] 计划明确新 11 图只在视觉层面优先，源码始终是唯一业务依据。
- [ ] 每个 Task 都列出确切文件、视觉修改、功能保护与验证命令。
- [ ] live legacy 页面按实际 `LegacyEmbedView` + static CSS 改造，没有误改 dormant Vue view 或切路由。
- [ ] 没有计划修改 API、Router、Store、Service、static JS、后端、数据库、权限或字段。
- [ ] 没有把设计说明板、示例数据或图中不存在于源码的能力实现到产品。
- [ ] 没有使用旧 232px/62px 深色视觉覆盖新 220px/56px 浅色工作台。
- [ ] 没有任何待定项、占位路径、占位命令或未定义接口。
- [ ] 执行计划会逐 Task 停止等待人工确认，当前计划阶段不修改生产代码。
