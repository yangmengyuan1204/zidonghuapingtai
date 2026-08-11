# Frontend V2 Phase 5.6C — AppModal Shared Integration Design

## Status

Design ready for review. Implementation not started.

## Git Baseline

- Branch: `codex/safe-refactor-preserve-features`
- HEAD: `a4c5764a759720707b34d65caddce7661d54e13d`
- Working tree: existing mixed Frontend V2 / regression changes already present
- Scope note: this design pass does not modify implementation files

## 1. AppModal 当前基线

`frontend/src/components/AppModal.vue` 当前仍是旧实现：

- props: `visible`, `title`, `submitLabel`
- emits: `close`, `submit`
- public slot: only `body`
- DOM:
  - `dialog.modal`
  - `form#modalForm`
  - header close button: `id="closeModal"`, `class="btn secondary"`, text `关闭`
  - submit button: `type="submit"`, `class="btn"`, inside the form
- keyboard behavior:
  - Enter submits the native form through `form#modalForm`
  - Escape closes the native dialog path
  - no custom Enter handler

Current structural risk:

- `close()` and native `onClose()` both emit `close`
- that is the double-emit path the shared adapter must remove structurally

Selector audit:

- `#closeModal`, `class="btn secondary"`, and the close text `关闭` exist only in the current AppModal DOM plus historical legacy/static references
- no production Vue view or current validator uses those selectors directly as a call-site dependency
- `type="submit"` on the footer button is the active native submit contract, so Enter behavior comes from the form rather than a custom key handler

## 2. AppModal → BaseModal 逐项映射

Approved adapter mapping:

- AppModal `visible`
  → `BaseModal.open`
- AppModal `body` slot
  → `BaseModal` default slot
- AppModal internal footer / action area
  → `BaseModal.footer` slot
- AppModal submit behavior
  → keep the native `form#modalForm` contract; footer submit button stays associated to that form

Non-mapping rules:

- no new public `footer` slot on `AppModal`
- no new public `actions` slot on `AppModal`
- no new public `header` slot on `AppModal`
- no new public `default` slot on `AppModal`
- `BaseModal` close reasons are swallowed inside `AppModal`
- `AppModal` only exposes the existing parameterless `close` plus existing `submit`

### Slot Compatibility Boundary

`AppModal` public slot API must stay unchanged.

Current public slot:

- `body`

Forbidden public slot additions:

- `footer`
- `actions`
- `header`
- `default`

Boundary rule:

- `BaseModal.footer` is internal implementation detail only
- `AppModal` may map its existing internal footer/action region into that slot
- `AppModal` must not declare or forward `#footer`
- `AppFormDialog` must not gain a footer-slot contract
- business consumers must not depend on BaseModal slot structure

## 3. 单次 close emit 路径

Design decision:

- no per-open close guard
- no `internalOpen` unless an implementation gap forces it; current preferred design is direct `visible -> BaseModal.open`
- AppModal must structurally avoid subscribing to both BaseModal `close` and `update:open` as outward parent triggers

Recommended event path:

1. user action occurs inside BaseModal
2. BaseModal manages its own internal close semantics
3. AppModal receives one adapter close notification only
4. AppModal emits one public `close`
5. parent turns `visible=false`

That keeps the outward API stable and avoids duplicate parent emissions.

## 4. 内部 footer / action 映射

AppModal内部 footer/action 区域的要求：

- 仍保留 close button
- submit button 仍为 `type="submit"`
- submit button 保持 `form#modalForm` 归属
- footer 内容只在 AppModal 内部实现，不对外暴露 slot API

Recommended detail:

- `BaseModal.footer` slot contains AppModal internal action group
- submit button may be associated to `modalForm` via `form="modalForm"` so Enter behavior stays native even when footer is outside the default slot

## 5. Escape / backdrop / close / cancel / submit 行为

保持方式：

- Escape:
  - BaseModal handles the user close request
  - AppModal emits one `close`
  - focus return stays in BaseModal
- backdrop:
  - same single close path
  - reason is swallowed inside AppModal
- close button:
  - still present
  - still `#closeModal`
  - still internal to AppModal
- cancel:
  - treated as the same outward close contract as the close button
- submit:
  - still native form submit
  - still reaches AppFormDialog / consumer `submit` unchanged

## 6. AppFormDialog 与所有调用方无需修改的证明

Current consumer inventory for `AppFormDialog` is fixed:

- `ApiCasesView.vue` — 2 instances
- `ProjectsView.vue` — 4 instances
- `UsersView.vue` — 1 instance
- `UiCasesView.vue` — 2 instances

Total: 9 instances.

Why call sites do not need changes:

- props stay the same: `visible`, `title`, `fields`, `values`, `submitLabel`
- emits stay the same: `close`, `submit`
- `AppFormDialog` still uses only the original `body` slot
- the shared textarea / select / table work already happened in earlier phases
- `UsersView.vue` is confirmed present and already consumes `AppFormDialog`; there is no unresolved consumer question

## 7. 预计修改文件与禁止文件

Likely implementation-touch set:

- `frontend/src/components/AppModal.vue`
- `frontend/src/components/AppFormDialog.vue` only if adapter wiring needs to consume the new BaseModal contract
- `frontend/scripts/validate-v2-modal-shared-integration.mjs` or equivalent new integration validator
- `docs/frontend-v2/phase-reports/frontend-v2-phase5-6c-appmodal-shared-integration-design-report-2026-07-31.md`

Explicitly not for this phase:

- `frontend/src/components/v2/base/BaseModal.vue`
- modal foundation validator
- any view file
- Router / Store / API
- AppShell / Dashboard / Projects / ApiCases / Users / UiCases business logic

## 8. Validator RED / GREEN 设计

Do not change the modal foundation validator.

Add a new Phase 5.6C integration validator that checks:

- `AppModal` imports and uses `BaseModal`
- `AppModal` public slot API stays unchanged
- `AppModal` does not add public `footer`, `actions`, `header`, or `default` slots
- `AppModal` does not declare `update:open` as a public contract
- `AppModal` does not use a per-open close guard
- `AppModal` does not require `internalOpen`
- `#closeModal`, close button class/text, and submit `type="submit"` remain compatible
- `AppFormDialog` props / emits / body-slot contract stay unchanged
- no new production consumer appears for `BaseModal`
- Lab / export / test usage remains allowed
- `BaseModal` remains exportable without adding a new production consumer

RED expectation:

- before implementation, the new integration validator should fail on the missing AppModal adapter path

GREEN expectation:

- after implementation, the validator passes without changing modal foundation rules

## 9. 浏览器验证矩阵

Verification scope must avoid real CRUD / write actions.

Planned browser checks:

- open / close AppModal through AppFormDialog
- Escape closes once
- backdrop closes once when enabled
- close button works once
- submit button remains a real form submit control
- Enter submits through native form ownership
- focus return occurs once
- no duplicate emit path
- no extra business writes during smoke

For consumers:

- `ApiCasesView.vue`
- `ProjectsView.vue`
- `UsersView.vue`
- `UiCasesView.vue`

Only modal-open / modal-close / keyboard / focus-path verification is in scope.

## 10. 风险与回滚点

Main risks:

- accidentally reintroducing double emits by listening to both BaseModal events
- adding `internalOpen` when direct controlled open is enough
- breaking native form Enter behavior when footer moves into BaseModal footer slot
- accidentally widening BaseModal production consumers beyond AppModal

Rollback point:

- if the adapter cannot preserve the single-close path and form contract together, stop and rework the adapter boundary rather than relaxing the validator

## 11. Conclusion

This design keeps AppModal’s public API stable, maps body/footer internally to BaseModal, removes the need for a per-open guard, keeps BaseModal reason details internal, and preserves all AppFormDialog consumers without call-site edits.
