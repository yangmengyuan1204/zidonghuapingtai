# Frontend V2 Phase 5.2B1 — Supporting Base Components Report

- 日期：2026-07-29
- 分支：`codex/safe-refactor-preserve-features`
- 目标：五个低风险 Supporting Base Components
- 最终结论：`PHASE 5.2B1 PASS`

## Scope

本轮仅实现：

1. BasePagination
2. BaseTooltip
3. BaseSkeleton
4. BaseEmptyState
5. BaseErrorState

本轮未实现或接入：

- BaseDropdown
- BaseModal
- BaseToast
- Portal 容器
- Focus Trap / Focus Management
- Sidebar
- Topbar
- AppShell
- API Cases
- 任何业务页面迁移

## Files Created

- `frontend/src/components/v2/base/BasePagination.vue`
- `frontend/src/components/v2/base/BaseTooltip.vue`
- `frontend/src/components/v2/base/BaseSkeleton.vue`
- `frontend/src/components/v2/base/BaseEmptyState.vue`
- `frontend/src/components/v2/base/BaseErrorState.vue`
- `frontend/scripts/validate-v2-support-components.mjs`
- `docs/frontend-v2/phase-reports/frontend-v2-phase5-2b1-support-components-report-2026-07-29.md`

## Files Modified

- `frontend/src/components/v2/base/index.js`
  - 保留 Phase 5.2A 七个直接 re-export。
  - 新增五个 Supporting Component 的 named export。
  - 最终对外导出 12 个 Base Component。
- `frontend/src/styles/v2/tokens.component.css`
  - 补充 Pagination、Tooltip、Skeleton、Empty State、Error State Component Token。
  - 所有新增 Token 只引用 Foundation 或 Semantic Token。
- `frontend/src/dev/V2BaseComponentsLab.vue`
  - 扩展开发专用状态矩阵和交互计数。
  - 保持独立 Vite dev 入口，不进入 production Router、菜单或 build input。

## Component Contracts

### BasePagination

- Props：`page`、`total`、`pageSize`、`siblingCount`、`disabled`、`ariaLabel`
- Emits：`change`
- 根节点：`nav`
- 页码和方向控件：原生 `button`
- 当前页：`aria-current="page"`
- 省略号：非交互 `span`
- 组件受控：只 emit 目标页码，不在内部持久化 page
- page 超出范围时只用于生成安全的 current page，不 emit 越界值
- 当前页、disabled、第一页 Previous、末页 Next 均不会错误 emit

### BaseTooltip

- Props：`content`、`placement`、`disabled`、`delay`、`id`
- Slot：`default`
- Tooltip：`role="tooltip"`，不进入 Tab 顺序
- 触发节点：通过 VNode clone 将 `aria-describedby` 放到真实触发元素
- 支持单根、多根 Fragment、mouseenter、mouseleave、focusin、focusout、Escape
- 离开、失焦、disabled、空 content、unmount 均清理 pending timer
- 不使用 Teleport、Portal、HTML 内容或 `v-html`
- 不覆盖触发元素的 click 行为

### BaseSkeleton

- Props：`variant`、`width`、`height`、`lines`、`animated`
- Variants：text、circle、rectangle
- Number 尺寸转换为非负 px；负数归零
- String 尺寸保留调用方单位，负值归零
- 多行 text 根据 lines 渲染，末行使用 V2 spacing class 缩短
- 根节点 `aria-hidden="true"`，不进入 Tab 顺序
- animated=false 和 reduced motion 下均停止 animation
- 不在内部输出 Loading 文案

### BaseEmptyState

- Props：`title`、`description`、`compact`、`iconHidden`
- Slots：`icon`、`action`、`default`
- title 必填，使用非页面级 `h2`
- title id 与 section `aria-labelledby` 关联
- icon 作为装饰时 `aria-hidden="true"`
- 未提供 action slot 时不渲染 action 容器
- compact 只改变间距
- 不调用 Router，不自动选择业务文案

### BaseErrorState

- Props：`title`、`message`、`retryable`、`retryLabel`、`busy`、`compact`
- Emits：`retry`
- Slots：`icon`、`details`、`action`
- 初始错误使用 `role="alert"`
- busy 重试状态使用 `role="status"` 和 `aria-busy`
- retryable 且无 custom action 时复用 BaseButton
- busy 时 BaseButton loading + disabled，且 retry handler 不 emit
- custom action 存在时不重复渲染默认重试按钮
- 不调用 API，不分类错误，不展示原始堆栈，不使用 `v-html`

## Pagination Algorithm

1. total 先归一为大于等于 0 的有限数。
2. pageSize 归一为至少 1。
3. 总页数使用：

   `Math.max(1, Math.ceil(total / pageSize))`

4. 当前页 clamp 到 `[1, totalPages]`。
5. 当页数不超过 `siblingCount * 2 + 5` 时全部展示。
6. 大页数时使用 Set 收集：
   - 首页
   - 末页
   - 当前页
   - 当前页左右 siblingCount 个页码
7. 排序后：
   - gap=2 时直接补齐缺失页码
   - gap>2 时加入唯一 ellipsis 标记
8. 因为使用 Set 和最终范围判断：
   - 无重复页码
   - 无页码 0
   - 无大于 totalPages 的页码
   - 支持首页、中间、末页和百万级总页数

实际浏览器序列覆盖：

- 1 页：`1`
- 5 页：`1 2 3 4 5`
- 靠前：`1 2 3 … 100`
- 首页：`1 2 … 100`
- 居中：`1 … 49 50 51 … 100`
- 靠后：`1 … 98 99 100`
- 末页：`1 … 99 100`
- 超大 total：`1 … 499999 500000 500001 … 1000000`

## Tooltip Lifecycle

### Open

- mouseenter：设置 hovered，清理旧 timer，按 delay 调度显示。
- focusin：设置 focused，按相同规则调度显示。
- disabled 或 content.trim() 为空时拒绝调度。

### Close

- mouseleave：清除 hovered；未聚焦时隐藏并清 timer。
- focusout：仅在焦点离开整个 Tooltip root 时清除 focused；未 hover 时隐藏。
- Escape：立即隐藏并清 timer，不拦截触发元素业务 click。
- content/disabled 变化：watch canShow，不可展示时立即隐藏。
- unmount：`onBeforeUnmount(clearShowTimer)`。

### ARIA

- visible 时生成真实 tooltip id。
- 单根触发 VNode clone `aria-describedby`。
- Fragment 被递归扁平化。
- 多根触发节点分别 clone 同一 tooltip id。
- 已有 `aria-describedby` 会与 tooltip id 合并。

## Token Usage

组件样式继续遵循：

`Foundation → Semantic → Component Token → scoped SFC style`

- Pagination：control size、surface、border、text、active、focus、disabled。
- Tooltip：inverse surface/text、dropdown shadow/z-index、offset、arrow、max width。
- Skeleton：surface/highlight、radius、dimensions、motion。
- Empty State：spacing、icon well、title/description、content width。
- Error State：danger soft icon well、title/message/details、spacing。

未修改 Foundation Token，未改变 Phase 5.2A Primitive Token 的公共语义。

## RED / GREEN Verification

### Initial RED

首次执行：

`node frontend/scripts/validate-v2-support-components.mjs`

准确失败：

- 五个组件文件缺失
- index.js 不是 12 个导出
- 五个 Supporting Component 导出缺失

### Tooltip DOM RED

首次真实浏览器验证发现：

- Tooltip 可见
- 但单根 trigger 的 `aria-describedby` 为 null

根因：slot VNode 可能被 Fragment 包装，属性 clone 到 Fragment 后不会落到真实 DOM。

修复后单根 trigger 的 describedBy 与 tooltip id 一致。

### Multi-root RED

审查补充多根 Fragment 回归：

- 修复前 Multi A / Multi B 的 `aria-describedby` 均为 None
- 修复后两个真实按钮均关联同一个 tooltip id

### GREEN

- Foundation：通过，6 个 CSS 文件、189 个 required token。
- Redirect：通过，9/9。
- Primitive：通过，7 个组件。
- Support Components：通过，5 个组件、12 个总导出。
- Build：通过，Vite 转换 123 个 production module。
- IDE lint：无新增错误。
- `git diff --check`：通过，仅有仓库既有 LF/CRLF 提示。

`frontend/package.json` 只有 dev/build/preview，无 lint 或 test script，因此未声称不存在的 npm lint/test 通过。

## Browser Verification

Component Lab：

`http://127.0.0.1:5174/v3/dev/v2-base-components.html`

实际渲染：

- Pagination：9 个状态组
- Tooltip：单根、四方向、键盘、disabled、empty、pending unmount、多根 Fragment
- Skeleton：6 个状态
- Empty State：5 个状态
- Error State：6 个状态

验证结果：

- Console error：0
- Component Lab API request：0
- 根节点 `.frontend-v2`：存在
- enabled 交互元素 Tab 顺序：完整、无重复、disabled 不进入

### Pagination

- current page 存在 `aria-current=page`
- First Previous disabled
- Last Next disabled
- 点击当前页：0 emit
- 单次 click：1 emit
- Enter 和 Space：各 1 emit
- disabled：0 emit
- 所有测试序列无重复、无 0、无越界
- ellipsis 未渲染为 button

### Tooltip

- Hover 显示和离开隐藏
- Focus 显示和 blur 隐藏
- Escape 关闭
- top/right/bottom/left placement class 正确
- disabled 不显示
- empty content 不显示
- unmount pending timer 无残留或 error
- 单根和多根 trigger 的 aria-describedby 均指向真实 tooltip

### Skeleton

- 多行数量：4
- circle：48 × 48，实际圆形 radius
- animated=false：animation-name none
- reduced motion：animation-name none
- aria-hidden=true
- 不进入 Tab 顺序

### Empty State

- 标题、描述、icon、action 可读
- action 可由 Enter 操作且单次执行
- 无 action slot 时无 action 容器

### Error State

- retryable：显示一个默认重试按钮
- non-retryable：0 个默认按钮
- busy：button disabled，0 emit
- 单次 click：1 retry emit
- custom action：仅一个自定义按钮
- 初始 role=alert
- busy role=status

## Accessibility Audit

- Pagination 使用 nav、aria-label、aria-current、原生 button。
- Tooltip 的描述关系落到实际聚焦元素，不只落在包装容器。
- Skeleton 从 accessibility tree 隐藏。
- Empty/Error 标题使用 h2 并通过 aria-labelledby 命名 region。
- Error busy 不反复使用 alert。
- 所有新增可交互控件保留 focus-visible。
- disabled 使用原生 disabled。
- 状态不只依赖颜色，均有文字、ARIA 或原生状态属性。

## Viewport Verification

- 1080：clientWidth=1080，scrollWidth=1080，无横向溢出。
- 1240：clientWidth=1240，scrollWidth=1240，无横向溢出。
- 1440：clientWidth=1440，scrollWidth=1440，无横向溢出。
- 1920：clientWidth=1920，scrollWidth=1920，无横向溢出。

## Production Regression

- `/`：legacy login form 正常。
- `/v3/login`：Vue login form 正常。
- 使用测试账号登录后 `/v3/dashboard` 正常进入。
- 浏览器 page error：0。
- legacy documentElement V2 Token：0。
- legacy body V2 Token：0。
- legacy `.frontend-v2/.frontend-v2-portal` 节点：0。

## Diff Audit

本轮开始时已存在大量未提交修改；其中 payment amount regression 相关后端、静态页和测试改动不属于本轮，本轮未覆盖或回退。

本轮禁止范围确认：

- Router / Router Guard：零本轮修改
- navigation.js：零本轮修改
- LoginView / Auth / 401：零本轮修改
- Store：零本轮修改
- API：零本轮修改
- App.vue / main.js：零本轮修改
- AppShell / Sidebar / Topbar：零本轮修改
- 业务页面：零本轮修改
- Prototype：零本轮修改
- legacy：零本轮修改
- FastAPI：零本轮修改
- migration-config.json：零本轮修改
- Vite base / production build input：零本轮修改
- package dependency / lockfile：零本轮修改

实施过程中分支 HEAD 前进到 `797a7e1`，该提交包含 V2 Foundation、Phase 5.2A 及本轮主体文件；最终复审补强仍仅涉及 Support validator、BaseTooltip 和 Component Lab。未由本轮执行 commit 或 push。

## Remaining Risks

1. BaseTooltip 是轻量定位，不实现碰撞检测、自动翻转、viewport avoidance 或 Portal。
2. BaseEmptyState 对“已声明但运行时返回空 VNode 的 action slot”按 slot 已提供处理；正常未提供 action slot 不生成容器。
3. Supporting Components 尚未接入任何生产页面。
4. Dropdown、Modal、Toast、Portal 和 Focus Management 尚未开始，留待 Phase 5.2B2。

## Final Result

`PHASE 5.2B1 PASS`
