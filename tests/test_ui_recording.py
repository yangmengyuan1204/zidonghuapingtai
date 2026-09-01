import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import ui_cases, ui_record
from app.services import ui_recording_session
from app.services.ui_recording_session import build_ui_steps
from app.models import UiRecordPreflight


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


def test_build_ui_steps_keeps_popup_context_for_actions_and_final_assertions():
    events = [
        {"action": "click", "locator": "#open", "url": "https://example.test", "page_index": 0},
        {
            "action": "url_change",
            "value": "https://pay.example.test/checkout",
            "url": "https://pay.example.test/checkout",
            "page_index": 1,
        },
        {
            "action": "input",
            "locator": "#card",
            "value": "4111",
            "url": "https://pay.example.test/checkout",
            "page_index": 1,
        },
    ]

    steps = build_ui_steps("https://example.test", "https://example.test", events, "支付成功")

    assert [step["action"] for step in steps] == ["goto", "click", "input", "text_assert", "assert_url"]
    assert steps[2]["page_index"] == 1
    assert steps[-2]["page_index"] == 1
    assert steps[-1]["page_index"] == 1
    assert steps[-1]["value"] == "https://pay.example.test/checkout"


def test_recorded_step_contains_scored_locator_profile_and_uses_stable_primary():
    events = [
        {
            "action": "click",
            "locator": "#button_1723456789012",
            "fallback_locators": ['button:has-text("提交订单")'],
            "locator_candidates": [
                {"value": "#button_1723456789012", "strategy": "id", "count": 1, "visible": True},
                {"value": 'button:has-text("提交订单")', "strategy": "role_text", "count": 1, "visible": True},
            ],
            "tag": "button",
            "role": "button",
            "text": "提交订单",
            "url": "https://example.test/order",
        }
    ]

    steps = build_ui_steps("https://example.test/order", "", events)

    click_step = steps[1]
    assert click_step["locator"] == 'button:has-text("提交订单")'
    assert click_step["locator_profile"]["quality"] == "stable"
    assert click_step["locator_profile"]["schema_version"] == 2


def test_sanitize_event_keeps_frame_and_structured_locator_metadata():
    event = ui_recording_session._sanitize_event(
        {
            "action": "click",
            "locator": "#save",
            "locator_candidates": [
                {"value": "#save", "strategy": "id", "count": 1, "visible": True},
            ],
            "frame_path": [{"name": "checkout-frame", "url": "https://pay.example.test/frame"}],
            "page_index": 1,
            "role": "button",
            "label": "保存",
            "url": "https://example.test/order",
        },
        1,
    )

    assert event["page_index"] == 1
    assert event["frame_path"][0]["name"] == "checkout-frame"
    assert event["locator_candidates"][0]["strategy"] == "id"
    assert event["role"] == "button"


def test_recording_script_collects_candidate_counts_labels_and_accessible_metadata():
    script = ui_recording_session.RECORDING_SCRIPT

    assert "locator_candidates" in script
    assert "querySelectorAll" in script
    assert "accessible_name" in script
    assert "stable_attrs" in script
    assert "frame_path" in script


def test_recording_script_captures_correlated_before_and_after_states():
    script = ui_recording_session.RECORDING_SCRIPT

    assert "interaction_id" in script
    assert "capturePageState" in script
    assert "before_state" in script
    assert "effect_observation" in script
    assert "after_state" in script
    assert "400" in script
    assert "1200" in script


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


def test_recording_session_locator_override_is_applied_to_preview_steps():
    session_id = "locator-override-test"
    ui_recording_session._SESSIONS[session_id] = ui_recording_session._Session(
        playwright=None,
        browser=None,
        context=None,
        page=SimpleNamespace(url="https://example.test"),
        project_id=1,
        case_name="修复定位器",
        start_url="https://example.test",
        events=[{"action": "click", "locator": "#old", "url": "https://example.test"}],
    )
    try:
        ui_recording_session.override_session_step_locator(session_id, 2, "#new")
        state = ui_recording_session.get_session_state(session_id)
        assert state["preview_steps"][1]["locator"] == "#new"
        assert "#old" in state["preview_steps"][1]["fallback_locators"]
    finally:
        ui_recording_session._SESSIONS.pop(session_id, None)


def test_ui_record_router_exposes_locator_override_contract():
    source = Path("app/routers/ui_record.py").read_text(encoding="utf-8")
    assert '@router.post("/sessions/{session_id}/steps/{step_index}/locator")' in source


def test_attach_page_recorder_captures_navigation_from_second_tab():
    class FakePage:
        def __init__(self):
            self.main_frame = object()
            self.handlers = {}
            self.binding_name = ""

        async def expose_binding(self, name, _callback):
            self.binding_name = name

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
    asyncio.run(ui_recording_session._attach_page_recorder(session, page))

    page.main_frame = SimpleNamespace(url="https://example.test/detail")
    page.handlers["framenavigated"](page.main_frame)

    assert {"framenavigated", "domcontentloaded", "load"}.issubset(page.handlers)
    assert page.binding_name == "__recordUiEvent"
    assert session.events[-1]["url"] == "https://example.test/detail"


def test_page_binding_marks_new_tab_and_frame_context():
    class FakePage:
        def __init__(self):
            self.main_frame = object()
            self.binding = None

        async def expose_binding(self, _name, callback):
            self.binding = callback

        def on(self, _event, _callback):
            pass

    first_page = object()
    second_page = FakePage()
    context = SimpleNamespace(pages=[first_page, second_page])
    frame = SimpleNamespace(url="https://pay.example.test/frame", name="checkout-frame")
    session = ui_recording_session._Session(
        playwright=None,
        browser=None,
        context=context,
        page=first_page,
        project_id=1,
        case_name="新窗口支付",
        start_url="https://example.test",
    )
    asyncio.run(ui_recording_session._attach_page_recorder(session, second_page))

    asyncio.run(
        second_page.binding(
            {"page": second_page, "frame": frame},
            {"action": "click", "locator": "#pay", "url": frame.url},
        )
    )

    assert session.events[-1]["page_index"] == 1
    assert session.events[-1]["frame_path"][0]["name"] == "checkout-frame"


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
        saved_case = None

        def get(self, _model, profile_id):
            assert profile_id == 12
            return profile

        def add(self, item):
            item.id = 88
            self.saved_case = item

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

    db = FakeDb()
    asyncio.run(ui_record.save_ui_record_session("recording-session", db=db, current_user=SimpleNamespace(id=7)))

    assert profile.browser_state_encrypted == "encrypted:front-session"
    assert profile.browser_session_status == "valid"
    assert bindings == [("ui_case", 88, 12)]
    assert db.saved_case.status == "draft"


def test_save_recording_session_activates_case_only_for_matching_passed_preflight(monkeypatch):
    from app.services.ui_recording_preflight import steps_snapshot_hash

    stable_steps = [
        {"action": "goto", "value": "https://example.test"},
        {"action": "click", "locator": "#save", "locator_profile": {"quality": "stable"}},
    ]
    preflight = SimpleNamespace(
        run_id="passed-run",
        session_id="recording-session",
        project_id=1,
        status="passed",
        case_id=None,
        report_json=json.dumps({
            "verification_mode": "verified",
            "verified_rounds": 2,
            "rounds": [{"round_no": 1, "status": "passed", "frozen": False}, {"round_no": 2, "status": "passed", "frozen": True}],
            "steps_snapshot_hash": steps_snapshot_hash(stable_steps),
        }, ensure_ascii=False),
    )

    class FakeDb:
        saved_case = None

        def get(self, model, key):
            if model is UiRecordPreflight and key == "passed-run":
                return preflight
            return None

        def add(self, item):
            item.id = 91
            self.saved_case = item

        def flush(self):
            pass

        def commit(self):
            pass

        def refresh(self, _item):
            pass

    preflight.steps_json = json.dumps(stable_steps, ensure_ascii=False)
    monkeypatch.setattr(
        ui_record.ui_recording_session,
        "get_session_state",
        lambda *_: {
            "project_id": 1,
            "case_name": "可靠录制",
            "start_url": "https://example.test",
            "preview_steps": stable_steps,
            "count": 1,
            "account_profile_id": None,
        },
    )

    async def fake_storage_state(_session_id):
        return {}

    async def fake_close_session(_session_id):
        return None

    monkeypatch.setattr(ui_record.ui_recording_session, "get_session_storage_state", fake_storage_state)
    monkeypatch.setattr(ui_record.ui_recording_session, "close_session", fake_close_session)

    db = FakeDb()
    result = asyncio.run(
        ui_record.save_ui_record_session(
            "recording-session",
            payload={"preflight_run_id": "passed-run"},
            db=db,
            current_user=SimpleNamespace(id=7),
        )
    )

    assert db.saved_case.status == "active"
    assert preflight.case_id == 91
    assert result["quality_status"] == "executable"


def test_draft_ui_case_is_rejected_by_normal_and_visual_execution(monkeypatch):
    draft_case = SimpleNamespace(id=9, project_id=1, page_url="https://example.test", status="draft")
    monkeypatch.setattr(ui_cases, "get_or_404", lambda *_args, **_kwargs: draft_case)

    with pytest.raises(HTTPException, match="待修复草稿"):
        ui_cases.run_ui_case(9, payload=None, db=SimpleNamespace(), current_user=SimpleNamespace(id=1))
    with pytest.raises(HTTPException, match="待修复草稿"):
        ui_cases.start_visual_ui_case(9, payload=None, db=SimpleNamespace(), current_user=SimpleNamespace(id=1))


def test_override_session_step_target_applies_to_preview_steps():
    session = ui_recording_session._Session(
        playwright=None,
        browser=None,
        context=None,
        page=SimpleNamespace(url="https://example.test/list"),
        project_id=1,
        case_name="测试",
        start_url="https://example.test/list",
    )
    session.events.append({
        "action": "click",
        "locator": 'button:has-text("旧按钮")',
        "text": "旧按钮",
        "url": "https://example.test/list",
    })
    ui_recording_session._SESSIONS["repick-session"] = session
    try:
        payload = ui_recording_session.override_session_step_target(
            "repick-session",
            2,
            ["#new-btn", '[data-testid="new-btn"]'],
            {"element": {"stable_attrs": {"id": "new-btn"}}},
        )
        steps = payload["preview_steps"]
        assert steps[1]["locator"] == "#new-btn"
        assert steps[1]["fallback_locators"] == ['[data-testid="new-btn"]', 'button:has-text("旧按钮")']
        assert steps[1]["target_profile"]["element"]["stable_attrs"]["id"] == "new-btn"
    finally:
        ui_recording_session._SESSIONS.pop("repick-session", None)


def _fake_async(result):
    async def _fn(*_args, **_kwargs):
        return result

    return _fn

# ─── Task 8: 预检/重新选点/重启/保存 API ─────────────────────────

class _FakeDb:
    def __init__(self, preflight=None):
        self.preflight = preflight
        self.added = []

    def get(self, model, key):
        if model is UiRecordPreflight and self.preflight is not None:
            return self.preflight
        return None

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        return None

    def commit(self):
        return None

    def refresh(self, obj):
        obj.id = 7
        return None

    def rollback(self):
        return None


def _fake_session_state(steps):
    return {
        "project_id": 1,
        "case_name": "订单下单",
        "start_url": "https://example.test/orders",
        "preview_steps": steps,
        "account_profile_id": None,
        "count": 0,
        "items": [],
    }


def _fake_preflight_row(status="queued", report=None, session_id="session", project_id=1, steps=None):
    return SimpleNamespace(
        run_id="run",
        session_id=session_id,
        project_id=project_id,
        case_id=0,
        status=status,
        assertion_text="",
        steps_json=json.dumps(steps, ensure_ascii=False) if steps is not None else "[]",
        report_json=json.dumps(report or {}, ensure_ascii=False),
        screenshot="",
        error_category="",
        update_time=None,
    )


def test_start_preflight_without_config_uses_legacy_single_round(monkeypatch):
    monkeypatch.setattr(ui_record.ui_recording_session, "get_session_state", lambda _sid, _text="": _fake_session_state([]))
    monkeypatch.setattr(ui_record.ui_recording_session, "get_session_storage_state", _fake_async({}))
    monkeypatch.setattr(ui_record, "get_recording_config", lambda _db, _pid: None)
    monkeypatch.setattr(ui_record, "serialize_recording_config", lambda _db, _pid: {"config": None})
    launched = {"verification": 0, "legacy": 0}
    monkeypatch.setattr(ui_record, "launch_verification", lambda *_args, **_kwargs: launched.__setitem__("verification", 1))
    monkeypatch.setattr(ui_record, "launch_legacy_preflight", lambda *_args, **_kwargs: launched.__setitem__("legacy", 1))
    row = _fake_preflight_row()
    monkeypatch.setattr(ui_record, "create_preflight", lambda *_args, **_kwargs: row)
    monkeypatch.setattr(ui_record, "serialize_preflight", lambda r: {"report": json.loads(r.report_json or "{}")})

    result = asyncio.run(ui_record.start_ui_record_preflight("session", payload={}, db=_FakeDb(), current_user=SimpleNamespace()))

    assert result["report"]["verification_mode"] == "legacy"
    assert result["report"]["required_rounds"] == 1
    assert launched == {"verification": 0, "legacy": 1}


def test_start_preflight_with_config_uses_verified_two_rounds(monkeypatch):
    monkeypatch.setattr(ui_record.ui_recording_session, "get_session_state", lambda _sid, _text="": _fake_session_state([]))
    monkeypatch.setattr(ui_record.ui_recording_session, "get_session_storage_state", _fake_async({}))
    monkeypatch.setattr(ui_record, "get_recording_config", lambda _db, _pid: SimpleNamespace(reset_script_key="reset", reset_env_id=1))
    monkeypatch.setattr(ui_record, "serialize_recording_config", lambda _db, _pid: {"config": {"reset_script_key": "reset"}})
    launched = {"verification": 0, "legacy": 0}
    monkeypatch.setattr(ui_record, "launch_verification", lambda *_args, **_kwargs: launched.__setitem__("verification", 1))
    monkeypatch.setattr(ui_record, "launch_legacy_preflight", lambda *_args, **_kwargs: launched.__setitem__("legacy", 1))
    row = _fake_preflight_row()
    monkeypatch.setattr(ui_record, "create_preflight", lambda *_args, **_kwargs: row)
    monkeypatch.setattr(ui_record, "serialize_preflight", lambda r: {"report": json.loads(r.report_json or "{}")})

    result = asyncio.run(ui_record.start_ui_record_preflight("session", payload={}, db=_FakeDb(), current_user=SimpleNamespace()))

    assert result["report"]["verification_mode"] == "verified"
    assert result["report"]["required_rounds"] == 2
    assert result["report"]["config"] == {"reset_script_key": "reset"}
    assert launched == {"verification": 1, "legacy": 0}


def test_repick_requires_matching_failed_step(monkeypatch):
    row = _fake_preflight_row(status="repair_required", report={"repair": {"failed_step_index": 2}})
    db = _FakeDb(preflight=row)
    monkeypatch.setattr(ui_record, "request_repick", lambda *_args: {"ok": True})

    with pytest.raises(HTTPException, match="只能重新选择当前失败步骤"):
        ui_record.start_ui_record_repick("run", 4, db=db, current_user=SimpleNamespace())


def test_repick_delegates_when_step_matches(monkeypatch):
    row = _fake_preflight_row(status="repair_required", report={"repair": {"failed_step_index": 3}})
    db = _FakeDb(preflight=row)
    calls = {}
    monkeypatch.setattr(ui_record, "request_repick", lambda run_id, index: calls.update({"run_id": run_id, "index": index}) or {"ok": True})
    monkeypatch.setattr(ui_record, "serialize_preflight", lambda r: {"status": r.status})

    result = ui_record.start_ui_record_repick("run", 3, db=db, current_user=SimpleNamespace())

    assert calls == {"run_id": "run", "index": 3}
    assert result["status"] == "repair_required"


def test_case_is_active_only_after_two_frozen_rounds(monkeypatch):
    from app.services.ui_recording_preflight import steps_snapshot_hash

    steps = [{"action": "goto", "value": "https://example.test"}, {"action": "click", "locator": "#save"}]
    report = {
        "verification_mode": "verified",
        "verified_rounds": 2,
        "rounds": [{"round_no": 1, "status": "passed", "frozen": False}, {"round_no": 2, "status": "passed", "frozen": True}],
        "steps_snapshot_hash": steps_snapshot_hash(steps),
    }
    row = _fake_preflight_row(status="passed", report=report, steps=steps)
    monkeypatch.setattr(ui_record.ui_recording_session, "get_session_state", lambda _sid, _text="": _fake_session_state(steps))
    monkeypatch.setattr(ui_record.ui_recording_session, "get_session_storage_state", _fake_async({}))
    monkeypatch.setattr(ui_record.ui_recording_session, "close_session", _fake_async(None))
    monkeypatch.setattr(ui_record, "save_test_account_binding", lambda *_args: None)
    monkeypatch.setattr(ui_record, "serialize", lambda case: {"id": getattr(case, "id", 0), "status": case.status})

    result = asyncio.run(ui_record.save_ui_record_session(
        "session",
        payload={"preflight_run_id": "run"},
        db=_FakeDb(preflight=row),
        current_user=SimpleNamespace(),
    ))

    assert result["case"]["status"] == "active"


def test_legacy_single_preflight_can_only_save_draft(monkeypatch):
    steps = [{"action": "goto", "value": "https://example.test"}, {"action": "click", "locator": "#save"}]
    report = {"verification_mode": "legacy", "required_rounds": 1, "verified_rounds": 1}
    row = _fake_preflight_row(status="passed", report=report, steps=steps)
    monkeypatch.setattr(ui_record.ui_recording_session, "get_session_state", lambda _sid, _text="": _fake_session_state(steps))
    monkeypatch.setattr(ui_record.ui_recording_session, "get_session_storage_state", _fake_async({}))
    monkeypatch.setattr(ui_record.ui_recording_session, "close_session", _fake_async(None))
    monkeypatch.setattr(ui_record, "save_test_account_binding", lambda *_args: None)
    monkeypatch.setattr(ui_record, "serialize", lambda case: {"id": getattr(case, "id", 0), "status": case.status})

    result = asyncio.run(ui_record.save_ui_record_session(
        "session",
        payload={"preflight_run_id": "run"},
        db=_FakeDb(preflight=row),
        current_user=SimpleNamespace(),
    ))

    assert result["case"]["status"] == "draft"
