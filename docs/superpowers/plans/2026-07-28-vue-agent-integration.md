# Vue3 And Metadata Agent Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the completed metadata-driven DeepSeek data agent into the current uncommitted Vue3 migration without overwriting either the Vue work or concurrent backend/script work.

**Architecture:** Keep `dataScripts` on the legacy application until its dedicated Vue migration. Merge the agent backend additively, load the contract editor and learning center as legacy modules, preserve the Vue `/v3` mount and migration bridge, and keep Vue Records consuming `DataFactoryAgent.renderRecordSummary`. Resolve shared files with a three-way merge using `f82e3c1` as the common base, the current working file as ours, and `codex/metadata-agent-contract-learning` as theirs.

**Tech Stack:** Python 3.11, FastAPI, SQLite, vanilla JavaScript legacy shell, Vue 3/Vite, pytest, Node.js, GitNexus.

## Global Constraints

- Preserve every pre-existing tracked and untracked working-tree change; never replace a shared file wholesale.
- Do not modify database files, secrets, environment configuration, logs, reports, or generated Vue `dist/` artifacts.
- Use `.venv\Scripts\python.exe` for every Python test.
- Keep `dataScripts` absent from `static/migration-config.json`; the current data-agent UI remains in the legacy application.
- Preserve `/static/migration-bridge.js`, `/static/api-harvester.js`, and the `/v3` FastAPI mount.
- Load legacy modules in this order: `data-agent-contract-editor.js`, `data-agent-learning-center.js`, `data-factory-agent.js`.
- Treat `context.variables` as the runtime base and let normalized execution-contract fields override duplicate keys.
- Never stage with `git add -A`; stage only integration-owned files after reviewing the final status.

---

### Task 1: Baseline And Cross-App Navigation Contract

**Files:**
- Modify: `static/migration-bridge.js`
- Modify: `tests/test_route_contracts.py`
- Inspect: `frontend/src/services/navigation.js`
- Inspect: `static/migration-config.json`

**Interfaces:**
- Consumes: Vue fallback URL `/#/<viewKey>` emitted by `navigateToView(viewKey)`.
- Produces: legacy bridge activation of the matching `[data-view]` button after the old shell becomes available.

- [ ] **Step 1: Add a failing route-contract test**

Add a Node-backed assertion proving that `/#/dataScripts` selects the legacy `dataScripts` view while migrated views remain redirected to `/v3/<view>`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_route_contracts.py -v -k "migration_bridge and dataScripts"
```

Expected: failure because the current bridge only intercepts clicks and never consumes the initial hash.

- [ ] **Step 3: Implement bounded legacy hash activation**

Extend `migration-bridge.js` to parse only `#/` view keys matching `[A-Za-z][A-Za-z0-9_-]*`, wait for the corresponding legacy navigation button with a bounded retry loop, and invoke `button.click()` only when the view is not in `migratedSet`.

- [ ] **Step 4: Verify GREEN**

Run the focused test and `node --check static/migration-bridge.js`.

---

### Task 2: Import Agent-Owned Backend And UI Modules

**Files:**
- Create from feature branch: `app/services/data_agent_contract_compiler.py`
- Create from feature branch: `app/services/data_agent_contracts.py`
- Create from feature branch: `app/services/data_agent_learning.py`
- Create from feature branch: `static/data-agent-contract-editor.js`
- Create from feature branch: `static/data-agent-learning-center.js`
- Modify from feature branch: `app/agent_schemas.py`
- Modify from feature branch: `app/data_scripts/capabilities.py`
- Modify from feature branch: `app/routers/data_factory_agent.py`
- Modify from feature branch: `app/services/data_factory_agent_prompts.py`
- Add corresponding focused tests from `codex/metadata-agent-contract-learning`.

**Interfaces:**
- Consumes: existing FastAPI router registration and legacy `options.api` adapter.
- Produces: contract editor schema, contract preview/apply/feedback endpoints, learning sample/metrics APIs, capability metadata, and two independent legacy UI modules.

- [ ] **Step 1: Record GitNexus impacts for modified existing symbols**

Run upstream impact analysis for the router handlers, capability catalog, and prompt builders before importing changes; report HIGH/CRITICAL results.

- [ ] **Step 2: Import only files with no current working-tree edits**

Use the exact blobs from `codex/metadata-agent-contract-learning`; do not touch shared files listed in Task 3.

- [ ] **Step 3: Run focused contract and learning tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_data_agent_contracts.py tests/test_data_agent_learning.py tests/test_data_agent_learning_metrics.py tests/test_data_factory_agent_contract.py -q
```

Expected: tests may remain RED until Task 3 supplies the integrated runtime.

---

### Task 3: Three-Way Merge Shared Backend And Script Files

**Files:**
- Modify: `app/core/data_script_catalog.py`
- Modify: `app/data_scripts/__init__.py`
- Modify: `app/data_scripts/_legacy.py`
- Modify: `app/data_scripts/full_flow.py`
- Modify: `app/data_scripts/porder_resume_support.py`
- Modify: `app/data_scripts/registry.py`
- Modify: `app/routers/data_scripts.py`
- Modify: `app/services/data_factory_agent.py`
- Modify: `app/services/data_factory_agent_tools.py`
- Preserve identical untracked files: `app/data_scripts/porder_shipment.py`, `tests/test_porder_shipment.py`

**Interfaces:**
- Consumes: current Vue-era backend/script behavior plus the feature branch contract compiler, learning service, capability catalog, account strategy, and registered runner/validator path.
- Produces: one runtime that preserves current shipment/API work and executes confirmed metadata contracts with full environment variables.

- [ ] **Step 1: Generate three-way merge previews outside the repository**

For each shared file, use `f82e3c1:<path>` as base, the current file as ours, and `codex/metadata-agent-contract-learning:<path>` as theirs. Apply only conflict-free merged output mechanically; resolve conflict markers with targeted patches that preserve both behaviors.

- [ ] **Step 2: Verify registered capability runtime invariants**

Confirm `_execute_registered_capability_operation` starts from `context.variables`, overlays normalized contract fields, calls exactly one registered runner and validator, and fails closed on invalid operations or validation.

- [ ] **Step 3: Run backend RED/GREEN suites**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py tests/test_data_factory_agent_contract.py tests/test_data_script_capabilities.py tests/test_permissions.py tests/test_porder_shipment.py -q
```

Expected: all selected tests pass with no database/config modifications.

---

### Task 4: Merge Legacy UI Without Regressing Vue

**Files:**
- Modify: `static/index.html`
- Modify: `static/data-factory-agent.js`
- Modify: `static/app.js`
- Modify: `static/full-flow.js`
- Modify: `static/requirement-pack.js`
- Modify: `tests/route_contract_expected.json`
- Modify: `tests/test_route_contracts.py`

**Interfaces:**
- Consumes: legacy data factory mount contract and Vue Records dynamic loader.
- Produces: editable execution contract, single-flight save-before-confirm, learning center, and compatible intelligent-agent record summaries in both applications.

- [ ] **Step 1: Add failing integration assertions**

Assert that `static/index.html` retains `api-harvester.js` and `migration-bridge.js`, loads the two agent modules before `data-factory-agent.js`, and that Vue `recordLog.js` still calls the exported `renderRecordSummary` signature.

- [ ] **Step 2: Merge shared JavaScript with current files as ours**

Preserve every current script addition. Add contract/learning calls from the feature branch and retain the feature branch dirty-save confirmation ordering and learning-center error handling.

- [ ] **Step 3: Regenerate or minimally update the route golden**

Keep the union of current Vue/API routes and agent contract/learning routes; never replace the current golden with the feature branch copy.

- [ ] **Step 4: Run frontend syntax and route contracts**

Run:

```powershell
node --check static/data-agent-contract-editor.js
node --check static/data-agent-learning-center.js
node --check static/data-factory-agent.js
node --check static/migration-bridge.js
.venv\Scripts\python.exe -m pytest tests/test_route_contracts.py -q
```

---

### Task 5: Integrated Verification And Handoff

**Files:**
- Verify: `frontend/`
- Verify: all files changed by Tasks 1-4

**Interfaces:**
- Consumes: the merged Vue and agent runtime.
- Produces: evidence that both applications build/run and the cross-app user journey is intact.

- [ ] **Step 1: Build Vue without committing generated output**

Run `pnpm --dir frontend build`; verify `/v3` assets compile and leave `frontend/dist/` untracked/ignored.

- [ ] **Step 2: Run Python compilation and complete regression**

Run:

```powershell
.venv\Scripts\python.exe -m py_compile app/services/data_factory_agent.py app/services/data_agent_learning.py app/services/data_agent_contracts.py app/services/data_agent_contract_compiler.py
.venv\Scripts\python.exe -m pytest tests/ -q
```

- [ ] **Step 3: Run GitNexus change detection**

Run `detect-changes` against the current working changes, inspect every HIGH/CRITICAL flow, and verify no Vue mount, authentication, project isolation, permission, or unrelated script path was removed.

- [ ] **Step 4: Perform browser acceptance**

Verify `/v3` login, Vue-to-legacy Data Factory navigation, first-turn editable contract, dirty save-before-confirm, learning center, legacy-to-Vue migrated-page navigation, and Vue Records rendering of an intelligent-agent log.

- [ ] **Step 5: Report integration-owned files separately**

Do not commit or stage pre-existing user changes automatically. Provide the exact integration file list, tests, remaining risks, and recommended safe commit grouping.
