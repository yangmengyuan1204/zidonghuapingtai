# Frontend V2 Phase 5.3 Dashboard Foundation Migration Report

- Date: 2026-07-29
- Branch: `codex/safe-refactor-preserve-features`
- Baseline HEAD: `797a7e1c3d00293e0cb29cf89f894b1113e2d667`
- Browser URL: `http://127.0.0.1:8000/v3/dashboard`
- Implementation: PASS
- Verification: PASS

## Scope

Only the existing Dashboard UI was migrated. Router, Store, API modules, permissions, login flow, Dashboard data shape, query behavior, lifecycle, Sidebar, Topbar, Shell, Prototype, Projects, API Cases, Modal, and Toast were not changed.

The page-level order remains:

1. Project filter
2. Five statistics
3. Recent execution heading
4. Loading, empty, or table content

## Component Mapping

| Existing Dashboard UI | V2 replacement |
|---|---|
| Native project selector | `BaseDropdown` + `BaseDropdownItem` + `BaseButton` trigger |
| Five `.stat` surfaces | `BaseCard` |
| Loading text | `BaseSkeleton` |
| Empty table message | `BaseEmptyState` |
| Case type and result badges | `BaseBadge` |
| Log, report, and screenshot buttons | `BaseButton` |

`BaseChip`, `BaseIconButton`, and `BaseErrorState` were not introduced because Dashboard has no one-to-one existing UI for them. Existing error handling remains the current Toast flow.

## Protected Contracts

- Project ID continues to use `app.filters.projectId` and `app.setProjectId()`.
- Project list and Dashboard requests remain `app.fetchProjects()` and `getDashboard()`.
- Dashboard response fields and recent-record columns are unchanged.
- Log navigation and protected report/screenshot behavior are unchanged.
- No Dashboard API, Router, Store, permission, or lifecycle contract was changed.
- Dashboard source uses V2-scoped classes and `--v2-*` tokens; migrated regions do not reintroduce legacy component classes.

## Validator Architecture Upgrade

`validate-v2-support-components.mjs` now uses a single Approved Production Usage map for Supporting and Overlay component consumers.

Approved production usage for this phase is limited to:

- `BaseDropdown` → `src/views/DashboardView.vue`
- `BaseDropdownItem` → `src/views/DashboardView.vue`
- `BaseSkeleton` → `src/views/DashboardView.vue`
- `BaseEmptyState` → `src/views/DashboardView.vue`

All other production pages remain rejected for these components. Other Supporting Components remain Component Lab only. Primitive validation, Supporting contracts, Component Lab coverage, Portal isolation, legacy isolation, and export validation remain active.

The policy probes confirmed that Projects and API Cases are rejected, and that approved consumers using legacy classes or non-V2 custom properties are rejected.

## RED / GREEN

- RED: Dashboard lacked all seven target Base Component references and contained eleven listed legacy Dashboard classes.
- GREEN: all seven target references are present and those legacy classes are absent from `DashboardView.vue`.
- Validator RED: the Phase 5.2B1 blanket production ban rejected Dashboard usage.
- Validator GREEN: configuration-driven Approved Production Usage accepts only Dashboard and preserves negative isolation checks.

## Automated Verification

All commands passed:

- `node frontend/scripts/validate-v2-foundation.mjs`
- `node frontend/scripts/validate-login-redirect.mjs`
- `node frontend/scripts/validate-v2-base-components.mjs`
- `node frontend/scripts/validate-v2-support-components.mjs`
- `node frontend/scripts/validate-v2-dropdown.mjs`
- `npm run build`
- `git diff --check`

The production build completed with the existing warnings for external static CSS resources and the non-module theme-lock script. No new build dependency or build input was added.

## Browser Verification

Authenticated with the provided admin account.

- Login: PASS; `/api/auth/login`, `/api/projects`, and `/api/dashboard` returned 200.
- Refresh: PASS; route stayed on `/v3/dashboard`, auth/project/dashboard requests returned 200, and Dashboard content restored.
- Project switching: PASS; selecting `requirement-pack-project` issued the project-filtered Dashboard request and updated the trigger label.
- Loading: PASS; a delayed real Dashboard request displayed `BaseSkeleton`, then restored the table after the 200 response.
- Empty: PASS; the selected project returned no recent records and displayed `BaseEmptyState` without a table.
- Error: PASS; a controlled 500 response retained the existing Toast behavior, removed loading, and did not invent an inline error state.
- Dropdown: PASS for click, outside click, mutual lifecycle, controlled open state, and selection.
- Keyboard: PASS for ArrowDown, ArrowUp, Home, End, Enter, Space, Escape, and Tab. Escape restored trigger focus; Tab closed without trapping focus.
- ARIA: trigger exposed `aria-haspopup="menu"`, `aria-expanded`, and `aria-controls`; the menu exposed `role="menu"`; four items exposed `role="menuitem"`.
- Portal: exactly one `.frontend-v2-portal` while open; menu read `--v2-dropdown-surface` as `#ffffff`.
- Resize: menu recomputed its trigger-relative position.
- Scroll: mouse-wheel scroll caused menu repositioning and retained the configured 8px offset.
- Viewport clamp: at a 300px probe, the menu remained within the 12px left/right viewport gap.
- Responsive widths: 1080, 1240, 1440, and 1920 had no horizontal overflow; all retained five statistic cards and the same information hierarchy.
- Console: authenticated refresh completed with 0 errors and 0 warnings. The initial unauthenticated document request still exposes the repository's pre-existing `/favicon.ico` 404 before refresh; it is unrelated to Dashboard production code.
- Normal API responses: all observed normal login, auth, projects, and Dashboard requests returned 200. The only 500 was the intentional error-state probe.

## Diff Audit

Phase 5.3 production changes are limited to `DashboardView.vue`. The approved validator architecture change is limited to `validate-v2-support-components.mjs`. This report is the only new Phase 5.3 file.

No Git add, reset, checkout, restore, clean, stash, commit, or push command was executed. Existing payment amount regression, system regression, backend, static, test, cache, and other Frontend V2 changes were left untouched.

## Remaining Legacy Components

- `AppTable.vue` remains the shared legacy table implementation and still renders its own `table-wrap panel` shell. It was intentionally not changed because no completed V2 table component exists and changing it would affect other business pages.
- The shared `badgeClass()` semantic mapping is adapted to V2 badge tones inside Dashboard; it is not used as a CSS class.
- Existing global Shell, Sidebar, Topbar, Toast, and table CSS remain outside Phase 5.3.

## Result

PHASE 5.3 PASS
