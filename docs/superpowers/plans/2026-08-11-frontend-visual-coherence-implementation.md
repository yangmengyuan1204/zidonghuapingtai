# Frontend Visual Coherence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify typography, layout proportions, surface hierarchy, shell, panels, and tables while preserving all functionality outside style regions.

**Architecture:** Correct shared V2 tokens first, consume them in style-only regions of the shell and shared components, then bridge the same system into legacy embedded pages through `html.v3-embed`. Views, templates, scripts, routes, stores, APIs, and backend code remain frozen.

**Tech Stack:** Vue 3.5, Vite 5.4, scoped CSS, V2 design tokens, legacy scoped CSS.

## Global Constraints

- Only CSS and design-token declarations may change.
- Do not change any feature, route, API, data structure, field, button, event, dialog, permission, or workflow.
- Do not add icons, dependencies, gradients, glass effects, or heavy shadows.
- Do not modify Vue template/script regions, views, router, stores, APIs, backend, migration configuration, HTML entry, or build configuration.
- Preserve unrelated dirty-worktree changes. Do not commit or push.

---

### Task 1: Freeze behavior and establish RED

**Files:**
- Read: `frontend/src/components/AppShell.vue`
- Read: `frontend/src/components/v2/workbench/WorkbenchPageHeader.vue`
- Read: `frontend/src/components/v2/workbench/WorkbenchPanel.vue`
- Read: `frontend/src/components/AppTable.vue`
- Read: `frontend/src/components/v2/base/BaseTable.vue`
- Read: `frontend/src/styles/v2/tokens.foundation.css`

**Interfaces:**
- Consumes: source before each component's first `<style` tag.
- Produces: immutable functional hashes and a failing visual contract.

- [ ] **Step 1: Lock these functional hashes**

```text
AppShell 067a36a4c57792384543a53984cdaa93173c2379c3a9cd923e82911c4d14e179
WorkbenchPageHeader 3e19a8c0c835538e675b17e7d9c0cf0ea53f4db809b0b63e3feac1eb709a5d1e
WorkbenchPanel 550af4229485fba5bf0e8600aed63438a9abe27375fa8dc498a753196f37ecd2
AppTable a50d4bb3856853225cd14748129bd6b48524350ffb13b817e6f9d27547169fcd
BaseTable 777435575d051c966fa1c86466724f6867257d5a34bf9bc1aa94665d6107857f
```

- [ ] **Step 2: Run a one-off Node assertion requiring the approved foundation values**

Require these exact declarations and expect failure before implementation:

```css
--v2-color-canvas-mist: #e8eef5;
--v2-color-sidebar-slate: #c9d9e7;
--v2-color-section-cool: #dde7f0;
--v2-color-utility-cool: #e7eef4;
--v2-color-context-blue: #d5e3ef;
--v2-color-ink-950: #172b3f;
--v2-layout-sidebar: 220px;
--v2-layout-topbar: 56px;
--v2-layout-workspace-max: 1560px;
--v2-size-table-header: 38px;
--v2-size-table-row: 46px;
```

Expected: FAIL because the approved system is not present.

---

### Task 2: Correct the shared token system

**Files:**
- Modify: `frontend/src/styles/v2/tokens.foundation.css`
- Modify: `frontend/src/styles/v2/tokens.semantic.css`
- Modify: `frontend/src/styles/v2/tokens.component.css`

**Interfaces:**
- Consumes: approved design specification.
- Produces: stable shell, surface, type, border, panel, and table aliases.

- [ ] **Step 1: Run GitNexus impact for `v2-layout-sidebar`, `v2-surface-section`, and `v2-table-header-surface`**

Expected: CSS tokens may be unindexed; report system-wide visual impact and zero business-flow impact.

- [ ] **Step 2: Apply the exact foundation values from Task 1 plus these values**

```css
--v2-color-border-slate: #b9c8d6;
--v2-color-border-cool: #d1dce6;
--v2-color-ink-700: #50677c;
--v2-color-ink-500: #6c8092;
--v2-font-family-display: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
--v2-font-family-sans: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
```

- [ ] **Step 3: Map semantic roles**

```css
--v2-text-primary: var(--v2-color-ink-950);
--v2-text-secondary: var(--v2-color-ink-700);
--v2-text-muted: var(--v2-color-ink-500);
--v2-surface-section: var(--v2-color-section-cool);
--v2-surface-context: var(--v2-color-context-blue);
--v2-surface-utility: var(--v2-color-utility-cool);
--v2-border-section: var(--v2-color-border-slate);
```

- [ ] **Step 4: Normalize component tokens**

Set button text to 13px, panel title to 15px, table body to 13px, table header to 12px/600, and keep all public component APIs unchanged.

- [ ] **Step 5: Rerun the Task 1 assertion**

Expected: PASS.

---

### Task 3: Refine the shell

**Files:**
- Modify: `frontend/src/components/AppShell.vue` style region only.

**Interfaces:**
- Consumes: Task 2 shell tokens.
- Produces: 220px slate sidebar, 56px topbar, centered workspace, readable navigation, no visible menu icons or active dots.

- [ ] **Step 1: Run GitNexus upstream impact on `AppShell`**

- [ ] **Step 2: Run a failing assertion requiring token-based shell columns, 14px navigation, 11px group labels, bounded content, and `content: none` on the active dot**

- [ ] **Step 3: Modify only final shell CSS overrides**

```css
.v2-shell {
  grid-template-columns: var(--v2-shell-sidebar-width) minmax(0, 1fr);
}

.v2-shell__content > * {
  width: 100%;
  max-width: var(--v2-layout-workspace-max);
  margin-inline: auto;
}

.v2-shell__nav-button--active::after {
  content: none;
}
```

Also set navigation items to 14px/500 and group labels to 11px/600. Retain the 3px left active edge.

- [ ] **Step 4: Rerun the style assertion and verify the AppShell functional hash**

Expected hash: `067a36a4c57792384543a53984cdaa93173c2379c3a9cd923e82911c4d14e179`.

---

### Task 4: Strengthen page-header and panel hierarchy

**Files:**
- Modify: `frontend/src/components/v2/workbench/WorkbenchPageHeader.vue` style region only.
- Modify: `frontend/src/components/v2/workbench/WorkbenchPanel.vue` style region only.

**Interfaces:**
- Consumes: section, utility, border, typography, and spacing tokens.
- Produces: 88px page identity region and clearly separated white work panels.

- [ ] **Step 1: Run GitNexus upstream impact for both workbench components**

- [ ] **Step 2: Run a failing assertion for 88px header height, title weight 700, and 15px panel title**

- [ ] **Step 3: Apply minimal CSS**

```css
.v2-workbench-page-header {
  min-height: 88px;
  align-items: center;
}

.v2-workbench-page-header__title {
  font-weight: var(--v2-font-weight-bold);
}

.v2-workbench-panel__title {
  font-size: var(--v2-panel-title-font-size);
}
```

- [ ] **Step 4: Verify GREEN and frozen hashes**

Expected hashes:

```text
WorkbenchPageHeader 3e19a8c0c835538e675b17e7d9c0cf0ea53f4db809b0b63e3feac1eb709a5d1e
WorkbenchPanel 550af4229485fba5bf0e8600aed63438a9abe27375fa8dc498a753196f37ecd2
```

---

### Task 5: Normalize both table implementations

**Files:**
- Modify: `frontend/src/components/AppTable.vue` style region only.
- Modify: `frontend/src/components/v2/base/BaseTable.vue` style region only.

**Interfaces:**
- Consumes: table tokens.
- Produces: consistent 38px headers, 46px rows, 13px body, 12px header, and legacy-safe cascade precedence.

- [ ] **Step 1: Run GitNexus upstream impact for `AppTable` and `BaseTable`**

- [ ] **Step 2: Run a failing assertion that both components consume all shared table typography/size tokens**

- [ ] **Step 3: Normalize CSS**

Remove uppercase transformation and decorative tracking from table headers. Keep the unlayered BaseTable header override so legacy global `th` cannot restore beige.

- [ ] **Step 4: Verify GREEN and frozen hashes**

Expected hashes:

```text
AppTable a50d4bb3856853225cd14748129bd6b48524350ffb13b817e6f9d27547169fcd
BaseTable 777435575d051c966fa1c86466724f6867257d5a34bf9bc1aa94665d6107857f
```

---

### Task 6: Align legacy embedded pages

**Files:**
- Modify: `static/styles.css` existing A3 embed region only.

**Interfaces:**
- Consumes: `html.v3-embed` scope.
- Produces: the same cool surfaces and sans typography for data factory and system regression.

- [ ] **Step 1: Run a failing assertion requiring the approved palette, sans stack, 12px minimum labels/header, and 13px table body**

- [ ] **Step 2: Update only the existing scoped override**

```css
html.v3-embed {
  --bg: #e8eef5;
  --soft: #d5e3ef;
  --text: #172b3f;
  --muted: #6c8092;
  --line: #b9c8d6;
}

html.v3-embed body,
html.v3-embed button,
html.v3-embed input,
html.v3-embed select,
html.v3-embed textarea {
  font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
}
```

Use `#dde7f0` for major headers and `#e7eef4` for utility/table headers. Remove the serif heading stack. Do not alter control visibility, order, state, or behavior.

- [ ] **Step 3: Rerun the legacy assertion**

Expected: PASS.

---

### Task 7: Full verification

**Files:**
- Verify the nine allowed production style files.
- Do not stage or commit.

**Interfaces:**
- Consumes: Tasks 1-6.
- Produces: build, served-asset, functional-freeze, and diff evidence.

- [ ] **Step 1: Recompute all five functional hashes**

Expected: exact match with Task 1.

- [ ] **Step 2: Run V3 style, shell, visual, core-page, migrated-page, route, and legacy-embed validators**

Expected: no new failure versus baseline. Existing protected-contract failures from unrelated dirty-worktree changes are reported and left untouched.

- [ ] **Step 3: Build**

```powershell
Set-Location frontend
npm run build
```

Expected: exit code 0.

- [ ] **Step 4: Verify served `/v3/` assets**

Assert the current hashed CSS contains the 220px sidebar, 1560px workspace, approved surface colors, and unlayered BaseTable header override.

- [ ] **Step 5: Audit status and formatting**

```powershell
git status --short
git diff --stat
git diff --check -- frontend/src/styles/v2/tokens.foundation.css frontend/src/styles/v2/tokens.semantic.css frontend/src/styles/v2/tokens.component.css frontend/src/components/AppShell.vue frontend/src/components/v2/workbench/WorkbenchPageHeader.vue frontend/src/components/v2/workbench/WorkbenchPanel.vue frontend/src/components/AppTable.vue frontend/src/components/v2/base/BaseTable.vue static/styles.css
```

Expected: no new formatting error, no staged files, and no commit.
