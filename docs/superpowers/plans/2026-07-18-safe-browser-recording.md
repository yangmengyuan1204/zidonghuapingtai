# 日本站安全浏览器录制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有实时浏览器录制器改造成登录阶段不捕获、单动作检查点捕获、敏感信息入口即脱敏且只有冻结检查点才能保存的安全录制器。

**Architecture:** 保留现有 Playwright 可见浏览器和 HAR/RecordedFlow 链路，在 `browser_session.py` 内增加录制状态机与纯函数脱敏边界，在 `browser_record.py` 增加检查点控制接口和保存前状态门禁。阶段 1 只提供安全、可审阅的脱敏事件，不猜测哪个请求是主回退接口，也不修改数据库结构。

**Tech Stack:** Python 3.11、FastAPI 0.115、Playwright 1.60、pytest、现有 SQLite/SQLAlchemy RecordedFlow 模型。

## Global Constraints

- 所有测试必须使用 `.venv\Scripts\python.exe`。
- 修改前执行 `git status --short`，保留并不提交所有用户现有改动。
- 不修改 `.secret_key`、数据库文件、环境配置或启动脚本。
- 不新增数据库表或字段。
- 不改变现有 `/api/browser-record/sessions`、`events`、`navigate`、`save` 和 `DELETE` 路径。
- 不把密码、验证码、Authorization、Cookie、Token、手机号等敏感原值写入事件、响应、日志、HAR 或 RecordedFlow。
- 敏感信息在请求/响应进入事件时立即脱敏，禁止先保存原文再清理。
- 阶段 1 不自动判断主变更接口；一个检查点录到多个请求时全部作为脱敏候选展示。
- 不启动浏览器做验证；先完成单元和路由测试，真实录制由用户在下一阶段明确发起。
- 每次提交只添加当前任务列出的文件，禁止 `git add -A`。

---

## File Map

- `app/services/browser_session.py`：录制会话状态机、入口脱敏、检查点事件生命周期和脱敏事件读取。
- `app/routers/browser_record.py`：会话状态、开始/停止检查点接口，以及保存前必须冻结的门禁。
- `tests/test_browser_recording_safety.py`：脱敏、状态机、路由合同和保存门禁的独立测试。

本计划不修改 `app/services/har_recorder.py`：它只接收已经脱敏的事件；测试会证明传给它的 HAR 不含敏感原值。

---

### Task 1: 入口脱敏与录制状态机

**Files:**
- Modify: `app/services/browser_session.py:19-286`
- Create: `tests/test_browser_recording_safety.py`

**Interfaces:**
- Consumes: Playwright request/response objects already passed to `_on_request_sync` and `_on_response_async`.
- Produces: `sanitize_headers(headers)`, `sanitize_mapping(value)`, `sanitize_body(text, content_type)`, `sanitize_response_body(text, content_type)`, `sanitize_url(url)`, `start_checkpoint(session_id)`, `stop_checkpoint(session_id)`, and `get_session_state(session_id)`.
- Preserves: `start_session`, `navigate_session`, `get_events`, `close_session`, and the existing `_SESSIONS` runtime registry.

- [ ] **Step 1: Write failing sanitization and state-machine tests**

Create `tests/test_browser_recording_safety.py` with focused fakes and these assertions:

```python
import asyncio
import json

import pytest

from app.services import browser_session


class FakeRequest:
    method = "POST"
    resource_type = "xhr"
    url = "https://example.test/order.rollback?order_sn=ORDER-1&token=query-secret"
    headers = {
        "content-type": "application/json",
        "accept": "application/json",
        "authorization": "Bearer header-secret",
        "cookie": "session=cookie-secret",
    }
    post_data = json.dumps({
        "order_sn": "ORDER-1",
        "password": "body-secret",
        "nested": {"access_token": "nested-secret", "target_status": "wait_offer"},
    })


class FakeResponse:
    status = 200
    headers = {"content-type": "application/json"}

    def __init__(self, request):
        self.request = request

    async def text(self):
        return json.dumps({
            "success": True,
            "token": "response-secret",
            "data": {"status": "wait_offer"},
        })


def make_session(state="login_ready"):
    session = browser_session._Session(None, None, None, None)
    session.state = state
    return session


def test_login_ready_does_not_capture_requests():
    session = make_session("login_ready")
    browser_session._on_request_sync(session, FakeRequest())
    assert session.events == []


def test_checkpoint_clears_old_events_and_captures_only_sanitized_data():
    session_id = "safe-checkpoint"
    session = make_session()
    session.events.append({"path": "/old"})
    browser_session._SESSIONS[session_id] = session
    try:
        state = browser_session.start_checkpoint(session_id)
        assert state == {"session_id": session_id, "status": "capturing", "event_count": 0}

        request = FakeRequest()
        browser_session._on_request_sync(session, request)
        asyncio.run(browser_session._on_response_async(session, FakeResponse(request)))
        frozen = browser_session.stop_checkpoint(session_id)

        assert frozen == {"session_id": session_id, "status": "frozen", "event_count": 1}
        event = browser_session.get_events(session_id)[0]
        serialized = json.dumps(event, ensure_ascii=False)
        for secret in ("query-secret", "header-secret", "cookie-secret", "body-secret", "nested-secret", "response-secret"):
            assert secret not in serialized
        assert event["headers"] == {"content-type": "application/json", "accept": "application/json"}
        assert event["query"] == {"order_sn": "ORDER-1", "token": "[REDACTED]"}
        assert json.loads(event["body"])["password"] == "[REDACTED]"
        assert event["response_body"]["token"] == "[REDACTED]"
        assert event["response_body"]["data"]["status"] == "wait_offer"
    finally:
        browser_session._SESSIONS.pop(session_id, None)


def test_start_and_stop_checkpoint_reject_missing_session():
    with pytest.raises(ValueError, match="会话不存在"):
        browser_session.start_checkpoint("missing")
    with pytest.raises(ValueError, match="会话不存在"):
        browser_session.stop_checkpoint("missing")


def test_non_json_response_body_is_omitted():
    assert browser_session.sanitize_response_body("plain token=secret", "text/plain") == "[NON_JSON_RESPONSE_OMITTED]"


def test_form_body_is_sanitized_without_losing_business_fields():
    body = browser_session.sanitize_body(
        "order_sn=ORDER-1&password=secret&target_status=wait_offer",
        "application/x-www-form-urlencoded",
    )
    assert "order_sn=ORDER-1" in body
    assert "target_status=wait_offer" in body
    assert "secret" not in body
    assert "password=%5BREDACTED%5D" in body
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_browser_recording_safety.py -v
```

Expected: FAIL because `_Session.state`, `start_checkpoint`, `stop_checkpoint`, `sanitize_body`, and `sanitize_response_body` do not exist and login requests are currently captured.

- [ ] **Step 3: Add pure sanitization helpers and limits**

In `app/services/browser_session.py`, extend imports with `parse_qsl`, `urlencode`, `urlunsplit`, and add these constants and helpers near the existing recorder constants:

```python
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

_SAFE_HEADER_NAMES = {"accept", "content-type", "x-requested-with"}
_SENSITIVE_FIELD_NAMES = {
    "access_token", "authorization", "captcha", "code", "compute_token",
    "cookie", "mobile", "otp", "passwd", "password", "phone", "pwd",
    "refresh_token", "token", "usertoken",
}
_REDACTED = "[REDACTED]"
_MAX_CAPTURE_TEXT = 100_000


def _is_sensitive_field(name: Any) -> bool:
    text = str(name or "").strip().lower().replace("-", "_")
    return text in _SENSITIVE_FIELD_NAMES or text.endswith("_password") or text.endswith("_token")


def sanitize_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in (headers or {}).items():
        lowered = str(name).strip().lower()
        if lowered in _SAFE_HEADER_NAMES:
            result[lowered] = str(value)[:1000]
    return result


def sanitize_mapping(value: Any, *, depth: int = 0) -> Any:
    if depth >= 8:
        return "[MAX_DEPTH]"
    if isinstance(value, dict):
        return {
            str(key): (_REDACTED if _is_sensitive_field(key) else sanitize_mapping(item, depth=depth + 1))
            for key, item in list(value.items())[:200]
        }
    if isinstance(value, list):
        return [sanitize_mapping(item, depth=depth + 1) for item in value[:200]]
    if isinstance(value, str):
        return value[:_MAX_CAPTURE_TEXT]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:_MAX_CAPTURE_TEXT]


def sanitize_body(text: str, content_type: str) -> str:
    raw = str(text or "")[:_MAX_CAPTURE_TEXT]
    lowered = str(content_type or "").lower()
    if not raw:
        return ""
    if "json" in lowered:
        parsed = _try_parse_json(raw)
        return json.dumps(sanitize_mapping(parsed), ensure_ascii=False) if parsed is not None else "[INVALID_JSON_OMITTED]"
    if "application/x-www-form-urlencoded" in lowered:
        pairs = parse_qsl(raw, keep_blank_values=True)
        sanitized = [(key, _REDACTED if _is_sensitive_field(key) else value[:_MAX_CAPTURE_TEXT]) for key, value in pairs]
        return urlencode(sanitized)
    return "[UNSUPPORTED_BODY_OMITTED]"


def sanitize_response_body(text: str, content_type: str) -> Any:
    raw = str(text or "")[:_MAX_CAPTURE_TEXT]
    if "json" not in str(content_type or "").lower():
        return "[NON_JSON_RESPONSE_OMITTED]" if raw else ""
    parsed = _try_parse_json(raw)
    return sanitize_mapping(parsed) if parsed is not None else "[INVALID_JSON_RESPONSE_OMITTED]"


def sanitize_url(url: str) -> tuple[str, dict[str, str]]:
    parsed = urlsplit(str(url or ""))
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    safe_pairs = [(key, _REDACTED if _is_sensitive_field(key) else value[:1000]) for key, value in pairs]
    safe_query = urlencode(safe_pairs)
    safe_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, ""))
    return safe_url, dict(safe_pairs)
```

Use field-name matching only. Do not attempt regular-expression replacement inside arbitrary business text because it can corrupt legitimate Japanese-site payloads.

- [ ] **Step 4: Add the session state and checkpoint API**

Add `self.state = "login_ready"` to `_Session.__init__`, then add:

```python
def get_session_state(session_id: str) -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")
    return {"session_id": session_id, "status": session.state, "event_count": len(session.events)}


def start_checkpoint(session_id: str) -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")
    session.events.clear()
    session.state = "capturing"
    session.last_activity = time.time()
    return get_session_state(session_id)


def stop_checkpoint(session_id: str) -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")
    session.state = "frozen"
    session.last_activity = time.time()
    return get_session_state(session_id)
```

At the top of `_on_request_sync`, return unless `session.state == "capturing"`. Replace raw URL/header/body assignment with:

```python
safe_url, safe_query = sanitize_url(request.url or "")
raw_headers = dict(request.headers) if request.headers else {}
content_type = str(raw_headers.get("content-type") or raw_headers.get("Content-Type") or "")
event = {
    "method": request.method or "GET",
    "url": safe_url,
    "path": urlsplit(safe_url).path or "",
    "query": safe_query,
    "headers": sanitize_headers(raw_headers),
    "body": sanitize_body(request.post_data or "", content_type),
    "response_status": None,
    "response_body": None,
    "started_at": datetime.now().isoformat(),
    "_request_id": id(request),
}
```

In `_on_response_async`, retain response matching after the session is frozen so a pending response may finish, but replace the raw response body assignment with:

```python
response_headers = dict(response.headers) if response.headers else {}
content_type = str(response_headers.get("content-type") or response_headers.get("Content-Type") or "")
text = await asyncio.wait_for(response.text(), timeout=10)
event["response_body"] = sanitize_response_body(text, content_type)
```

- [ ] **Step 5: Run the new tests and verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_browser_recording_safety.py -v
```

Expected: PASS.

- [ ] **Step 6: Run syntax verification**

Run:

```powershell
.venv\Scripts\python.exe -m py_compile app/services/browser_session.py tests/test_browser_recording_safety.py
```

Expected: no output and exit code 0.

- [ ] **Step 7: Commit Task 1 only**

Before staging, run `git status --short` and `git diff --stat`. Report that only these two files will be committed, then run:

```powershell
git add app/services/browser_session.py tests/test_browser_recording_safety.py
git commit -m "feat: add safe browser recording checkpoints"
```

Expected: commit succeeds without staging any existing unrelated file.

---

### Task 2: Checkpoint Routes and Save Guard

**Files:**
- Modify: `app/routers/browser_record.py:15-97`
- Modify: `tests/test_browser_recording_safety.py`

**Interfaces:**
- Consumes: `browser_session.get_session_state`, `start_checkpoint`, `stop_checkpoint`, and `get_events` from Task 1.
- Produces: `GET /api/browser-record/sessions/{session_id}`, `POST .../checkpoint/start`, and `POST .../checkpoint/stop`.
- Preserves: existing create, events, navigate, close, save paths and RecordedFlow persistence format.

- [ ] **Step 1: Write failing route tests**

Append to `tests/test_browser_recording_safety.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.routers import browser_record


class FakeDb:
    def add(self, value):
        raise AssertionError("save guard must stop before database writes")

    def flush(self):
        raise AssertionError("save guard must stop before database writes")

    def commit(self):
        raise AssertionError("save guard must stop before database writes")


def route_client():
    app = FastAPI()
    app.include_router(browser_record.router)
    app.dependency_overrides[get_db] = lambda: FakeDb()
    return TestClient(app)


def test_checkpoint_routes_expose_safe_state(monkeypatch):
    monkeypatch.setattr(browser_session, "get_session_state", lambda session_id: {
        "session_id": session_id, "status": "login_ready", "event_count": 0,
    })
    monkeypatch.setattr(browser_session, "start_checkpoint", lambda session_id: {
        "session_id": session_id, "status": "capturing", "event_count": 0,
    })
    monkeypatch.setattr(browser_session, "stop_checkpoint", lambda session_id: {
        "session_id": session_id, "status": "frozen", "event_count": 2,
    })
    client = route_client()

    assert client.get("/api/browser-record/sessions/S1").json()["status"] == "login_ready"
    assert client.post("/api/browser-record/sessions/S1/checkpoint/start").json()["status"] == "capturing"
    stopped = client.post("/api/browser-record/sessions/S1/checkpoint/stop").json()
    assert stopped == {"session_id": "S1", "status": "frozen", "event_count": 2}


def test_checkpoint_route_returns_404_for_missing_session(monkeypatch):
    def missing(_session_id):
        raise ValueError("会话不存在: missing")

    monkeypatch.setattr(browser_session, "start_checkpoint", missing)
    response = route_client().post("/api/browser-record/sessions/missing/checkpoint/start")
    assert response.status_code == 404
    assert response.json()["detail"] == "会话不存在: missing"


def test_save_rejects_non_frozen_session_before_database_write(monkeypatch):
    monkeypatch.setattr(browser_session, "get_session_state", lambda session_id: {
        "session_id": session_id, "status": "capturing", "event_count": 1,
    })
    response = route_client().post(
        "/api/browser-record/sessions/S1/save",
        json={"name": "不得保存"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "请先停止并冻结当前检查点"
```

- [ ] **Step 2: Run route tests and verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_browser_recording_safety.py -v -k "route or save"
```

Expected: FAIL with 404 for the three new routes and no save-state guard.

- [ ] **Step 3: Add session state and checkpoint routes**

In `app/routers/browser_record.py`, add a small adapter to keep 404 handling identical:

```python
def _session_action(action, session_id: str) -> Dict[str, Any]:
    try:
        return action(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/sessions/{session_id}")
def session_state(session_id: str) -> Dict[str, Any]:
    return _session_action(browser_session.get_session_state, session_id)


@router.post("/sessions/{session_id}/checkpoint/start")
def start_checkpoint(session_id: str) -> Dict[str, Any]:
    return _session_action(browser_session.start_checkpoint, session_id)


@router.post("/sessions/{session_id}/checkpoint/stop")
def stop_checkpoint(session_id: str) -> Dict[str, Any]:
    return _session_action(browser_session.stop_checkpoint, session_id)
```

Update `create_session` to return the initial status without changing its existing key:

```python
return {"session_id": session_id, "status": "login_ready"}
```

- [ ] **Step 4: Add the frozen-state save guard**

At the beginning of `save_session`, after validating `name` and before reading events or touching the database, add:

```python
try:
    session_state = browser_session.get_session_state(session_id)
except ValueError as exc:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
if session_state["status"] != "frozen":
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="请先停止并冻结当前检查点",
    )
```

Do not change RecordedFlow or RecordedFlowStep fields. The existing `_events_to_har` path receives sanitized events from Task 1.

- [ ] **Step 5: Add a HAR safety regression test**

Append:

```python
def test_events_to_har_preserves_only_sanitized_values():
    har = browser_record._events_to_har([{
        "method": "POST",
        "url": "https://example.test/order.rollback?token=%5BREDACTED%5D",
        "query": {"token": "[REDACTED]"},
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"password": "[REDACTED]", "order_sn": "ORDER-1"}),
        "response_status": 200,
        "response_body": {"token": "[REDACTED]", "status": "wait_offer"},
        "started_at": "2026-07-18T12:00:00",
    }])
    serialized = json.dumps(har, ensure_ascii=False)
    assert "ORDER-1" in serialized
    assert "wait_offer" in serialized
    assert "secret" not in serialized
    assert "authorization" not in serialized.lower()
    assert "cookie" not in serialized.lower()
```

- [ ] **Step 6: Run Task 2 tests and verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_browser_recording_safety.py -v
```

Expected: PASS.

- [ ] **Step 7: Run route and existing recorder-adjacent regressions**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_browser_recording_safety.py tests/test_ui_recording.py tests/test_record_reexecution.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2 only**

Before staging, run `git status --short` and `git diff --stat`. Report that only the router and safety test are part of this commit, then run:

```powershell
git add app/routers/browser_record.py tests/test_browser_recording_safety.py
git commit -m "feat: expose safe recording checkpoints"
```

Expected: commit succeeds without staging unrelated worktree changes.

---

### Task 3: Compatibility and Security Verification Gate

**Files:**
- Verify only: `app/services/browser_session.py`
- Verify only: `app/routers/browser_record.py`
- Verify only: `tests/test_browser_recording_safety.py`

**Interfaces:**
- Consumes: completed Task 1 and Task 2 behavior.
- Produces: evidence that the safe recorder is ready for one real user-operated rollback capture.

- [ ] **Step 1: Run targeted compilation**

```powershell
.venv\Scripts\python.exe -m py_compile app/services/browser_session.py app/routers/browser_record.py tests/test_browser_recording_safety.py
```

Expected: no output and exit code 0.

- [ ] **Step 2: Run all recorder-adjacent tests**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_browser_recording_safety.py tests/test_ui_recording.py tests/test_record_reexecution.py -v
```

Expected: PASS.

- [ ] **Step 3: Run the project test suite**

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q --tb=short
```

Expected: PASS. If unrelated pre-existing failures occur, record only the failing test names and verify the three recorder-adjacent test files still pass; do not modify unrelated code.

- [ ] **Step 4: Inspect the final diff and staged scope**

```powershell
git status --short
git diff --stat
git diff --check -- app/services/browser_session.py app/routers/browser_record.py tests/test_browser_recording_safety.py
```

Expected:

- No whitespace errors in the three target files.
- No database, log, report, `.superpowers/`, configuration, or unrelated user file is staged.
- Existing unrelated worktree changes remain untouched.

- [ ] **Step 5: Perform the manual security gate before real recording**

Do not start a real browser session inside automated verification. Present this exact checklist to the user:

```text
1. 启动录制浏览器后先登录，此时状态必须是 login_ready，事件数必须为 0。
2. 打开目标订单或配送单页面后，再开始检查点。
3. 一次只操作一条相邻回退边。
4. 操作完成后立即停止检查点。
5. 预览中只能出现脱敏后的请求；发现任何密码、Cookie、Token 或手机号原值立即终止，不保存。
6. 用户确认候选请求后，才进入回退接口事实整理阶段。
```

Expected: user explicitly authorizes the first real single-edge recording after reviewing this checklist.

---

## Follow-up Plan Gates

Do not write or execute the rollback-script plan until the safe recorder produces confirmed facts for all required edges:

1. 订单已报价 → 待报价。
2. 订单待报价 → 订单采购。
3. 订单采购 → 订单翻译。
4. 配送单已报价 → 待报价。
5. 配送单待报价 → 待装箱。
6. 配送单待装箱 → 待翻译。
7. 指定已上架商品以负数数量回到核查中。

For each edge, the next plan requires exact method, path, sanitized request structure, object identifier source, pre-state query, post-state query, success field, and failure response. After those facts are confirmed, create separate plans for:

- `日本站回退脚本与状态校验`：新增独立 `app/data_scripts/rollback.py` 和对应测试。
- `DeepSeek 回退能力接入`：扩展能力元数据、合同编译和智能体工具测试。

