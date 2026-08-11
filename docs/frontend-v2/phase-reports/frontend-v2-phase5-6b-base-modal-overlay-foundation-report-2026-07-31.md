# Frontend V2 Phase 5.6B BaseModal & Modal Overlay Foundation Report

## Status

- Implementation: PASS
- Verification: PASS
- PHASE 5.6B: PASS

## Git Baseline

- Branch: `codex/safe-refactor-preserve-features`
- HEAD: `a4c5764a759720707b34d65caddce7661d54e13d`
- Start status: 93 entries total, 36 tracked modified, 57 untracked, 0 staged
- End status: 93 entries total, 36 tracked modified, 57 untracked, 0 staged
- `git diff --cached --name-status`: 0
- The worktree already contained unrelated payment/regression and broader Frontend V2 dirty files before this phase.

## Scope

Implemented only the modal foundation layer:

- real Teleport portal mounting
- modal overlay stack ownership
- shared focus trap
- reference-counted scroll lock
- lab-only BaseModal exposure
- modal validator and validator-decoupling update

## Files Created

- `frontend/src/components/v2/base/BaseModal.vue`
- `frontend/src/components/v2/overlay/focusTrap.js`
- `frontend/src/components/v2/overlay/overlayStack.js`
- `frontend/src/components/v2/overlay/scrollLock.js`
- `frontend/scripts/validate-v2-modal-foundation.mjs`
- `docs/frontend-v2/phase-reports/frontend-v2-phase5-6b-base-modal-overlay-foundation-report-2026-07-31.md`

## Files Modified

- `frontend/src/components/v2/overlay/portal.js` (preexisting worktree file; touched in this phase, not newly created)
- `frontend/src/components/v2/base/index.js`
- `frontend/src/dev/V2BaseComponentsLab.vue`
- `frontend/scripts/validate-v2-support-components.mjs`
- `frontend/scripts/validate-v2-favicon-static-asset.mjs`

## Read-only Validation Objects

These were inspected during the phase but not changed by this phase:

- `frontend/public/favicon.ico`
- `frontend/index.html`
- `frontend/dev/v2-base-components.html`
- `frontend/vite.config.js`
- `app/core/app_setup.py`
- `frontend/src/styles/v2/tokens.component.css`

## Architecture

`BaseModal` is controlled. It never mutates `open` internally; it emits `update:open` and `close`.

Overlay primitives are split by responsibility:

- `portal.js` owns the singleton `.frontend-v2-portal` container and its owner count.
- `overlayStack.js` tracks modal/dropdown ordering and top-most interaction.
- `focusTrap.js` keeps focus in the active modal and is Teleport-aware.
- `scrollLock.js` reference-counts body overflow locking and restores the previous inline value on cleanup.

## BaseModal API

Actual public props:

- `open`
- `title`
- `description`
- `ariaLabel`
- `closeOnEscape`
- `closeOnBackdrop`

Actual DOM contract:

- `aria-label` is generated only as a DOM fallback when there is no visible title.
- `aria-labelledby` and `aria-describedby` are generated internally from stable IDs when `title` / `description` are present.
- callers do not pass raw `aria-labelledby` / `aria-describedby` props.

## Portal Contract

- only one runtime portal container exists
- modal overlays share the same portal container as dropdown overlays
- portal ownership is released on close and unmount
- legacy pages do not create a V2 portal

## Overlay Stack Contract

- modal overlays register as `group: modal`
- nested modals remain top-ordered
- background modals become inert while a child is topmost
- dropdowns inside modals still close before the modal itself
- Escape only affects the top-most active overlay

## RED

I cannot substantiate a full validator-first contract RED from the available trace.

The first recorded failure during this phase was the lab count gate:

- `validate-v2-modal-foundation.mjs` failed because the Lab still said `17 base components ready`

That is a real failure, but it is not a full contract RED for BaseModal existence / export / stack / focus / scroll / ARIA. This phase therefore contains a TDD process deviation.

## TDD Process Deviation

The modal validator was introduced after the modal implementation was already in place, so the first captured failure was a Lab content mismatch rather than a clean contract-failure RED.

That deviation is recorded here instead of being hidden.

## GREEN

After the Lab count was updated to `18 base components ready`, the modal validator passed.

The favicon validator was also decoupled from the whole-file SHA of `tokens.component.css` and now checks the exact favicon contract only.

## Validator Self-check

Passed validators:

- `node frontend/scripts/validate-v2-foundation.mjs`
- `node frontend/scripts/validate-login-redirect.mjs`
- `node frontend/scripts/validate-v2-base-components.mjs`
- `node frontend/scripts/validate-v2-support-components.mjs`
- `node frontend/scripts/validate-v2-dropdown.mjs`
- `node frontend/scripts/validate-v2-resource-foundation.mjs`
- `node frontend/scripts/validate-v2-api-cases-direct-mapping.mjs`
- `node frontend/scripts/validate-v2-api-cases-foundation-integration.mjs`
- `node frontend/scripts/validate-v2-favicon-static-asset.mjs`
- `node frontend/scripts/validate-v2-modal-foundation.mjs`

Modal validator self-check still rejects:

- production imports of `BaseModal`
- missing Teleport / portal / stack / focus-trap / scroll-lock contracts
- missing lab coverage

Favicon validator self-check still rejects:

- `href="/v3/favicon.ico"`
- duplicate favicon declarations
- wrong build output href
- global Vite base rewrites
- bad favicon file parity
- protected Phase 5.5D business-file changes

## Component Lab Scenarios

Verified in `http://127.0.0.1:5173/v3/dev/v2-base-components.html`:

- Default
- Long Content
- Footer Slot
- No Footer
- Title + Description
- ariaLabel Fallback
- Default Backdrop
- Opt-in Backdrop
- Escape Disabled
- Initial Autofocus
- No Focusable Content
- Two Nested
- Dropdown Inside
- Dropdown Then Modal
- External Controlled
- Unmount While Open
- Opener Removed
- Scroll Lock Proof
- Background Blocking Proof

## Browser Verification

### Component Lab

- URL: `http://127.0.0.1:5173/v3/dev/v2-base-components.html`
- Title: `Frontend V2 Base Components Lab`
- Console: 2 debug messages only (`[vite] connecting...`, `[vite] connected.`)
- Console errors: 0
- Console warnings: 0
- Page errors: 0
- API requests: 0

### Production Smoke

| route | verified result |
| --- | --- |
| `/v3/login` → `/v3/dashboard` | login works with `admin / 123456`; dashboard survives refresh |
| `/v3/projects` | `AppFormDialog` opens as native `<dialog class="modal">`; close button works; Escape closes; backdrop click does not close |
| `/v3/api-cases` | create dialog opens as native `<dialog class="modal">`; close button works; Escape closes |
| `/v3/records` | log dialog opens and closes; no V2 portal appears |
| `/v3/ui-cases` | record-start dialog opens only; `/api/ui-record/sessions` and execute requests stayed at 0 |
| `/` | legacy root keeps `portalCount = 0` and no errors |

Production smoke console/page errors: 0 / 0

## Accessibility

Default modal behavior:

- initial focus goes to `Close modal`
- Tab sequence: `Close modal -> Cancel -> Continue -> Close modal -> Cancel`
- Shift+Tab sequence: `Cancel -> Close modal -> Continue -> Cancel`
- no-focusable modal keeps focus on the panel itself
- opener-removed close falls back to the first usable focus target (`button[data-testid="button-primary"]`)

Nested focus return:

- page opener -> `Open parent`
- parent initial focus -> `Close modal`
- child opener -> `Open child`
- child initial focus -> `Close modal`
- after child close -> `Open child`
- after parent close -> `Open parent`

ARIA checks:

- `dialog` role resolves for `Accessible review`
- `dialog` role resolves for `ARIA label fallback dialog`

Escape-disabled checks:

- modal stays open on Escape
- focus remains trapped
- close button still works

## Backdrop / Emit

- Default backdrop click did not close; `update:open = 0`, `close = 0`, reason stayed `none`.
- Opt-in backdrop click closed once with reason `backdrop`; `update:open = 1`, `close = 1`.
- Panel, header, body, and footer click dispatches left the modal open; footer noop clicked once without closing.
- Nested child open: clicking the backdrop while the child was topmost left both parent and child visible; the lower backdrop did not act.

## Listener / rAF Cleanup

- After three open/close cycles, the modal-specific document listeners returned to the same baseline counts; the Lab already had one unrelated `focusin` listener, but the modal listeners did not accumulate.
- A quick close left focus on the opener, and reopening still focused `Close modal`; no stale callback refocused a detached modal.
- The same held for the unmount path: the modal disappeared cleanly and the next open still resolved focus normally.

## External Controlled Close

- External `open = false` from the caller did not fabricate a close reason.
- `focusReturn = 1` on the opener.
- Portal, stack, scroll, and inert cleanup all returned to zero after close.

## Responsive

Long-content modal on 2x zoom simulation and normal responsive widths:

| viewport | fitsX | fitsY | panel size | body scrollable |
| --- | --- | --- | --- | --- |
| 375x760 | true | true | 327x712 | true |
| 390x780 | true | true | 342x732 | true |
| 720x450 | true | true | 576x402 | true |
| 1080x800 | true | true | 576x752 | true |
| 1240x800 | true | true | 576x752 | true |
| 1440x900 | true | true | 576x852 | true |
| 1920x1000 | true | true | 576x952 | true |

The 2x check used Chrome page scale factor 2 via CDP, not a viewport shrink:

- `visualViewport.scale = 2`
- panel stayed fully visible
- header/footer remained reachable
- body remained scrollable
- close button remained visible
- no horizontal overflow appeared

## Reduced Motion

- BaseModal does not define authored `transition` / `animation` behavior.
- In a `prefers-reduced-motion: reduce` context, `matchMedia` was `true` and modal open/close behaved the same as normal.
- The component does not wait on `transitionend` for open, close, or cleanup.

## Dropdown Regression

Verified with live overlay counts:

- modal + dropdown open: `modal=1`, `dropdown=1`, `portalOwner=2`, `portalDom=1`, `scrollLock=1`
- first Escape closes the dropdown only
- second Escape closes the modal
- dropdown inside modal does not add another scroll lock owner

## Portal / Cleanup

Live module counts from the browser:

| state | overlayAll | modal | dropdown | portalOwner | portalDom | scrollLock | bodyOverflow |
| --- | --- | --- | --- | --- | --- | --- | --- |
| initial | 0 | 0 | 0 | 0 | 0 | 0 | `""` |
| default open | 1 | 1 | 0 | 1 | 1 | 1 | `hidden` |
| default closed | 0 | 0 | 0 | 0 | 0 | 0 | `""` |
| nested parent open | 1 | 1 | 0 | 1 | 1 | 1 | `hidden` |
| nested child open | 2 | 2 | 0 | 2 | 1 | 2 | `hidden` |
| child closed | 1 | 1 | 0 | 1 | 1 | 1 | `hidden` |
| parent closed | 0 | 0 | 0 | 0 | 0 | 0 | `""` |
| unmount open | 1 | 1 | 0 | 1 | 1 | 1 | `hidden` |
| unmount after | 0 | 0 | 0 | 0 | 0 | 0 | `""` |
| controlled open | 1 | 1 | 0 | 1 | 1 | 1 | `hidden` |
| controlled after | 0 | 0 | 0 | 0 | 0 | 0 | `""` |

Reopen loop:

- open/close repeated 3 times
- portal DOM returned to 0 each time
- overlay counts returned to 0 each time
- no accumulation observed

## Overlay Stack Provenance

- `frontend/src/components/v2/overlay/overlayStack.js` current filesystem timestamps: CreationTime `2026-07-30 16:56:44`, LastWriteTime `2026-07-30 16:56:44`
- current `git status --short` shows it as untracked in this worktree
- the 5.6A audit text references the overlay contract and the `BaseDropdown -> overlayStack.js` dependency, but it is not a file-provenance record
- the defensible conclusion is that the earlier 5.6A reading was a report-level error, not evidence that the file was physically preexisting before the 5.6B worktree window

## Scroll Lock

Reference-counted behavior with non-empty initial overflow:

- before open: `body.style.overflow = scroll`
- parent open: `hidden`, lock count `1`
- child open: `hidden`, lock count `2`
- child close: `hidden`, lock count `1`
- parent close: restored exactly to `scroll`

Dropdown inside modal did not add another modal lock owner.

## Background Inert

Browser-observed inert sets:

- parent open: `div#app.frontend-v2`, `script`
- child open: `div#app.frontend-v2`, `script`, `div.v2-base-modal`
- child close: `div#app.frontend-v2`, `script`
- final close: no inert nodes remain

The portal container itself was not left inert.

`script` appears because `syncModalInteractionBlocking()` currently walks `document.body.children` and conservatively inerted every non-portal sibling. That is broader than the interactive page tree, but it did not create a user-visible regression in this phase.

Background interaction blocking:

- background button click timed out because the modal subtree intercepted pointer events
- background button text stayed unchanged
- background input value stayed unchanged
- four Tab presses stayed on the modal close button and did not reach the background
- a preexisting inert sentinel node remained inert after the final close

## Diff Audit

Actual 5.6B file changes:

- Created: `BaseModal.vue`, `focusTrap.js`, `overlayStack.js`, `scrollLock.js`, `validate-v2-modal-foundation.mjs`
- Modified: `portal.js`, `base/index.js`, `V2BaseComponentsLab.vue`, `validate-v2-support-components.mjs`, `validate-v2-favicon-static-asset.mjs`

What this phase did not change:

- `frontend/public/favicon.ico`
- `frontend/index.html`
- `frontend/dev/v2-base-components.html`
- `frontend/vite.config.js`
- `app/core/app_setup.py`
- `frontend/src/styles/v2/tokens.component.css`

The earlier report line about “token evolution” was inaccurate for 5.6B; `tokens.component.css` is a pre-existing dirty file from earlier V2 phases and was not part of this phase’s delta.

## Automated Verification

`npm --prefix frontend run build` passed.

Observed non-fatal warnings:

- `/static/v2-theme-lock.js` could not be bundled as a non-module script
- several `/static/*.css` assets remain runtime-resolved

These warnings were observed during this phase; I did not prove they were introduced by this phase.

`git diff --check` passed.

## Known Risks

- The repository still has many unrelated dirty files from adjacent work streams.
- Some Lab proof text fields are not fully reactive; live module counts were used for cleanup evidence instead.

## Cross-phase Validator Decoupling

The favicon validator no longer freezes `frontend/src/styles/v2/tokens.component.css` with a whole-file SHA-256. That was too brittle for later valid token evolution.

What remains protected:

- single shared `frontend/public/favicon.ico`
- exact `href="/favicon.ico"` in both HTML entry points
- production build parity for `frontend/dist/favicon.ico`
- exact FastAPI `GET /favicon.ico` mapping
- rejection of `/v3/favicon.ico`
- rejection of duplicate favicon declarations
- rejection of global base rewrites and build-time URL corruption
- rejection of protected Phase 5.5D business-file changes

## Phase 5.6C Recommendation

Ready to proceed.
