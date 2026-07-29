# Frontend V2 Visual System Audit

**Document ID:** `2026-07-28-frontend-v2-visual-audit`  
**Date:** 2026-07-28  
**Branch:** `codex/safe-refactor-preserve-features`  
**Repo:** `https://github.com/yangmengyuan1204/zidonghuapingtai`  
**Status:** Phase 0 complete — audit only; no visual implementation in this document  
**Audience:** Design owner, product owner, engineering

---

# 1 Executive Summary

## 1.1 项目概况

本仓库是 AI 自动化测试与业务执行平台（FastAPI + SQLite + 双前端）。前端处于 Vue 3 渐进式迁移期：旧版 `static/` 原生应用仍承载高风险业务工作台；Vue 3 应用挂载在 `/v3/`，通过 `migration-config.json` + `migration-bridge.js` 按页面切换入口。

## 1.2 V2 目标

建立统一的 **Forest Light Design Language**，服务「Enterprise AI Workspace」：

- 深森林绿 + 奶油白 / 暖象牙白 + 暖灰 + 少量浅绿点缀
- 大量留白、克制、平静、温暖、清晰字体层级
- 轻边框、低阴影、统一圆角、不拥挤、不炫技、长时间使用不疲劳

**明确禁止：** 赛博朋克、霓虹科技、满屏蓝紫渐变、大量毛玻璃、大量发光、卡片重阴影、过度动画、Element Plus 默认后台感、纯黑代码编辑器风、花哨官网风。

**不是**照抄参考图文案或农场元素；提炼视觉语言后转为企业工作台语义。

## 1.3 当前架构（结论）

| 层 | 真相源 | 说明 |
|---|---|---|
| 旧前端 | `static/` | HTML/CSS/JS SPA 壳，`/` 入口 |
| 新前端 | `frontend/` | Vue 3 + Vite + vue-router + Pinia，base `/v3/` |
| 迁移开关 | `static/migration-config.json` | 已迁：`dashboard,users,projects,records,apiCases,uiCases` |
| 桥接 | `static/migration-bridge.js` | 拦截已迁 `[data-view]` → `/v3/<view>` |
| 后端挂载 | `app/main.py` `/`；`app/core/app_setup.py` `/v3`（依赖 `frontend/dist`） |
| 视觉现状 | `static/styles.css` | Vue `index.html` 外链同一份 CSS；无独立 Design Token 层 |

## 1.4 风险等级

| 维度 | 等级 | 说明 |
|---|---|---|
| 业务功能破坏 | **HIGH** | 数据工厂 / 数据智能体 / 全流程 / 问题产品仍在旧前端 |
| 视觉割裂 | **HIGH** | 四主题并存；Vue Toast 与旧 Toast 不一致；默认 `:root` 靛蓝紫与目标冲突 |
| 迁移运行时 | **HIGH** | 无 `frontend/dist` 时 `/v3` 不挂载，桥接仍可能跳转失败 |
| 样式耦合 | **MEDIUM** | 样式与业务模板字符串、scoped 覆盖、魔法数混用 |
| Token 缺失 | **MEDIUM** | 无语义 Token 层，后续改色易漏改 |

## 1.5 推荐策略

**方案 A（推荐）：先建立共享 Design Token，再分别适配新旧前端。**

- 以 Token 为全项目唯一设计真相源（见 §11–§12）
- Vue 与 Static 继续短期共享同一 CSS Token 文件，分阶段替换表现层
- 不阻塞后续 Vue 迁移；可分批验收；业务逻辑默认不动

不推荐方案 B（先全部 Vue 迁移再统一视觉）：高风险页迁移周期长，割裂持续。  
方案 C（Vue 先做、旧页兼容主题）可作为方案 A 的执行手法，而非替代策略。

---

# 2 Git Baseline

## 2.1 当前分支

```text
codex/safe-refactor-preserve-features
```

证据：`git branch --show-current`；`.git/HEAD` → `refs/heads/codex/safe-refactor-preserve-features`。

## 2.2 未提交修改（审计开始时已存在，本轮不得覆盖）

| 路径 | 状态 | 与本视觉审计关系 |
|---|---|---|
| `app/executors/api.py` | Modified | **无关** — 禁止混入视觉提交 |
| `tests/test_api_execution_trustworthiness.py` | Untracked | **无关** |
| `docs/final-fix-round1-api-execution-trustworthiness.html` | Untracked | **无关** |
| `docs/superpowers/specs/2026-07-28-frontend-v2-visual-audit.md` | 本轮新增 | **唯一允许新增的交付物** |

## 2.3 注意事项

- Phase 0 仅允许新增本审计文档。
- 禁止 `git add -A`。
- 禁止提交、禁止推送（除非用户后续单独授权）。
- 禁止还原、删除或改写上述无关工作区文件。

## 2.4 风险说明

若后续视觉提交误包含 `app/executors/api.py` 等无关改动，会导致业务回归与审计责任混淆。提交前必须人工核对 `git status --short` 与 `git diff --stat`。

---

# 3 Frontend Architecture

## 3.1 旧版 Static

| 项 | 证据 |
|---|---|
| 入口 | `GET /` → `FileResponse(STATIC_DIR / "index.html")`（`app/main.py`） |
| 壳与路由 | `static/app.js`：`state.view` + `views[]` + `renderCurrentView()` |
| 样式 | `static/styles.css`（`static/index.html` link） |
| Toast / Modal | `#toast`、`#modal`（原生 `dialog`） |
| 业务模块脚本 | `data-factory-agent.js`、`api-harvester.js`、`case-generation.js`、`requirement-*.js`、`full-flow.js`、`problem-goods.js`、`ai-config.js` 等 |

## 3.2 Vue3

| 项 | 证据 |
|---|---|
| 目录 | `frontend/` |
| 依赖 | `frontend/package.json`：`vue@^3.5.0`、`vite@^5.4.0`、`vue-router@^4.4.0`、`pinia@^2.2.0`、`axios` |
| 无 UI 库 | 无 Element Plus / Ant Design Vue / Tailwind / Sass |
| 入口 | `frontend/index.html` → `/src/main.js` |
| 样式策略 | 外链 `/static/styles.css` + 极薄 `frontend/src/styles/main.css` |

## 3.3 Migration Bridge

| 项 | 证据 |
|---|---|
| 配置 | `static/migration-config.json`：`{"migrated":[...]}` |
| 旧→新 | `static/migration-bridge.js`：capture 阶段拦截 `[data-view]`，已迁则 `location.href = /v3/<view>`；hash `#/<view>` 亦激活 |
| 新→旧 | `frontend/src/services/navigation.js`：`navigateToView` 未迁则 `/#/<viewKey>` |
| Vue 读取配置 | `frontend/src/services/migration.js` 同源 fetch `/static/migration-config.json` |

## 3.4 FastAPI

| 路径 | 行为 | 文件 |
|---|---|---|
| `/` | 旧应用 `index.html` | `app/main.py` |
| `/static/*` | StaticFiles | `app/core/app_setup.py` |
| `/reports/*` | 报告静态（若目录存在） | 同上 |
| `/v3` `/v3/*` | SPA：文件存在则返回，否则回退 `frontend/dist/index.html` | 同上；**仅当 `frontend/dist` 存在** |
| `/api/*` | 业务 API | `app/routers/*` |

## 3.5 部署关系

```text
Browser
  ├─ /                → static/index.html + app.js + migration-bridge.js
  ├─ /static/*        → CSS / JS / assets
  ├─ /v3/*            → frontend/dist (Vite build)  [optional if dist missing]
  └─ /api/*           → FastAPI (JWT Bearer)
```

开发时 Vue Vite 代理 `/api`、`/static` → `127.0.0.1:8000`（`frontend/vite.config.js`）。

## 3.6 目录结构（前端相关）

```text
/
├── static/                 # 旧前端真相源
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   ├── migration-bridge.js
│   ├── migration-config.json
│   ├── *.js                # 业务模块
│   └── admin/              # 独立管理页
├── frontend/               # Vue3 真相源
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.js
│       ├── App.vue
│       ├── router/
│       ├── stores/
│       ├── views/
│       ├── components/
│       ├── api/
│       ├── services/
│       └── styles/main.css
└── app/core/app_setup.py   # /v3 挂载
```

根目录另有 `package.json`（仅 `acorn` + pnpm packageManager），**不是**前端应用包。

## 3.7 数据流

1. 登录：`POST /api/auth/login` → `access_token` 写入 **共享** `localStorage.token`
2. 请求：旧 `fetch` / Vue `axios` 均注入 `Authorization: Bearer <token>`
3. 用户：`GET /api/auth/me`；`role === 'admin'` 控制菜单与写操作
4. 项目筛选：共享 `localStorage.projectId`
5. 主题：共享 `localStorage.theme` + `document.documentElement.dataset.theme`

## 3.8 页面流

```text
登录成功
  → navigation.navigateAfterLogin
      → 有已迁页面：进入 /v3/<firstMigrated>
      → 否则：旧应用 /
侧栏点击
  → 已迁：Vue Router /v3/...
  → 未迁：/#/<view> 旧壳 renderCurrentView
旧壳点击已迁 data-view
  → migration-bridge 强制 /v3/<view>
```

---

# 4 Vue Project

## 4.1 Vue 版本

`vue@^3.5.0`（`frontend/package.json`）

## 4.2 Vite

`vite@^5.4.0`，`@vitejs/plugin-vue@^5.1.0`  
- `base: '/v3/'`  
- `build.outDir: 'dist'`  
- dev port `5173`，代理 `/api` `/static`

## 4.3 Router

`frontend/src/router/index.js`  
- `createWebHistory('/v3/')`  
- 公开：`/login`  
- 受保护：`/dashboard` `/users`(adminOnly) `/projects` `/records` `/api-cases` `/ui-cases`  
- 守卫：未登录→login；`fetchMe` 恢复 user；非 admin 挡 adminOnly

`menuViews` 对齐旧 `views` 十项（含未迁菜单项，点击走 `navigateToView`）。

## 4.4 Pinia

| Store | 文件 | 职责 |
|---|---|---|
| auth | `stores/auth.js` | token/user/login/logout；`localStorage.token` |
| theme | `stores/theme.js` | 四主题；`localStorage.theme` |
| toast | `stores/toast.js` | 消息提示 |
| app | `stores/app.js` | projectId 筛选与项目缓存 |

## 4.5 组件组织

| 类型 | 路径 |
|---|---|
| Shell | `components/AppShell.vue` |
| Table / Pagination | `AppTable.vue` `AppPagination.vue` |
| Modal / Form | `AppModal.vue` `AppFormDialog.vue` |
| Toast | `AppToast.vue` |
| Views | `views/{Login,Dashboard,Users,Projects,Records,ApiCases,UiCases}View.vue` |
| API modules | `api/modules/*.js` + `api/client.js` |
| Services | `services/navigation.js` `services/migration.js` |

## 4.6 构建方式

```bash
cd frontend
pnpm install   # 或 npm；本审计禁止在 Phase0 执行
pnpm build     # → frontend/dist
```

生产服务依赖 dist 存在；审计时仓库内 **无 dist**。

---

# 5 Static Project

## 5.1 旧页面（主导航 views）

定义于 `static/app.js`：

| key | 中文名 | adminOnly |
|---|---|---|
| dashboard | 工作台总览 | 否 |
| projects | 项目空间 | 否 |
| apiCases | 接口用例库 | 否 |
| apiHarvester | 接口抓取 | 否 |
| dataScripts | 数据工厂 | 否 |
| caseGeneration | AI用例生成 | 否 |
| functionalTests | 功能验证中心 | 否 |
| uiCases | UI自动化 | 否 |
| records | 执行报告 | 否 |
| users | 权限中心 | 是 |

另有 `renderEnvs()` 遗留能力（`state.view === "envs"`），**不在主导航**；环境 CRUD 已并入「项目空间」。

## 5.2 旧脚本（模块清单）

| 文件 | 职责 |
|---|---|
| `app.js` | 壳、登录、CRUD、数据工厂核心、功能验证中心 |
| `api-harvester.js` | 接口抓取页 |
| `case-generation.js` | AI 用例生成 |
| `requirement-verification.js` / `v2` | 需求校验 |
| `requirement-pack.js` | 需求包 |
| `quick-start.js` | 快速开始 / AI 准备 |
| `test-status.js` | 功能用例状态 |
| `data-factory-agent.js` | DeepSeek 数据智能体 |
| `data-agent-contract-editor.js` | 合同编辑 |
| `data-agent-learning-center.js` | 学习中心 |
| `full-flow.js` | 全流程脚本增强 |
| `problem-goods.js` | 问题产品 UI |
| `ai-config.js` | 全局 AI 配置 Modal |
| `test-record-rerun.js` / `test-record-report.js` | 记录再执行 / 报告 |
| `admin/templates.html` | 操作模板管理 |
| `admin/heal-logs.html` | 自愈记录 |

## 5.3 旧 CSS

`static/styles.css`：主题变量、布局、按钮、表格、弹窗、日志、进度、响应式、空状态等。体积大、含重复选择器与魔法数。

## 5.4 旧 Modal

全局 `<dialog id="modal" class="modal">`；`openForm` / 各业务脚本直接写 `modalEl.innerHTML`。

## 5.5 Toast

`#toast.toast`：右下角、深色渐变底、约 2600ms（`showToast`）。

## 5.6 主题机制（现状 → V2 决策）

| 主题 key | 现状 | V2 决策 |
|---|---|---|
| `shuimo` | 水墨绿褐，默认 localStorage 倾向 | **废止为产品主题名**；视觉语义由 Forest Light 取代 |
| `zhuanye` | `:root` 靛蓝紫（专业蓝灰） | **废弃** |
| `qingxuan` | 清爽浅蓝 | **废弃** |
| `xiaolan` | 粉紫二次元背景 | **废弃** |

**V2 产品决策（设计负责人确认）：**

- 废弃：`zhuanye`、`qingxuan`、`xiaolan`
- 未来只保留：**Forest Light**
- 如需 Dark Mode：列入 **V3** 规划，不在 V2 范围

实现阶段再处理 localStorage 旧值迁移映射（本审计不实施）。

---

# 6 Migration Status

## 6.1 已经迁移页面

来源：`static/migration-config.json`（已代码复核）：

1. `dashboard` → `DashboardView.vue` `/v3/dashboard`
2. `users` → `UsersView.vue` `/v3/users`
3. `projects` → `ProjectsView.vue` `/v3/projects`（含环境、测试账号）
4. `records` → `RecordsView.vue` `/v3/records`
5. `apiCases` → `ApiCasesView.vue` `/v3/api-cases`
6. `uiCases` → `UiCasesView.vue` `/v3/ui-cases`

另：Vue 登录 `LoginView.vue` `/v3/login`（不在 migrated 数组，由鉴权守卫进入）。

## 6.2 未迁移页面

- `apiHarvester`
- `dataScripts`（及内嵌：全流程、问题产品、数据智能体、合同编辑、学习中心）
- `caseGeneration`
- `functionalTests`（及内嵌：需求校验、需求包、快速开始）
- 独立 admin 页

## 6.3 迁移方式

配置驱动：改 `migration-config.json` 的 `migrated` 列表；桥接与 `navigation.js` / `migration.js` 读取同一配置，避免硬编码分叉。

## 6.4 迁移风险

| 风险 | 说明 |
|---|---|
| 功能回退 | Dashboard「日志」在 Vue 侧简化为 `navigateToView('records')`，非旧版结构化 Modal |
| Vue AI 配置占位 | `AppShell.showAiConfigPlaceholder` 仅 toast，旧应用有完整 Modal |
| 双 Toast | Vue scoped Toast 与旧 Toast 位置/样式不一致 |
| 跨应用导航 | 已迁↔未迁整页跳转，状态除 localStorage 外不共享内存 |

## 6.5 SPA 刷新风险

- Vue History 模式依赖 FastAPI `/v3/{path}` fallback 到 `index.html`
- 深链 `/v3/records` 在无 dist / 无挂载时失败
- 旧应用 hash `#/dataScripts` 依赖 `migration-bridge.activateInitialHash`

## 6.6 dist 依赖风险

`app/core/app_setup.py`：`frontend/dist` **不存在则跳过 `/v3` 挂载**。  
同时 `migration-bridge` 仍会把已迁页导向 `/v3/...` → **生产未构建时高风险 404**。  
视觉重构任何阶段上线前必须保证构建产物与挂载一致。

---

# 7 Complete Page Inventory

图例：风险 L=低 / M=中 / H=高；「计划重构」= V2 视觉范围内计划触及。

| 页面名称 | 内部 key / 入口 | 路由 | 核心功能 | 风险 | Vue | 旧 | 计划重构 |
|---|---|---|---|---|---|---|---|
| 登录 | LoginView / renderLogin | `/v3/login` 或 `/` 内嵌 | JWT 登录、记住密码 | M | 是/是 | 是 | 是 Phase2 |
| 工作台总览 | dashboard | `/v3/dashboard` | 统计、最近执行、日志/报告/截图 | M | 是 | 桥接 | 是 Phase4 |
| 项目空间 | projects | `/v3/projects` | 项目/环境/测试账号 CRUD | M | 是 | 桥接 | 是 Phase7 |
| 环境管理 | 嵌于 projects（遗留 envs） | 同上 / 旧 envs | 环境 CRUD | M | 随 projects | 遗留 | 随 Phase7 |
| 接口用例库 | apiCases | `/v3/api-cases` | CRUD、执行、批量执行 | H | 是 | 桥接 | 是 Phase6 |
| UI 自动化 | uiCases | `/v3/ui-cases` | CRUD、执行、可视化、录制、heal | H | 是 | 桥接 | 是 Phase6 |
| 执行报告 | records | `/v3/records` | 列表、日志、再执行、报告下载 | H | 是 | 桥接 | 是 Phase6 |
| 权限中心 | users | `/v3/users` | 用户 CRUD（admin） | H | 是 | 桥接 | 是 Phase7 |
| 接口抓取 | apiHarvester | `/#/apiHarvester` | 抓取、分析、入库 | H | 否 | 是 | Phase8 |
| 数据工厂 | dataScripts | `/#/dataScripts` | 脚本列表/编辑/执行 | H | 否 | 是 | Phase5/8 |
| 全流程执行 | dataScripts 内嵌 | Modal / 脚本表单 | 全流程停节点、支付等 | H | 否 | 是 | Phase5 |
| 问题产品 | problem-goods | Modal | 日本站问题产品处理 | H | 否 | 是 | Phase5 |
| AI 数据智能体 | data-factory-agent | Modal | 会话、确认、权限、风险、轮询 | H | 否 | 是 | Phase5 |
| 合同编辑 | contract-editor | 智能体内 | 合同字段编辑/应用 | H | 否 | 是 | Phase5 |
| 学习中心 | learning-center | Dialog | 候选/规则/回归/回滚 | H | 否 | 是 | Phase5 |
| AI 用例生成 | caseGeneration | `/#/caseGeneration` | 截图、OCR、生成用例 | H | 否 | 是 | Phase8 |
| 功能验证中心 | functionalTests | `/#/functionalTests` | 任务、扫描、执行、预检 | H | 否 | 是 | Phase8 |
| 需求校验 | requirement-verification* | 功能中心内 | 澄清、预检、运行 | H | 否 | 是 | Phase8 |
| 需求包 | requirement-pack | 功能中心内 | 包管理与执行 | H | 否 | 是 | Phase8 |
| 快速开始 | quick-start | 功能中心工具条 | AI 准备 / 快捷开始 | H | 否 | 是 | Phase8 |
| 全局 AI 配置 | ai-config | Topbar Modal | provider/base_url/model/key | H | 占位 | 是 | Phase3 确认 |
| 操作模板 | admin/templates | `/static/admin/templates.html` | 模板 CRUD | M | 否 | 独立 | Phase8 |
| 自愈记录 | admin/heal-logs | `/static/admin/heal-logs.html` | 定位器自愈日志 | M | 否 | 独立 | Phase8 |

---

# 8 Component Inventory

## 8.1 Layout / Shell

| 组件 | 旧 | 新 | 备注 |
|---|---|---|---|
| Shell | `.shell` HTML 模板 | `AppShell.vue` | 结构对齐，应统一 Token |
| Sidebar | `.sidebar` `.nav` | 同左 | 菜单项来源双份（views / menuViews） |
| Topbar | `.topbar` | 同左 | AI 配置能力不一致 |

## 8.2 基础控件

| 控件 | 旧实现 | Vue 实现 | 重复？ | 统一建议 |
|---|---|---|---|---|
| Button | `.btn` `.secondary` `.danger` `.warn` | 复用 class | 样式同源 | Token 化层级 |
| Table | `renderTable()` | `AppTable.vue` | 逻辑双份 | 视觉统一；逻辑暂保留 |
| Pagination | 旧内联 | `AppPagination.vue` | 是 | 统一密度与样式 |
| Form field | `.field` + openForm | `AppFormDialog` | 是 | Token + 间距规范 |
| Dialog | `#modal` dialog | `AppModal.vue` | 是 | 统一尺寸层级 |
| Toast | `#toast` | `AppToast.vue` scoped **另写样式** | **严重重复** | 必须统一到 Token |
| Tag/Badge | `.badge` | `utils/badge.js` + class | 半统一 | 语义色 Token |
| Loading | 文案「加载中」 | `empty` 文案 | 弱 | 统一 Loading/Skeleton |
| Skeleton | 基本无 | 基本无 | — | V2 新增规范 |
| Empty | `.empty` / `.empty-state` | `.empty` | 双套空状态 | 合并 |
| Checkbox/Radio | 原生 + `.check-field` | 原生 | — | accent Token |
| Select/Input | `.field input/select` | 同 | — | 禁止魔法边框色 |

## 8.3 AI 相关组件（主要在旧前端）

| 能力 | 载体 | 统一建议 |
|---|---|---|
| AI 执行进度 | `.data-agent-progress` / progress 条 | AI Timeline 规范 |
| 事件步骤 | `#data-agent-events` | Timeline + 状态色 |
| 权限等待 | permission HTML | Permission Panel |
| 风险确认 | risk-confirm | Modal 危险层级 |
| 合同编辑 | ContractEditor | Form + Card |
| 学习中心 | LearningCenter dialog | Modal hierarchy |
| 日志 | `.log-view` 深色终端风 | Log Viewer（克制，非赛博） |

## 8.4 应统一清单

1. Toast（最高优先）  
2. Modal 尺寸与页脚操作区  
3. Button 主/次/危险层级  
4. Badge 状态映射  
5. Empty / Loading  
6. 表格密度与操作列  
7. AI Timeline / Permission Panel / Log Viewer（新规范，旧页渐进替换 class）

---

# 9 Visual Problems

按严重程度排序（≥20）。

| # | 问题 | 原因 | 影响 | 所在文件 / 选择器 | 建议 |
|---|---|---|---|---|---|
| 1 | 默认视觉语言是靛蓝紫渐变 | `:root` `--accent:#6366f1` 与 `--accent-gradient` | 与 Forest Light 目标直接冲突；属禁止风格 | `static/styles.css` `:root` | Token 替换为森林绿语义色；废弃蓝紫主题 |
| 2 | 四主题并存 | theme-picker + 多套 `[data-theme]` | 品牌不稳定；验收困难 | `styles.css`；`AppShell.vue`；`theme.js` | V2 仅 Forest Light |
| 3 | 大量毛玻璃 | `backdrop-filter: blur` | 疲劳、性能、非目标风格 | `.login-panel` `.topbar` `.panel` `.stat` | 移除毛玻璃，用实色 surface |
| 4 | 发光与 glow | `--accent-glow` `--brand-glow` nav indicator shadow | 类霓虹，不克制 | `:root` / 各主题 / `.nav button::before` | 删除 glow；阴影极低 |
| 5 | 按钮强阴影与扫光 | `.btn` box-shadow + `::after` 扫光动画 | 炫技、干扰操作层级 | `.btn` | 主按钮实色；次按钮描边；禁扫光 |
| 6 | Toast 双实现不一致 | Vue scoped 顶部 vs 旧右下 | 同一产品两种反馈语言 | `AppToast.vue`；`.toast` | 统一组件与位置 |
| 7 | 品牌字渐变镂空 | `-webkit-text-fill-color:transparent` + gradient | 官网感，对比度风险 | `.brand strong` `.login-panel h1` `.stat strong` | 实色标题层级 |
| 8 | 卡片 hover 抬升 | `.stat:hover` / `.panel:hover` translate + shadow | 过度动效 | `.stat` `.panel` | 弱化或取消抬升 |
| 9 | 超大 CSS + 魔法数 | 单文件堆叠历史样式 | 改一处漏多处；难 Token 化 | `static/styles.css` | Token 层 + 收敛选择器 |
| 10 | 表格过密 | nowrap + ellipsis + 多按钮 | 1366 易挤；可读性差 | `th,td`；各 View actions | 密度档位；操作菜单化 |
| 11 | Vue AI 配置占位 | Shell 未接 GlobalAiConfig | 功能与视觉双缺口 | `AppShell.vue` | 产品确认后恢复或明确跳旧 |
| 12 | Dashboard 日志简化 | showLog → 仅跳 records | 行为与旧不一致 | `DashboardView.vue` | 功能保护：恢复 Modal 或文档化差异 |
| 13 | dist 缺失仍桥接 /v3 | 挂载条件与桥接不同步 | 已迁页打不开 | `app_setup.py`；`migration-bridge.js` | 部署门禁；构建检查 |
| 14 | 登录动画底纹 | `.login-wrap::before` float 动画 | 非平静；分散注意 | `.login-wrap` | 静态暖底 |
| 15 | 进度条 shimmer | `.progress-fill::after` | 过度动效 | `.progress-fill` | 降级为简洁填充 |
| 16 | 空状态两套 | `.empty` vs `.empty-state`（含 spin） | 语言不统一 | `styles.css` | 单一 Empty 规范 |
| 17 | 字号层级跳跃 | 品牌 28/800、导航 17/700、统计 32 | 嘈杂 | `.brand` `.nav button` `.stat strong` | Typography scale |
| 18 | 侧栏过宽偏挤 | grid `280px` + 大 min-height 导航 | 内容区窄 | `.shell` `.nav button` | 收窄；减字重 |
| 19 | 字体加载未贯彻 | index 引 Noto Serif，body 仍系统无衬线为主 | 展示字体策略摇摆 | `static/index.html`；`body`；`--font-display` | Typography Strategy |
| 20 | 日志纯黑终端风 | `.log-view` 深色渐变 + 霓虹边 | 与暖色工作台割裂；偏编辑器风 | `.log-view` `.scan-progress-log` | 暖底或柔和深墨绿，禁霓虹边 |
| 21 | 行内 style 污染 | admin 链接、部分表格 `style=` | 破坏 Token | `AppShell.vue`；`app.js` 模板 | 类名 + Token |
| 22 | 主题圆点硬编码色 | `style="background:#6366f1"` 等 | 魔法数 | `app.js`；`AppShell.vue` | 废弃多主题后删除 picker 或单色 |
| 23 | focus 有但对比不足风险 | `:focus-visible` 用 accent-light | 浅色主题下可能不够 | `styles.css` `:focus-visible` | 专用 focus Token |
| 24 | 窄屏仅 900/560 断点 | 无 1366 专项 | 笔记本横向挤 | `@media` | 增加 desktop breakpoints |
| 25 | 次按钮 hover 仍带 accent 阴影 | `--btn-secondary-hover-shadow` | 次操作抢戏 | `:root` / `.btn.secondary` | 次按钮几乎无阴影 |

---

# 10 Functional Protection Matrix

**原则：V2 默认只改表现层。下列项未经书面批准不得改行为。**

| 功能名称 | 所在页面 | 源文件 | 关联 API | 权限 | 前置条件 | 成功表现 | 失败表现 | 重构如何保护 | 建议回归 |
|---|---|---|---|---|---|---|---|---|---|
| 登录 / Token | 登录 | `auth.js` stores；`app.js` api | `POST /api/auth/login` `GET /api/auth/me` | 公开 | 有效账号 | 写入 `localStorage.token` | toast + 留在登录 | 不改 key/字段/校验 | 登录成功跳转新旧入口 |
| 退出 | Shell | auth.logout；renderLogin | — | 已登录 | — | 清 token | — | 不改清除逻辑 | 退出后不可访问受保护页 |
| Admin 菜单 | users / AI 配置 | `isAdmin` / `adminOnly` | users / ai-config | admin | role=admin | 可见可写 | 非 admin 隐藏/只读 | 不改判断 | 子账号看不到权限中心 |
| 项目筛选 | 多页 | `projectId` localStorage | 各 list API query | 登录 | — | 列表过滤 | — | 不改 key | 切换项目后列表变化 |
| 项目 CRUD | projects | ProjectsView；renderProjects | `/api/projects` | 写：admin | — | 保存/删除 | toast | 不改字段与级联删除提示 | 创建编辑删除 |
| 环境 CRUD | projects | 同上；envs API | `/api/envs` | admin 写 | 项目存在 | 保存 | toast | 不改 JSON 字段 | 环境绑定项目 |
| 测试账号 | projects | testAccounts API | `/api/test-accounts` bindings | admin 写 | — | 掩码展示 | toast | 不改敏感字段处理 | 绑定/编辑 |
| 用户 CRUD | users | UsersView | `/api/users` | admin | — | 列表变更 | toast/confirm | 不改角色枚举 | 增删改 |
| API 用例执行 | apiCases | ApiCasesView；app.js | execute / batch-execute | 登录 | 选环境/用例 | 出记录 | toast | 不改 body/variables | 单条+批量 |
| UI 执行/录制/heal | uiCases | UiCasesView | ui-cases / ui-executions / ui-record | 写多 admin | — | 轮询完成 | toast | 不改轮询与 heal_map | 可视化+录制 |
| 记录再执行 | records | RecordsView；rerun.js | re-execute GET/POST | 登录 | confirm | 新执行 | toast | 不改 confirmed 语义 | 敏感提示 confirm |
| 报告/截图下载 | dashboard/records | openProtectedFile | report/screenshot | JWT | 有路径 | blob 打开 | toast | 不改鉴权下载 | 带 token 可开 |
| 接口抓取 | apiHarvester | api-harvester.js | `/api/api-harvester/*` | admin 抓取 | — | 任务轮询 | 权限提示 | 仅样式 | 启动/轮询/入库 |
| 数据脚本执行 | dataScripts | app.js；full-flow | data-scripts / batch-execute | 登录 | 脚本变量 | 进度+结果 | fail 进度 | 不改变量 schema | 购物车/全流程抽样 |
| 问题产品 | Modal | problem-goods.js | problem-goods* | 登录 | 选单 | 阶段提交 | toast | 不改状态机 | 检索+提交 |
| 数据智能体会话 | Modal | data-factory-agent.js | `/api/data-scripts/agent/sessions*` | 登录 | 项目 | 确认/执行/事件 | 取消/失败 | **禁止改状态机/轮询/权限/风险确认** | 完整会话回归 |
| 合同编辑 | 智能体内 | contract-editor.js | contract-preview/apply | 登录 | 有 fields | 应用合同 | toast | 不改字段模型 | 预览/应用 |
| 学习中心 | Dialog | learning-center.js | learning/* | 登录 | — | 批准/晋升/回滚 | toast | 不改审批语义 | 候选审批 |
| 全局 AI 配置 | Modal | ai-config.js | `/api/ai-config` | admin | — | 保存/测连 | toast | 不改 payload | 保存后新任务生效 |
| 功能验证执行 | functionalTests | app.js；quick-start | functional-tasks* | 登录 | 任务 | 执行统计 | 阻断/失败 | 不改任务流 | 扫描+执行 |
| 需求校验 | 功能中心 | requirement-verification* | requirement-verifications* | 视角色 | 任务 | 澄清闭环 | defer | 不改澄清状态 | 回答/确认 |
| 用例生成 | caseGeneration | case-generation.js | case-generation/* | 登录 | 项目 | 生成用例 | toast | 不改上传/分析 | 上传截图生成 |
| SSE/WebSocket | （若有） | 各执行模块 | 相关端点 | — | — | 实时更新 | 重试 | 不改协议 | 长任务不断流 |
| 路由语义 | 全局 | router；views key | — | — | — | 入口不变 | — | **不改 view key / path 语义** | 桥接往返 |
| migration 配置语义 | 全局 | migration-config | — | — | — | 已迁列表生效 | 空则不拦 | 视觉阶段不改 unless 迁移任务 | 已迁跳 /v3 |

**绝对禁止（未经批准）：** API 路径/方法/参数/解析、Token key、角色判断、表单字段与默认值校验、按钮启用条件、状态机、AI 执行流、权限暂停恢复、风险确认、任务轮询、下载导出、日志原始数据结构、真实写操作语义。

---

# 11 Visual Strategy

## 11.1 Forest Light Design Language

采用 **Forest Light**，拒绝科技蓝 / 赛博朋克 / 渐变风 / 毛玻璃。

**关键词：** Warm · Professional · Calm · Minimal · Enterprise · AI Workspace

## 11.2 主题生命周期决策

| 决策 | 内容 |
|---|---|
| 废弃 | `zhuanye`、`qingxuan`、`xiaolan` |
| V2 唯一 | **Forest Light** |
| Dark Mode | **V3 规划**，不在 V2 实施 |

## 11.3 Design Token 作为唯一真相源

**强制规则（自 Phase1 起生效，本审计先立规）：**

1. Design Token 是全项目唯一设计真相源。  
2. **禁止**组件直接写颜色十六进制 / rgb（除 Token 定义文件本身）。  
3. **禁止**魔法数字间距/圆角/字号散落（必须引用 scale）。  
4. **禁止**重复发明同一组件的第二套样式。  
5. 所有颜色必须来自 **Semantic Token**（如 `--color-bg-canvas`、`--color-brand-primary`）。  
6. 新旧前端共享同一 Token 源文件（推荐演进路径：`static/styles.css` 顶部 Token 区 → 未来可拆 `design-tokens.css`，仍只改表现层）。

## 11.4 策略对齐

- 方案 A：Token 先行，旧/新同时消费  
- 分批验收：Login → Shell → Dashboard → AI Workspace → Cases/Records → CRUD → 旧页收尾  
- 业务稳定优先于视觉完美

---

# 12 Design System Draft

> 本草案仅供评审，**不得在本阶段实现**。色值待设计负责人按参考图批准后锁定；下列为语义用途与方向性建议。

## 12.1 Brand Personality

平静、可信、专业、温暖、留白、长期可读。像「森林中的工作室」，不是「霓虹机房」。

## 12.2 Color Tokens（语义）

| Token | 用途 |
|---|---|
| `--color-bg-canvas` | 页面画布底（暖象牙/雾绿灰） |
| `--color-bg-surface` | 卡片/面板实色表面 |
| `--color-bg-subtle` | 表头、次级区块 |
| `--color-bg-sidebar` | 侧栏（深森林绿实色，禁毛玻璃） |
| `--color-brand-primary` | 主品牌/主按钮 |
| `--color-brand-primary-hover` | 主色悬停 |
| `--color-brand-primary-muted` | 浅绿点缀/选中浅底 |
| `--color-text-primary` | 主文案 |
| `--color-text-secondary` | 次文案 |
| `--color-text-inverse` | 深色底上的文字 |
| `--color-border-default` | 默认轻边框 |
| `--color-border-strong` | 强调分隔 |
| `--color-status-success` | 成功 |
| `--color-status-warning` | 警告 |
| `--color-status-danger` | 危险 |
| `--color-status-info` | 信息（柔和，非艳蓝） |
| `--color-focus-ring` | 无障碍焦点 |

**禁止**在业务组件中写死 `#6366f1` 等旧 accent。

## 12.3 Neutral Tokens

暖灰阶：canvas → subtle → line → muted text → primary text。避免冷灰科技感。

## 12.4 Semantic Colors

成功/警告/危险与 Badge、Timeline、Toast 共用同一组语义 Token，禁止页面私自发明状态色。

## 12.5 Typography Strategy

| 层级 | 用途 | 方向 |
|---|---|---|
| Display | 登录标题、品牌名 | 克制；可用衬线或人文无衬线，**禁止渐变镂空** |
| Title | Topbar / Modal 标题 | 清晰字重 600 |
| Body | 正文 | 中文优先系统或统一中文字体栈 |
| Caption | 标签、表头 | 较小，次色 |
| Mono | 日志、JSON | 等宽；日志区非纯黑霓虹 |

**统一：**

- 中文字体栈（唯一）  
- 英文字体栈（唯一）  
- 数字：与正文一致或等宽表内数字  
- 字重：400 / 500 / 600 为主；避免导航 700–800 全站加粗  
- 字号 scale：12 / 13 / 14 / 16 / 18 / 22 / 28  
- 行高：正文 ~1.5–1.6；标题 ~1.25

## 12.6 Spacing Scale

`4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48`  
组件内边距与区块间距只允许取 scale。

## 12.7 Radius Scale

`sm=8` `md=12` `lg=16`（下调现有 14/20 炫技感；全站统一）

## 12.8 Shadow Scale

`none` / `xs`（极轻） / `sm`（Modal 仅此）  
默认卡片 **无阴影或 xs**；禁止大面积 `shadow-lg` glow。

## 12.9 Border Rules

1px `color-border-default`；分组用 subtle 底而非重阴影。

## 12.10 Layout / Grid / Width

- Shell：侧栏固定宽度 Token（建议 ≤240–260）+ 主区 `minmax(0,1fr)`  
- 内容最大可读宽：工作台可全宽；表单 Modal 分层宽度  
- 工具条：左筛选右主操作，间距 scale

## 12.11 Breakpoint（Desktop first）

| 名称 | 宽度 | 用途 |
|---|---|---|
| `bp-sm` | 560 | 单列 |
| `bp-md` | 900 | 侧栏折叠/双列导航 |
| `bp-lg` | 1200 | 舒适桌面 |
| `bp-xl` | 1440 | 宽屏  

专项验收：**1366×768** 无横向失控溢出。

## 12.12 Sidebar / Topbar Rules

- Sidebar：深森林绿实色；导航字重中等；active 浅底+左边线，无光晕  
- Topbar：实色 surface；标题一级；操作区按钮层级清晰  
- V2 移除多主题圆点（或仅保留无切换）

## 12.13 Card Rules

轻边框、实色、低阴影、无 hover 飞起；一块卡片一件事。

## 12.14 Form Rules

标签次色；控件高度统一；焦点用 focus-ring；错误文案 status-danger。

## 12.15 Button Hierarchy

1. Primary — brand 实色  
2. Secondary — 白底描边  
3. Danger — 实色危险，仅破坏操作  
4. Ghost/Text — 低优先级  

禁用扫光、强阴影、无故 translate。

## 12.16 Table Density

提供 `comfortable`（默认）密度；长文本可换行或详情抽屉；操作列收敛。

## 12.17 Modal Hierarchy

`sm` 确认 / `md` 表单 / `lg` AI 工作台；页头页脚固定，body 滚动。

## 12.18 Status Badges

仅 success/warning/danger/neutral 语义；与执行状态枚举映射表固定。

## 12.19 AI Execution Timeline

纵向时间线：pending / running / success / fail；左色条+短文案；禁霓虹。

## 12.20 Log Viewer

可读等宽；背景可用深墨绿或暖深灰；**禁止**亮边 glow；支持复制；不改日志数据结构。

## 12.21 Permission Confirmation Panel

等待权限：清晰说明账号范围 + 主操作确认 + 次操作取消；与风险确认分级（risk 用 danger 按钮）。

## 12.22 Loading / Empty / Error

- Loading：轻 spinner 或 Skeleton，时长规范见 Motion  
- Empty：一句话 + 可选主操作  
- Error：alert 块，status-danger 边，可重试

## 12.23 Motion Design（统一规范）

| 场景 | 时长 | 缓动 | 规则 |
|---|---|---|---|
| Hover | 120–160ms | `ease-out` | 仅颜色/边框；禁止位移>2px |
| Click / Active | ≤100ms | `ease-out` | 按下反馈克制 |
| Dialog 开闭 | 160–200ms | `cubic-bezier(0.2,0.8,0.2,1)` | 淡入+轻微 scale≤1.02 |
| Toast 进出 | 180ms | `ease-out` | 单方向滑入；停留 2.4–3s |
| Loading | — | linear | 旋转匀速；可 `prefers-reduced-motion` 降级 |
| Skeleton | 1.2–1.6s | ease-in-out | 微光扫描可选，低对比 |
| Route/View Transition | ≤200ms 或无 | — | 默认不做花哨整页动效 |
| Progress | width 200–300ms | ease | 禁 shimmer 炫光 |

全站遵守 `prefers-reduced-motion: reduce` → 近瞬时或无动画。

## 12.24 Icon Strategy

- **统一单一图标体系**（落地前选定一套：如 Lucide / Heroicons 大纲风，二选一）  
- **禁止**多风格混用（面性+线性+emoji 混搭）  
- 导航与按钮图标同 stroke 宽度与尺寸 Token（如 16/20）  
- Phase0–1 可先定规范；引入依赖需单独批准（本审计不安装）

## 12.25 Focus & Accessibility

- 所有可交互元素可见 `:focus-visible`  
- 文本对比达标（主文案 vs canvas）  
- 危险操作保留 confirm；不靠颜色唯一传达状态

---

# 13 Phase Plan

> 下列顺序以设计负责人审核版为准（AI Workspace 先于 Cases/CRUD）。

## Phase 0 — 审计

| 项 | 内容 |
|---|---|
| 目标 | 完成架构/页面/功能保护/策略审计文档 |
| 修改范围 | **仅**本 Markdown |
| 禁止 | 任何生产代码、CSS、Vue、Static、Router、API、migration、提交推送 |
| 验收 | 文档目录齐全；证据可追溯；待确认问题列出 |
| 风险 | 低 |
| 回滚 | 删除本文件即可 |

## Phase 1 — Design Token

| 项 | 内容 |
|---|---|
| 目标 | 落地 Forest Light Token；确立唯一真相源；废弃三主题配置路径（产品层） |
| 修改范围 | Token 定义文件（如 styles 顶部或新 tokens css）；极薄消费层 |
| 禁止 | 改 API、业务 JS 逻辑、migration 列表 |
| 验收 | 语义 Token 齐；组件抽检无新增硬编码色；旧主题 key 废弃方案明确 |
| 风险 | 中（全局换色） |
| 回滚 | 还原 Token 文件 / Git revert |

## Phase 2 — Login

| 项 | 内容 |
|---|---|
| 目标 | 登录页 Forest Light |
| 修改范围 | 登录相关样式；必要时 Vue/旧登录模板 class（不改字段） |
| 禁止 | 改登录 API、token key、记住密码存储语义（除非安全专项） |
| 验收 | 登录/失败/记住密码行为不变；视觉达标 |
| 风险 | 中 |
| 回滚 | revert 登录样式提交 |

## Phase 3 — Shell

| 项 | 内容 |
|---|---|
| 目标 | Sidebar/Topbar/全局 Toast 统一；处理 AI 配置入口产品决策 |
| 修改范围 | AppShell、旧壳样式、Toast 统一 |
| 禁止 | 改导航 view key、权限判断 |
| 验收 | 已迁/未迁跳转仍正确；Toast 单一表现 |
| 风险 | 中高 |
| 回滚 | revert Shell/Toast |

## Phase 4 — Dashboard

| 项 | 内容 |
|---|---|
| 目标 | 总览视觉与信息层级 |
| 修改范围 | DashboardView + 统计/表格样式 |
| 禁止 | 改 dashboard API 与筛选 key |
| 验收 | 五卡+最近执行数据正确 |
| 风险 | 中 |
| 回滚 | revert |

## Phase 5 — AI Workspace

| 项 | 内容 |
|---|---|
| 目标 | 数据工厂/智能体/合同/学习中心/权限面板/时间线/日志视觉 |
| 修改范围 | 旧 AI 相关 CSS class；必要时模板 class 名 |
| 禁止 | **任何** agent 状态机、轮询、permission、risk-confirm、合同字段模型 |
| 验收 | 完整智能体会话功能回归 + 视觉抽样 |
| 风险 | **CRITICAL** |
| 回滚 | 立即 revert；功能测试优先 |

## Phase 6 — API / UI Cases / Records

| 项 | 内容 |
|---|---|
| 目标 | 用例库与执行报告视觉 |
| 修改范围 | 对应 Vue views + 表格/弹窗样式 |
| 禁止 | 改执行/录制/再执行/下载 API |
| 验收 | 执行与再执行、下载通过 |
| 风险 | 高 |
| 回滚 | revert |

## Phase 7 — CRUD

| 项 | 内容 |
|---|---|
| 目标 | users / projects / envs / accounts 视觉 |
| 修改范围 | 对应 Vue views |
| 禁止 | 改 CRUD API 与 admin 规则 |
| 验收 | 增删改查与权限矩阵 |
| 风险 | 中 |
| 回滚 | revert |

## Phase 8 — 旧页面统一

| 项 | 内容 |
|---|---|
| 目标 | harvester / caseGeneration / functionalTests / admin 页 Token 对齐 |
| 修改范围 | 旧页 CSS/class |
| 禁止 | 改业务脚本流程 |
| 验收 | 主路径功能回归 |
| 风险 | 高 |
| 回滚 | revert |

## Phase 9 — 剩余 Vue 迁移

| 项 | 内容 |
|---|---|
| 目标 | 按迁移计划搬页（独立项目）；视觉跟随 Token |
| 修改范围 | 新 Vue 页 + migration-config（迁移任务专批） |
| 禁止 | 与视觉混提；禁止一次搬多个高风险模块除非批准 |
| 验收 | 桥接与功能对等 |
| 风险 | 高 |
| 回滚 | 从 migrated 列表移除 + revert |

## Phase 10 — 最终验收

| 项 | 内容 |
|---|---|
| 目标 | 全量视觉 + 功能回归 |
| 修改范围 | 仅缺陷修复 |
| 禁止 | 新需求塞入 |
| 验收 | 清单全绿；1366；无障碍抽样；AI 会话；执行下载 |
| 风险 | 中 |
| 回滚 | 按缺陷提交粒度回滚 |

---

# 14 Open Questions

1. Forest Light 最终色板（十六进制）是否由设计负责人从图中锁定后写入 Token？  
2. Phase1 Token 文件形态：继续写在 `static/styles.css` 顶部，还是新建 `design-tokens.css` 并双向引用？  
3. Vue Shell「全局 AI 配置」：Phase3 恢复旧能力，还是跳转旧应用 Modal，或暂缓？  
4. Icon 库选型（Lucide vs Heroicons 等）与是否允许新增前端依赖？  
5. 中文字体：继续 Noto Serif SC 仅用于 Display，还是全站人文无衬线？  
6. Toast 统一位置：右下（旧）还是顶部（Vue 现状）？  
7. Dashboard「日志」是否必须恢复旧版结构化 Modal（功能债）？  
8. `frontend/dist` 构建是否纳入每次上线 CI 门禁？  
9. localStorage `theme` 旧值（zhuanye/qingxuan/xiaolan/shuimo）映射到 Forest Light 的兼容策略？  
10. 工作区无关改动（`app/executors/api.py` 等）是否确认与 V2 视觉隔离、另案处理？  
11. Phase5（AI Workspace）是否需要单独「功能冻结窗口」与双人验收？  
12. 1366×768 与手机窄屏：V2 是否承诺移动端完整可用，还是仅桌面+可勉强使用？

---

## Document Control

| 项 | 值 |
|---|---|
| Phase | 0 — Audit only |
| Implementation | **Not started** |
| Production code changed in this deliverable | **No** |
| Next gate | 设计负责人确认 §11–§14 后，方可批准 Phase 1 |

---

*End of audit specification.*
