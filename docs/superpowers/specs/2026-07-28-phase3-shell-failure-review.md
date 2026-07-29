# Phase 3 Shell Failure Review — 2026-07-28

## 1. 导航 Bug 复现步骤

**稳定复现（问题 A）**

1. 打开已迁移页面（例如 `/v3/dashboard`），使用 Vue `AppShell`。
2. 侧栏点击「功能验证中心」（Vue `menuViews` key = `functionalTests`）。
3. `navigateToView('functionalTests')` 跳转到旧应用：`/#/functionalTests`。
4. Static 启动后默认 `state.view = "dashboard"`，渲染工作台总览。
5. `migration-bridge` 的 `activateInitialHash` 查找 `[data-view="functionalTests"]`。
6. **找不到按钮**（该 key 已被运行时从菜单移除）→ 重试耗尽 → **停留在工作台总览**。

等价入口：直接访问 `http://127.0.0.1:8000/#/functionalTests`（已登录）。

**说明：** 纯 Static 可见菜单中并没有「功能验证中心」文案，对应项已被替换为「需求验证中心」（`requirementVerification`）。验收时若从 Vue Shell 点击旧文案，会表现为「点了功能验证中心却回到总览」。

---

## 2. 根因

**单一根因：**

`static/requirement-verification.js` 在加载时从全局 `views` 删除 `caseGeneration` / `functionalTests`，并插入 `requirementVerification`；  
但 Vue `menuViews` 仍保留 `functionalTests`（标签「功能验证中心」），并通过 `navigation.js` 跳到 `/#/functionalTests`。  
Hash 激活找不到对应 `data-view`，默认视图保持 `dashboard`。

**证据：**

| 检查项 | 结果 |
|---|---|
| Phase 3 `app.js` views / nav map / click handler vs HEAD | **相同**（仅品牌区 HTML class） |
| `shell.css` 按钮 hit-test（含 functionalTests） | **通过**，`dataset.view` 正确 |
| 运行时可见菜单 | `… dataScripts, requirementVerification, uiCases …`（无 functionalTests） |
| Vue `menuViews` | 仍含 `functionalTests` / `caseGeneration` |
| `migration-config` | functionalTests **未**迁移（符合预期） |

**非根因（已排除）：**

- Phase 3 DOM 品牌结构破坏 `closest('[data-view]')`
- `shell.css` 遮挡点击
- functionalTests 被错误映射成 dashboard 的显式代码
- Phase 3 修改了 Router / migration-bridge / 权限

---

## 3. 修复内容

**最小修复（仅针对该根因）：**

| 文件 | 改动 |
|---|---|
| `static/requirement-verification.js` | 1) 为 legacy key 注入隐藏 `[data-view]` 目标，供 hash 激活；2) `renderShell` 入口将 legacy view 规范化为 `requirementVerification`；3) `renderCurrentView` 同步映射 |
| `frontend/src/services/navigation.js` | Vue 跳转未迁移页时，将 `functionalTests` / `caseGeneration` 别名到 `requirementVerification` |
| `static/index.html` | 仅 bump `requirement-verification.js` cache query |
| `frontend/dist/*` | 重建以包含 navigation 别名 |

**未改：** migration-bridge、migration-config、Router routes、菜单顺序、可见 view key、API、权限、Login、业务页。

---

## 4. 菜单逐项验证结果

自动化（Playwright + API mock，1366×768）：**ALL_PASS**

| 菜单 | key | 结果 |
|---|---|---|
| 工作台总览 | dashboard | → `/v3/dashboard` PASS |
| 项目空间 | projects | → `/v3/projects` PASS |
| 接口用例库 | apiCases | → `/v3/` PASS |
| 接口抓取 | apiHarvester | Static active=apiHarvester PASS |
| 数据工厂 | dataScripts | Static active=dataScripts PASS |
| 需求验证中心 | requirementVerification | Static active=requirementVerification PASS |
| UI 自动化 | uiCases | → `/v3/` PASS |
| 执行报告 | records | → `/v3/` PASS |
| 权限中心 | users | → `/v3/` PASS |
| Hash `#/functionalTests` | （legacy） | active=`requirementVerification`，标题非「工作台总览」 PASS |
| Hash `#/caseGeneration` | （legacy） | 同上 PASS |

> 验收文案「功能验证中心」：Vue 侧仍显示该标签；跳转后进入 **需求验证中心**（产品上已替换原 functionalTests 页），**不再进入 dashboard**。

---

## 5. 当前 Shell 视觉失败原因

Phase 3 只换了 Shell 壳层，业务模块仍大量依赖旧 `styles.css`。结果是「新壳 + 旧内页」，整体发灰、层级弱、割裂。

具体：

1. **Canvas `#f3f1ea` 偏灰米色**，大面积铺底后对比不足，感觉「灰蒙蒙」。
2. **Surface `#fffdf8` 与 Canvas 明度差过小**，Panel / Table 边界弱。
3. **Sidebar 字号压到 14px / muted 色**，品牌区弱，长期可读性不足。
4. **Topbar 仅一条浅底 + 标题**，信息结构空，像分割线而非工具条。
5. **内容区与背景缺少明确 surface 容器**，业务表格/按钮仍走旧样式（圆角偏大、旧 hover、旧密度）。
6. **未宣称、也不可能「全站已统一」**——只改 Shell 不会自动完成 Dashboard / Cases / Records 等模块重构。

---

## 6. 新旧 CSS 覆盖关系

加载顺序（Static / Vue index）：

```
styles.css（旧全站）
→ design-tokens.css（Forest Light Token）
→ design-system-base.css（基础组件 + 部分壳）
→ login.css
→ shell.css（Phase 3 壳层）
```

| 层 | 作用 | 问题 |
|---|---|---|
| `styles.css` | 旧登录/壳/表格/面板/主题残留 | 仍主导业务模块视觉 |
| `design-tokens.css` | Token 源 | 业务页未广泛消费 |
| `design-system-base.css` | Button/Toast/部分 shell/table 覆盖 | 覆盖不完整 |
| `shell.css` | Sidebar/Topbar/Layout | 只影响壳；内页仍旧 |

`shell.css` **不能**也不应重写 Dashboard 内容；因此壳与内页割裂是阶段范围的必然结果，不是「Token 失效」的单一 bug。

---

## 7. 未被统一的模块清单

| 模块 | 状态 |
|---|---|
| Login | Phase 2/2.6 已单独处理 |
| Shell（Sidebar/Topbar/Layout） | Phase 3 已改；需 3.2 修正对比度 |
| Dashboard | **未统一**（禁止本轮改） |
| Projects / Users / Records / API Cases / UI Cases | Vue 页 + 旧 table/panel 样式，**未统一** |
| Data Factory / AI Workspace / Case Generation | Static 旧页，**未统一** |
| 需求验证中心 | Static 旧页，**未统一** |
| Admin 页 | **未统一** |
| Toast | Phase 1 已统一基础 |

---

## 8. 第二版 Shell 设计修正方案（本轮不实施）

目标：Warm 但不灰、Minimal 但有层级、Calm 但不模糊。

| 项 | 建议 |
|---|---|
| Canvas | 更干净暖白（降低灰米色占比），接近 `#faf8f4` / `#fbfaf7` |
| Surface | 接近纯白 / 象牙白，与 Canvas 拉开可感知明度差 |
| Border | 略提高 `--color-border` 对比 |
| Text Primary | 略加深 |
| Text Secondary / Muted | 避免过浅 |
| Sidebar | 保持深森林绿实色；正文 ≥15px；active 浅底 + 左边线，无 glow |
| Topbar | 明确标题区 + 操作区节奏；轻边框实色；不要空白横条感 |
| 内容区 | 主列使用清晰 surface / 页面标题层级（仍属 Shell 辅助，不改业务组件） |
| 禁止 | 蓝紫、Glow、毛玻璃、大阴影、炫酷背景 |

**Phase 3.2 建议范围（仅 Shell + Token 微调）：**

1. 调整 Token：canvas / surface / border / text（若需，小步改 `design-tokens.css`）
2. 修正 `shell.css`：Sidebar 字号字重、品牌区、Topbar 结构、内容区边界
3. **不**改 Dashboard / AI Workspace / 业务表格逻辑
4. 人工视觉验收后再进 Phase 4

---

## 9. 是否建议进入 Phase 3.2

**是。**

先完成 Phase 3.2 Shell 视觉修正（对比度与层级），再进入 Dashboard。  
本轮导航回归已用最小别名修复；Vue 菜单文案与 Static「需求验证中心」对齐可作为 3.2/后续清理项（非阻断）。
