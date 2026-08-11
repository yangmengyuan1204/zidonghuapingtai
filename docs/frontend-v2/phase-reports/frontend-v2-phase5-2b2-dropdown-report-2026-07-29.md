# Frontend V2 Phase 5.2B2 — Overlay Foundation & BaseDropdown Report

- 日期：2026-07-29
- 分支：`codex/safe-refactor-preserve-features`
- 基线 HEAD：`797a7e1c3d00293e0cb29cf89f894b1113e2d667`
- Implementation：`PASS`
- Verification：`PASS`
- 最终结论：`PHASE 5.2B2 PASS`

## Scope

本阶段只实现运行时 V2 Portal、最小 Overlay Stack、BaseDropdown、BaseDropdownItem、Dropdown validator、Component Lab 场景、必要 Component Token 与导出更新。未开始 Modal、Toast、Focus Trap、Scroll Lock、Shell、API Cases 或业务页面接入。

## Files Created

- `frontend/src/components/v2/overlay/portal.js`：运行时唯一 `.frontend-v2-portal` 与 owner 生命周期。
- `frontend/src/components/v2/overlay/overlayStack.js`：最小 Overlay 登记、同组互斥、顶层 Escape。
- `frontend/src/components/v2/base/BaseDropdown.vue`：受控 Dropdown、Teleport、定位和交互。
- `frontend/src/components/v2/base/BaseDropdownItem.vue`：menuitem、disabled、icon、suffix、danger 与 select。
- `frontend/scripts/validate-v2-dropdown.mjs`：本阶段静态合同 validator。
- `docs/frontend-v2/phase-reports/frontend-v2-phase5-2b2-dropdown-report-2026-07-29.md`：本报告。

## Files Modified

- `frontend/src/components/v2/base/index.js`：新增 BaseDropdown 与 BaseDropdownItem 导入/导出，总导出数 14。
- `frontend/src/styles/v2/tokens.component.css`：新增 Dropdown 菜单、菜单项、定位与 danger cue Component Token。
- `frontend/src/dev/V2BaseComponentsLab.vue`：新增全部 Dropdown 验证场景。
- `frontend/scripts/validate-v2-support-components.mjs`：保留既有 12 个组件全部校验，将完成组件导出合同扩展为 14；Primitive 与 Supporting Components 校验逻辑未删除或降级。

阶段开始前，Support validator、BaseTooltip 和 Component Lab 已包含 Phase 5.2B1 后续增强；这些既有改动不归属于本阶段。本阶段未覆盖或回退它们。

## Portal / Overlay Architecture

- Dropdown 打开时按 owner acquire，创建带 `data-v2-portal-managed="true"` 的唯一 `.frontend-v2-portal`。
- 只复用本模块管理的 Portal；重复 managed Portal 合并子节点后删除。外部误建同名节点仅移除保留 class，不删除或清空其 DOM。
- 最后一个 owner 释放时清空并删除 managed Portal；unmount 同步释放。
- Portal 使用已有 `.frontend-v2, .frontend-v2-portal` Token 作用域，未向 `:root/html/body` 注入 V2 Token。
- Overlay Stack 只提供登记、同 `dropdown` group 互斥、顶层 Escape 与全局 keydown listener 生命周期；未实现 Focus Trap 或 Scroll Lock。

## Dropdown Contracts

- `open` 是严格受控真值：可见性由 `computed(() => props.open && !props.disabled)` 派生，用户交互只 emit `update:open`。
- 支持 `bottom-start`、`bottom-end`、`top-start`、`top-end`。
- fixed 定位；左右按 viewport gap clamp；resize 与 capture scroll 通过 requestAnimationFrame 重新定位。
- 支持 outside click、`closeOnSelect=false`、`closeOnOutside=false`、`matchTriggerWidth` 和同组互斥。
- 所有 pointerdown、resize、scroll、keydown listener 与 requestAnimationFrame 均在关闭或卸载时清理。
- BaseDropdownItem 支持 disabled、icon、suffix、danger；danger 提供 Token 化颜色和非颜色 `!` cue。
- 一次 item 激活只经过一条 item select 与一条 parent select 路径；未使用 `v-html`、Router、API、Store 或第三方定位依赖。

## Keyboard / ARIA

- Trigger：`aria-haspopup="menu"`、受控 `aria-expanded`、唯一 `aria-controls`。
- Menu：`role="menu"`、`aria-orientation="vertical"`。
- Item：原生 button、`role="menuitem"`、disabled 同时提供原生 disabled 与 `aria-disabled="true"`。
- 浏览器实测 ArrowDown、ArrowUp、Home、End、Enter、Space、Escape、Tab。
- disabled item 被跳过；Escape 关闭并把焦点返回 trigger；Tab 关闭且不阻止原生焦点前进，不形成 Focus Trap。

## Component Lab

实际地址：`http://127.0.0.1:5173/v3/dev/v2-base-components.html`

实际覆盖四种 placement、Disabled Trigger、Disabled Item、Danger Item、Icon、Suffix、`closeOnSelect=false`、`closeOnOutside=false`、`matchTriggerWidth`、无可用项、长文本、viewport edge、双 Dropdown 互斥、打开时卸载、外部受控 open/close。

## RED / GREEN

### 初始 RED

首次只创建 `validate-v2-dropdown.mjs` 后执行，因 Portal/Overlay/Dropdown/Item/Token/Lab 合同缺失退出 1。

按人工批准调整 Support validator 后再次执行，仍因 BaseDropdown 与 BaseDropdownItem 导出缺失退出 1，没有提前 GREEN。

### 审查补充 RED

独立审查发现 open 内部镜像不够严格、Portal 所有权边界和 validator 证据不足。先补断言后运行 Dropdown validator，退出 1，失败项为：严格受控可见性、禁止内部写受控状态、danger 非颜色 cue、只复用 owned Portal。最小修复后转 GREEN；复审无 Critical / Important 阻塞。

## Validators / Build

- `node frontend/scripts/validate-v2-foundation.mjs`：通过，6 个 CSS 文件、189 required tokens。
- `node frontend/scripts/validate-login-redirect.mjs`：通过，9/9。
- `node frontend/scripts/validate-v2-base-components.mjs`：通过，7 个 Primitive。
- `node frontend/scripts/validate-v2-support-components.mjs`：通过，5 个 Supporting、14 个总导出。
- `node frontend/scripts/validate-v2-dropdown.mjs`：通过。
- `npm run build`：通过，Vite 5.4.21，123 modules transformed。
- `git diff --check`：通过；只有仓库已有 LF/CRLF 提示，无 whitespace error。

Build 保留既有警告：非 module 的 `/static/v2-theme-lock.js` 以及若干 `/static/*.css` 在 build time 不解析，运行时由 FastAPI 静态路径提供。本阶段未修改 Vite base、production input、package 或 lockfile。

## Browser Verification

- Portal：打开时唯一，关闭和 unmount 后数量 0；额外注入同名 unmanaged 节点时仍保持一个 reserved Portal 且不删除外部节点。
- Portal Token：`--v2-dropdown-surface` 计算值为 `#ffffff`。
- Trigger/Menu/Item ARIA、完整键盘模型、disabled skip、Escape 焦点恢复、Tab 非 trap：通过。
- outside click、互斥、外部受控 open/close、打开时卸载：通过。
- resize / scroll 重新定位、matchTriggerWidth、长文本最大宽度、左右 viewport clamp：通过。
- Component Lab API request：0；fetch/xhr：0。
- Component Lab 应用 Console error：0。浏览器默认 favicon 请求在未拦截首开时产生一条 404，因此干净验证会话仅拦截该非业务 favicon 请求；没有 Vue/Dropdown error 或 warning。
- 生产入口 `http://127.0.0.1:8000/v3/login`：表单正常，Console error 0，Portal 0。
- 未认证访问 `http://127.0.0.1:8000/v3/dashboard`：正确重定向到 `/v3/login?redirect=/dashboard`。
- 认证后 Dashboard：使用人工提供的有效账号完成真实登录；`POST /api/auth/login`、`GET /api/projects`、`GET /api/dashboard` 均返回 200，项目/环境/接口用例/UI 用例/执行记录统计与最近执行表正常渲染，Console error 0。
- legacy `http://127.0.0.1:8000/`：V2 Token 0、`.frontend-v2-portal` 0、Console error 0。

Vite 开发地址的 Vue Login 会对 `/v3/static/v2-theme-lock.js` 产生既有 404；生产 FastAPI 地址加载正常。本阶段禁止修改该静态路径或构建输入。

## Viewport Verification

- 1080：clientWidth=1080，scrollWidth=1080；edge menu left=875，right=1007。
- 1240：clientWidth=1240，scrollWidth=1240；edge menu left=350，right=482。
- 1440：clientWidth=1440，scrollWidth=1440；edge menu left=1227，right=1359。
- 1920：clientWidth=1920，scrollWidth=1920；edge menu left=1118，right=1250。

四档均无横向页面溢出，菜单均位于 12px viewport gap 内。

## Diff Audit

- 当前分支和 HEAD 未变化；未 stage、commit 或 push，cached diff 为空。
- GitNexus 索引无法识别新 Vue symbol，impact 为 UNKNOWN；生产源码扫描确认 Dropdown/Lab 未接入 main、App、Router、业务页面或 Vite production input。
- `detect-changes --scope all` 报告当前混合工作区 14 个 tracked files、7 symbols、0 affected processes、low risk；索引未覆盖本阶段 untracked Vue 文件，因此只作为辅助证据。
- 本阶段未执行 git add、reset、checkout、restore、clean、stash、commit 或 push。
- payment amount regression、system regression、backend、static、tests、pycache 及其他无关改动均未处理。
- Router、Guard、navigation.js、LoginView、Store、API、401、migration-config.json、Prototype、legacy、FastAPI、Vite base、production input、package、lockfile：本阶段零修改。

## Remaining Risks

1. Lab 原始首次导航会产生浏览器 favicon 404；应用自身 Console error 为 0。修复 favicon 需要修改允许清单外文件，本阶段未扩大范围。
2. Vite dev 下 Vue Login 的既有 `/v3/static/v2-theme-lock.js` 404 仅在开发地址出现；FastAPI 生产入口无该错误。
3. Portal 冲突处理会移除外部误用的保留 class，但不会删除或清空其节点；这是维持唯一性的明确边界策略。
4. Modal、Toast、Toast Store、完整 Focus Trap、Scroll Lock、Sidebar、Topbar、AppShell、API Cases 尚未开始。

## Final Result

`PHASE 5.2B2 PASS`
