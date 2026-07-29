# Frontend V2 Phase 1 Review & Stabilization Report

**Document ID:** `2026-07-28-phase1-review`  
**Date:** 2026-07-28  
**Phase:** 1.5 — Review only  
**Scope:** Phase 1 Design System Foundation  
**Constraint:** 本轮不修改生产代码、不开始 Phase 2

---

## 1. 修改文件分析

### 1.1 新增文件

| 文件 | 职责 | 评价 |
|---|---|---|
| `static/design-tokens.css` | Semantic Token + Legacy Bridge | **合格**：作为唯一真相源方向正确；存在命名冲突与未消费 Token（见 §3） |
| `static/design-system-base.css` | Button/Toast/Shell/Focus/Motion 基础覆盖 | **基本合格**：实现了去渐变/去 glow/去扫光；含 `!important` 与少量魔法数 |
| `static/v2-theme-lock.js` | 强制 `forest-light` | **有风险但可接受**：未改业务 API；会改写 `localStorage.theme` 的**值**（key 未改） |
| `docs/superpowers/specs/2026-07-28-design-system.md` | 规范文档 | 合格 |

### 1.2 修改文件

| 文件 | 改动摘要 | 业务影响 |
|---|---|---|
| `static/index.html` | 追加 tokens/base/lock 引用 | 无业务逻辑变更 |
| `frontend/index.html` | 同上 | 无 |
| `static/admin/templates.html` | 同上 | 无 |
| `static/admin/heal-logs.html` | 同上 | 无 |
| `frontend/src/stores/theme.js` | 多主题 → Forest Light 归一 | 仅主题表现；key 仍为 `theme` |
| `frontend/src/components/AppShell.vue` | 移除主题切换 UI；admin 链接去行内色 | 导航/权限/退出未改 |
| `frontend/src/components/AppToast.vue` | 删除 scoped 覆写，复用全局 `.toast` | 仅视觉；生命周期仍 2600ms |
| `frontend/src/styles/main.css` | 挂载点使用 Token | 无 |

### 1.3 未触碰（确认）

- `static/migration-bridge.js` / `migration-config.json`
- Router、API、Python、数据库、Agent/数据工厂逻辑
- `static/app.js` 业务逻辑（主题 picker DOM 仍在，靠 CSS 隐藏）

### 1.4 加载顺序（正确）

```text
styles.css
  → design-tokens.css
  → design-system-base.css
  → v2-theme-lock.js
```

结论：**覆盖顺序设计正确**。Token 在 `styles.css` 之后，可压过 `:root` 靛蓝默认。

---

## 2. 风险分析

| ID | 级别 | 问题 | 影响 | 建议时机 |
|---|---|---|---|---|
| R1 | **Medium** | `--shadow-sm` 先定义为语义 sm，后被 Legacy Bridge 覆盖为 `var(--shadow-xs)` | Modal/Toast 的 `--modal-shadow`/`--toast-shadow` 解析时可能变成 xs；Token 语义混乱 | Phase 1.5 修复批（可选）或 Phase 2 前 |
| R2 | **Medium** | Toast **机制仍双轨**：Static `#toast`+`showToast`；Vue `AppToast`+Pinia；`frontend/index.html` 仍保留闲置 `#toast` | 样式已统一，但 DOM/状态机仍两套；未来易再分叉 | Phase 3 Shell 统一机制（非必须挡 Phase 2） |
| R3 | **Medium** | `v2-theme-lock` 的 `MutationObserver` 强制任何 `data-theme` 回写 `forest-light` | 会阻碍未来 Dark Mode（V3）实验；也会压制调试旧主题 | V3 前必须改造；文档已声明 V3 |
| R4 | **Low** | `localStorage.theme` **值**被改写为 `forest-light`（key 未改） | 用户旧主题偏好丢失；符合产品决策，但不可逆除非备份 | 可接受；文档注明 |
| R5 | **Low** | `design-system-base` 已覆盖 `.login-panel` / `.login-wrap` | Phase 1 边界略越到登录外观；Phase 2 可能重复劳动 | Phase 2 以 Token 精修即可，勿大拆 |
| R6 | **Low** | `[data-theme="shuimo"] .brand strong` 等旧规则特异性更高 | 若 lock 失效且 theme=shuimo，渐变镂空可能回潮 | 保持 lock；或后续提高 base 特异性 |
| R7 | **Low** | Base 中魔法数：`#9a6e24`、`28px`、`15px`、`0.8s` 等 | 违反「禁止魔法数」严格标准 | 收敛进 Token |
| R8 | **Info** | `.theme-picker { display:none !important }` | Static 仍渲染 4 个 theme-dot 按钮（不可见） | 可接受；勿在本轮改 app.js |
| R9 | **Info** | Migration Bridge / Router / API | **未发现影响** | 保持 |

**总体风险：** Phase 1 对业务路径安全；主要风险在 Token 命名自洽性与 Toast 双机制技术债，**不阻塞登录视觉 Phase 2**，但建议先做小修复或明确接受。

---

## 3. Design Token 完整性

### 3.1 已覆盖类别（达标）

Color / Background / Surface / Text / Border / Shadow / Radius / Spacing / Typography / Motion / Z-index / Layout / Sidebar / Topbar / Button / Input / Card / Table / Modal / Toast / Badge / Timeline / Permission / Log / Loading / Skeleton / Empty / Error。

### 3.2 重复 / 冲突

| 问题 | 说明 |
|---|---|
| `--shadow-sm` 自覆盖 | 语义定义被 Legacy Bridge 再次赋值覆盖（R1） |
| `--font-weight-bold` == `--font-weight-semibold` | 均为 600，区分无效 |
| `--color-focus` == `--color-brand-primary` | 可接受别名，但属重复字面量 |
| `--color-log-bg` == `--color-sidebar` | 可改为引用 |

### 3.3 命名不一致

| 现象 | 建议 |
|---|---|
| 文档曾用 `--color-brand-primary-hover`，实现为 `--color-brand-hover` | 统一文档与代码（推荐保留实现名） |
| 文档曾用 `--color-border-default`，实现为 `--color-border` | 同上 |
| Legacy `--shadow-sm` 与 Semantic `--shadow-sm` 同名不同义 | Legacy 应映射到 `--legacy-shadow-sm` 或只 bridge `--shadow` |

### 3.4 未引用 / 弱引用 Token（预留可接受）

以下在 Phase 1 几乎未被 base 消费，属「先行定义」：

- `--bp-sm/md/lg/xl`（断点仅作文档值，media query 未用变量——CSS 限制）
- `--motion-dialog`
- `--z-base` / `--z-dropdown` / `--z-overlay`（overlay 数值 45 > modal 40，语义可疑）
- `--grid-gap` / `--font-numeric` / `--color-bg-muted`
- `--input-placeholder` / `--card-padding`
- `--modal-width-sm` / `--modal-width-lg`
- `--toast-lifetime`（JS 仍硬编码 2600）
- `.ds-timeline*` / `.ds-permission-panel` / `.ds-skeleton` / `.ds-loading`（基建 class，页面未用）

### 3.5 Legacy Bridge 评价

| 项 | 结论 |
|---|---|
| 是否合理 | **是** — 用旧变量名指向语义 Token，避免改 `app.js` 模板 |
| 是否消灭蓝紫默认 | **是** — `:root` 与四旧 theme 选择器均映射 Forest Light |
| 是否消灭 glow | **是** — `--accent-glow` 等为 `transparent` |
| 副作用 | shadow 命名冲突（R1）；旧 `styles.css` 主题块仍在，靠后加载覆盖 |

### 3.6 蓝紫残留

| 位置 | 状态 |
|---|---|
| `design-tokens.css` / `design-system-base.css` | **无** `#6366f1` / `#3b82f6` |
| `styles.css` 内旧主题定义 | **仍存在**（兼容保留）；运行时被 Token 覆盖 |
| Static theme-dot 行内 `background:#6366f1` | DOM 仍在但 `display:none`，用户不可见 |

---

## 4. 兼容性分析

### 4.1 旧 Static

| 检查项 | 结果 |
|---|---|
| 入口仍加载 `app.js` + migration-bridge | 是 |
| 旧 class（`.btn` `.panel` `.toast`）仍工作 | 是，样式被 base 重绘 |
| 主题切换 UI | 隐藏，不删业务事件绑定 |
| 风险 | 全局替换按钮/面板观感；功能路径未改 |

### 4.2 Vue

| 检查项 | 结果 |
|---|---|
| `/v3` 同源 CSS | 是 |
| `theme.js` 与 lock 一致 | 是，均强制 `forest-light` |
| AppShell 导航 / adminOnly / logout | **保留** |
| AppToast 样式 | 与 Static 共用 `.toast` |

### 4.3 Migration Bridge

| 检查项 | 结果 |
|---|---|
| 文件是否修改 | **否** |
| 跳转 `/v3/<view>` / `/#/<view>` | **不受影响** |
| `migration-config.json` | **未改** |

### 4.4 Theme Lock 专项

| 问题 | 结论 |
|---|---|
| 是否修改业务逻辑 | **否**（无 API/权限/流程） |
| `localStorage` key | 仍为 `theme` |
| `localStorage` value | 会被写成 `forest-light`（产品决策） |
| 旧主题兼容 | CSS 块保留；运行时视觉统一为 Forest Light |
| 未来 Dark Mode | **当前 Observer 会阻拦**；V3 需改为允许名单或关闭 lock |

### 4.5 Toast 专项

| 问题 | 结论 |
|---|---|
| 样式是否统一 | **是** — 均用全局 `.toast`（右下、Forest 色） |
| 是否仍双 Toast | **机制双轨仍在**（R2）：Static DOM vs Vue 组件；Vue HTML 闲置 `#toast` |
| 生命周期 | 双方约 2600ms，一致 |

### 4.6 AppShell 专项

| 问题 | 结论 |
|---|---|
| 是否只去主题切换 | **是**（Vue 模板删除 picker；Static CSS 隐藏） |
| 是否删除业务逻辑 | **否** |
| 权限 | `adminOnly` / `isAdmin` 链接仍在 |
| 导航 | `navigateToView` 未改 |

---

## 5. CSS 质量检查

### 5.1 `!important`

| 位置 | 用途 | 评价 |
|---|---|---|
| `.theme-picker` | 隐藏旧 picker | 可接受 |
| `.toast[hidden]` | 保证 hidden 生效 | 可接受 |
| `prefers-reduced-motion` 块 | 无障碍降级 | 可接受 |

### 5.2 魔法数（base 中）

`#9a6e24`、`28px`（stat）、`15px`/`44px`（nav）、`14px`/`10px`（padding）、`3px`、`0.8s`（spin）、`8px`/`6px`（timeline）等。

### 5.3 重复颜色 / 阴影 / 动画

- 多处直接写 `rgba(255,255,245,…)` 未 Token 化  
- `--shadow-sm` 语义重复覆盖（R1）  
- `styles.css` 旧 `@keyframes` 仍在，base 已关掉部分（btn::after、shimmer）

---

## 6. 遗留问题

1. Shadow Token 自相矛盾（R1）  
2. Toast 双机制（R2）  
3. Theme lock 对 V3 Dark Mode 不友好（R3）  
4. Base 魔法数未清零（R7）  
5. 大量预留 Token / `.ds-*` 尚未被页面消费（预期内）  
6. `styles.css` 巨型旧主题块仍在，增加认知负担  
7. Vue `index.html` 闲置 `#toast`/`#modal` 与组件方案并存  
8. `sidebar-admin-link` class 未单独定义（靠 `.sidebar-foot a`，无功能问题）  
9. 工作区仍有无关未提交：`app/executors/api.py` 等（勿混入视觉提交）

---

## 7. 建议修改（稳定化清单，本轮不实施）

> 下列为建议，**Phase 1.5 审查轮次不改代码**。若开「Phase 1.5 fix」小批，优先 P0。

### P0（进入 Phase 2 前建议处理）

1. **修复 `--shadow-sm` 覆盖**：Legacy Bridge 不要重定义语义 `--shadow-sm`；改为  
   `--shadow: var(--shadow-xs); --shadow-lg: var(--shadow-sm);` 且保留语义 sm 不被覆盖。  
2. **文档对齐**：`design-system.md` 与实际 Token 名（`brand-hover` / `color-border`）一致。

### P1（Phase 2/3 可顺带）

3. 将 `#9a6e24`、stat 字号等收入 Token。  
4. Vue `index.html` 移除闲置 `#toast`（确认无代码依赖后）。  
5. `--toast-lifetime` 与 `toast.js` 2600 单一来源（或文档标明 JS 为准）。

### P2（后续）

6. Theme lock 增加 `ALLOWED_THEMES` 白名单，为 V3 `dark` 预留。  
7. 评估删除或归档 `styles.css` 中废弃主题块（需单独批准）。  
8. Toast 机制合并为单一实现（Phase 3）。

---

## 8. 是否建议进入 Phase 2 Login Redesign

### 结论：**有条件建议进入**

| 条件 | 说明 |
|---|---|
| 可进入 | Phase 1 未破坏 API / Router / Migration / 权限 / 导航；Forest Light Token 已挂载 Static+Vue |
| 建议先确认 | 是否接受 R1 shadow 命名问题在 Phase 2 前用 1 个小 fix 修掉；或明确接受技术债 |
| Phase 2 边界 | **仅**登录页视觉（旧 `renderLogin` + Vue `LoginView`）；禁止改登录 API、token key、记住密码语义 |
| 注意 | Base 已部分样式化 `.login-panel`；Phase 2 应增量精修，避免推翻 Token |

### 不建议无门禁直接大改

若设计负责人要求「Token 零冲突再动页面」，则先做 **P0 shadow 修复** 再开 Phase 2。

---

## 9. Review 结论摘要

| 项 | 结果 |
|---|---|
| Phase 1 目标达成 | **是**（Token + Base + Theme Lock + 文档） |
| 业务安全 | **是** |
| Migration 安全 | **是** |
| 样式债务 | **有**（shadow 冲突、Toast 双轨、魔法数） |
| 生产代码本轮是否修改 | **否**（本审查轮次） |
| 建议 Phase 2 | **有条件同意** |

---

*End of Phase 1.5 review. No production code changed in this deliverable.*
