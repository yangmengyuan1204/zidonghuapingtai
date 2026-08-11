# Frontend V2 Docs Index

短索引。细节见交接与迁移计划，不要把本文件当完整说明书。

## Core

| Doc | Path |
|---|---|
| Handoff (Codex) | [handoff/CODEX-HANDOFF.md](handoff/CODEX-HANDOFF.md) |
| Current Task | [handoff/CURRENT-TASK.md](handoff/CURRENT-TASK.md) |
| Machine State | [handoff/STATE.json](handoff/STATE.json) |
| Migration Plan | [../migration/frontend-v2-vue-migration-plan.md](../migration/frontend-v2-vue-migration-plan.md) |
| Visual Prototype | [../prototypes/frontend-v2-shell-prototype.html](../prototypes/frontend-v2-shell-prototype.html) |

## Phase Reports

优先目录（不被 `reports/` gitignore）：

- [phase-reports/](phase-reports/)

已知报告：

- `phase-reports/frontend-v2-phase5-2b1-support-components-report-2026-07-29.md`

磁盘仍可能存在、但被 `.gitignore` 忽略：

- `docs/reports/frontend-v2-phase5-1-1-login-redirect-hotfix-report-2026-07-29.md`
- `docs/reports/frontend-v2-phase5-2a-base-primitives-report-2026-07-29.md`
- `docs/frontend-v2-phase5-1-foundation-completion-report-2026-07-29.html`

## Component Lab

- HTML: `frontend/dev/v2-base-components.html`
- Entry: `frontend/src/dev/v2-base-components-main.js`
- Lab UI: `frontend/src/dev/V2BaseComponentsLab.vue`
- Dev URL: `http://127.0.0.1:5173/v3/dev/v2-base-components.html`（`cd frontend && npm run dev`）

## Validation Scripts

- `frontend/scripts/validate-v2-foundation.mjs`
- `frontend/scripts/validate-login-redirect.mjs`
- `frontend/scripts/validate-v2-base-components.mjs`
- `frontend/scripts/validate-v2-support-components.mjs`

## Next Phase

**Phase 5.2B2 — Overlay Foundation & BaseDropdown**（尚未开始）→ 见 [CURRENT-TASK.md](handoff/CURRENT-TASK.md)
