# Frontend V2 Vue Migration Baseline Audit & Implementation Plan

> **For agentic workers:** 实施本计划时必须逐阶段执行、逐阶段回归；未经人工批准不得修改“保持不变”边界。

**Goal:** 以 `docs/prototypes/frontend-v2-shell-prototype.html` 为视觉基准，在不改变现有业务契约的前提下，将当前 Vue/legacy 双应用逐步收敛为可维护的 Frontend V2。

**Architecture:** 保留现有 `/` legacy 与 `/v3/` Vue 双应用、共享同源 `localStorage` 和 `migration-config.json` 的页面级切换机制。先在 Vue 范围内建立隔离的 V2 Token 与基础组件，再迁移 Shell 和 API Cases，最后按风险迁移剩余 legacy 模块；任何阶段都可通过迁移配置按页面回滚。

**Tech Stack:** Vue 3.5、Vite 5.4、Vue Router 4.4、Pinia 2.2、Axios 1.7、FastAPI 静态挂载、原生 CSS。

## Global Constraints

- 不修改后端 API、接口字段、Router Path、Router Name、Permission Key、Pinia 数据结构、登录流程、业务规则、按钮行为和既有功能。
- 不在迁移阶段安装或升级依赖；不引入新的 UI 框架或图标依赖。
- 不修改或删除 legacy 文件；Prototype 仅作为视觉基准，不作为运行时代码复制源。
- 每个页面迁移前建立行为基线，迁移后执行等价回归；未通过时从 `static/migration-config.json` 移除对应 view key。

---

## 1. Executive Summary

### 1.1 真实现状

项目已经存在一个可运行的 Vue 3 应用，不是从零迁移：

- Legacy 入口为 `/`，由 `static/index.html` 加载 `static/app.js` 及多个全局 IIFE 模块。
- Vue 源码入口为 `/v3/`，由 `frontend/src/main.js` 挂载到 `#app`；当前工作区没有 `frontend/dist/`，FastAPI 仅在构建产物存在时注册 `/v3` 路由。
- `static/migration-config.json` 当前标记 `dashboard`、`users`、`projects`、`records`、`apiCases`、`uiCases` 已迁移。
- Vue 与 legacy 是两个独立 HTML 文档，通过 `window.location.href` 页面级切换，不共享运行时内存，只共享同源 API、CSS 文件和 Web Storage。
- Vue 已有 7 个视图（含 Login）、4 个 Pinia Store、统一 Axios Client、9 个领域 API 模块及基础 Table/Modal/FormDialog/Toast 组件。
- 尚未迁移的主模块是接口抓取、数据工厂、需求验证中心及其 AI/录制/学习子流程；两个 admin 静态页仍独立存在。

### 1.2 本轮迁移的性质

本轮不是“把 legacy 首次改为 Vue”，而是：

1. 将已验收 Prototype 的信息架构、Shell、视觉语言和交互规范迁入现有 Vue 应用。
2. 清除 Vue 页面对 legacy 全局 CSS 结构的长期依赖，但迁移期保持兼容。
3. 保留现有双应用桥接，继续按页面收敛剩余 legacy 模块。
4. 用 API Cases 作为首个业务页面验证 V2 Token、基础组件、Shell、表格、筛选、分页和操作菜单。

### 1.3 审计依据

实际读取范围包括：

- Vue：`frontend/package.json`、`frontend/vite.config.js`、`frontend/index.html`、`frontend/src/main.js`、`App.vue`、全部 Router/Store/View/Component/API/Service/Style/Utils。
- Legacy：`static/index.html`、`static/app.js`、`migration-bridge.js`、`migration-config.json`、独立业务 JS、全局 CSS、admin 页面。
- 服务挂载：`app/core/app_setup.py`。
- 视觉基准：`docs/prototypes/frontend-v2-shell-prototype.html`。

确认不存在：`frontend/src/layouts/`、`frontend/src/assets/`、`frontend/public/`、CSS Modules、独立 Workspace Store、菜单 Store、页面缓存 Store、Vue 404 页面、Vue Permission Denied 页面。

---

## 2. Current Architecture Map

### 2.1 Application Entry

| 项目 | 真实实现 | 证据与结论 |
|---|---|---|
| Vue 入口 | `frontend/src/main.js` | `createApp(App)`，依次注册 `createPinia()`、Router，挂载 `#app`；无其他 Vue entry。 |
| HTML 入口 | `frontend/index.html` | 加载 `/static/styles.css`、design tokens、base、login CSS 和主题锁脚本，再加载 `/src/main.js`。 |
| App 根组件 | `frontend/src/App.vue` | 全局 `AppToast`；公开路由直接 `router-view`，非公开路由使用 `AppShell`。 |
| 全局插件 | Pinia、Vue Router | 未注册 UI 框架、国际化、持久化插件或全局组件插件。 |
| 全局样式入口 | `frontend/src/styles/main.css` + HTML 外链 | `main.css` 只处理挂载点；真实组件样式仍大量来自共享 legacy CSS。 |
| Vite 配置 | `frontend/vite.config.js` | `base: '/v3/'`，开发代理 `/api`、`/static` 到 8000，构建输出 `frontend/dist`。 |
| 服务端挂载 | `app/core/app_setup.py` | `/v3` 和 `/v3/{path}` 提供 dist 与 History fallback；dist 不存在时跳过。当前工作区未发现 `frontend/dist/`，因此部署/验收前必须先确认构建产物由发布流程提供。 |
| Legacy 入口 | `static/index.html` | `/` 下的独立 SPA，加载 `app.js` 和十余个业务脚本。 |
| 多入口结论 | 存在 | 主 legacy、Vue `/v3/`、`static/admin/templates.html`、`static/admin/heal-logs.html` 四类入口。 |

### 2.2 Routing

#### Vue Router

- 创建位置：`frontend/src/router/index.js`，`createWebHistory('/v3/')`。
- 静态路由：
  - `/login` → `login`
  - `/` → redirect `/dashboard`
  - `/dashboard` → `dashboard`
  - `/users` → `users`
  - `/projects` → `projects`
  - `/records` → `records`
  - `/api-cases`，alias `/apiCases` → `apiCases`
  - `/ui-cases`，alias `/uiCases` → `uiCases`
- 动态路由：不存在；没有运行时 `addRoute`。
- 路由 meta：`public`、`viewKey`、`adminOnly`。
- 前置守卫：未登录跳 `login?redirect=...`；有 token 无 user 时调用 `fetchMe()`；非 admin 访问 `adminOnly` 时跳 `/dashboard`。
- 404：不存在 catch-all；未知 `/v3/*` 可能显示 Shell + 空 `router-view`。
- keep-alive：不存在；没有页面缓存和 include/exclude 策略。

#### Vue/legacy 切换

- Vue → legacy：`frontend/src/services/navigation.js#navigateToView` 根据迁移配置决定 `router.push({ name })` 或 `window.location.href = '/#/' + viewKey`。
- Legacy → Vue：`static/migration-bridge.js` 在 capture 阶段拦截 `[data-view]` 点击；已迁移 key 跳 `/v3/<view>`。
- 配置源：`static/migration-config.json`，Vue 与 legacy 均读取此文件。
- 静态 alias：`functionalTests`、`caseGeneration` 在 Vue 导航服务中映射为 `requirementVerification`。
- Legacy 不是标准 Hash Router：主应用内部仍由 `state.view + renderCurrentView()` 分发；Hash 只作为 Vue→legacy 的跨应用协议，再由 bridge 查找 `[data-view]` 并模拟点击。
- Legacy 原始 `views` 含 `caseGeneration`、`functionalTests`；`static/requirement-verification.js` 在运行时移除二者、插入 `requirementVerification`，并注入隐藏 alias 按钮。因此菜单事实源实际有 legacy `views`、Vue `menuViews`、migration config 三处。

#### 路由风险结论

1. Router 定义仅覆盖已迁移页面，菜单却同时包含未迁移页面，正确性依赖异步迁移配置与硬编码 name 完全一致。
2. `migration-config.json` 加载失败时 Vue 回退为空集合，所有菜单跳 legacy；legacy 同样回退空集合。安全但会造成体验突变。
3. API Client 的 401 直接设置 `window.location.href`，未通过 Router/导航服务，且只移除 localStorage token，不同步清空当前 Pinia `auth.token/user`。
4. `ApiCasesView`、`UiCasesView` 内部直接 `router.push('/records')`，绕开统一导航服务；当前 records 已迁移所以暂时可用，但破坏逐页回滚约束。
5. alias `/apiCases`、`/uiCases` 与主路径并存；迁移时必须保留两者，避免旧书签失效。
6. 无 404、Permission Denied、route error UI；权限失败只静默跳 Dashboard，无法区分无权限与错误路由。
7. Legacy 的菜单运行时改写及隐藏 alias 强依赖脚本加载顺序；`migration-bridge.js` 必须最后加载，否则需求验证入口可能失效或回到默认 Dashboard。

### 2.3 State Management

| Store / 状态源 | 状态 | 持久化 | 责任与风险 |
|---|---|---|---|
| `auth` | `token`、`user`、`isLoggedIn`、`isAdmin` | `token` → localStorage | 登录、恢复当前用户、退出；401 与 Store 内存不同步是高风险。 |
| `app` | `filters.projectId/envId/recordType`、`projectsCache` | 仅 `projectId` → localStorage | Workspace/Project/Environment 的事实承载者；没有独立 Workspace/Project/Env Store。 |
| `toast` | `message`、`visible`、模块级 timer | 不持久化 | 仅单消息、2600ms；没有类型、队列、action、去重。 |
| `theme` | `theme` | `theme` → localStorage | 将历史主题值统一归一为 `forest-light` 并写 `data-theme`。 |
| Router/menu | `menuViews` 常量、route meta | 不持久化 | 菜单不是 Store；权限过滤在 AppShell computed 中完成。 |
| 页面本地状态 | 分页、筛选、选择、弹窗、轮询 | 大多不持久化 | 刷新后丢失；项目 ID 例外。 |

Legacy `static/app.js` 维护全局 `state`、`_projectsCache`、多个 timer 与隐式全局函数。已确认的持久化状态包括：

- 通用：`token`、`projectId`、`theme`、`savedUsername`、`savedPassword`。
- 数据工厂：`factoryFlowId`、`factoryProjectId`、`factoryEnvId`、`factoryCaseIds`、`factoryVariables`、`dataScriptTab`、数据工厂流程/删除/隐藏数据、`dataScriptCustomerIds`。
- 需求/功能验证：`functionalTaskId`、`verificationProjectId`、`verificationTaskId`、`verificationArchivedFilter`、`verificationSort`、`verificationLearningSession:<taskId>`。
- AI/生成：`caseGenerationProjectId`。
- sessionStorage：数据工厂 Agent 当前 session；需求验证完成通知去重 key。

结论：

- 没有统一持久化 schema/version/migration 机制。
- Vue 与 legacy 共享 key 是兼容前提，不能在视觉迁移中改名、改类型或改变写入时机。
- `savedPassword` 只是 Base64，不是加密；本计划记录为安全技术债，不在视觉迁移中擅自改变登录流程。

### 2.4 API Layer

| 项目 | Vue | Legacy |
|---|---|---|
| 统一入口 | `frontend/src/api/client.js` | `static/app.js#api` |
| 实现 | Axios instance | `fetch` wrapper |
| Base URL | 空字符串，同源；Vite dev proxy | 同源相对路径 |
| Token 注入 | request interceptor 从 localStorage 读 token | 从 `state.token` 注入 |
| 响应解包 | interceptor 返回 `response.data` | 手工读取 response/json |
| 401 | 清 localStorage，硬跳 `/v3/login` | 清 state/localStorage，调用 `renderLogin()` |
| 错误提示 | interceptor 调 Toast Store | `showToast()` |
| 模块组织 | `src/api/modules/*.js` | API 调用散落于 `app.js` 与业务 IIFE |
| 超时 | 30 秒 | 无统一超时 |
| 取消请求 | 未实现 | 未实现 |

Vue API 模块已按 auth/dashboard/projects/envs/testAccounts/users/apiCases/uiCases/records 拆分。页面直接请求例外：

- `RecordsView.vue#openProtectedFile` 直接 `fetch`，自行注入 token，绕过 Axios 的 401/错误处理。
- `services/migration.js` 直接 `fetch` 配置，属于静态配置读取，可保留但需明确超时/缓存行为。
- `recordLog.js` 动态加载 legacy `data-factory-agent.js` 并调用 `window.DataFactoryAgent`，形成 Vue 对 legacy 全局实现的运行时依赖。

重复封装风险：

- Vue Axios 与 legacy fetch wrapper 的错误消息、401 时序、Store 更新不同。
- 部分页面 catch 后再次 `toast.show(error.message)`，而 Axios interceptor 已 Toast，可能重复提示。
- 文件下载、上传和普通 JSON 请求没有统一 transport 策略。

### 2.5 Layout

#### Vue Layout

`AppShell.vue` 当前同时承担：

- Sidebar 品牌、菜单、权限过滤、admin 静态链接。
- Topbar 标题、AI 配置占位按钮、退出。
- 主内容容器和嵌套路由出口。
- 用户恢复、主题初始化、导航和退出。

该组件不是单纯 Layout，职责过多；但拆分应按 Prototype 的稳定区域进行，不能一次性把所有小 DOM 抽组件。

#### Legacy Layout

`static/app.js#renderShell` 动态拼接与 Vue 相似的 `.shell > .sidebar + .main > .topbar + .content`。Legacy 还拥有：

- 真实 `GlobalAiConfig` 挂载。
- 旧主题选择器 DOM（被 `design-system-base.css` 隐藏）。
- 独立 `#toast` 与 `#modal`。
- admin 链接和退出。

#### 重复与缺口

- 存在两套 Sidebar、Topbar、用户/退出入口、Toast、Modal 和导航运行时。
- Prototype 中的全局搜索、通知、帮助、AI Settings、账户菜单在真实 Vue 中不存在或只是占位。
- Vue 的“全局 AI 配置”只是 Toast，占位行为不能被误判为已迁移功能。
- Environments 不是独立页面，嵌在 Projects 页。
- Workspace Settings、通知中心、全局搜索结果页、独立 User Menu 均未实现。

### 2.6 Styling

#### 当前样式链

1. `static/styles.css`：旧全局 CSS、四套历史主题、布局和业务规则，大量无命名空间选择器。
2. `static/design-tokens.css`：Forest Light 全局语义 token，并把 legacy 变量 alias 到语义 token。
3. `static/design-system-base.css`：全局覆盖 Shell/Button/Input/Card/Table/Modal/Toast/Empty 等。
4. `static/login.css`：登录页专用全局 CSS。
5. `frontend/src/styles/main.css`：仅 Vue root。
6. SFC scoped style：少量；多数 Vue 视图明确依赖 legacy 全局 class。

#### 风险

- Prototype 的 `--space-1` 是 8px，现有 token 的 `--space-1` 是 4px；同名 token 语义冲突。
- Prototype sidebar 208px，当前 token sidebar 248px；直接覆盖会同时改变 legacy。
- Prototype radius、control height、table row、z-index、motion 命名和现有体系不一致。
- `styles.css` 和 `design-system-base.css` 含全局 `body`、`.shell`、`.btn`、`.modal`、`.toast`、`table` 等规则，Vue/legacy 相互覆盖概率高。
- 现有 scoped CSS 中仍有 Magic Number；`UiCasesView.vue` 还存在 inline style。
- 没有 CSS Modules；第三方 UI 库不存在，因此当前没有第三方组件样式覆盖，但后续也不应为迁移新增 UI 框架。
- 仅使用 CSS Layer 不能自动解决旧样式优先级：未分层的 legacy CSS 会压过分层规则。必须同时使用 V2 根命名空间。

---

## 3. Page Migration Inventory

| 页面 / 模块 | 当前文件 | Vue / Legacy | 当前路由 | 主要依赖 | 业务复杂度 | 迁移风险 | 推荐阶段 |
|---|---|---|---|---|---|---|---|
| Login | `frontend/src/views/LoginView.vue`；legacy `renderLogin` | 双实现，Vue 已迁移 | `/v3/login`；legacy 内部登录态 | auth/store、auth API、remember keys | 中 | 登录回跳、401、双应用 token、一致性 | 5.3 Shell 后专项 |
| Overview / 工作台总览 | `DashboardView.vue` | Vue 已迁移 | `/v3/dashboard` | app store、dashboard API、AppTable、文件打开 | 低-中 | 统计字段、项目筛选、日志跳转 | 5.5 第一批 |
| 项目空间 | `ProjectsView.vue` | Vue 已迁移 | `/v3/projects` | projects/envs/accounts API、4 个表单 | 高 | 级联删除、账号绑定、多表联动 | 5.5 第二批 |
| 接口用例库 | `ApiCasesView.vue` | Vue 已迁移 | `/v3/api-cases`；alias `/v3/apiCases` | API cases/envs、批量选择、分页、执行 | 中-高 | 批量执行、筛选/分页、权限按钮 | **5.4 首个业务页** |
| UI 自动化 | `UiCasesView.vue` | Vue 已迁移 | `/v3/ui-cases`；alias `/v3/uiCases` | UI API、录制、轮询、截图、多个 dialog | 极高 | timer 清理、录制会话、长组件、弹窗层级 | 5.5 后段 |
| 数据工厂 / Test Data | `static/app.js`、`data-factory-agent.js` 等 | Legacy | `/#/dataScripts` | 多 localStorage、Agent session、拖拽、脚本执行 | 极高 | 本地草稿兼容、动态流程、AI session | 5.5 后段 |
| 执行报告 | `RecordsView.vue` | Vue 已迁移 | `/v3/records` | records API、日志 HTML、下载、重跑 | 高 | `v-html`、legacy Agent renderer、直接 fetch | 5.5 中段 |
| AI Copilot / AI Workspace | 无独立真实页面；能力散落在数据工厂 Agent、需求验证、AI Config | Legacy/缺失 | 无稳定独立路由 | Agent session、模型配置、业务工具 | 极高 | Prototype 名称与真实 IA 不一一对应 | 人工确认 IA 后 5.5 最后 |
| 接口抓取 / API Discovery | `static/api-harvester.js` | Legacy | `/#/apiHarvester` | crawl/analyze API、admin 权限、动态表格 | 高 | 长任务、错误/权限状态、内联 HTML | 5.5 中段 |
| Environments | `ProjectsView.vue` 内嵌 | Vue 已迁移子模块 | `/v3/projects` | env API、project filter | 中 | 不得擅自新增 Router Path/Name | 跟随 Projects |
| 需求验证中心 | `requirement-verification*.js`、`requirement-pack.js`、`quick-start.js` 等 | Legacy | `/#/requirementVerification`，兼容 `functionalTests/caseGeneration` | 多模块覆盖、上传、轮询、通知 | 极高 | 全局函数覆盖链、alias、状态恢复 | 5.5 最后 |
| Workspace Settings | 真实项目不存在 | 缺失 | 无 | Prototype 导航概念 | 未定 | 不得把“缺失”当作纯视觉迁移新增 | Phase 6 另立需求 |
| 权限中心 | `UsersView.vue` | Vue 已迁移 | `/v3/users` | auth、users API、adminOnly | 中 | 权限失败仅 redirect、按钮权限 | 5.5 第一批 |
| 用户菜单 | `AppShell.vue` 与 legacy Shell 的 role/admin links/logout | 双实现 | 非独立路由 | auth、静态 admin links | 中 | Prototype dropdown 尚不存在 | 5.3 |
| 通知 | Prototype 仅 trigger；legacy V2 有浏览器 Notification 去重 | 缺失/局部 | 无 | Notification API、sessionStorage | 未定 | 不能伪造通知中心 | Phase 6 另立需求 |
| 全局搜索 | Prototype 仅搜索 trigger | 缺失 | 无 | 无真实搜索 API | 未定 | 不能只做无功能输入框 | Phase 6 另立需求 |
| Modal | `AppModal.vue`、`AppFormDialog.vue`、页面原生 dialog、legacy `#modal` | 双实现 | 全局能力 | dialog、表单、焦点/遮罩 | 高 | 多套 modal、焦点恢复、z-index | 5.2 |
| Toast | `AppToast.vue` + toast store；legacy `#toast` | 双实现 | 全局能力 | timer、API errors | 中 | 重复 Toast、无队列/类型 | 5.2 |
| Loading | 页面文字、button 文案、`.ds-loading` 基础样式 | 不统一 | 页面内 | 本地 loading refs | 中 | 请求并发、闪烁、状态遗漏 | 5.2 |
| Empty State | `AppTable.vue` 与多页 `.empty` | Vue/legacy | 页面内 | 表格/查询结果 | 低 | 文案和高度不统一 | 5.2 |
| Error State | Toast + 个别 `.alert.error` | 不完整 | 页面内 | API client | 中 | 无可恢复页面级错误 | 5.2 |
| Permission Denied | 不存在；Router redirect Dashboard | 缺失 | 无 | auth meta | 中 | 无权限被误认为导航成功 | 5.3 |
| 404 | 不存在 | 缺失 | 无 catch-all | Router | 中 | 空 Shell、错误书签无反馈 | 5.3 |
| Admin 模板管理 | `static/admin/templates.html` | Legacy 独立页 | `/static/admin/templates.html` | 独立 HTML/权限 API | 中 | 与主 Shell 脱离 | 5.5 最后 |
| Admin 自愈记录 | `static/admin/heal-logs.html` | Legacy 独立页 | `/static/admin/heal-logs.html` | 独立 HTML/权限 API | 中 | 与主 Shell 脱离 | 5.5 最后 |

---

## 4. Component Mapping

抽取原则：至少满足复用、独立交互、明确规范、独立测试价值、明显减少重复之一。页面专属业务块在第二次复用前不继续细拆。

### 4.1 Layout Components

| 组件 | 职责 | Props | Emits | Slots | 数据来源 | 是否通用 | 当前项目可复用内容 |
|---|---|---|---|---|---|---|---|
| AppShell | 组合 Sidebar/Topbar/Content 和全局 portal | `navItems`, `loading` | `navigate` | `topbar`, `default` | route/auth/app | 是 | 现 `AppShell.vue` 的导航与退出逻辑 |
| AppSidebar | 品牌、分组导航、账户入口 | `groups`, `activeKey`, `collapsed` | `select`, `account` | `footer` | menu config/auth | 是 | `menuViews`、admin filter |
| AppTopbar | breadcrumbs/search/AI/notification/user controls | `title`, `searchable` | `search`, `ai`, `notify` | `actions` | route/workspace | 是 | 当前 topbar 标题；真实缺失项必须禁用或不渲染 |
| WorkspaceContent | 内容宽度、滚动、响应式容器 | `maxWidth`, `density` | 无 | `default` | 无 | 是 | `.content` 容器 |
| WorkspaceHeader | 标题、描述、meta、主操作 | `title`, `description`, `meta` | 无 | `leading`, `actions` | 页面数据 | 是 | Prototype header 结构 |
| AppBreadcrumbs | 层级导航；仅有真实层级时使用 | `items` | `select` | `item` | route meta | 是 | 当前无实现；不得为单层页强制显示 |

### 4.2 Navigation Components

| 组件 | 职责 | Props | Emits | Slots | 数据来源 | 是否通用 | 当前项目可复用内容 |
|---|---|---|---|---|---|---|---|
| SidebarGroup | 分组标题与条目容器 | `label`, `collapsed` | 无 | `default` | menu config | 是 | Prototype Workspace/Resources 分组 |
| SidebarItem | active/permission/a11y 导航项 | `item`, `active`, `disabled` | `select` | `icon`, `badge` | menu config/route | 是 | `isActive`、`navigateToView` |
| UserMenu | 账户信息、admin links、退出 | `user`, `items` | `select`, `logout` | `header` | auth | 是 | role、模板/自愈链接、logout |
| GlobalSearchTrigger | 打开搜索；没有搜索能力时不渲染 | `shortcut`, `disabled` | `open` | 无 | 后续搜索服务 | 是 | Prototype 视觉，无真实业务实现 |
| NotificationTrigger | 未读状态与通知入口 | `count`, `hasUnread`, `disabled` | `open` | 无 | 后续通知服务 | 是 | Prototype 视觉；legacy 浏览器通知不能直接等同通知中心 |

### 4.3 Base Components

| 组件 | 职责 | Props | Emits | Slots | 数据来源 | 是否通用 | 当前项目可复用内容 |
|---|---|---|---|---|---|---|---|
| BaseButton | variant/size/loading/disabled | `variant`, `size`, `loading`, `disabled` | `click` | `default`, `icon` | 无 | 是 | `.btn` 行为与 token |
| BaseIconButton | 图标按钮与 accessible label | `label`, `size`, `pressed` | `click` | `icon` | 无 | 是 | Prototype `.icon-btn` |
| BaseInput | label/error/help/前后缀 | `modelValue`, `type`, `label`, `error` | `update:modelValue`, `blur` | `prefix`, `suffix` | 表单 | 是 | `.field` 输入样式 |
| BaseCheckbox | 单选/全选/indeterminate | `modelValue`, `indeterminate`, `label` | `update:modelValue` | `default` | 表格选择 | 是 | API Cases 与 Prototype checkbox |
| BaseBadge | 状态语义展示 | `tone`, `label` | 无 | `default` | row status | 是 | `badgeText/badgeClass` |
| BaseChip | 可选筛选标签 | `selected`, `disabled` | `select` | `default` | filter state | 是 | Prototype filter chip |
| BaseCard | surface/padding/interactive | `variant`, `padding`, `interactive` | `click` | `header`, `default`, `footer` | 无 | 是 | `.panel`/`.stat` |
| BaseDropdown | trigger/menu/键盘导航/焦点恢复 | `open`, `placement`, `items` | `update:open`, `select` | `trigger`, `default` | 操作项 | 是 | Prototype 行操作菜单；当前项目无通用实现 |
| BasePagination | 页码、前后翻页、省略号 | `page`, `total`, `pageSize` | `change` | 无 | 列表查询 | 是 | `AppPagination.vue` + 页面重复逻辑 |
| BaseTooltip | 非文本图标说明 | `content`, `placement` | 无 | `default` | 无 | 是 | 当前无实现；图标按钮需要 |
| BaseSkeleton | 页面/卡片/表格加载占位 | `rows`, `variant` | 无 | 无 | loading | 是 | `.ds-skeleton` |
| BaseEmptyState | 空结果、说明、可选 action | `title`, `description`, `icon` | `action` | `action` | 查询结果 | 是 | `AppTable` 空状态、`.empty-state` |
| BaseErrorState | 可恢复错误与重试 | `title`, `message`, `retryable` | `retry` | `details` | API error | 是 | `.alert.error` |

### 4.4 Workspace Components

| 组件 | 职责 | Props | Emits | Slots | 数据来源 | 是否通用 | 当前项目可复用内容 |
|---|---|---|---|---|---|---|---|
| WorkspaceHealth | 一组质量指标区域 | `title`, `description` | 无 | `default` | dashboard API | 否，工作台域 | Prototype section heading |
| StatCard | 单个指标、趋势、sparkline slot | `label`, `value`, `trend`, `tone` | `click` | `visual` | dashboard | 是 | Dashboard `.stat` |
| QuickActionCard | 常用动作入口 | `title`, `description`, `disabled` | `action` | `icon` | permission/menu | 是 | Prototype quick actions |
| ResourceLibrary | 资源区组合容器 | `title`, `description`, `total` | 无 | `toolbar`, `default`, `pagination` | page query | 是 | API Cases 页面整体结构 |
| ResourceToolbar | 搜索、筛选、视图和批量操作 | `filters`, `selectedCount` | `search`, `filter`, `batch` | `filters`, `actions` | page state | 是 | ApiCases toolbar |
| ResourceTable | 资源型表格；不替代所有业务表格 | `columns`, `rows`, `loading` | `select`, `rowAction` | 各列 slot | API list | 是 | `AppTable.vue`，需去除 v-html 作为默认扩展点 |
| ResourceStatus | health/status 的语义展示 | `status`, `label`, `detail` | 无 | 无 | row | 是 | Badge 工具 |
| ResourceActions | Run + more menu | `actions`, `busy`, `disabled` | `select` | `primary` | permission/row | 是 | Prototype Run/menu，ApiCases action 按钮 |

不建议首轮抽取：每个 API method badge、每种统计数字、每个表头单元格、每个 quick action 的独立组件。这些可通过 props/slots 表达，继续拆分只会增加层级。

---

## 5. Design Token Plan

### 5.1 Token 层级

#### Foundation Token

- Color primitives：neutral、green、red、amber、blue 色阶。
- Typography：family、size、line-height、weight、letter-spacing。
- Spacing：以 Prototype 8/12/16/24/32/48/64 为产品尺度；保留 4px 作为内部微间距 token，不复用冲突的旧名称。
- Radius：4/6/10/999。
- Shadow：menu、focus、selected。
- Motion：duration、ease、reduced motion、pressed/disabled opacity。
- Icon Size：12/16/24。
- Control Height：32/40。
- Layout Width：1080 最小设计宽度、208 sidebar、64 topbar、1500 workspace max。
- Z-index：base/sticky/sidebar/dropdown/modal/overlay/toast。

#### Semantic Token

- Text：primary、secondary、muted、inverse、disabled。
- Surface：canvas、surface、soft、hover、pressed、disabled。
- Border：default、strong、focus。
- Action：primary、primary-hover。
- Feedback：success、warning、danger、info。
- Focus、Disabled、Overlay。

#### Component Token

- Button、Input、Sidebar、Topbar、Card、Table、Dropdown、Pagination、Badge、Chip。
- Component token 只能引用 semantic/foundation token，不直接放品牌色值。

### 5.2 推荐文件

实施阶段建议新增：

- `frontend/src/styles/v2/tokens.foundation.css`
- `frontend/src/styles/v2/tokens.semantic.css`
- `frontend/src/styles/v2/tokens.component.css`
- `frontend/src/styles/v2/reset.css`
- `frontend/src/styles/v2/base.css`
- `frontend/src/styles/v2/index.css`

由 `frontend/src/main.js` 在 legacy 外链 CSS 之后引入 `v2/index.css`。本计划不要求移动或删除现有 `static/design-tokens.css`。

### 5.3 命名空间与隔离

- Token 使用 `--v2-*`，例如 `--v2-space-1`、`--v2-sidebar-width`，避免与现有 `--space-1` 等冲突。
- 所有 V2 变量挂在 `.frontend-v2`，不挂 `:root`。
- 所有 V2 基础选择器以 `.frontend-v2` 开始，不直接覆盖 `body`、`button`、`table`、`.modal`、`.toast`。
- Modal/Toast 若 Teleport 到 body，目标容器必须带 `.frontend-v2-portal` 并承接 V2 variables。
- Legacy 页面继续消费 `static/styles.css`、`design-tokens.css`、`design-system-base.css`，V2 文件不得由 `static/index.html` 引入。

### 5.4 CSS Layer 决策

V2 内部使用：

`@layer v2-reset, v2-tokens, v2-base, v2-components, v2-utilities, v2-overrides`

但不能只依赖 Layer 对抗 legacy：当前 legacy CSS 未分层，未分层规则在 cascade 中可能高于 layered rules。隔离必须以 `.frontend-v2` 命名空间为主，Layer 只管理 V2 内部顺序。

### 5.5 Legacy 兼容策略

1. 迁移页允许短期使用 legacy alias，但新组件只能读 `--v2-*`。
2. 建立显式映射表，不直接把 Prototype token 覆盖到现有全局同名 token。
3. 每迁移一个组件，减少该组件对 `.btn/.panel/.field/.modal` 等全局 class 的依赖。
4. 未迁移页面继续保持原 CSS；完成全量回归前不删除任何 legacy rule。
5. 已验收 Prototype 是 Vue V2 的视觉真相源；现有共享 Token 中的深色 Sidebar 等表现仅作为 legacy 兼容现状保留，不得反向修改 Prototype，也不得用共享全局覆盖改变 legacy 页面。

---

## 6. Recommended Migration Sequence

### Phase 5.1 — Foundation

- 新建 Vue-only V2 Token 文件和 `.frontend-v2` 根作用域。
- 建立 reset、typography、icon size、motion、focus、control height、layout width。
- 采用 Prototype 内联 SVG sprite 思路或项目内 SVG 组件，不新增图标依赖。
- 建立 1080/1240/1440/1920 四档视觉基线。
- 验收：挂载 V2 root 后 legacy `/` 截图零变化；Vue token 不泄漏到 legacy。

### Phase 5.2 — Base Components

优先顺序：

1. BaseButton / BaseIconButton
2. BaseInput / BaseCheckbox
3. BaseBadge / BaseChip
4. BaseCard
5. BaseDropdown
6. BasePagination
7. BaseSkeleton / BaseEmptyState / BaseErrorState
8. Modal 与 Toast 收敛

验收重点：键盘操作、focus-visible、disabled/loading、菜单 Escape/Arrow/Home/End、Modal 焦点恢复、Toast 不重复。

### Phase 5.3 — Application Shell

- 将现 `AppShell.vue` 拆为 AppShell、AppSidebar、AppTopbar、WorkspaceContent、UserMenu。
- `menuViews` 继续作为现有 menu/permission truth，不改 key、label 对应关系。
- Global Search、Notification、Workspace Settings 若无真实服务则不启用；不能用无功能按钮冒充完成。
- 加入 404 和 Permission Denied 展示，但是否新增 Router Name/Path 必须单独人工批准；在批准前可使用无新 name 的 catch-all/状态组件方案。
- 保留 admin 静态链接、退出、AI Config 现状；真实 AI Config 未迁移前不得只保留占位 Toast。

### Phase 5.4 — First Business Page: API Cases

推荐 API Cases，而不是 Dashboard 或 Projects：

- Prototype 的 Resource Library、筛选 chip、列表、状态、Run、更多菜单、分页与 API Cases 一一对应，视觉映射最直接。
- 当前 Vue 已有稳定路由、API module、分页、批量选择、CRUD、执行和权限逻辑，不需要先重构业务服务。
- 复杂度足以验证基础组件和 Shell，但低于 Projects 的多实体级联，也远低于 UI Cases 的录制/轮询。
- 成功后产生的 ResourceToolbar/Table/Actions/Status/Pagination 可复用于 Records、Projects 和后续 Discovery。

实施边界：

- 保留 `/api-cases`、`apiCases`、alias `/apiCases`。
- 保留请求 URL/method/payload、20 条分页、项目/环境联动、选中清理时机、执行后跳 Records、admin 按钮权限。
- 只替换 DOM、CSS、组件组合和图标。

### Phase 5.5 — Remaining Pages

按顺序：

1. Dashboard：低风险验证 StatCard/WorkspaceHealth。
2. Users：验证 adminOnly、表单和 Permission UI。
3. Records：收敛分页、日志 Modal、下载 transport；保持日志内容和重跑规则。
4. Projects + Environments + Test Accounts：高业务耦合，整页迁移。
5. API Discovery：复用 Resource 组件，保留长任务状态。
6. UI Cases：录制、执行、轮询和多个 dialog 作为独立专项。
7. Data Factory / AI Agent：先冻结 Web Storage schema，再迁移复杂 session 与流程编辑器。
8. Requirement Verification：最后迁移全局覆盖链、上传、轮询和通知。
9. Admin 静态页：主应用稳定后再评估是否纳入 Shell。

### 6.1 明确迁移边界

#### 保持不变

- 后端 API 与字段。
- Router Path、Router Name、alias、viewKey。
- Permission Key、`adminOnly` 语义和后端鉴权。
- Pinia 已有数据结构和 localStorage/sessionStorage key/value。
- 登录、退出、Token 过期和 redirect 流程的业务结果。
- 项目/环境切换、CRUD、批量、执行、录制、重跑等业务规则与按钮行为。
- Existing Feature，包括目前只存在于 legacy 的功能。

#### 允许变化

- DOM 结构、CSS、Layout、视觉样式。
- 合理的组件拆分和内部 props/emits/slots。
- SVG 图标实现。
- 页面内部展示结构和响应式排列。

任何“保持不变”项的修改必须先形成独立变更说明并获得人工批准。

---

## 7. Risk Matrix

| 风险 | 影响 | 发生概率 | 优先级 | 预防方案 | 验证方式 |
|---|---|---|---|---|---|
| Prototype token 与现有全局 token 同名异义 | 同时破坏 Vue/legacy 全站布局 | 高 | P0 | `--v2-*` + `.frontend-v2`，禁止写入共享 `:root` | Vue/legacy 双端截图 + computed style |
| 401 只清 localStorage、不清 Pinia 内存 | 守卫认为仍登录、跳转循环或状态错乱 | 中 | P0 | 实施前定义统一 logout/session-expired 单一入口；保持最终用户流程不变 | 运行中让 token 过期，连续请求与刷新 |
| 统一导航被页面 `router.push` 绕过 | 单页回滚后跳错应用 | 中 | P0 | 所有跨模块跳转走 navigation service；变更前做行为锁定测试 | 从 migration config 移除 records 后执行用例 |
| legacy `renderFunctionalTests` 多模块覆盖链 | 需求验证功能遗漏 | 高 | P0 | 最后迁移；逐模块列行为和加载顺序，不边迁移边重构业务 | v1/v2/pack/quick-start/test-status 全链路对照 |
| Data Factory Web Storage/schema 改变 | 草稿、流程、Agent session 丢失 | 高 | P0 | 冻结 key、类型、序列化、写入时机 | 旧版建草稿→Vue恢复；反向同测 |
| UI Cases timer/session 生命周期丢失 | 后台持续轮询、重复执行、会话泄漏 | 中 | P0 | 所有 timer 有 owner 和 unmount cleanup；请求幂等保护 | 导航离开后 Network 无轮询 |
| 无 404 catch-all | 空 Shell、用户无法恢复 | 高 | P1 | Shell 阶段补受控 404，保留现有 route names | 随机 `/v3/not-exist`、刷新、返回 |
| 权限失败静默跳 Dashboard | 用户误判功能消失 | 高 | P1 | Permission State 与 redirect 策略经人工批准后统一 | normal 用户直达 `/users`、按钮可见性 |
| migration config 异步失败 | 页面全部退回 legacy、首击体验不一致 | 中 | P1 | 明确 loading/fallback、缓存和诊断日志 | 404/超时/非法 JSON 三种故障注入 |
| migration config 已标记 Vue 页但部署缺少 `frontend/dist` | 从 legacy 点击已迁页面直接 404 | 中 | P0 | 发布门禁同时校验 dist、`/v3/` 健康检查和 migration config | 删除/缺失 dist 的部署演练 |
| legacy views、Vue menuViews、migration config 三源漂移 | 菜单消失、错页或默认 Dashboard | 高 | P0 | 建 viewKey 契约清单和自动一致性检查；保留隐藏 alias | 逐项点击 9 个菜单与 2 个历史 alias |
| Vue API 与 legacy API wrapper 行为不同 | 错误文案、401、Content-Type 不一致 | 高 | P1 | 建请求契约清单；下载/上传/JSON 分类 | Network 对比 URL/method/header/body/error |
| Records 直接 fetch 绕过 Client | Token 过期处理和 Toast 不一致 | 高 | P1 | 在不改 API 的前提下统一 transport | 过期 token 下载报告/截图 |
| Axios interceptor + 页面 catch 双 Toast | 重复提示 | 高 | P1 | 规定错误只由一个层展示，业务成功由页面展示 | 每个失败请求统计 Toast 次数 |
| 双 Shell/双 User Menu | 切应用时 IA、权限和行为不一致 | 高 | P1 | 单一 menu schema；逐页迁移期间双端对照 | 每个菜单 admin/normal 点击矩阵 |
| AI Config Vue 仅占位、legacy 为真实功能 | 功能倒退 | 高 | P1 | 未迁移前导航回真实 legacy 功能或保留入口 | admin 打开、读取、保存配置 |
| Modal 多实现与 z-index 冲突 | 遮罩错误、焦点丢失、无法关闭 | 高 | P1 | BaseDropdown/Modal portal 层级规范 | 键盘、嵌套、滚动、ESC、焦点恢复 |
| Table 宽度与 1080 最小宽度 | 横向溢出或列不可用 | 高 | P1 | 明确 min-width/overflow/列优先级 | 1080/1240/1440/1920 |
| 筛选/分页/选择状态在重渲染时丢失 | 批量操作错误 | 中 | P1 | 保持当前 reset 时机，写组件行为测试 | 切项目/环境/页码后检查 selection |
| `v-html` 日志与动态 HTML | XSS/样式泄漏风险 | 中 | P1 | 不扩大 v-html；保留 escape 边界，日志组件专项审计 | 恶意日志字段与样式隔离测试 |
| 字体变化 | 表头/按钮/菜单宽度变化 | 高 | P2 | 固定字体 fallback、line-height、数字样式 | 四宽度截图和文本溢出检查 |
| CSS Layer 被未分层 legacy 压制 | V2 样式不稳定 | 高 | P1 | Layer + root namespace + 限定选择器 | 检查 cascade 来源和 specificity |
| 搜索/通知/Settings 仅有 Prototype 外观 | 产生“可点但无功能”假功能 | 高 | P1 | 无真实能力则不渲染或明确 disabled；另立需求 | 点击所有 Topbar/Sidebar controls |

---

## 8. Regression Checklist

### 8.1 Authentication & Permission

- [ ] 正常登录，token/user 与当前实现一致。
- [ ] 记住/不记住密码行为一致。
- [ ] 登录后 redirect：Vue 内部路径、legacy hash、无 redirect。
- [ ] 退出后 Vue 与 legacy 均失效。
- [ ] Token 过期：当前请求、并发请求、刷新、返回键无循环。
- [ ] admin/normal 菜单可见性一致。
- [ ] adminOnly 直达、按钮级权限、后端 403 的 UI 结果一致。

### 8.2 Routing & Shell

- [ ] Sidebar 每个条目从 Vue 和 legacy 双向切换正确。
- [ ] `/api-cases` 与 `/apiCases`、`/ui-cases` 与 `/uiCases` 均可用。
- [ ] `functionalTests`、`caseGeneration`、`requirementVerification` alias 行为一致。
- [ ] 刷新、浏览器返回/前进、深链、未知路由。
- [ ] migration config 正常、空数组、加载失败、移除单页四种场景。
- [ ] Topbar 标题、用户菜单、退出、admin links、AI Config。
- [ ] 搜索/通知/Settings 没有无功能的可交互入口。

### 8.3 Workspace State

- [ ] 项目切换同步 `projectId`，Vue→legacy→Vue 后保持。
- [ ] 环境联动、环境失效时清理。
- [ ] 页面刷新后应恢复的状态恢复，不应恢复的 selection 清空。
- [ ] 数据工厂、需求验证、AI session 的 local/session storage 兼容。

### 8.4 List & CRUD

- [ ] 搜索、筛选、清空筛选。
- [ ] 分页：首页、末页、省略号、越界、空结果、返回后状态。
- [ ] 单选、全选、跨页选择规则、筛选后选择清理。
- [ ] 创建、编辑、复制、删除、取消、校验失败。
- [ ] 批量操作、重复点击、防并发提交。
- [ ] normal 用户不显示写操作，手工构造请求仍由后端拒绝。

### 8.5 Execution

- [ ] API 单条执行、批量执行、执行结果 Toast、跳 Records。
- [ ] UI 录制启动、事件轮询、取消、返回录制、保存。
- [ ] UI 可视化执行、进度、截图、完成/失败、关闭后 timer。
- [ ] Records 日志、报告、截图、再次执行。
- [ ] 数据工厂和需求验证长任务、取消、恢复、错误。

### 8.6 Feedback Components

- [ ] Button loading/disabled/pressed。
- [ ] Loading 首次、刷新、并发和快速响应不闪烁。
- [ ] Empty 初始空、筛选空、权限空三种文案。
- [ ] Error 可重试与不可重试。
- [ ] Toast 成功/失败、去重、连续消息、过期自动关闭。
- [ ] Modal 打开/提交/取消/ESC/遮罩/滚动锁/焦点恢复。
- [ ] Dropdown Arrow/Home/End/Escape、点击外部关闭。
- [ ] Tooltip 和 IconButton accessible name。

### 8.7 Responsive & Visual

- [ ] 1080px：Sidebar、Topbar、表格最小可用，无不可达操作。
- [ ] 1240px：Prototype compact 规则正确。
- [ ] 1440px：标准基线。
- [ ] 1920px：workspace max-width 和留白正确。
- [ ] 字体加载失败 fallback。
- [ ] 200% 浏览器缩放和键盘 focus-visible。
- [ ] prefers-reduced-motion。
- [ ] legacy `/` 在每个阶段无视觉变化。

---

## 9. Rollback Strategy

### 9.1 页面级回滚

1. 从 `static/migration-config.json` 的 `migrated` 数组移除目标 view key。
2. 重新加载配置资源。
3. 验证 legacy `/#/<viewKey>` 恢复，菜单、token、projectId 和业务操作正常。
4. Vue 路由文件和组件可保留，不需要删除代码。

### 9.2 Shell/Token 回滚

- V2 样式仅由 Vue `v2/index.css` 引入，回滚时移除该入口引用并恢复旧 AppShell 组合。
- 因 V2 token 只存在 `.frontend-v2`，回滚不应影响 legacy。
- Modal/Toast portal 切换必须能恢复到当前 AppToast/AppModal，不修改共享静态 DOM。

### 9.3 全量回滚

- 清空 migration config，所有业务入口回 legacy。
- `/v3/` 保留作为非默认入口，不切换 FastAPI `/`。
- 不删除 legacy JS/CSS/admin 页面，至少保留一个完整发布周期。

### 9.4 数据回滚

- 视觉迁移不做数据库 migration。
- Web Storage schema 不变化，因此回滚不需要数据转换。
- 若后续获批修改 schema，必须提供双读、旧格式写回或明确 migration/version；该工作不属于本计划默认范围。

---

## 10. Definition of Done

### Phase 5 计划阶段

- [x] 已读取真实 Vue 入口、Router、Store、API、View、Component、Style 和 bridge。
- [x] 已识别 `/` legacy 与 `/v3/` Vue 边界。
- [x] 已列出主要页面、缺失能力和独立 admin 页面。
- [x] 已确认 Router、登录、权限和 migration config 机制。
- [x] 已确认 Pinia、localStorage、sessionStorage 和全局状态。
- [x] 已确认 Axios/legacy fetch 双 API 层和直接 fetch 例外。
- [x] 已给出 Prototype 到 Vue 的组件映射。
- [x] 已给出隔离的 Token 迁移方案。
- [x] 已给出迁移顺序、首个业务页、风险、回归和回滚方案。
- [x] 未修改生产代码、Prototype、依赖或 legacy 文件。

### 后续每个实施阶段

- [ ] Router Path/Name/viewKey/alias 未变化。
- [ ] API URL/method/header/body/response 字段未变化。
- [ ] Permission、Pinia 和 Web Storage 契约未变化。
- [ ] 对应页面 admin/normal 功能回归通过。
- [ ] 1080/1240/1440/1920 视觉回归通过。
- [ ] 键盘与 focus-visible 回归通过。
- [ ] legacy 对照页无样式污染。
- [ ] 页面级回滚演练通过。
- [ ] 人工验收通过后才允许进入下一阶段。

---

## 11. P0 / P1 Decision Gate

开始 Phase 5.1 前必须由人工确认以下决策：

1. P0：V2 token 使用 Vue-only `--v2-*` 命名空间，不覆盖当前共享 token。
2. P0：跨 Vue/legacy 导航统一经过 navigation service，页面不得绕过逐页回滚机制。
3. P0：401 必须同步清理 localStorage 与 Pinia 内存，但保持现有登录结果和 redirect 语义。
4. P0：UI Cases、Data Factory、Requirement Verification 在建立 timer/session/storage 行为基线前不得迁移。
5. P0：发布流程必须保证 `frontend/dist` 与 migration config 同步；不存在 dist 时不得把任何页面标记为 migrated。
6. P0：legacy `views`、Vue `menuViews`、migration config 与历史 alias 必须建立一致性校验。
7. P1：404 与 Permission Denied 是否允许增加内部展示状态；任何 Router Name/Path 新增需单独批准。
8. P1：Prototype 的搜索、通知、Workspace Settings 不具备真实业务后端，默认不作为可交互功能上线。
9. P1：AI Config 在 Vue 仍为占位，Shell 迁移时必须保留真实 legacy 能力入口。

