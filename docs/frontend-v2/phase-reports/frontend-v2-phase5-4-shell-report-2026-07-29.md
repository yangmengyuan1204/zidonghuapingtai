# Frontend V2 Phase 5.4 — Shell Foundation Migration

## Status

- Implementation: PASS
- Verification: PASS
- Phase: PHASE 5.4 PASS
- Verification completed: 2026-07-30 (Asia/Shanghai)

## Scope

Phase 5.4 only migrated the existing `AppShell.vue` Sidebar and Topbar UI to completed V2 Base Components. Navigation data, menu order, permissions, Router, Store, API, login, logout, Dashboard, and page content behavior were not changed.

Git baseline before implementation:

- Branch: `codex/safe-refactor-preserve-features`
- HEAD: `a4c5764a759720707b34d65caddce7661d54e13d`
- Staged changes: none
- Worktree: mixed pre-existing Frontend V2, backend, payment amount regression, and system regression changes

## Component Mapping

| Existing Shell UI | V2 mapping | Count | Behavior |
| --- | --- | ---: | --- |
| Sidebar navigation `button` | `BaseButton` (`ghost`, `block`) | 9 | Existing `navigate(item)` unchanged |
| Topbar secondary `button` | `BaseButton` (`secondary`) | 2 for admin | Existing AI placeholder and logout handlers unchanged |
| Sidebar role pill `span` | `BaseBadge` (`neutral`) | 1 | Existing role text unchanged |
| Brand text | Native text | Existing | No equivalent Base Component; unchanged content |
| Admin external links | Native anchors | 2 for admin | No equivalent Base Component; href/target unchanged |

The Shell page-level element order remains `div > aside + main > header + section`. Only Base Component internal DOM differs.

## Validator Changes

- Added only `BaseBadge -> src/components/AppShell.vue` to `approvedProductionUsage`.
- Did not approve `BaseDropdown` or `BaseDropdownItem` for AppShell.
- Primitive, Supporting, Component Lab, Portal isolation, and legacy isolation validation logic remains unchanged.
- Phase 5.4 contract test was run RED before production migration and failed for the expected reasons: `BaseButton` missing, `BaseBadge` missing, and Shell legacy classes present.
- The same contract check passed after implementation.

## V2 Token and CSS Isolation

- Added Shell-specific V2 Component Tokens under `.frontend-v2` / `.frontend-v2-portal` scope.
- `AppShell.vue` now uses a single scoped `@layer v2-overrides` style block and only `--v2-*` custom properties.
- Shell classes were renamed to the `v2-shell*` namespace.
- Runtime audit found zero legacy Shell classes inside `.v2-shell`.
- Existing desktop geometry was retained: Sidebar `248px`, Topbar `64px`, navigation button `44px`, role badge `38px`, and content padding `24px 32px`.

## Contract Gap

The real AppShell does not contain the following UI or behavior, so Phase 5.4 did not add or migrate them:

- Dropdown
- User Menu
- Sidebar Collapse
- Portal
- IconButton
- Notification UI

These are future capabilities, not Phase 5.4 coverage gaps to solve by adding features.

## Automated Verification

- `node frontend/scripts/validate-v2-foundation.mjs`: PASS
- `node frontend/scripts/validate-login-redirect.mjs`: PASS (9/9)
- `node frontend/scripts/validate-v2-base-components.mjs`: PASS
- `node frontend/scripts/validate-v2-support-components.mjs`: PASS
- `node frontend/scripts/validate-v2-dropdown.mjs`: PASS
- `npm --prefix frontend run build`: PASS
- `git diff --check`: PASS

The production build emitted only the existing external static asset resolution notices; it produced no build error.

## Browser Verification

Real browser address: `http://127.0.0.1:8000/v3/`

- Login with the supplied admin account: PASS
- Dashboard refresh: PASS; authenticated user and all 9 navigation items remained present
- Navigation with mouse-equivalent activation: PASS
- Keyboard navigation: PASS; Tab advanced from Dashboard to Projects, Enter activated Projects, and Space returned to Dashboard
- Active route state: PASS; the current item exposes `aria-current="page"`
- Navigation landmark: PASS; `nav` exposes `aria-label="主导航"`
- Logout: PASS; returned to `/v3/login`
- Sticky Topbar: PASS; remained at `y=0` after scrolling
- Portal count with Shell/Dashboard dropdown closed: `0`
- Console after authenticated refresh: `0` errors, `0` warnings
- API: no Shell-specific request was added; observed requests remained auth, projects, and Dashboard requests

Responsive geometry:

| Viewport width | Sidebar | Topbar | Menu count | Portal |
| ---: | ---: | ---: | ---: | ---: |
| 1080 | 248px | 64px | 9 | 0 |
| 1240 | 248px | 64px | 9 | 0 |
| 1440 | 248px | 64px | 9 | 0 |
| 1920 | 248px | 64px | 9 | 0 |

Legacy homepage `http://127.0.0.1:8000/`:

- V2 Token count: `0`
- `.frontend-v2-portal` count: `0`
- `.frontend-v2` root count: `0`
- Console errors: `0`

## Diff Audit

Phase 5.4 files:

- `frontend/src/components/AppShell.vue`
- `frontend/src/styles/v2/tokens.component.css`
- `frontend/scripts/validate-v2-support-components.mjs`
- `docs/frontend-v2/phase-reports/frontend-v2-phase5-4-shell-report-2026-07-29.md`

No file was staged, committed, pushed, restored, reset, cleaned, or stashed. Unrelated dirty-worktree files were not modified for Phase 5.4.

GitNexus reported the combined dirty worktree as CRITICAL because it includes 27 tracked files and unrelated backend/payment/system-regression flows. This result cannot isolate Phase 5.4 from the pre-existing mixed changes; Phase 5.4 scope was instead verified by explicit file audit, validators, build, and browser checks.

## Remaining Legacy UI

- AppShell structural elements and text remain native HTML because no Base Component replacement is applicable.
- Admin management links remain native anchors because BaseButton has no anchor contract.
- Dashboard and all other business-page legacy UI are outside Phase 5.4.
- The global legacy stylesheet remains loaded for unmigrated application areas, but the migrated Shell no longer references its Shell class contracts.

## Remaining Risks

- The repository remains heavily dirty with unrelated work; any future staging must use explicit Phase-specific paths.
- GitNexus does not index the Vue SFC AppShell symbol, so its symbol-level upstream impact was unavailable; browser coverage was used for the authenticated Shell surface.
- `BaseBadge` remains classified as a Primitive Component by the existing validator architecture; the requested AppShell approval entry was added without changing Primitive validation behavior.

PHASE 5.4 PASS
