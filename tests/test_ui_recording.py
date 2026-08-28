import asyncio
from types import SimpleNamespace

from app.routers import ui_record
from app.services import ui_recording_session
from app.services.ui_recording_session import build_ui_steps


def test_build_ui_steps_merges_consecutive_input_and_appends_assertions():
    events = [
        {
            "action": "input",
            "locator": "#username",
            "fallback_locators": ['[name="username"]'],
            "value": "a",
            "url": "https://example.test/login",
        },
        {
            "action": "input",
            "locator": "#username",
            "fallback_locators": ['[name="username"]'],
            "value": "admin",
            "url": "https://example.test/login",
        },
        {
            "action": "click",
            "locator": 'button:has-text("登录")',
            "fallback_locators": ['text="登录"'],
            "text": "登录",
            "url": "https://example.test/home",
        },
    ]

    steps = build_ui_steps(
        "https://example.test/login",
        "https://example.test/home",
        events,
        "欢迎回来",
    )

    assert steps[0] == {"name": "打开起始页面", "action": "goto", "value": "https://example.test/login"}
    input_steps = [step for step in steps if step["action"] == "input"]
    assert len(input_steps) == 1
    assert input_steps[0]["value"] == "admin"
    assert input_steps[0]["fallback_locators"] == ['[name="username"]']
    assert any(step["action"] == "click" and step["locator"] == 'button:has-text("登录")' for step in steps)
    assert steps[-2] == {"name": "检查页面文案", "action": "text_assert", "locator": "body", "value": "欢迎回来"}
    assert steps[-1] == {"name": "检查最终地址", "action": "assert_url", "value": "https://example.test/home", "exact": False}


def test_build_ui_steps_ignores_url_change_as_action_but_uses_final_url():
    events = [
        {"action": "url_change", "value": "https://example.test/list", "url": "https://example.test/list"},
        {"action": "select", "locator": '[name="status"]', "value": "paid", "url": "https://example.test/list"},
        {"action": "check", "locator": "#agree", "value": "yes", "url": "https://example.test/list?done=1"},
    ]

    steps = build_ui_steps("https://example.test", "", events)

    assert [step["action"] for step in steps] == ["goto", "goto", "select", "check", "assert_url"]
    assert steps[1]["value"] == "https://example.test/list"
    assert steps[2]["value"] == "paid"
    assert steps[3]["value"] == "yes"
    assert steps[-1]["value"] == "https://example.test/list?done=1"


def test_build_ui_steps_keeps_full_navigation_before_form_input():
    events = [
        {"action": "click", "locator": 'text="Login"', "text": "Login", "url": "https://example.test/search"},
        {"action": "url_change", "value": "https://example.test/login", "url": "https://example.test/login"},
        {"action": "input", "locator": '[name="username"]', "value": "demo", "url": "https://example.test/login"},
    ]

    steps = build_ui_steps("https://example.test/search", "https://example.test/login", events)

    assert [step["action"] for step in steps] == ["goto", "click", "goto", "input", "assert_url"]
    assert steps[2] == {"name": "打开跳转页面", "action": "goto", "value": "https://example.test/login"}


def test_get_session_storage_state_returns_live_browser_state():
    class FakeContext:
        async def storage_state(self):
            return {"cookies": [{"name": "session", "value": "masked"}], "origins": []}

    session_id = "storage-state-test"
    ui_recording_session._SESSIONS[session_id] = ui_recording_session._Session(
        playwright=None,
        browser=None,
        context=FakeContext(),
        page=None,
        project_id=1,
        case_name="登录态保存",
        start_url="https://example.test",
        persistent=True,
    )
    try:
        state = asyncio.run(ui_recording_session.get_session_storage_state(session_id))
        assert state["cookies"][0]["name"] == "session"
        assert ui_recording_session._SESSIONS[session_id].persistent is True
    finally:
        ui_recording_session._SESSIONS.pop(session_id, None)


def test_recording_session_state_exposes_account_profile_id():
    session_id = "account-profile-test"
    ui_recording_session._SESSIONS[session_id] = ui_recording_session._Session(
        playwright=None,
        browser=None,
        context=None,
        page=None,
        project_id=1,
        case_name="前台订单录制",
        start_url="https://example.test/orders",
    )
    try:
        state = ui_recording_session.get_session_state(session_id)
        assert state["account_profile_id"] is None
    finally:
        ui_recording_session._SESSIONS.pop(session_id, None)


def test_attach_page_recorder_captures_navigation_from_second_tab():
    class FakePage:
        def __init__(self):
            self.main_frame = object()
            self.handlers = {}

        def on(self, event, callback):
            self.handlers[event] = callback

    page = FakePage()
    session = ui_recording_session._Session(
        playwright=None,
        browser=None,
        context=None,
        page=None,
        project_id=1,
        case_name="多标签页录制",
        start_url="https://example.test",
    )
    ui_recording_session._attach_page_recorder(session, page)

    page.main_frame = SimpleNamespace(url="https://example.test/detail")
    page.handlers["framenavigated"](page.main_frame)

    assert {"framenavigated", "domcontentloaded", "load"}.issubset(page.handlers)
    assert session.events[-1]["url"] == "https://example.test/detail"


def test_create_recording_session_restores_selected_account_browser_state(monkeypatch):
    captured = {}
    profile = SimpleNamespace(
        id=12,
        project_id=1,
        status="active",
        browser_state_encrypted="encrypted-state",
    )

    class FakeDb:
        def get(self, _model, profile_id):
            assert profile_id == 12
            return profile

    async def fake_start_session(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "recording-session"

    monkeypatch.setattr(ui_record, "ensure_project_exists", lambda *_: None)
    monkeypatch.setattr(ui_record.ui_recording_session, "start_session", fake_start_session)
    monkeypatch.setattr(
        ui_record,
        "decrypt_account_payload",
        lambda _: {"storage_state": {"cookies": [{"name": "front-session"}]}},
        raising=False,
    )

    result = asyncio.run(
        ui_record.create_ui_record_session(
            {"project_id": 1, "case_name": "前台订单", "start_url": "https://example.test/orders", "account_profile_id": 12},
            db=FakeDb(),
            current_user=SimpleNamespace(id=7),
        )
    )

    assert result["account_profile_id"] == 12
    assert captured["kwargs"]["account_profile_id"] == 12
    assert captured["kwargs"]["storage_state"]["cookies"][0]["name"] == "front-session"


def test_save_recording_session_updates_selected_account_browser_state(monkeypatch):
    profile = SimpleNamespace(
        id=12,
        project_id=1,
        status="active",
        browser_state_encrypted="",
        browser_session_status="empty",
        browser_session_validated_at=None,
        update_time=None,
    )

    class FakeDb:
        def get(self, _model, profile_id):
            assert profile_id == 12
            return profile

        def add(self, item):
            item.id = 88

        def flush(self):
            pass

        def commit(self):
            pass

        def refresh(self, _item):
            pass

    monkeypatch.setattr(
        ui_record.ui_recording_session,
        "get_session_state",
        lambda *_: {
            "project_id": 1,
            "case_name": "前台订单",
            "start_url": "https://example.test/orders",
            "preview_steps": [],
            "count": 0,
            "account_profile_id": 12,
        },
    )

    async def fake_storage_state(_session_id):
        return {"cookies": [{"name": "front-session"}], "origins": []}

    async def fake_close_session(_session_id):
        return None

    bindings = []
    monkeypatch.setattr(ui_record.ui_recording_session, "get_session_storage_state", fake_storage_state)
    monkeypatch.setattr(ui_record.ui_recording_session, "close_session", fake_close_session)
    monkeypatch.setattr(ui_record, "encrypt_account_payload", lambda value: f"encrypted:{value['storage_state']['cookies'][0]['name']}", raising=False)
    monkeypatch.setattr(ui_record, "save_test_account_binding", lambda _db, target_type, target_id, profile_id: bindings.append((target_type, target_id, profile_id)), raising=False)

    asyncio.run(ui_record.save_ui_record_session("recording-session", db=FakeDb(), current_user=SimpleNamespace(id=7)))

    assert profile.browser_state_encrypted == "encrypted:front-session"
    assert profile.browser_session_status == "valid"
    assert bindings == [("ui_case", 88, 12)]
