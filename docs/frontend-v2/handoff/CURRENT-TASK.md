# Current Task — Frontend V3 Light Workbench Visual Redesign

> **Status:** COMPLETE on branch `codex/frontend-v3-workbench-redesign` at baseline HEAD `0b5bf58722c057a2253b7aabe6f33249f915ebf9`; left uncommitted for user review.
> **Plan:** `docs/superpowers/plans/2026-08-11-frontend-v3-light-workbench-visual-redesign.md`
> **Constraint:** 源码决定功能，UI 图决定视觉；只允许 CSS / `<style>` 修改，功能变化必须为 0。
> **Visual precedence:** `docs/ui-redesign/` 的浅色 220px/56px 新图为当前视觉依据；旧深色合同原样保留为历史基线，不得覆盖新设计。
> **Verification:** production build and HTTP smoke PASS; full pytest `1332 passed, 2 warnings`; active style/light/historical contracts PASS. Six stale V2 digest/allowlist validators remain identical to the pre-change baseline.

---

# Previous Task — Frontend V3 Workbench Redesign Complete

> **Status:** COMPLETE. Tasks 1–14 finished on branch `codex/frontend-v3-workbench-redesign` at base HEAD `a4c5764`.
> **Plan:** `docs/superpowers/plans/2026-08-10-frontend-v3-workbench-redesign-implementation.md`
> **Final report:** `docs/frontend-v2/phase-reports/frontend-v3-redesign-task14-final-verification-report-2026-08-10.md`

## Current approved scope

Frontend V3 visual redesign and native route convergence are complete. All V2/V3 validators, production build, 117 route/permission tests, and browser viewport checks pass.

## Baseline facts

- The historical handoff below is no longer the current implementation state.
- Dropdown, Modal, Select, Table, Textarea, overlay helpers, LegacyEmbed, Shell integration, Dashboard integration, and API Cases integration already exist as uncommitted work.
- Baseline: 8/11 validators pass, 3/11 fail because three validators protect the pre-LegacyEmbed digest of `frontend/src/router/index.js`; the twelfth check, `npm run build`, passes.
- Existing uncommitted changes remain protected. Do not overwrite or reset them.
- Approved baseline: `docs/frontend-v2/visual-baseline/workbench-v1-v2-hybrid.png`.
- Visual contract: `docs/frontend-v2/visual-baseline/VISUAL-CONTRACT.md`.
- Task 2 RED: 14 missing locked declarations plus one raw 32px shadow in legacy `AppModal.vue`; no production code was changed in Task 2.

---

# Historical Task — Phase 5.2B2 Overlay Foundation & BaseDropdown

> **Status:** NOT STARTED. Awaiting human approval after Codex reads handoff.  
> **Source:** Consolidated from Frontend V2 migration plan (Phase 5.2 BaseDropdown + Portal rules), Phase 5.2B1 exit criteria (“Dropdown、Modal、Toast、Portal 和 Focus Management 尚未开始”), and Cursor → Codex handoff designation.  
> **Do not** implement until the human explicitly approves this task after the Codex understanding summary.

========================================================

# 一、本轮目标

本轮只实现 Overlay 基础与 Dropdown：

1. Portal 容器（挂载点使用 `.frontend-v2-portal`，承接 V2 Token）
2. Overlay Stack（最小可用：层级登记 / 打开关闭顺序；不做完整 Focus Trap / Scroll Lock 产品化）
3. `BaseDropdown`
4. `BaseDropdownItem`

本轮编号：

**Phase 5.2B2 — Overlay Foundation & BaseDropdown**

========================================================

# 二、明确禁止提前进入

本轮禁止实现或接入：

- BaseModal
- BaseToast
- 完整 Focus Trap 产品组件
- 完整 Scroll Lock 产品组件
- Sidebar / Topbar / AppShell 重构
- API Cases 或任何业务页面迁移
- 新的第三方 floating-ui / headless UI / 图标依赖
- 修改 Router / Store / API / legacy / Prototype / migration-config / package.json / lockfile / Vite base

========================================================

# 三、实施原则

1. 所有样式消费现有 `--v2-*` Token；不足时只允许在 `tokens.component.css` 追加 Component Token（只能引用 Foundation/Semantic）。
2. 禁止依赖 legacy class 与 legacy Token。
3. 禁止新增第三方依赖。
4. 禁止修改 Router、Store、API、业务页面。
5. 禁止把新组件接入生产页面（仅 Component Lab 验收）。
6. 继续使用独立 Component Lab 验证。
7. 必须先建立失败验证（RED），再写生产组件（GREEN）。
8. 不要修改 Phase 5.2A / 5.2B1 已完成组件的公共契约；除明确缺陷外不重构。
9. 每个组件保持最小 API。
10. 不得覆盖或回退工作区中属于其他任务的改动（见 Handoff 第 9 节）。

========================================================

# 四、Required Reading（开始前必读）

按顺序：

1. `docs/frontend-v2/handoff/CODEX-HANDOFF.md`
2. `docs/frontend-v2/handoff/STATE.json`
3. `docs/migration/frontend-v2-vue-migration-plan.md`（尤其 Design Token、BaseDropdown、Portal、Risk Matrix）
4. `docs/prototypes/frontend-v2-shell-prototype.html`（行操作菜单 / menu 视觉）
5. `docs/frontend-v2/phase-reports/frontend-v2-phase5-2b1-support-components-report-2026-07-29.md`
6. 磁盘可读报告（可能被 gitignore）：
   - `docs/reports/frontend-v2-phase5-2a-base-primitives-report-2026-07-29.md`
   - `docs/reports/frontend-v2-phase5-1-1-login-redirect-hotfix-report-2026-07-29.md`
7. 当前代码：
   - `frontend/src/styles/v2/**`
   - `frontend/src/components/v2/base/**`
   - `frontend/src/dev/V2BaseComponentsLab.vue`
   - `frontend/scripts/validate-v2-*.mjs`
   - `frontend/scripts/validate-login-redirect.mjs`
   - 现有 `AppToast.vue` / `AppFormDialog.vue`（只读，理解现状；本轮不替换）

开始前执行并记录：

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git diff --stat
git diff --name-status
```

========================================================

# 五、Allowed Files

建议创建：

- `frontend/src/components/v2/overlay/` 或等价最小 Portal/Overlay 模块（目录名需在实施前说明并获批准若与本文不一致）
- `frontend/src/components/v2/base/BaseDropdown.vue`
- `frontend/src/components/v2/base/BaseDropdownItem.vue`
- `frontend/scripts/validate-v2-overlay-dropdown.mjs`（或同等命名的新校验脚本）

允许修改：

- `frontend/src/components/v2/base/index.js`（导出新增组件；保留既有 12 个导出）
- `frontend/src/styles/v2/tokens.component.css`（仅追加 Dropdown/Overlay 相关 Component Token）
- `frontend/src/dev/V2BaseComponentsLab.vue`（扩展验收）
- 必要时 `frontend/src/dev/v2-base-components-main.js`

报告：

- `docs/frontend-v2/phase-reports/frontend-v2-phase5-2b2-overlay-dropdown-report-YYYY-MM-DD.md`

========================================================

# 六、Forbidden Files

禁止修改：

- `frontend/src/router/**`
- `frontend/src/services/navigation.js`
- `frontend/src/views/**`
- `frontend/src/App.vue`
- `frontend/src/main.js`（除非人工明确批准为 Portal 根挂载所必需；默认禁止）
- `frontend/src/stores/**`
- `frontend/src/api/**`
- `frontend/vite.config.js`
- `frontend/package.json` / lockfile
- `static/**`（含 migration-config、legacy CSS/JS）
- `docs/prototypes/**`
- `app/**`
- Phase 5.2A/5.2B1 组件公共 API（除修明确缺陷）

========================================================

# 七、Portal Requirements

1. Teleport / Portal 目标节点必须带 class `frontend-v2-portal`。
2. Portal 节点必须能继承 / 定义与 `.frontend-v2` 相同的 V2 Token（已有 CSS 选择器 `.frontend-v2, .frontend-v2-portal`）。
3. 不得把 V2 Token 写到 `:root` / `html` / `body` 全局污染 legacy。
4. 不得修改 `static/index.html` 去加载 V2 CSS。
5. Portal 仅服务于本轮 Dropdown（及 Overlay Stack 登记）；不要借机实现 Modal/Toast。
6. unmount 时必须清理 Portal 内容与监听，无残留 DOM / timer / listener。
7. 默认不进入 Tab 顺序的装饰层不得抢焦点；触发器焦点行为见 Dropdown。

========================================================

# 八、Overlay Stack Requirements（最小）

本轮 Overlay Stack 目标是 **可测试的最小基础**，不是完整弹层框架：

1. 记录当前打开的 overlay 实例顺序（至少支持 Dropdown）。
2. 后打开的层级使用已有 `--v2-z-dropdown` / overlay 相关 Token，不得硬编码魔法数字品牌色。
3. Escape 优先关闭最上层 overlay。
4. 同层外点击关闭当前 Dropdown（可配置）。
5. **不要**在本轮实现完整 Focus Trap 组件与 Scroll Lock 产品 API。
6. 若 Dropdown 需要临时管理焦点，行为必须写在 Dropdown 合同内，并在报告 Remaining Risks 标明完整 Focus Management 未完成。

========================================================

# 九、BaseDropdown Requirements

## Props（至少）

- `open`：Boolean（受控优先；若同时支持非受控，必须文档化且 Lab 覆盖）
- `placement`：至少 `bottom-start` / `bottom-end`（可扩展 top；无自动碰撞引擎也可，但必须在报告写明限制）
- `disabled`：Boolean
- `ariaLabel` 或通过 trigger slot 保证可访问名称

## Emits（至少）

- `update:open`
- `select`（选中项时）

## Slots（至少）

- `trigger`
- `default`（菜单内容；可与 items 二选一，但必须有明确合同）

## Behavior

1. 打开/关闭只通过 props/emits，不持久化业务状态到 Pinia/Storage。
2. Escape 关闭并恢复焦点到 trigger（最小焦点恢复；不是完整 Focus Trap 产品）。
3. 点击外部关闭。
4. disabled 时不打开。
5. 菜单通过 Portal 渲染到 `.frontend-v2-portal`（本轮允许且需要 Portal；与 5.2B1 Tooltip「禁止 Portal」不同）。
6. 不使用 `v-html`。
7. 不调用 Router / API。
8. 一次选择只 emit 一次 `select`，并按合同关闭或保持 open。
9. 不得复制 Prototype 内联 style。

## Keyboard Model

至少支持：

- `Enter` / `Space`：打开或激活 trigger
- `Escape`：关闭
- `ArrowDown` / `ArrowUp`：在打开的菜单项间移动
- `Home` / `End`：跳到首/末项（迁移计划验收重点）
- `Enter`：在聚焦菜单项上选择
- Tab：不得把焦点困死在未声明的 trap 里；关闭后焦点回到 trigger

## ARIA Requirements

- trigger：适当的 `aria-expanded`、`aria-haspopup="menu"`（或 listbox，二选一且全文一致）
- menu：`role="menu"`（或与 haspopup 一致的 listbox）
- item：`role="menuitem"`（或 option）
- 禁用项：`aria-disabled` 或原生 disabled，且不可选中
- 活动项：可用 `aria-activedescendant` 或 tabindex 漫游，二选一写清

## Positioning Constraints

1. 本轮允许轻量定位（相对 trigger 的 fixed/absolute + placement）。
2. **不要求**完整 collision detection / flip middleware（可记 Remaining Risk）。
3. 不得遮挡 trigger 的 focus-visible 轮廓到不可见。
4. 使用 Dropdown Component Token / z-index Token。
5. 1080 宽度下菜单不得造成页面横向溢出（可在容器内滚动）。

========================================================

# 十、BaseDropdownItem Requirements

1. 可键盘聚焦（在 Dropdown 漫游模型内）。
2. disabled 不可选。
3. 支持可选 icon / danger 视觉（若做，必须用 Token，不只靠颜色）。
4. 点击或 Enter 触发 select。
5. 无 Router / API / Storage。

========================================================

# 十一、Component Lab

扩展现有 Lab，至少展示：

- Closed / Open
- Bottom-start / Bottom-end（及已实现的 placement）
- Keyboard navigation
- Escape close + focus return
- Outside click close
- Disabled dropdown
- Disabled item
- Select emit 计数
- Portal 渲染在 `.frontend-v2-portal`（DevTools/DOM 可验证）

Lab 继续满足：

- 不注册 Router
- 不进生产菜单
- 不改 App.vue / 默认禁止改 main.js
- 不调用 API
- 不依赖 Pinia 业务状态
- 根节点 `.frontend-v2`

========================================================

# 十二、Required Validators

生产组件创建前，先写失败校验脚本并确认 RED。

至少检查：

1. 新组件文件存在
2. index 导出包含新组件且保留原 12 个
3. 无 Router / Pinia / API / Storage 依赖
4. 无 legacy class
5. class 使用 `v2-` 前缀
6. CSS 使用 `--v2-*`
7. 无共享 `:root`
8. Dropdown 使用 Portal + `.frontend-v2-portal`
9. Escape / Arrow 键盘合同有实现证据（源码级）
10. 无 `v-html`
11. self-check：故意违规样本必须被检测

完成时仍须通过：

```bash
node frontend/scripts/validate-v2-foundation.mjs
node frontend/scripts/validate-login-redirect.mjs
node frontend/scripts/validate-v2-base-components.mjs
node frontend/scripts/validate-v2-support-components.mjs
node frontend/scripts/validate-v2-overlay-dropdown.mjs   # 名称以实际脚本为准
cd frontend && npm run build
git diff --check
```

========================================================

# 十三、Browser Verification

至少验证：

- Dropdown 打开关闭、键盘、ARIA、Portal 挂载
- 四档宽度 1080/1240/1440/1920
- `/v3/login`、`/v3/dashboard`、`/` 无回归
- legacy V2 Token 仍为 0
- Lab console error = 0

测试账号不得写入报告。

========================================================

# 十四、Git Safety Rules

1. 开始前 `git status --short`，区分 Frontend V2 与其他任务改动。
2. 禁止 `git add -A`。
3. 禁止提交 payment amount regression / 无关测试 / `*.db` / `logs/` / `reports/`。
4. 禁止覆盖未提交的其他任务文件。
5. 默认不 commit、不 push；仅当人工明确要求时再按 AGENTS.md Git 规则提交。
6. 禁止 `git reset --hard`、`git clean -fd`、`git push --force`。
7. 报告写入 `docs/frontend-v2/phase-reports/`，不要写入被 ignore 的 `docs/reports/`，不要改 `.gitignore`。

========================================================

# 十五、Completion Criteria

全部满足才可宣布完成：

- Portal + Overlay Stack（最小）+ BaseDropdown + BaseDropdownItem 已实现
- 仅 Lab 验证，未接入生产页
- RED 真实发生后 GREEN
- 四个既有 validator + 新 validator + build + `git diff --check` 通过
- 浏览器 / 键盘 / ARIA / 四档宽度 / 生产回归完成
- 禁止范围零修改
- 报告落入 `docs/frontend-v2/phase-reports/`
- Remaining Risks 明确：Modal、Toast、完整 Focus Trap、Scroll Lock、Shell、API Cases 尚未开始

========================================================

# 十六、Report Path

`docs/frontend-v2/phase-reports/frontend-v2-phase5-2b2-overlay-dropdown-report-YYYY-MM-DD.md`

报告至少包含：

Scope、Files Created/Modified、Contracts、Portal/Overlay 设计、Keyboard/ARIA、Token Usage、RED/GREEN、Browser、Viewport、Production Regression、Diff Audit、Remaining Risks

========================================================

# 十七、最终输出格式（完成时）

只输出：

1. Files Created
2. Files Modified
3. 组件完成状态
4. RED 结果
5–9. 各 validator / build 结果
10. 浏览器验证结果
11. Diff Audit
12. 报告路径

最后：

`PHASE 5.2B2 PASS` 或 `PHASE 5.2B2 BLOCKED`

然后停止。不要进入 Modal/Toast/Shell/API Cases。
