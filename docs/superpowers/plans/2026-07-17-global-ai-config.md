# Global AI Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide one administrator-only global AI configuration entry in the top-right header, remove every module-level configuration button and override path, preserve an existing API key when left blank, and test connectivity without saving.

**Architecture:** Keep the existing `AiConfig` table and shared `/api/ai-config` read/update path. Add a non-persisting connection-test endpoint, move the UI into a focused global JavaScript module, mount one button from the application shell, and remove all module aliases.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, requests-based shared model client, vanilla JavaScript, pytest.

## Global Constraints

- The global configuration controls every future AI task on the platform.
- Only administrators may read, test, or update connection secrets/configuration.
- Leaving API Key blank preserves the current stored key.
- Testing a connection must not persist any field.
- Do not change the `AiConfig` database schema.
- Preserve existing workspace changes; do not commit or push.

---

### Task 1: Safe global update and non-persisting connection test API

**Files:**
- Modify: `app/schemas.py:352-358`
- Modify: `app/routers/ai_config.py`
- Create: `tests/test_ai_config.py`

**Interfaces:**
- Consumes: existing `AiConfig`, `latest_ai_config`, `serialize_ai_config`, and shared model HTTP conventions.
- Produces: `POST /api/ai-config/test` with `{provider, base_url, model, api_key}` and `{ok, message, model}` response.

- [ ] **Step 1: Write failing API tests**

```python
def test_blank_api_key_preserves_existing_secret(client, admin_headers, ai_config):
    response = client.put("/api/ai-config", headers=admin_headers, json={"model": "new-model", "api_key": ""})
    assert response.status_code == 200
    assert reload_config().api_key == ai_config.api_key

def test_connection_check_does_not_persist_form_values(client, admin_headers, monkeypatch):
    before = snapshot_config()
    response = client.post("/api/ai-config/test", headers=admin_headers, json={"base_url": "https://example.test", "model": "candidate", "api_key": "secret"})
    assert response.status_code == 200
    assert snapshot_config() == before
```

Also test 401/403 behavior and Chinese categories for authentication, unavailable model, proxy/network, timeout, and invalid response.

- [ ] **Step 2: Run tests and verify they fail**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_ai_config.py -v`

Expected: FAIL because blank currently clears the key and the test endpoint does not exist.

- [ ] **Step 3: Add request schema and preserve blank secrets**

Add `AiConfigConnectionTest` with optional provider/base URL/model/API key. In `update_ai_config`, update `api_key` only when `str(value or "").strip()` is non-empty. Other fields retain current validation and table usage.

- [ ] **Step 4: Implement connection testing**

Build an unsaved `AiConfig` candidate by combining form values with the current config, where blank API Key inherits the stored secret. Make one minimal JSON model request through the shared model client, classify exceptions into Chinese messages, and never call `db.commit()`.

- [ ] **Step 5: Run API tests**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_ai_config.py -v`

Expected: PASS.

### Task 2: One top-right global entry and no module configuration buttons

**Files:**
- Create: `static/ai-config.js`
- Modify: `static/app.js:renderShell, renderFunctionalTests, openAiConfigForm`
- Modify: `static/requirement-pack.js:754-803`
- Modify: `static/requirement-verification.js:1239-1274`
- Modify: `static/index.html:16-18`
- Modify: `static/styles.css`
- Modify: `tests/test_ai_config.py`

**Interfaces:**
- Consumes: global `api`, `modalEl`, `showToast`, `escapeHtml`, and `state.user` passed from `renderShell`.
- Produces: `window.GlobalAiConfig.mount({api, modalEl, showToast, escapeHtml, isAdmin})` and one `#globalAiConfigBtn`.

- [ ] **Step 1: Write failing frontend source-contract tests**

Assert:

```python
assert 'id="globalAiConfigBtn"' in app_js
assert 'window.GlobalAiConfig.mount' in app_js
assert 'id="aiConfigBtn"' not in app_js
assert 'verificationAiConfig' not in verification_js
assert 'id="aiConfigBtn"' not in requirement_pack_js
assert 'static/ai-config.js' in index_html
```

- [ ] **Step 2: Run source-contract tests and verify they fail**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_ai_config.py -v -k "frontend"`

Expected: FAIL because module buttons still exist and the global module is absent.

- [ ] **Step 3: Implement focused global configuration UI**

`static/ai-config.js` renders a Chinese modal with service type, API address, model, masked API-key input, current model, global-impact warning, “测试连接”, and “保存配置”. Test and save buttons have independent loading states restored in `finally`. Blank key is sent as an empty string and preserved by the backend.

- [ ] **Step 4: Mount the only entry from the shell**

Wrap theme controls, global AI button, and logout in a `.topbar-actions` container. Render `#globalAiConfigBtn` only for administrators and call `window.GlobalAiConfig.mount({ api, modalEl, showToast, escapeHtml, isAdmin: isAdmin() })` once after the shell is created. Add minimal `.topbar-actions` and model-label styles.

- [ ] **Step 5: Remove module aliases and old form code**

Delete the functional-test `#aiConfigBtn`, requirement-pack `#aiConfigBtn`, requirement-verification `#verificationAiConfig`, their event bindings, and the old `openAiConfigForm` implementation from `static/app.js`. Confirm with `rg -n "aiConfigBtn|verificationAiConfig|openAiConfigForm|localStorage.*ai.*config" static` that none remain; retain module-specific prompts and business parameters.

- [ ] **Step 6: Update script order and cache versions**

Load `/static/ai-config.js` before `/static/app.js` and bump the affected script query versions. Do not change unrelated asset versions.

- [ ] **Step 7: Run frontend tests and syntax checks**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_ai_config.py -v`

Run: `node --check static/ai-config.js`

Run: `node --check static/app.js`

Run: `node --check static/requirement-pack.js`

Run: `node --check static/requirement-verification.js`

Expected: PASS and no syntax errors.

### Task 3: Cross-module configuration regression

**Files:**
- Modify: `tests/test_ai_config.py`
- Modify: `tests/test_route_contracts.py`

**Interfaces:**
- Consumes: final global API and UI.
- Produces: proof that all server-side AI consumers resolve the same latest `AiConfig` and no module override endpoint exists.

- [ ] **Step 1: Add shared-config tests**

Monkeypatch each relevant AI consumer at its model call boundary, update the global model once, and assert data agent, requirement verification, functional generation, and diagnosis receive that same model on their next invocation. Assert no route matching module-specific AI configuration is registered.

- [ ] **Step 2: Run focused route and permission tests**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_ai_config.py tests/test_route_contracts.py tests/test_permissions.py -v -k "ai_config or global_ai"`

Expected: PASS.

- [ ] **Step 3: Final engineering checks**

Run: `git diff --check`

Run: `git status --short`

Run: `git diff --stat`

Expected: no whitespace errors; no database, secret, log, report, or temporary file changes are introduced by this work.
