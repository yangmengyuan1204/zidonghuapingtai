# Vue3 迁移实施计划 · 2026-07-27

> 依据：`docs/vue3-migration-baseline-2026-07-24.md`（第二轮验证通过，已作为 Vue3 重构唯一 Truth Source）。
> 阶段定位：**实施计划阶段**，不开始迁移、不创建 Vue 工程、不编写 Vue 代码、不修改任何业务源码。
> 唯一新增/修改文件：`docs/vue3-migration-implementation-plan-2026-07-27.md`。

---

## 报告目录

- 第一章 技术选型
- 第二章 新旧系统共存方案
- 第三章 Phase 划分（Phase 0 ~ Phase 8）
- 第四章 页面迁移顺序
- 第五章 每个阶段验收方式
- 第六章 最终结论

---

## 第一章 技术选型

### 1.1 选型总览

| 类别 | 选型 | 理由摘要 |
|---|---|---|
| 框架 | Vue 3（`<script setup>` + Composition API） | 官方推荐写法，逻辑复用性强；项目视图多、弹窗多，组合式优于选项式 |
| 构建 | Vite 5 | Vue3 官方构建工具，HMR 快；替代当前 14 个同步 `<script>` 的加载方式 |
| 语言 | **JavaScript** | 见 1.3 |
| 路由 | Vue Router 4（History 模式） | 替代当前 `state.view` + `renderCurrentView` 手动分发；支持嵌套路由与守卫 |
| 状态 | Pinia | 替代 `state` 对象 + 14 个 localStorage key 的散落读写；支持持久化插件 |
| HTTP | Axios（封装统一 client） | 替代 `api(path, options)`；支持拦截器统一注入 JWT、错误提示、超时 |
| UI 组件 | Element Plus | 替代 `renderTable`/`openForm`/`#modal`；提供 Table、Dialog、Form、Pagination 等 |
| CSS | 保留 `static/styles.css` + CSS 变量主题 | 见 1.5 |
| 包管理 | pnpm | 磁盘占用小，monorepo 友好；当前项目无 node_modules |
| 测试 | Vitest + Vue Test Utils | 单元/组件测试；阶段验收补充手动用例 |

### 1.2 框架：Vue3 + Composition API

基线报告显示当前前端为"裸全局符号 + IIFE"混合模式，`app.js` 暴露近 70 个隐式全局函数，`window.renderFunctionalTests` 被三次覆盖（基线 R-04）。Vue3 Composition API 的优势：

- `setup()` 内逻辑按功能聚合，替代当前散落在 `app.js` 各处的同主题函数。
- 组合式函数（composables）可复用，替代当前 `openForm`/`renderTable` 等通用函数。
- 无 `window` 全局，从根本上消除 R-04（三次覆盖）与 R-05（70 隐式全局）风险。

### 1.3 语言：JavaScript（含理由）

**选择 JavaScript，理由如下：**

1. **本次迁移只做前端框架迁移**：目标是把原生 JS SPA 迁移到 Vue3 框架，不是语言升级。引入 TypeScript 会同时改变语言与框架两个维度，增加迁移风险与认知负担。
2. **降低迁移复杂度**：迁移本身已涉及 14 个 JS 文件、11 视图、39 弹窗、23 表格、203 API 的重写，保持 JS 可让团队专注于框架适配，不被类型系统分心。
3. **团队已熟悉 JavaScript**：现有代码全为 JS，团队对 JS 语义掌握充分；迁移期引入新语言语法会拖慢进度。
4. **渐进式策略**：Vue3 + Vite 对 JS 原生支持，无需额外配置；待整个 Vue3 迁移完成并稳定后，再评估是否逐步迁移到 TypeScript（可作为后续独立技术债）。
5. **Element Plus 与 Pinia 均支持 JS**：虽然两者原生支持 TS，但并不强制；用 JS 调用完全可行，不影响功能。
6. **迁移完成后再评估 TS**：TS 的类型收益在大型项目长期维护中确实有价值，但应在框架迁移稳定后作为独立阶段推进，避免一次做太多事。

**与 TypeScript 的对比**：

| 维度 | JavaScript（本次选型） | TypeScript |
|---|---|---|
| 迁移期复杂度 | 只改框架，不改语言 | 同时改框架+语言，风险叠加 |
| 学习成本 | 团队已熟悉 | 需额外学习 TS 语法 |
| 开发速度 | 迁移期最快 | 初期较慢 |
| 类型安全 | 无，靠运行时与测试保证 | 编译期捕获类型错误 |
| 后续演进 | 迁移稳定后可再评估引入 TS | — |

**结论**：本次 Vue3 迁移保持 JavaScript，降低迁移风险与复杂度。待整个 Vue3 迁移完成并稳定运行后，再作为独立阶段评估是否逐步引入 TypeScript。

### 1.4 API 封装方案

当前：`api(path, options)` 统一封装（`app.js#L123`），自动注入 `Authorization` header，返回 JSON。少量 `fetch` 直连用于 FormData 文件上传（基线 R-15）。

新方案分层：

| 层 | 职责 | 对应旧代码 |
|---|---|---|
| `src/api/client.js` | Axios 实例：baseURL、JWT 拦截器、401 跳登录、统一错误 toast、超时 | `api()` 函数 |
| `src/api/types.js` | 通用响应结构约定（`ApiResponse`、`Paginated`，用 JSDoc 注释标注字段） | 无 |
| `src/api/modules/*.js` | 按业务域拆分：auth、projects、envs、apiCases、dataScripts、uiCases、records、users、functional、requirement、caseGeneration、harvester、flowRecorder、browserRecord、healLogs、templates、proxy、dashboard、aiConfig、dataFactoryAgent | 散落在各 render 函数内的 `api(...)` 调用 |
| `src/api/upload.js` | 文件上传专用（FormData + 进度） | 散落的 `fetch` 直连 |

迁移规则：
- 每个 `api(...)` 调用点必须对应到 `src/api/modules/` 中一个具名函数，禁止在组件内直接调用 axios。
- 文件上传统一走 `upload.js`，消除 R-15（fetch 直连未走统一封装）。
- JWT 注入由拦截器统一处理，组件无感知。

### 1.5 CSS 保留方案

当前：`static/styles.css`（单文件，`index.html#L10`），主题通过 `document.documentElement.dataset.theme` 切换（4 主题：shuimo/zhuanye/qingxuan/xiaolan），CSS 变量驱动。

新方案：

| 项 | 处理 |
|---|---|
| `styles.css` | 原文件保留在 `static/` 不动；Vue3 工程将其复制/引入为全局样式（`src/styles/legacy.css`），保证迁移期视觉一致 |
| 主题切换 | Pinia `themeStore` 管理，`data-theme` 仍写 `<html>`，与旧应用 localStorage `theme` key 共享，保证两套应用主题同步 |
| CSS 变量 | 保留原有变量定义，新增组件优先使用已有变量 |
| 组件样式 | 新组件用 `<style scoped>`，不污染全局；通用样式抽取到 `src/styles/` |
| Element Plus 主题 | 通过 CSS 变量覆盖 Element Plus 默认主题，与现有 4 主题对齐 |

迁移期不重写 CSS，保证 UI 视觉零差异；迁移完成后再评估是否重构样式系统。

### 1.6 不选型清单（明确排除）

| 排除项 | 理由 |
|---|---|
| Nuxt | 项目是 SPA + FastAPI 后端，无需 SSR；Nuxt 增加复杂度 |
| Vuex | 已被 Pinia 取代，Vue 官方推荐 Pinia |
| Tailwind | 现有 styles.css 已定义完整设计系统，引入 Tailwind 会造成两套样式系统冲突 |
| 微前端（qiankun/wujie） | 单团队单应用，微前端过度设计；用路由级共存即可 |

---

## 第二章 新旧系统共存方案

### 2.1 总体策略：双应用 + 路由级切换 + 共享 localStorage

核心思路：旧应用与 Vue3 应用是**两个独立 HTML 文档**，通过 FastAPI 分别挂载，按页面粒度互相重定向，共享 localStorage（同源）。

```
浏览器
  ├─ /                → 旧应用 static/index.html（默认入口，迁移期保持）
  ├─ /v3/             → 新应用 frontend/dist/index.html（Vue3）
  └─ /static/         → 旧静态资源（不动）
  └─ /api/            → FastAPI 后端（共用）
```

### 2.2 保证旧前端继续运行

- `static/` 目录与 `static/index.html` **全程不动**，FastAPI 的 `/` 路由与 `/static` 挂载保持不变（`app/main.py#L268`、`app/core/app_setup.py#L63`）。
- 迁移期默认入口仍是 `/`（旧应用）。用户通过导航栏进入已迁移页面时，旧应用重定向到 `/v3/<route>`。
- 旧应用的 14 个 JS 文件、`styles.css`、`admin/` 子页面均不修改。

### 2.3 逐页面迁移机制

**迁移配置**：新增 `frontend/migration-config.json`（由 Vue3 工程管理，构建时输出），列出已迁移的页面 key：

```json
{ "migrated": ["dashboard", "users"] }
```

**旧应用侧（不改源码，通过外部注入脚本）**：
- 在 `static/index.html` 末尾追加一个 `<script src="/static/migration-bridge.js">`（Phase 0 新增，唯一对旧前端的侵入点，仅此一个文件）。
- 该脚本劫持 `renderCurrentView`：若目标 view 在 `migrated` 列表内，则 `window.location.href = '/v3/' + view`。
- 该脚本通过 fetch `/static/migration-config.json` 读取配置（可缓存）。

> 注：`migration-bridge.js` 是 Phase 0 唯一新增到 `static/` 的文件，由实施计划批准后执行；本计划阶段不创建。

**Vue3 应用侧**：
- Vue Router 配置所有页面路由。
- 路由守卫：若目标路由**不在** `migrated` 列表，重定向回旧应用 `window.location.href = '/#' + view`。
- 已迁移页面正常渲染；未迁移页面由 Vue3 展示"该功能尚未迁移，正在跳转旧版…"后重定向。

**切换流程示例（dashboard 已迁移，apiCases 未迁移）**：
1. 用户在旧应用点击"工作台" → `migration-bridge.js` 检测 dashboard 已迁移 → 跳转 `/v3/dashboard`。
2. 用户在 Vue3 点击"接口用例库" → 路由守卫检测 apiCases 未迁移 → 跳转 `/#apiCases`。
3. 两个应用通过 localStorage 共享 token/projectId/theme，无需重新登录。

### 2.4 逐页面回滚方案

回滚粒度：**单页面**。

回滚操作：
1. 从 `migration-config.json` 的 `migrated` 数组中移除该页面 key。
2. 刷新浏览器（旧应用 fetch 新配置后不再重定向该页面）。
3. Vue3 应用路由守卫检测该页面未迁移，自动跳回旧应用。

回滚无需重新部署后端、无需改代码、无需 git 操作，仅需编辑一个 JSON 文件。

全量回滚：清空 `migrated` 数组，所有页面回归旧应用。

### 2.5 避免 window 全局冲突

| 措施 | 说明 |
|---|---|
| 独立文档 | 旧应用与 Vue3 应用是两个独立 HTML 文档，`window` 命名空间完全隔离，零冲突 |
| 无 iframe | 用 `window.location` 重定向而非 iframe，避免跨文档 DOM 操作 |
| 共享通道仅 localStorage | 两应用通过同源 localStorage 共享状态（token/projectId/theme/factory 草稿），不共享 `window` |
| Vue3 无 window 挂载 | Vue3 应用内部不向 `window` 挂载任何符号（除调试需要），从根本上消除旧应用的 window 污染问题 |

### 2.6 保持 FastAPI 当前静态资源结构

| 现状 | 迁移期变化 |
|---|---|
| `/` → `static/index.html`（`app/main.py#L268`） | 不变 |
| `/static` → `StaticFiles(directory=static)`（`app_setup.py#L63`） | 不变 |
| `/static/styles.css` | 不变 |
| `/static/admin/*.html` | 不变 |
| 新增 `/v3` → `StaticFiles(directory=frontend/dist)` | Phase 0 新增挂载（仅新增，不改已有） |
| 新增 `/static/migration-bridge.js` | Phase 0 新增一个桥接脚本 |

FastAPI 改动仅在 `app/main.py` 或 `app_setup.py` 新增一处 `app.mount("/v3", ...)`，不修改任何已有路由与挂载。该改动在 Phase 0 执行，本计划阶段不实施。

### 2.7 共享状态清单（localStorage 同步）

基线 6.3 节列出 14 个 localStorage key，两应用必须共享：

| key | 共享策略 |
|---|---|
| `token` | 共享（登录态） |
| `projectId` | 共享（当前项目） |
| `theme` | 共享（主题同步） |
| `factoryFlowId`/`factoryProjectId`/`factoryEnvId`/`factoryCaseIds`/`factoryVariables` | 共享（数据工厂草稿，Phase 7 迁移后旧应用不再写） |
| `dataScriptTab` | 共享 |
| `functionalTaskId` | 共享 |
| `savedUsername`/`savedPassword` | 共享（记住密码，迁移后建议改安全方案） |
| `dataFactoryFlows`/`dataFactoryDeletedBuiltins`/`dataFactoryDeletedFlows`/`dataFactoryHiddenFlows`/`dataFactoryHiddenBuiltins` | 共享（数据脚本流程列表） |
| `dataScriptCustomerIds` | 共享 |
| `functionalScanAuth:{origin}` | 共享 |

Vue3 侧通过 Pinia persistedstate 插件读写这些 key，key 名与值格式必须与旧应用完全一致（迁移期不得改 key 名或值结构）。

---

## 第三章 Phase 划分

### Phase 0：迁移准备

| 项 | 内容 |
|---|---|
| **涉及模块** | 工程脚手架（`frontend/`）、FastAPI 挂载、`migration-bridge.js`、`migration-config.json`、CI/构建脚本 |
| **前置条件** | ① 基线审计通过（已完成）；② 本实施计划通过人工审核（已完成）。**本次迁移只做前端框架迁移，不修复后端/历史 Bug/安全问题，这些全部记录为独立技术债（见第三章末"独立技术债清单"），不作为 Phase 0 前置条件** |
| **风险** | ① `migration-bridge.js` 注入旧应用可能影响现有页面加载（需限定只劫持 `renderCurrentView`，不改其他逻辑）；② Vue3 工程依赖安装引入 node_modules（需加入 .gitignore） |
| **验收标准** | ① Vue3 工程能 `pnpm dev` 启动空白页；② `pnpm build` 产出 `frontend/dist/`；③ FastAPI `/v3` 可访问 Vue3 空白页；④ 旧应用 `/` 正常运行，行为与迁移前完全一致；⑤ `migration-config.json` 为空数组时，旧应用无任何重定向行为；⑥ localStorage 共享 token 后，Vue3 空白页能读取到登录态 |
| **回滚方案** | 删除 `frontend/` 目录、删除 `/v3` 挂载、删除 `migration-bridge.js`，旧应用完全不受影响 |

### Phase 1：公共基础设施

| 项 | 内容 |
|---|---|
| **涉及模块** | Axios client + 拦截器、Pinia stores（auth/theme/app）、Vue Router 骨架、布局组件（Shell/Sidebar/Nav/Toast/Modal）、`legacy.css` 引入、通用组件（Table/FormDialog/Pagination） |
| **前置条件** | Phase 0 完成 |
| **风险** | ① 通用组件抽象不当导致后续页面反复改造；② `legacy.css` 与 Element Plus 样式冲突 |
| **验收标准** | ① 登录页能调用 `/api/auth/login` 并存 token；② 401 自动跳登录；③ 主题切换同步到 `<html data-theme>`；④ 侧边栏导航能跳转（未迁移页面跳回旧应用）；⑤ Toast/Modal 通用组件可用；⑥ Table 通用组件能渲染基线 23 个表格中的至少 1 个 |
| **回滚方案** | 清空 `migration-config.json`，Vue3 应用无页面被访问；Phase 1 代码保留在 `frontend/` 不影响旧应用 |

### Phase 2：低风险页面（dashboard / users / records）

| 项 | 内容 |
|---|---|
| **涉及模块** | dashboard 工作台总览、users 权限中心、records 执行报告（含分页） |
| **前置条件** | Phase 1 完成 |
| **风险** | ① records 分页逻辑（pageSize=20）与旧应用不一致；② dashboard 项目下拉筛选状态同步 |
| **验收标准** | ① 3 个页面 UI 与旧应用视觉一致（截图对比）；② API 调用 URL/method/payload 与旧应用一致；③ records 分页、筛选、重跑功能正常；④ localStorage `projectId`/`recordType` 读写一致；⑤ admin/非 admin 权限行为一致；⑥ 控制台 0 error |
| **回滚方案** | 从 `migration-config.json` 移除对应页面 key，该页面回退旧应用 |

### Phase 3：普通 CRUD（projects / envs / apiCases）

| 项 | 内容 |
|---|---|
| **涉及模块** | projects 项目空间（含环境表、测试账号表）、envs 残留路由（迁移时清理）、apiCases 接口用例库（含批量执行） |
| **前置条件** | Phase 2 完成 |
| **风险** | ① projects 级联删除逻辑；② apiCases 批量执行 + 多选（`selectedApiIds` Set）；③ 测试账号绑定弹窗（`openAccountBindingForm`）逻辑复杂 |
| **验收标准** | ① CRUD 全流程正常；② 批量执行结果与旧应用一致；③ 项目下拉全局筛选同步；④ envs 残留路由清理后无副作用；⑤ 权限：非 admin 不能增删改；⑥ 控制台 0 error |
| **回滚方案** | 从 `migration-config.json` 移除对应页面 key |

### Phase 4：复杂表格/弹窗（dataScripts / apiHarvester / caseGeneration）

| 项 | 内容 |
|---|---|
| **涉及模块** | dataScripts 数据工厂（拖拽排序、13 内置流程、5 localStorage key、已删除/已隐藏表）、apiHarvester 接口抓取、caseGeneration AI用例生成 |
| **前置条件** | Phase 3 完成 |
| **风险** | ① dataScripts 拖拽排序（需 vuedraggable 替代，基线 R-14）；② 13 内置流程硬编码（基线 R-13，建议下沉后端，但迁移期保持前端一致）；③ 5 个 localStorage key 读写时机；④ apiHarvester/caseGeneration 为外部 IIFE 模块，API 调用需逐一展开（基线 B-02） |
| **验收标准** | ① 拖拽排序与旧应用行为一致；② 13 内置流程参数表单与旧应用一致；③ 已删除/已隐藏/恢复功能正常；④ localStorage 5 key 值格式一致；⑤ apiHarvester 抓取/分析流程正常；⑥ caseGeneration 截图上传/生成用例正常；⑦ 控制台 0 error |
| **回滚方案** | 从 `migration-config.json` 移除对应页面 key |

### Phase 5：录制与执行模块（uiCases / uiRecord / uiVisual / flowRecorder / liveRecorder / browserRecord）

| 项 | 内容 |
|---|---|
| **涉及模块** | uiCases UI自动化（含录制、可视化执行）、flowRecorder HAR 录制、liveRecorder 实时录制、browserRecord 会话管理 |
| **前置条件** | Phase 4 完成（注：后端 11 个无鉴权端点属独立技术债，不作为前置条件；Vue3 前端迁移时按现状对接，鉴权缺失问题由独立技术债跟踪） |
| **风险** | ① UI 录制涉及轮询（`uiRecordState`/`uiVisualExecutionState` Timer，基线 6.1）；② 可视化执行步骤表动态更新；③ 实时录制会话生命周期管理；④ `openUiExecuteForm`/`renderUiCases` 重复定义（基线 R-12，属独立技术债，迁移时以当前运行版本为准，不修复旧代码）；⑤ 文件上传（HAR/截图）走 FormData |
| **验收标准** | ① UI 用例录制→保存→执行→查看结果全流程正常；② 可视化执行步骤实时更新；③ 实时录制启动/停止/保存正常；④ HAR 上传/预览/执行回放正常；⑤ Timer 正确清理，无内存泄漏；⑥ 控制台 0 error |
| **回滚方案** | 从 `migration-config.json` 移除对应页面 key |

### Phase 6：功能验证中心（functionalTests + 装饰器链重构）

| 项 | 内容 |
|---|---|
| **涉及模块** | functionalTests 功能验证中心，含 `window.renderFunctionalTests` 三次覆盖链（app.js → requirement-pack.js → quick-start.js）、requirement-verification/v2、test-status、test-record-rerun、test-record-report、problem-goods |
| **前置条件** | Phase 5 完成 |
| **风险** | ① **最高风险**：`renderFunctionalTests` 装饰器链（基线 R-04）需重构为模块化组合式函数，强依赖加载顺序的猴子补丁必须消除；② 功能测试执行异步进度轮询（`watchFunctionalExecutionProgress`）；③ Axure/截图上传；④ 失败诊断/自愈；⑤ requirement-pack/quick-start/test-status 三个模块的覆盖逻辑需逐一拆解理解后再重组 |
| **验收标准** | ① 功能任务 CRUD 正常；② 用例执行→进度→日志→截图→诊断全流程正常；③ 装饰器链重构后功能与旧应用完全一致；④ requirement-verification v1/v2 切换正常；⑤ test-status 状态刷新正常；⑥ 控制台 0 error |
| **回滚方案** | 从 `migration-config.json` 移除 functionalTests key（该模块是最后一个迁移的页面，回滚后旧应用全量接管） |

### Phase 7：旧代码退役

| 项 | 内容 |
|---|---|
| **涉及模块** | 切换默认入口 `/` → Vue3 应用、旧 `static/index.html` 与 14 个 JS 文件归档、`migration-bridge.js` 移除、`migration-config.json` 标记全量迁移 |
| **前置条件** | Phase 1 ~ Phase 6 全部页面迁移完成并通过验收 |
| **风险** | ① 切换默认入口后若有遗漏功能，用户无法回退（需保留旧应用可访问路径如 `/legacy/`）；② 旧应用归档可能影响 admin 外链（heal-logs/templates 独立页） |
| **验收标准** | ① `/` 直接打开 Vue3 应用；② 旧应用可通过 `/legacy/` 访问（保留 1 个版本周期）；③ 所有页面功能正常；④ `migration-bridge.js` 已移除；⑤ 控制台 0 error |
| **回滚方案** | 将 `/` 路由恢复指向 `static/index.html`，Vue3 应用退回 `/v3`；`migration-config.json` 清空 |

### Phase 8：最终回归测试

| 项 | 内容 |
|---|---|
| **涉及模块** | 全量功能回归、性能对比、旧应用下线 |
| **前置条件** | Phase 7 完成，Vue3 应用稳定运行 1 个版本周期 |
| **风险** | ① 长尾功能遗漏；② 性能问题（首屏加载、大数据量表格） |
| **验收标准** | ① 基线 Inventory 全量核对（11 视图 + 39 弹窗 + 23 表格 + 103 前端 API 调用 + 14 localStorage key）；② 性能不劣于旧应用（首屏 < 旧应用，表格渲染 ≤ 旧应用）；③ 旧应用 `static/` 下线（移入 `legacy/` 归档）；④ 控制台 0 error 0 warning |
| **回滚方案** | 恢复旧应用 `/` 入口（Phase 7 回滚方案的兜底） |

### 独立技术债清单（不纳入本次 Vue3 迁移）

> 本次 Vue3 项目只做前端框架迁移。以下问题全部记录为独立技术债，**不作为 Phase 0 前置条件，不在迁移期间修复**。Vue3 前端迁移时按现状对接，这些问题由独立任务跟踪处理。

| 技术债 ID | 来源 | 描述 | 处理时机 |
|---|---|---|---|
| TD-01 | 基线 R-01 | `browser_record.py`（5 个端点）与 `flow_recorder.py`（6 个端点）无鉴权，共 11 个端点 | 独立安全任务，不阻塞迁移 |
| TD-02 | 基线 R-02 | 资源归属校验全局缺失（核心业务表无 owner 字段） | 独立安全任务，不阻塞迁移 |
| TD-03 | 基线 R-03 / B-01 | `app/routers/functional_tasks.py` 文件缺失但 `__init__.py` 引用 | 独立后端任务，不阻塞迁移 |
| TD-04 | 基线 R-12 | `renderUiCases`/`openUiExecuteForm` 重复定义后者覆盖前者 | 迁移时以当前运行版本为准，旧代码不修复 |
| TD-05 | 基线 R-10 | `/api/files/screenshot?path=` 路径穿越风险 | 独立安全任务，不阻塞迁移 |
| TD-06 | 基线 R-11 | CORS allow_credentials=True + 多源 origins | 独立安全任务，不阻塞迁移 |
| TD-07 | 基线 R-13 | dataScripts 13 个内置流程硬编码在前端 | 迁移期保持前端一致，迁移稳定后再评估下沉后端 |
| TD-08 | 基线 R-16 | 记住密码用 base64 存储（非加密） | 迁移期保持现状，稳定后改安全方案 |
| TD-09 | 基线 R-18 | envs 残留路由 | 迁移时清理（Phase 3），不修复旧代码 |
| — | — | 数据库修改、后端 Router 修改、历史 Bug、安全问题 | 全部不纳入本次迁移 |

---

## 第四章 页面迁移顺序

### 4.1 迁移顺序与风险等级

| 序 | 页面 | 风险等级 | Phase | 安排理由 |
|---:|---|---|---|---|
| 1 | dashboard | 低 | Phase 2 | 只读为主，仅项目下拉筛选 + 最近执行表，无 CRUD 无弹窗，验证基础设施是否可用 |
| 2 | users | 低 | Phase 2 | 简单 CRUD，admin only，验证权限控制与表格组件 |
| 3 | records | 低-中 | Phase 2 | 含分页（唯一分页页），只读 + 重跑，验证分页与报告导出 |
| 4 | projects | 中 | Phase 3 | CRUD + 级联 + 环境表 + 测试账号表，验证级联与多表联动 |
| 5 | envs | 低 | Phase 3 | 残留路由，迁移时直接清理，顺便验证路由清理流程 |
| 6 | apiCases | 中 | Phase 3 | CRUD + 执行 + 批量 + 多选，验证执行类操作与 Set 状态 |
| 7 | apiHarvester | 中 | Phase 4 | 外部 IIFE 模块，API 调用需展开，验证外部模块迁移流程 |
| 8 | caseGeneration | 中-高 | Phase 4 | 截图上传 + AI 生成，验证文件上传与异步流程 |
| 9 | dataScripts | 高 | Phase 4 | 拖拽 + 13 内置流程 + 5 localStorage key + 已删除/已隐藏表，复杂度最高的 CRUD 页 |
| 10 | uiCases | 高 | Phase 5 | 录制 + 可视化执行 + Timer 轮询，验证录制类模块 |
| 11 | flowRecorder/liveRecorder/browserRecord | 高 | Phase 5 | HAR 上传 + 实时录制 + 会话管理，与 uiCases 同期迁移（录制类集中处理） |
| 12 | functionalTests | 极高 | Phase 6 | 装饰器链三次覆盖，最后迁移，需完整理解 requirement-pack/quick-start/test-status 链路后重构 |
| 13 | heal-logs | 低 | Phase 7 | 独立 admin 页，可在旧代码退役阶段迁移 |
| 14 | templates | 低 | Phase 7 | 独立 admin 页，同上 |

### 4.2 顺序设计原则

1. **自底向上**：先迁移依赖少的页面（dashboard 只读），后迁移依赖多的页面（functionalTests 装饰器链）。
2. **风险递增**：低风险页面先行，验证基础设施与通用组件；高风险页面待基础设施稳定后迁移。
3. **同类集中**：录制类（uiCases/flowRecorder/liveRecorder）集中在 Phase 5，复用录制/轮询/会话管理的通用逻辑。
4. **独立页最后**：admin 独立页（heal-logs/templates）与主 SPA 解耦，最后迁移不影响主线。
5. **装饰器链压轴**：functionalTests 涉及 3 个文件覆盖 `renderFunctionalTests`，是全项目最复杂的迁移点，放最后确保前序基础设施已充分验证。

---

## 第五章 每个阶段验收方式

### 5.1 通用验收清单（每个 Phase 均执行）

| 验收项 | 方法 | 通过标准 |
|---|---|---|
| **UI 对比** | 同一页面在旧应用与新应用各截图，并排对比 | 视觉无差异（布局/颜色/字体/间距/图标一致） |
| **API 对比** | 浏览器 DevTools Network 录制两应用的请求 | URL/method/payload/response 字段一致；调用时机一致 |
| **功能对比** | 按"页面行为矩阵"（基线 2.4）逐项手动测试 | 14 项行为（加载/刷新/筛选/新建/编辑/删除/执行/批量/导入/导出/弹窗/表格/分页/权限）全部一致 |
| **localStorage 对比** | DevTools Application 面板对比两应用的 localStorage | 涉及的 key 值格式与读写时机一致 |
| **权限对比** | 分别用 admin 与非 admin 账号测试 | 增删改按钮可见性与后端 403 行为一致 |
| **控制台错误检查** | DevTools Console | 0 error；warning 评估是否可接受 |
| **回滚验证** | 从 `migration-config.json` 移除该页面 key 后刷新 | 该页面回退旧应用且功能正常 |

### 5.2 各 Phase 专项验收

| Phase | 专项验收 |
|---|---|
| Phase 0 | 旧应用零影响（`migration-config.json` 空数组时行为与迁移前完全一致） |
| Phase 1 | 登录态跨应用共享（旧应用登录 → Vue3 免登录；Vue3 登出 → 旧应用也登出） |
| Phase 2 | records 分页 pageSize=20 与旧应用一致；重跑功能 API 调用一致 |
| Phase 3 | projects 级联删除后 envs/apiCases/testRecords 同步删除行为一致 |
| Phase 4 | dataScripts 拖拽排序后 localStorage `dataFactoryFlows` 顺序一致；13 内置流程参数 schema 一致 |
| Phase 5 | Timer 清理验证（离开页面后无残留轮询请求）；录制保存后数据与旧应用格式一致 |
| Phase 6 | 装饰器链重构后功能等价性验证（requirement-pack/quick-start/test-status 三模块覆盖的功能逐一对比） |
| Phase 7 | 默认入口切换后全量页面可访问；旧应用 `/legacy/` 可访问 |
| Phase 8 | 基线 Inventory 全量核对（见 5.3） |

### 5.3 Phase 8 Inventory 全量核对清单

迁移完成后必须与基线报告附录 E 逐项核对：

| 类别 | 基线数量 | 核对方法 |
|---|---:|---|
| HTML 文件 | 3 | Vue3 工程产出 1 个 index.html + 2 个 admin 页 |
| JS 文件 | 14 | Vue3 工程不再有裸 JS 文件，转为 SFC + JS 模块 |
| SPA 视图 | 11 | Vue Router 路由数 = 11 |
| 残留路由 | 1（envs） | 应已清理，= 0 |
| 独立 admin 页 | 2 | heal-logs + templates |
| 弹窗 | 39 | 组件数核对（38 主应用 + 1 admin） |
| 表格 | 23 | 组件数核对 |
| 菜单条目 | 10 | 侧边栏导航数 |
| localStorage key | 14 | Pinia persistedstate 配置核对 |
| 后端 API 调用 | 103 | `src/api/modules/` 函数数核对（.js 文件） |
| 主题 | 4 | themeStore 核对 |
| 内置数据脚本流程 | 13 | 核对（建议已下沉后端则核对后端配置） |

---

## 第六章 最终结论

### 6.1 是否具备开始 Phase 0 的条件

**结论：已具备，可直接进入 Phase 0。**

本次 Vue3 迁移只做前端框架迁移，不修复后端/历史 Bug/安全问题（详见第三章末"独立技术债清单"）。基线审计（第二轮验证通过）已提供完整的 Truth Source，技术选型（JavaScript）与共存方案已明确，Phase 划分与验收标准已定义，无其他前置阻塞项。

### 6.2 计划完整性自检

| 要求项 | 是否覆盖 |
|---|---|
| ① 技术选型（Vue3/Vite/TS 理由/Router/Pinia/API 封装/CSS 保留） | ✓ 第一章 |
| ② 新旧系统共存方案（旧前端运行/逐页迁移/逐页回滚/window 冲突/FastAPI 结构） | ✓ 第二章 |
| ③ Phase 划分（Phase 0~8，每 Phase 含模块/前置/风险/验收/回滚） | ✓ 第三章 |
| ④ 页面迁移顺序（顺序/风险等级/理由） | ✓ 第四章 |
| ⑤ 每阶段验收方式（UI/API/功能/localStorage/权限/控制台/回滚） | ✓ 第五章 |
| ⑥ 最终结论（是否具备 Phase 0 条件） | ✓ 第六章 |

### 6.3 关键风险提示

| 风险 | 应对 |
|---|---|
| functionalTests 装饰器链重构（R-04）是最高风险点 | 放在 Phase 6 最后迁移；迁移前需完整记录 `requirement-pack.js`/`quick-start.js`/`test-status.js` 三模块的覆盖逻辑 |
| 14 个 JS 文件的外部模块 API 调用未完全展开（B-02） | Phase 4/5/6 迁移时需逐文件展开 API 调用，补充到 `src/api/modules/` |
| dataScripts 13 内置流程硬编码（TD-07） | 迁移期保持前端一致，属独立技术债，迁移稳定后再评估下沉后端 |
| localStorage 值格式不一致导致跨应用状态错乱 | 迁移期严格保持 key 名与值格式不变；Pinia persistedstate 配置需逐一核对 |
| JavaScript 无类型检查 | 迁移期靠运行时测试与 5.1 节验收清单保证；TS 作为迁移稳定后的独立技术债评估 |

### 6.4 后续行动

本实施计划已通过人工审核（含本次调整）。后续：

1. 直接启动 Phase 0（迁移准备）。
2. 每个 Phase 完成后执行 5.1 节通用验收 + 5.2 节专项验收，通过后方可进入下一 Phase。
3. 独立技术债清单（TD-01 ~ TD-09）由独立任务跟踪，不阻塞迁移主线。

**本轮仅更新实施计划，不开始真正迁移。完成后停止。**
