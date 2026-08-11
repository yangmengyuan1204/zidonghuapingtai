# Frontend V3 Redesign Task 1 — Baseline Audit

## Scope

- Branch: `codex/frontend-v3-workbench-redesign`
- Base HEAD: `a4c5764a759720707b34d65caddce7661d54e13d`
- Plan: `docs/superpowers/plans/2026-08-10-frontend-v3-workbench-redesign-implementation.md`
- This task changed handoff/report documentation only. It did not change production Vue, CSS, Router, API, legacy code, backend code, database, configuration, or dependencies.

## Git and ownership audit

The branch was created in the current checkout so the existing uncommitted work remained visible for audit. A clean worktree was intentionally not used because it would omit the exact changes Task 1 must classify.

### Protected unrelated work

- `app/**`: data factory Agent, payment amount regression, system regression, recovery, router and service work from other tasks.
- `static/payment-amount-regression.js`, `static/system-regression.*`: other task work.
- `tests/test_payment_amount_*`, `tests/test_system_regression_*`, data-script and permission tests: other task work.
- `*.db`, `logs/`, `reports/`, `artifacts/`: never stage for this task.
- `AGENTS.md`, `CLAUDE.md`: pre-existing instructions changes; do not overwrite.

### Existing Frontend V2/V3 work to preserve

| Area | Files | Audited state |
|---|---|---|
| Phase 5.2B1 follow-up | `BaseTooltip.vue`, support validator, Component Lab | Modified after historical handoff; validator passes |
| Overlay/Dropdown | `BaseDropdown.vue`, `BaseDropdownItem.vue`, `overlay/*`, dropdown validator | Present untracked; validator passes |
| Modal | `BaseModal.vue`, modal validator | Present untracked; validator passes |
| Resource foundation | `BaseSelect.vue`, `BaseTable.vue`, `BaseTextarea.vue`, resource validator | Present untracked; validator passes |
| Production integration | `AppShell.vue`, `AppFormDialog.vue`, `DashboardView.vue`, `ApiCasesView.vue`, `tokens.component.css`, base index | Modified and actively consuming V2 components |
| Legacy bridge | `LegacyEmbedView.vue`, Router, migration config/bridge, legacy embed validator | Data Scripts and Requirement Verification currently use iframe bridge |
| Static asset/build | `frontend/public/favicon.ico`, index/vite changes, favicon validator | Asset exists; validator currently blocked by Router protected digest |

## Architecture truth

- Native Vue views: Login, Dashboard, Projects, API Cases, UI Cases, Records, Users.
- iframe Vue routes: Data Scripts, Requirement Verification through `LegacyEmbedView.vue`.
- Missing native Vue route/page: API Harvester and System Regression.
- `static/migration-config.json` marks Data Scripts and Requirement Verification as migrated even though they are iframe-backed; therefore “migrated” currently means “reachable from Vue”, not “native Vue parity”.
- `AppShell.vue` still hides `apiHarvester` through `HIDDEN_SIDEBAR_KEYS`.
- Production imports already use BaseBadge, BaseButton, BaseCard, BaseCheckbox, BaseDropdown, BaseDropdownItem, BaseEmptyState, BasePagination, BaseSelect, BaseSkeleton, BaseTable, and BaseTextarea.

## Baseline verification

### Passed validators — 8

- `validate-login-redirect.mjs`
- `validate-v2-base-components.mjs`
- `validate-v2-dropdown.mjs`
- `validate-v2-foundation.mjs`
- `validate-v2-legacy-embed.mjs`
- `validate-v2-modal-foundation.mjs`
- `validate-v2-resource-foundation.mjs`
- `validate-v2-support-components.mjs`

### Failed validators — 3

- `validate-v2-api-cases-direct-mapping.mjs`
- `validate-v2-api-cases-foundation-integration.mjs`
- `validate-v2-favicon-static-asset.mjs`

All three failures share one root cause: they protect digest `ebb5f746...` for `frontend/src/router/index.js`, while the working tree adds Data Scripts and Requirement Verification routes that render `LegacyEmbedView.vue`. Task 1 does not decide whether to bless the new digest or change the route approach; that decision belongs to the phase owning those validators/routes.

The twelfth baseline check, the Vite production build, passed. It emitted pre-existing warnings for non-module `v2-theme-lock.js` and `/static/*.css` paths resolved at runtime.

## Risk assessment

- **High overlap risk:** `AppShell.vue`, `DashboardView.vue`, `ApiCasesView.vue`, `router/index.js`, `tokens.component.css`, base index, Component Lab and validators already contain uncommitted work. Every later phase must inspect their diffs before editing.
- **Contract drift risk:** three validator digests lag behind legitimate-looking Router additions; updating hashes without phase ownership would hide unexpected changes.
- **Migration semantics risk:** iframe-backed pages are labeled migrated, which can conceal remaining native Vue work.
- **Lifecycle risk:** UI Cases, Requirement Verification and Data Factory contain polling/session state and must not be converted as pure visual rewrites.
- **No GitNexus symbol impact required in Task 1:** only Markdown and machine-readable handoff state were edited. Symbol impact becomes mandatory before production code changes.

## Files changed by Task 1

- `docs/frontend-v2/handoff/CURRENT-TASK.md`: added authoritative current task and preserved the historical 5.2B2 specification below it.
- `docs/frontend-v2/handoff/STATE.json`: updated branch/HEAD/current phase, component inventory, validators and baseline notes.
- `docs/frontend-v2/phase-reports/frontend-v3-redesign-baseline-audit-2026-08-10.md`: added this audit.

## Next gate

Task 2 may only freeze the approved hybrid image, write the visual contract, and add a RED visual-contract validator. It must not modify production Vue or CSS. Human approval is required before Task 2 begins.
