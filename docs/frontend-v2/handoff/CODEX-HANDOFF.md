# Frontend V2 — Codex Handoff

> 生成时间：2026-07-29T06:29:13Z  
> 分支：`codex/safe-refactor-preserve-features`  
> HEAD：`797a7e1c3d00293e0cb29cf89f894b1113e2d667`（短 SHA：`797a7e1`）  
> 用途：无 Cursor 会话历史的新 Agent（Codex + GPT-5.6-sol）安全接手 Frontend V2  
> 本文件为交接地图，**不是**实施许可证。开始任何代码修改前必须：读完本文件 → 检查 Git → 运行校验 → 输出理解摘要 → **等待人工批准**。

---

## 1. Project Goal

Frontend V2 的最终目标：

1. **保留全部现有业务功能**，包括目前只存在于 legacy 的功能。
2. **保留业务契约**：API URL/method/payload/response、Router Path/Name/alias/viewKey、Permission Key、Pinia 数据结构、Web Storage key、Login/Logout 结果语义。
3. **以最终 Prototype 为视觉基准**：`docs/prototypes/frontend-v2-shell-prototype.html`。
4. **逐阶段替换 Vue UI**：先 Token/基础组件，再 Overlay/Dropdown，再 Shell，再业务页。
5. **迁移期保留 legacy**：`/` 继续可运行；通过 `static/migration-config.json` 按页面回滚。

本轮不是从零建 Vue，而是在已有 `/v3/` Vue + `/` legacy 双应用上做第二轮视觉与组件体系迁移。

---

## 2. Repository Architecture

| 层 | 路径 / 机制 | 说明 |
|---|---|---|
| Legacy SPA | `/` → `static/index.html` + `static/app.js` | 独立 HTML 文档；Hash 仅作跨应用协议 |
| Vue SPA | `/v3/` → `frontend/`（Vite `base: '/v3/'`） | `frontend/src/main.js` 挂载 `#app.frontend-v2` |
| 迁移配置 | `static/migration-config.json` | 当前 `migrated`: dashboard, users, projects, records, apiCases, uiCases |
| 迁移桥 | `static/migration-bridge.js` | legacy 拦截已迁移 `[data-view]` → `/v3/<view>` |
| Vue 导航 | `frontend/src/services/navigation.js` | 已迁移 `router.push`；未迁移 `window.location.href = '/#/' + viewKey` |
| Vue Router | `frontend/src/router/index.js` | `createWebHistory('/v3/')`；`menuViews` 常量；守卫鉴权 |
| Pinia | `frontend/src/stores/*` | auth / app / toast / theme |
| HTTP | Axios `frontend/src/api/client.js` | 统一拦截；401 清 localStorage token（已知与 Pinia 不同步） |
| 后端挂载 | FastAPI `app/core/app_setup.py` | `/v3` 提供 `frontend/dist`；dist 不存在时跳过 |
| 切换方式 | 页面级硬导航 | 不共享运行时内存；共享同源 API、部分 CSS、Web Storage |

---

## 3. Source of Truth Order

Codex 必须按以下顺序理解项目：

1. **当前真实代码**
2. **当前 Git 状态与 diff**
3. **本文件** `docs/frontend-v2/handoff/CODEX-HANDOFF.md`
4. **Vue Migration Plan** `docs/migration/frontend-v2-vue-migration-plan.md`
5. **最终 Prototype** `docs/prototypes/frontend-v2-shell-prototype.html`
6. **Phase Reports**（见第 4 节路径）
7. **旧会话总结**（最低优先级）

若报告与真实代码或 Git 冲突：**以真实代码和 Git 为准**，并在回复中报告差异。

---

## 4. Completed Phases

### Phase 1 — Design System

- **内容**：共享 design tokens / design-system-base / login CSS / theme lock（legacy 侧）。
- **主要文件**：`static/design-tokens.css`、`static/design-system-base.css`、`static/login.css`、`static/v2-theme-lock.js`
- **验证**：人工视觉验收；后续由 Foundation validator 保护 Vue 侧隔离。
- **报告**：`docs/superpowers/specs/2026-07-28-design-system.md`、`docs/superpowers/specs/2026-07-28-phase1-review.md`
- **接入生产**：是（legacy/login 样式）
- **已提交**：是（含于 `797a7e1`）

### Login Prototype / Production redesign

- **内容**：Vue LoginView 视觉与 legacy login CSS 对齐方向。
- **主要文件**：`frontend/src/views/LoginView.vue`、`static/login.css`
- **验证**：人工；登录 redirect 后续由 5.1.1 修复。
- **报告**：无独立 Frontend V2 phase-report；见 migration plan / visual audit。
- **接入生产**：是
- **已提交**：是（`797a7e1` 含 LoginView 相关改动）

### Frontend V2 Prototype

- **内容**：高保真 Shell / API Cases Workspace 视觉基准。
- **主要文件**：`docs/prototypes/frontend-v2-shell-prototype.html`
- **验证**：人工验收通过，正式作为 Baseline。
- **报告**：`docs/superpowers/specs/2026-07-28-frontend-v2-visual-audit.md`
- **接入生产**：否（文档/原型，非运行时代码）
- **已提交**：是

### Phase 5 — Migration Audit

- **内容**：真实架构盘点 + 分阶段迁移计划；不改生产代码。
- **主要文件**：`docs/migration/frontend-v2-vue-migration-plan.md`
- **验证**：人工审核通过。
- **报告**：即迁移计划本身。
- **接入生产**：否
- **已提交**：是

### Phase 5.1 — Foundation

- **内容**：Vue-only `--v2-*` Token、`.frontend-v2` / `.frontend-v2-portal`、reset/base、`@layer`、`main.js` 引入 V2 CSS、`#app.frontend-v2`。
- **主要文件**：`frontend/src/styles/v2/**`、`frontend/scripts/validate-v2-foundation.mjs`、`frontend/src/main.js`、`frontend/index.html`
- **验证**：`node frontend/scripts/validate-v2-foundation.mjs`
- **报告**：
  - 非忽略：`docs/frontend-v2-phase5-1-foundation-completion-report-2026-07-29.html`（untracked）
  - 说明：早期报告也曾放 `docs/reports/`，该目录被 `.gitignore` 的 `reports/` 规则忽略
- **接入生产**：Token/CSS 已进入 Vue 构建入口；**未**替换业务组件样式为 V2 组件
- **已提交**：代码是；HTML 报告未提交

### Phase 5.1.1 — Login Redirect Hotfix

- **内容**：登录后从 `/v3/dashboard` 被踢回 login 再登录时落到 `/dashboard`（404）→ 修复 `navigateAfterLogin`。
- **主要文件**：`frontend/src/services/navigation.js`、`frontend/scripts/validate-login-redirect.mjs`
- **验证**：`node frontend/scripts/validate-login-redirect.mjs`（9/9）
- **报告**：`docs/reports/frontend-v2-phase5-1-1-login-redirect-hotfix-report-2026-07-29.md`（**被 gitignore**，磁盘存在）
- **接入生产**：是（导航服务）
- **已提交**：修复代码在 `797a7e1`；报告被忽略

### Phase 5.2A — Base Primitive Components

- **内容**：BaseButton、BaseIconButton、BaseInput、BaseCheckbox、BaseBadge、BaseChip、BaseCard + 独立 Component Lab。
- **主要文件**：`frontend/src/components/v2/base/Base*.vue`（7）、`index.js`、`frontend/dev/v2-base-components.html`、`frontend/src/dev/*`、`frontend/scripts/validate-v2-base-components.mjs`
- **验证**：`node frontend/scripts/validate-v2-base-components.mjs`
- **报告**：`docs/reports/frontend-v2-phase5-2a-base-primitives-report-2026-07-29.md`（**被 gitignore**）
- **接入生产**：**否**（仅 Component Lab）
- **已提交**：代码在 `797a7e1`；报告被忽略

### Phase 5.2B1 — Supporting Base Components

- **内容**：BasePagination、BaseTooltip、BaseSkeleton、BaseEmptyState、BaseErrorState；扩展 Lab；Support validator。
- **主要文件**：五个新组件、`tokens.component.css` 补充、`index.js` 总导出 12、`validate-v2-support-components.mjs`、Lab 扩展
- **验证**：`node frontend/scripts/validate-v2-support-components.mjs`
- **报告**：`docs/frontend-v2/phase-reports/frontend-v2-phase5-2b1-support-components-report-2026-07-29.md`（untracked，**不在** gitignore）
- **接入生产**：**否**
- **已提交**：主体在 `797a7e1`；**后续复审补强未提交**（见第 9 节）：
  - `frontend/src/components/v2/base/BaseTooltip.vue`（多根 Fragment `aria-describedby`）
  - `frontend/scripts/validate-v2-support-components.mjs`（生产扫描 / Portal 检测加强）
  - `frontend/src/dev/V2BaseComponentsLab.vue`（多根 Tooltip 回归用例）

**HEAD 一致性**：Phase 5.2B1 报告 Diff Audit 记载实施中 HEAD 前进到 `797a7e1`，与当前 `git rev-parse HEAD` **一致**。未提交的是该提交之后的复审补强与报告目录。

---

## 5. Current Component Inventory

导出入口：`frontend/src/components/v2/base/index.js`（12 个）。

| 组件 | Props / Emits 事实源 | Lab | 业务页 | 验证脚本 |
|---|---|---|---|---|
| BaseButton | `BaseButton.vue` | 是 | 否 | validate-v2-base-components |
| BaseIconButton | `BaseIconButton.vue` | 是 | 否 | validate-v2-base-components |
| BaseInput | `BaseInput.vue` | 是 | 否 | validate-v2-base-components |
| BaseCheckbox | `BaseCheckbox.vue` | 是 | 否 | validate-v2-base-components |
| BaseBadge | `BaseBadge.vue` | 是 | 否 | validate-v2-base-components |
| BaseChip | `BaseChip.vue` | 是 | 否 | validate-v2-base-components |
| BaseCard | `BaseCard.vue`（emit: `activate`） | 是 | 否 | validate-v2-base-components |
| BasePagination | `BasePagination.vue`（emit: `change`） | 是 | 否 | validate-v2-support-components |
| BaseTooltip | `BaseTooltip.vue` | 是 | 否 | validate-v2-support-components |
| BaseSkeleton | `BaseSkeleton.vue` | 是 | 否 | validate-v2-support-components |
| BaseEmptyState | `BaseEmptyState.vue` | 是 | 否 | validate-v2-support-components |
| BaseErrorState | `BaseErrorState.vue`（emit: `retry`；复用 BaseButton） | 是 | 否 | validate-v2-support-components |

**约定**：Props/Emits 以各 SFC 的 `defineProps` / `defineEmits` 为准，不以报告表格猜测。  
**隔离**：Component Lab 不进 Router、不进菜单、不进 production build input；入口 `frontend/dev/v2-base-components.html` → `frontend/src/dev/v2-base-components-main.js`。

---

## 6. Design System Rules

1. Token 命名：`--v2-*`。
2. 根作用域：`.frontend-v2`（Vue `#app`）。
3. Portal 作用域：`.frontend-v2-portal`（已预留；**尚未实现 Portal 容器**）。
4. **禁止**把 V2 Token 写到共享 `:root` / 污染 legacy。
5. **禁止**新 V2 组件依赖 legacy class（`btn`/`panel`/`field`/`modal`/`toast` 等）。
6. Token 层级：Foundation → Semantic → Component → SFC scoped style。
7. Prototype 是视觉基准；不得复制 Prototype 内联 style 为生产实现。
8. 不新增 UI Framework 或图标 npm 依赖；图标用内联 SVG / slot。
9. CSS Layer 只管理 V2 内部顺序；隔离靠命名空间。

---

## 7. Protected Contracts

未经人工书面批准不得修改：

- Router Path / Name / alias / viewKey / route meta
- API URL / method / payload / response 字段
- Permission Key / `adminOnly` / 后端鉴权结果语义
- Pinia store 公共数据结构
- localStorage / sessionStorage key 与序列化约定
- Login / Logout / redirect 业务结果语义（可修 bug，但结果不变）
- `static/migration-config.json` 机制与 view key 契约
- legacy existing features 与入口行为
- Vite `base: '/v3/'`、production build input
- package.json / lockfile 依赖版本

---

## 8. Known Risks

1. **401**：Axios 清 localStorage token，但 Pinia `auth` 内存可能不同步。
2. **无 Vue 404**：未知 `/v3/*` 可能空 Shell。
3. **无 Permission Denied UI**：非 admin 访问 adminOnly 静默跳 Dashboard。
4. **菜单三源**：legacy views、Vue `menuViews`、`migration-config.json` 可能漂移。
5. **发布同步**：`migration-config` 标记已迁但缺少 `frontend/dist` → `/v3` 404。
6. **AI Config**：Vue 侧仍可能占位；legacy 为真实能力。
7. **UI Cases**：timer / session / 轮询生命周期风险。
8. **Data Factory**：Web Storage schema 冻结前不可随意改。
9. **Requirement Verification**：多模块全局覆盖链，最后迁移。
10. **Modal / Toast Portal**：尚未实施；现有 AppToast/AppFormDialog 仍为旧实现。
11. **BaseTooltip**：轻量定位，无碰撞检测、无自动翻转、无 Portal。
12. **docs/reports/**：被 `.gitignore` 的 `reports/` 忽略；后续报告必须写 `docs/frontend-v2/phase-reports/`。

---

## 9. Current Git State

### Snapshot（交接生成时实测）

- **Branch**：`codex/safe-refactor-preserve-features`
- **HEAD**：`797a7e1c3d00293e0cb29cf89f894b1113e2d667`
- **最近提交**：`797a7e1 feat: 建立前端 V2 设计系统基础`
- **Staged**：无
- **Stash**：无

### 已提交的 Frontend V2 范围（`797a7e1` 内，节选）

- `docs/migration/frontend-v2-vue-migration-plan.md`
- `docs/prototypes/frontend-v2-shell-prototype.html`
- `frontend/src/styles/v2/**`
- `frontend/src/components/v2/base/**`（12 组件 + index）
- `frontend/dev/v2-base-components.html`、`frontend/src/dev/**`
- `frontend/scripts/validate-v2-foundation.mjs`
- `frontend/scripts/validate-v2-base-components.mjs`
- `frontend/scripts/validate-v2-support-components.mjs`（提交版）
- `frontend/scripts/validate-login-redirect.mjs`
- `frontend/src/main.js`、`frontend/index.html`（`.frontend-v2`）
- `frontend/src/services/navigation.js`（含 redirect 修复）
- 相关 legacy design-system / login / theme-lock 文件

### 未提交 — Frontend V2 复审补强（归属 Phase 5.2B1 收尾）

| 路径 | 归属 |
|---|---|
| `frontend/src/components/v2/base/BaseTooltip.vue` | 多根 trigger ARIA 修复 |
| `frontend/scripts/validate-v2-support-components.mjs` | 校验器加强 |
| `frontend/src/dev/V2BaseComponentsLab.vue` | 多根 Tooltip Lab 用例 |
| `docs/frontend-v2/`（整个目录 untracked） | 含 5.2B1 报告与本 handoff |

### 未提交 — 其他任务（payment amount regression 等）

**Codex 绝对不得回退、覆盖、提交或“顺手清理”：**

| 路径 | 归属判断 |
|---|---|
| `app/data_scripts/__init__.py` | payment amount regression |
| `app/data_scripts/order_support.py` | 订单确认运费相关（与 payment 同批工作区） |
| `app/data_scripts/registry.py` | payment amount regression |
| `app/routers/data_scripts.py` | payment amount regression 路由 |
| `app/data_scripts/payment_amount_regression/**` | 新模块 untracked |
| `static/index.html` | 引入 payment-amount-regression.js |
| `static/payment-amount-regression.js` | untracked |
| `tests/route_contract_expected.json` | 路由契约测试更新 |
| `tests/test_data_factory_agent.py` | 既有测试改动 |
| `tests/test_data_script_contract.py` | 数据脚本契约 |
| `tests/test_payment_amount_*.py` | untracked |
| `docs/final-fix-round1-api-execution-trustworthiness.html` | 其他任务文档 |
| `docs/frontend-v2-phase5-1-foundation-completion-report-2026-07-29.html` | V2 报告（可保留；勿删除） |

### 磁盘存在但被 gitignore 的报告

- `docs/reports/frontend-v2-phase5-1-1-login-redirect-hotfix-report-2026-07-29.md`
- `docs/reports/frontend-v2-phase5-2a-base-primitives-report-2026-07-29.md`

**不要修改 `.gitignore`。** 后续报告统一放 `docs/frontend-v2/phase-reports/`。

---

## 10. Validation Commands

实际存在的命令（`frontend/package.json` **没有** lint/test script）：

```bash
node frontend/scripts/validate-v2-foundation.mjs
node frontend/scripts/validate-login-redirect.mjs
node frontend/scripts/validate-v2-base-components.mjs
node frontend/scripts/validate-v2-support-components.mjs
cd frontend && npm run build
git diff --check
```

不要声称不存在的 `npm test` / `npm run lint` 通过。

---

## 11. Browser Verification

| 项 | 说明 |
|---|---|
| Component Lab | `cd frontend && npm run dev` → `http://127.0.0.1:5173/v3/dev/v2-base-components.html` |
| 账号 | **不得写入任何交接文档**；向人工索取 |
| 视口 | 1080 / 1240 / 1440 / 1920，无横向溢出 |
| Vue | `/v3/login`、`/v3/dashboard` |
| Legacy | `/` |
| 隔离 | legacy `documentElement`/`body` 上 `--v2-*` 计数应为 0 |
| Lab | Console error = 0；Lab 页面不应发业务 `/api/` 请求 |

---

## 12. Next Phase

**下一阶段唯一目标：**

`Phase 5.2B2 — Overlay Foundation & BaseDropdown`

详见：`docs/frontend-v2/handoff/CURRENT-TASK.md`

**本阶段应落地：**

- Portal 容器（`.frontend-v2-portal`）
- Overlay Stack（最小）
- BaseDropdown
- BaseDropdownItem

**明确禁止提前进入：**

- BaseModal
- BaseToast
- Focus Trap（完整实现）
- Scroll Lock（完整实现）
- Shell / Sidebar / Topbar
- API Cases 业务迁移

---

## 13. Definition of Safe Handoff

Codex 接手前 **必须**：

1. 读取 `CODEX-HANDOFF.md`、`CURRENT-TASK.md`、`docs/frontend-v2/README.md`
2. 读取 migration plan 与 Prototype
3. 读取全部可访问的 Phase Reports
4. 执行 `git status` / `git diff`，区分 V2 与其他任务改动
5. 核对真实组件与校验脚本存在
6. 运行第 10 节四个 validator + build（若要宣称环境可用）
7. 输出理解摘要（分支、HEAD、未提交归属、下一阶段范围）
8. **等待人工批准后再改代码**
9. 不得直接开始 Phase 5.2B2 实现
10. 不得 `git add -A`、不得覆盖其他任务文件、不得 force push / hard reset / clean

---

## Quick Links

- Index: `docs/frontend-v2/README.md`
- Current Task: `docs/frontend-v2/handoff/CURRENT-TASK.md`
- Machine state: `docs/frontend-v2/handoff/STATE.json`
- Migration plan: `docs/migration/frontend-v2-vue-migration-plan.md`
- Prototype: `docs/prototypes/frontend-v2-shell-prototype.html`
- Phase 5.2B1 report: `docs/frontend-v2/phase-reports/frontend-v2-phase5-2b1-support-components-report-2026-07-29.md`
