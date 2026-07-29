# Frontend V2 Design System — Forest Light

**Document ID:** `2026-07-28-design-system`  
**Date:** 2026-07-28  
**Phase:** 1 / 1.6 — Design System Foundation + P0 Stabilization  
**Based on:** `docs/superpowers/specs/2026-07-28-frontend-v2-visual-audit.md`  
**Review:** `docs/superpowers/specs/2026-07-28-phase1-review.md`  
**Status:** Token + Base layer; Phase 1.6 fixed Shadow Legacy Bridge conflict  
**Canonical names:** code in `static/design-tokens.css` is the source of truth

---

## Design Philosophy

Forest Light 是面向 **Enterprise AI Workspace** 的视觉语言：

- Warm · Professional · Calm · Minimal
- 深森林绿 + 奶油白 / 暖象牙 + 暖灰 + 少量浅绿点缀
- 轻边框、低阴影、统一圆角、大量留白
- 长时间使用不疲劳

**禁止：** 科技蓝、赛博朋克、蓝紫渐变、毛玻璃、发光 glow、扫光、大阴影、过度动画。

**产品主题：**

| 项 | 决策 |
|---|---|
| V2 唯一主题 | `forest-light`（Forest Light） |
| 废弃产品切换 | `zhuanye` / `qingxuan` / `xiaolan` |
| 兼容 | 旧主题 CSS 块保留在 `styles.css`；运行时锁定为 Forest Light |
| Dark Mode | **V3**，本系统不定义 |

---

## Implementation Layout

### 为何新增独立文件

| 文件 | 原因 |
|---|---|
| `static/design-tokens.css` | 审计要求 Token 为唯一真相源；避免继续膨胀 `styles.css`；Static 与 Vue 同源消费 |
| `static/design-system-base.css` | 基础组件规则与禁用炫技覆盖，与 Token 分离便于回滚 |
| `static/v2-theme-lock.js` | 不改 `app.js` 业务逻辑的前提下锁定 `data-theme` / `localStorage.theme` 值 |

### 加载顺序（必须）

```text
styles.css
  → design-tokens.css      （语义 Token + 旧变量桥接，覆盖靛蓝默认）
  → design-system-base.css （Button/Toast/Shell/Focus/Motion）
  → v2-theme-lock.js       （产品主题锁定）
```

入口已接入：

- `static/index.html`
- `frontend/index.html`
- `static/admin/templates.html`
- `static/admin/heal-logs.html`

### 兼容性

- Migration Bridge：未改  
- Router / API / Token key 名 `theme`：未改  
- 旧页面继续使用 `.btn` / `.panel` / `.toast` 等 class；通过 legacy bridge 吃到 Forest Light  

---

## Color Token

> 下列名称与 `static/design-tokens.css` **完全一致**。  
> 不使用：`--color-brand-primary-hover`（正确名：`--color-brand-hover`）。  
> 不使用：`--color-border-default`（正确名：`--color-border`）。

| Token | 值 | 用途 |
|---|---|---|
| `--color-brand-primary` | `#2f5c4f` | 主品牌 / Primary 按钮 |
| `--color-brand-secondary` | `#7a9a88` | 辅助点缀 |
| `--color-brand-hover` | `#254a40` | 主色悬停 |
| `--color-brand-muted` | `#d8e5de` | 浅绿浅底 |
| `--color-bg-canvas` | `#f3f1ea` | 页面画布 |
| `--color-bg-surface` | `#fffdf8` | 卡片 / 面板 |
| `--color-bg-subtle` | `#ece8df` | 表头 / 次级区 |
| `--color-bg-muted` | `#e4e0d6` | 更弱底 |
| `--color-sidebar` | `#24352f` | 侧栏 |
| `--color-topbar` | `#fffdf8` | 顶栏 |
| `--color-border` | `rgba(68, 82, 74, 0.22)` | 默认边框 |
| `--color-border-light` | `rgba(68, 82, 74, 0.12)` | 轻边框 |
| `--color-border-strong` | `rgba(68, 82, 74, 0.36)` | 强调边框 |
| `--color-text-primary` | `#22332e` | 主文案 |
| `--color-text-secondary` | `#5c6b63` | 次文案 |
| `--color-text-muted` | `#7a877f` | 弱文案 |
| `--color-text-inverse` | `#f4f7f4` | 深色底文字 |
| `--color-text-on-brand` | `#ffffff` | 主按钮文字 |
| `--color-success` | `#2f7b5f` | 成功 |
| `--color-success-subtle` | `#d8eee4` | 成功浅底 |
| `--color-warning` | `#b5812f` | 警告 |
| `--color-warning-subtle` | `#f5ead2` | 警告浅底 |
| `--color-danger` | `#9b3a32` | 危险 |
| `--color-danger-subtle` | `#f3ddd9` | 危险浅底 |
| `--color-info` | `#4a7c6f` | 信息（柔和青绿，非艳蓝） |
| `--color-info-subtle` | `#d9e8e2` | 信息浅底 |
| `--color-focus` | `#2f5c4f` | 焦点描边色 |
| `--color-focus-ring` | `rgba(47, 92, 79, 0.28)` | 焦点光晕（非 glow 装饰） |
| `--color-overlay` | `rgba(34, 51, 46, 0.42)` | Modal backdrop |
| `--color-log-bg` | `#24352f` | 日志背景 |
| `--color-log-text` | `#e6ebe7` | 日志文字 |

**不得出现：** `#6366f1`、`#3b82f6`、蓝紫渐变、glow。

旧变量桥接示例：`--accent` → `--color-brand-primary`；`--accent-dark` → `--color-brand-hover`；`--line` → `--color-border`；`--accent-glow` → `transparent`。

---

## Typography

| 层级 | Token | 规格 |
|---|---|---|
| Display | `--text-display-size` | 28 / 600 / 1.25 / display 字体 |
| H1 | `--text-h1-size` | 22 / 600 / 1.3 |
| H2 | `--text-h2-size` | 18 / 600 / 1.35 |
| H3 | `--text-h3-size` | 16 / 600 / 1.4 |
| Body | `--text-body-size` | 14 / 400 / 1.55 |
| Caption | `--text-caption-size` | 12 / 600 / 1.45 |
| Code | `--text-code-size` | 13 / mono / 1.6 |

**字体栈：**

- 中文/UI：`--font-sans`（PingFang SC / Microsoft YaHei / system）
- Display：`--font-display`（Noto Serif SC…）— **禁止渐变镂空**
- 代码：`--font-mono`
- 数字：默认跟随 sans

字重主档：400 / 500 / 600。

---

## Spacing

```text
--space-1  4
--space-2  8
--space-3  12
--space-4  16
--space-5  20
--space-6  24
--space-7  32
--space-8  40
--space-9  48
```

---

## Radius

| Token | 值 |
|---|---|
| `--radius-sm` | 8 |
| `--radius-md` | 12 |
| `--radius-lg` | 16 |
| `--radius-xl` | 20（extra） |
| `--radius-pill` | 999 |

---

## Shadow

### Semantic（唯一真相，禁止被 Legacy 覆盖）

| Token | 值 | 用途 |
|---|---|---|
| `--shadow-none` | `none` | 默认按钮 / 多数控件 |
| `--shadow-xs` | `0 1px 2px rgba(34, 51, 46, 0.05)` | 卡片极轻（`--card-shadow`） |
| `--shadow-sm` | `0 4px 14px rgba(34, 51, 46, 0.08)` | Modal / Toast（`--modal-shadow` / `--toast-shadow`） |

禁止 glow 与更大阴影。

### Legacy Bridge（仅兼容旧名，Phase 1.6 P0）

| 旧变量名 | 映射 | 说明 |
|---|---|---|
| `--shadow` | `var(--shadow-xs)` | 旧「中阴影」降为 xs |
| `--shadow-lg` | `var(--shadow-sm)` | 旧「大阴影」封顶为 sm |

**禁止：** `--shadow-sm: var(--shadow-xs)`（Phase 1 曾因此覆盖语义 sm，已在 1.6 移除）。

组件应写：

```text
✅ box-shadow: var(--shadow-none);
✅ box-shadow: var(--shadow-xs);
✅ box-shadow: var(--shadow-sm);
✅ box-shadow: var(--card-shadow);   /* → xs */
✅ box-shadow: var(--modal-shadow);  /* → sm */
❌ box-shadow: none;                 /* 优先用 --shadow-none */
❌ 重新赋值 --shadow-sm / --shadow-xs / --shadow-none
```

---

## Motion

| 场景 | Token | 时长 |
|---|---|---|
| Hover | `--motion-hover` | 140ms（120–160） |
| Click | `--motion-click` | 100ms |
| Dialog | `--motion-dialog` | 180ms |
| Toast | `--motion-toast` | 180ms |
| Progress | `--motion-progress` | 200ms |
| Skeleton | `--motion-skeleton` | 1.4s |

缓动：`--ease-out` / `--ease-standard`。  
全站：`prefers-reduced-motion: reduce` 时近瞬时。

---

## Layout / Grid / Breakpoint

| Token | 值 |
|---|---|
| `--layout-sidebar-width` | 248px |
| `--layout-topbar-height` | 64px |
| `--grid-gap` | `--space-4` |
| `--bp-sm` | 560 |
| `--bp-md` | 900 |
| `--bp-lg` | 1200 |
| `--bp-xl` | 1440 |

验收关注：**1366×768**。

---

## Button

| 变体 | Class | 规则 |
|---|---|---|
| Primary | `.btn` | 实色 `--btn-primary-bg` |
| Secondary | `.btn.secondary` | 白底描边 |
| Danger | `.btn.danger` | 实色危险 |
| Ghost / Text | `.btn.ghost` `.btn.text` | 透明底 |

禁止：扫光 `::after`、渐变、glow、hover 位移抬升。

---

## Input

统一高度 `--input-height`、圆角、边框、focus ring（`--color-focus-ring`）。  
覆盖：input / textarea / select / checkbox accent。

---

## Card

`.panel` / `.stat`：实色 surface、轻边框、`--shadow-xs`、**无毛玻璃**、**无 hover 飞起**。

---

## Table

Header：`--table-header-bg`  
Row hover：`--table-row-hover`  
Density：comfortable（cell padding 12×16）  
Action：沿用 `.actions`，Phase 后续可收敛菜单。

---

## Modal

Header / Body / Footer padding 来自 Token。  
宽度：sm 420 / md 640 / lg 880。  
Backdrop：`--color-overlay`，无 blur。

---

## Toast

**全项目唯一风格：**

| 项 | 规范 |
|---|---|
| 位置 | 右下（`right/bottom: var(--toast-offset)`） |
| 颜色 | `--toast-bg` + 左边 `--toast-border` |
| 动画 | `ds-toast-in` 180ms |
| 生命周期 | ~2600ms（与旧 `showToast` 一致） |
| Vue | `AppToast.vue` 去掉 scoped 覆写，复用全局 `.toast` |

---

## Sidebar

- 宽 `--layout-sidebar-width`
- 背景 `--color-sidebar`
- Hover / Active：浅透明底 + 左侧指示条（无光晕）
- 字体：15 / medium（下调旧 17/700）

---

## Topbar

- 高 `--layout-topbar-height`
- 背景 `--color-topbar` 实色
- 无 backdrop-filter
- 标题 H1 规格

---

## AI Components

| 组件 | Token / Class 基础 | Phase |
|---|---|---|
| Timeline | `.ds-timeline` / `.ds-timeline-item` | 1 基建，5 应用 |
| Permission Panel | `.ds-permission-panel` | 1 基建，5 应用 |
| Log Viewer | `.log-view` → `--log-bg` / `--log-text` | 1 去霓虹边 |

不改 Agent 状态机、轮询、合同、学习中心逻辑。

---

## Loading / Skeleton / Empty / Error

| 类型 | 规范 |
|---|---|
| Loading | `.ds-loading` spinner |
| Skeleton | `.ds-skeleton` 1.4s 微光 |
| Empty | `.empty` / `.empty-state` 静色，去掉 spin 炫技 |
| Error | `.alert.error` 使用 danger subtle |

---

## Accessibility

- `:focus-visible` → `--color-focus` 2px ring  
- 状态不只靠颜色（保留 badge 文案）  
- `prefers-reduced-motion` 全站降级  
- 危险操作仍依赖既有 `confirm`（不在本阶段改）

---

## Responsive

沿用既有 `@media (max-width: 900px/560px)`；Token 提供 `--bp-*` 供后续统一。  
Phase 2+ 页面改造时按 Token 断点收敛。

---

## Implementation Rules

1. Design Token 是唯一颜色/间距/圆角/阴影/动效真相源。  
2. 禁止组件内写死 hex（除 `design-tokens.css`）。  
3. 禁止新增第二套 Toast / Button 样式。  
4. 禁止恢复产品层多主题切换。  
5. 禁止本阶段修改 API / Router / migration / 业务 JS 流程。  
6. 新增样式优先 class + Token，禁止行内颜色。

---

## Component Rules

- 能复用 `.btn` / `.panel` / `.field` / `.modal` / `.toast` 则复用。  
- 新组件必须引用 semantic token。  
- Vue scoped 样式不得覆盖全局 Toast 位置/颜色。  

---

## Coding Rules

```text
✅ background: var(--color-bg-surface);
❌ background: #ffffff;

✅ transition: background-color var(--motion-hover) var(--ease-out);
❌ transition: all 0.25s ease;

✅ box-shadow: var(--shadow-xs);
❌ box-shadow: 0 12px 40px rgba(99,102,241,.25);
```

---

## Migration Strategy

| 阶段 | 动作 |
|---|---|
| Phase 1 | Token + Base + 主题锁定 + Toast 样式统一 |
| Phase 1.5 | Review（只出报告） |
| Phase 1.6 | **P0**：修复 Shadow Legacy 覆盖；文档与代码命名对齐 |
| Phase 2 | Login 页按 Token 精修 |
| Phase 3 | Shell 信息架构与 AI 配置入口产品确认 |
| Phase 4+ | 页面级视觉，仍禁止改业务 |
| 旧主题 CSS | 暂留；确认无回退需求后可删（另批） |

回滚：移除三个 CSS/JS 引用与相关 Vue 改动即可回到 Phase 0 后状态；不影响 API。

---

## Naming Canonical List（文档 ≡ 代码）

| 用途 | 正确 Token | 错误别名（禁止） |
|---|---|---|
| 主色悬停 | `--color-brand-hover` | `--color-brand-primary-hover` |
| 默认边框 | `--color-border` | `--color-border-default` |
| 语义小阴影 | `--shadow-sm` | 被 Legacy 改写成 xs |
| 卡片阴影 | `--card-shadow` → `--shadow-xs` | 硬编码 rgba |
| Modal 阴影 | `--modal-shadow` → `--shadow-sm` | `--shadow-lg` 直接用于 Modal |

---

## Icon Strategy（规范，未引依赖）

- 未来只允许 **一套** 线性图标体系（候选 Lucide / Heroicons）  
- Phase 1 **未安装** 任何图标依赖  
- 禁止 emoji / 多风格混用  

---

## File Index

| 路径 | 角色 |
|---|---|
| `static/design-tokens.css` | Semantic Token + legacy bridge |
| `static/design-system-base.css` | 基础组件与壳层 |
| `static/v2-theme-lock.js` | Forest Light 锁定 |
| `frontend/src/stores/theme.js` | Vue 主题 store 锁定 |
| `frontend/src/components/AppToast.vue` | 统一 Toast |
| `frontend/src/components/AppShell.vue` | 移除主题切换 UI |
| `docs/superpowers/specs/2026-07-28-design-system.md` | 本文档 |

---

*End of Design System specification (Phase 1 + 1.6 P0).*
