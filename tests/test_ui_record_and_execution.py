import pytest
from types import SimpleNamespace
from app.services.ui_recording_session import (
    _Session,
    _append_event,
    _event_to_step,
    _sanitize_event,
    _source_frame_chain,
    build_ui_steps,
)
from app.executors.runtime import _active_page
from app.executors import runtime
from app.executors import actions
from app.executors import UiStepExecutionError


def test_sanitize_event_preserves_values_and_sets_default_value():
    event = {
        "action": "input",
        "locator": "input[name='username']",
        "value": "12345678990",
        "input_type": "text",
        "text": "账号",
    }
    sanitized = _sanitize_event(event, 1)
    assert sanitized is not None
    assert sanitized["value"] == "{{username}}"
    assert sanitized["default_value"] == "12345678990"
    assert sanitized["raw_value"] == "12345678990"

    # Step conversion retains default_value
    step = _event_to_step(sanitized)
    assert step is not None
    assert step["value"] == "{{username}}"
    assert step["default_value"] == "12345678990"


def test_sanitize_event_does_not_strip_ordinary_phone():
    event = {
        "action": "input",
        "locator": "input[name='recipient_phone']",
        "value": "13800138000",
        "input_type": "text",
        "text": "收货人号码",
    }
    sanitized = _sanitize_event(event, 2)
    assert sanitized["value"] == "13800138000"


def test_sanitize_event_preserves_legacy_input_effect_without_state_payload():
    sanitized = _sanitize_event(
        {
            "action": "input",
            "locator": "#email",
            "value": "demo@example.test",
        },
        3,
    )

    assert sanitized is not None
    assert "before_state" not in sanitized
    assert "after_state" not in sanitized
    step = _event_to_step(sanitized)
    assert step is not None
    assert step["effect_profile"]["effects"] == [
        {"type": "target_value", "expected": "demo@example.test"}
    ]


def test_build_ui_steps_preserves_legacy_input_effect_without_state_payload():
    event = _sanitize_event(
        {
            "action": "input",
            "locator": "#email",
            "value": "demo@example.test",
        },
        4,
    )

    steps = build_ui_steps("https://example.test", events=[event])

    assert steps[1]["effect_profile"]["effects"] == [
        {"type": "target_value", "expected": "demo@example.test"}
    ]


def test_event_to_step_keeps_legacy_locator_profile_and_adds_target_profile():
    event = _sanitize_event(
        {
            "action": "click",
            "locator": '[data-testid="delete-order"]',
            "locator_candidates": [
                {"value": '[data-testid="delete-order"]', "strategy": "test_id", "count": 1, "visible": True},
            ],
            "url": "https://example.test/orders?ts=123",
            "page_title": "订单管理",
            "scope_chain": [{"kind": "table_row", "headers": {"订单号": "A100"}}],
            "tag": "button",
            "role": "button",
            "accessible_name": "删除",
            "stable_attrs": {"data-testid": "delete-order"},
            "capabilities": {"click": True},
            "recorded_match_count": 1,
        },
        3,
    )

    step = _event_to_step(event)

    assert step["locator_profile"]["schema_version"] == 2
    assert step["target_profile"]["schema_version"] == 1
    assert step["target_profile"]["scope_chain"][0]["headers"]["订单号"] == "A100"


def test_effect_observation_merges_into_action_without_creating_business_step():
    session = _Session(
        playwright=None,
        browser=None,
        context=None,
        page=None,
        project_id=1,
        case_name="效果合并",
        start_url="https://example.test/orders",
    )
    _append_event(
        session,
        {
            "action": "click",
            "locator": "#details",
            "interaction_id": "interaction-1",
            "before_state": {"url": "https://example.test/orders", "dialogs": []},
        },
    )
    _append_event(
        session,
        {
            "action": "effect_observation",
            "interaction_id": "interaction-1",
            "after_state": {"url": "https://example.test/orders/1", "dialogs": ["订单详情"]},
            "final": True,
        },
    )

    assert len(session.events) == 1
    assert session.events[0]["after_state"]["url"] == "https://example.test/orders/1"
    steps = build_ui_steps(session.start_url, session.current_url, session.events)
    assert [step["action"] for step in steps].count("click") == 1
    assert {item["type"] for item in steps[1]["effect_profile"]["effects"]} == {
        "url_change",
        "dialog_visible",
    }
    assert steps[1]["retry_policy"]["max_attempts"] == 2


def test_sanitize_event_redacts_sensitive_page_state_values():
    event = _sanitize_event(
        {
            "action": "input",
            "locator": "#password",
            "input_type": "password",
            "value": "secret-value",
            "interaction_id": "interaction-secret",
            "url": "https://example.test/reset?token=url-secret",
            "before_state": {"target": {"value": "old-secret"}},
            "after_state": {"target": {"value": "secret-value"}},
        },
        4,
    )

    assert event["interaction_id"] == "interaction-secret"
    assert event["before_state"]["target"]["value"] == "***"
    assert event["after_state"]["target"]["value"] == "***"
    assert "secret-value" not in str(event["before_state"])
    assert "secret-value" not in str(event["after_state"])
    assert "secret-value" not in str(event)
    assert "url-secret" not in str(event)


def test_sanitize_event_redacts_explicit_sensitive_named_input_value_everywhere():
    event = _sanitize_event(
        {
            "action": "input",
            "name": "password",
            "sensitive": True,
            "value": "secret",
            "before_state": {"target": {"value": "old-secret"}},
            "after_state": {"target": {"value": "secret"}},
        },
        5,
    )

    assert event is not None
    assert "secret" not in str(event)
    assert event["sensitive"] is True


def test_source_frame_chain_keeps_nested_cross_origin_frame_context():
    class FakeFrame:
        def __init__(self, name, url, parent_frame=None):
            self.name = name
            self.url = url
            self.parent_frame = parent_frame

    main = FakeFrame("", "https://example.test")
    outer = FakeFrame("payment", "https://pay.test/outer", main)
    inner = FakeFrame("challenge", "https://bank.test/challenge", outer)

    assert _source_frame_chain(inner, main) == [
        {"name": "payment", "url": "https://pay.test/outer", "selector": ""},
        {"name": "challenge", "url": "https://bank.test/challenge", "selector": ""},
    ]


def test_build_ui_steps_cleans_dynamic_query_assert_url():
    events = [
        {"action": "click", "locator": "button#submit", "url": "https://example.com/step1"},
        {"action": "url_change", "value": "https://example.com/ProductDetails?goods_id=787606985812&source=kw"},
    ]
    steps = build_ui_steps("https://example.com/home", "https://example.com/ProductDetails?goods_id=787606985812&source=kw", events)
    assert len(steps) >= 2
    assert_step = steps[-1]
    assert assert_step["action"] == "assert_url"
    assert assert_step["value"] == "https://example.com/ProductDetails"


def test_extract_text_with_regex():
    from unittest.mock import MagicMock
    from app.executors.actions import _run_ui_step

    mock_target = MagicMock()
    mock_target.inner_text.return_value = "注文番号： RO26082725460831"
    mock_target.count.return_value = 1

    mock_page = MagicMock()
    mock_page.locator.return_value = mock_target

    step = {
        "action": "extract_text",
        "locator": "span:has-text('注文番号')",
        "variable_name": "order_sn",
        "regex": r"RO\d+",
    }
    detail = _run_ui_step(mock_page, step, [], 10)
    assert detail["status"] == "passed"
    assert detail["extracted"]["order_sn"] == "RO26082725460831"


def test_dangerous_action_timeout_is_not_retried(monkeypatch):
    calls = []
    page = type("Page", (), {"url": "https://example.test/orders", "wait_for_timeout": lambda *_args: None})()
    resolved = SimpleNamespace(
        target=object(),
        used_locator="#submit",
        matched_count=1,
        score=100,
        reasons=("唯一目标",),
        page_identity={"url": page.url, "title": ""},
    )
    step = {
        "action": "click",
        "name": "提交订单",
        "target_profile": {"element": {"stable_attrs": {"id": "submit"}}},
        "effect_profile": {"required": True, "effects": [{"type": "dialog_hidden", "name": "提交订单"}]},
    }
    monkeypatch.setattr(actions, "resolve_target", lambda *_args, **_kwargs: resolved, raising=False)
    monkeypatch.setattr(actions, "execute_adapted_action", lambda *_args: calls.append(1) or {}, raising=False)
    monkeypatch.setattr(actions, "wait_for_effect_profile", lambda *_args: (_ for _ in ()).throw(TimeoutError("effect timed out")), raising=False)
    monkeypatch.setattr(actions, "effect_already_satisfied", lambda *_args: False, raising=False)
    monkeypatch.setattr(actions, "_capture_evidence_screenshot", lambda *_args: "", raising=False)
    monkeypatch.setattr(actions, "_page_text_excerpt", lambda *_args, **_kwargs: "", raising=False)

    actions._sync_compat_globals()
    with pytest.raises(UiStepExecutionError):
        actions._impl__run_ui_step(page, step, [], 5)

    assert len(calls) == 1


def test_retry_round_freezes_resolution_and_disables_ai_heal(monkeypatch):
    contexts = []
    page = type("Page", (), {
        "url": "https://example.test/orders",
        "set_default_timeout": lambda *_args: None,
        "wait_for_timeout": lambda *_args: None,
        "screenshot": lambda *_args, **_kwargs: None,
    })()
    case = SimpleNamespace(
        id=1,
        case_name="可安全重试的输入",
        timeout=1,
        page_url="",
        steps=[{"action": "input", "locator": "#name", "value": "张三"}],
    )
    step_error = UiStepExecutionError("首次执行失败", {"category": "timeout", "reason": "timeout"})

    runtime._sync_compat_globals()
    monkeypatch.setattr(runtime, "ensure_report_dirs", lambda: None)
    monkeypatch.setattr(runtime, "builtin_variables", lambda: {})
    monkeypatch.setattr(runtime, "parse_json_value", lambda value, _default: value)
    monkeypatch.setattr(runtime, "render_template", lambda value, _variables: value)
    monkeypatch.setattr(runtime, "_business_variables_from_text", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(runtime, "_merge_inferred_business_variables", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(runtime, "_page_text_excerpt", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(runtime, "_stabilize_runtime_steps", lambda steps, _variables: (steps, []))
    monkeypatch.setattr(runtime, "_validate_ui_steps_for_execution", lambda steps: (steps, []))
    monkeypatch.setattr(runtime, "_wait_page_stable", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_wait_after_action", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_quick_screenshot_check", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(runtime, "_url_looks_reasonable", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(runtime, "_final_business_verification", lambda *_args, **_kwargs: (True, [], {}))
    monkeypatch.setattr(runtime, "_json_dump_log", lambda *_args, **_kwargs: "log")
    monkeypatch.setattr(runtime, "write_allure_result", lambda *_args, **_kwargs: "report")

    def run_step(_page, _step, _shots, _timeout, **kwargs):
        contexts.append(kwargs["execution_context"])
        if len(contexts) == 1:
            raise step_error
        return {"status": "passed"}

    monkeypatch.setattr(runtime, "_run_ui_step", run_step)

    assert runtime._impl_execute_ui_case_in_page(
        case,
        page,
        execution_context={"retry_count": 1, "retry_interval_ms": 0},
    )[0] is True
    assert contexts[1]["freeze_resolution"] is True
    assert contexts[1]["disable_ai_heal"] is True
    assert contexts[1]["_retry_round"] is True

def test_target_profile_step_does_not_require_legacy_locator():
    actions._sync_compat_globals()

    _steps, issues = actions._impl__validate_ui_steps_for_execution([{
        "action": "click",
        "target_profile": {"element": {"stable_attrs": {"id": "submit"}}},
    }])

    assert not [item for item in issues if item["severity"] == "error"]


def test_dangerous_action_ignores_external_retry_policy(monkeypatch):
    calls = []
    page = type("Page", (), {
        "url": "https://example.test/orders",
        "set_default_timeout": lambda *_args: None,
        "wait_for_timeout": lambda *_args: None,
        "screenshot": lambda *_args, **_kwargs: None,
    })()
    case = SimpleNamespace(
        id=1,
        case_name="提交订单",
        timeout=1,
        page_url="",
        steps=[{
            "action": "click",
            "name": "提交订单",
            "locator": "#submit",
            "retry_policy": {"safe_retry": True, "max_attempts": 2},
        }],
    )
    step_error = UiStepExecutionError("执行失败", {"category": "timeout", "reason": "timeout"})

    runtime._sync_compat_globals()
    monkeypatch.setattr(runtime, "ensure_report_dirs", lambda: None)
    monkeypatch.setattr(runtime, "builtin_variables", lambda: {})
    monkeypatch.setattr(runtime, "parse_json_value", lambda value, _default: value)
    monkeypatch.setattr(runtime, "render_template", lambda value, _variables: value)
    monkeypatch.setattr(runtime, "_business_variables_from_text", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(runtime, "_merge_inferred_business_variables", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(runtime, "_page_text_excerpt", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(runtime, "_stabilize_runtime_steps", lambda steps, _variables: (steps, []))
    monkeypatch.setattr(runtime, "_validate_ui_steps_for_execution", lambda steps: (steps, []))
    monkeypatch.setattr(runtime, "_wait_page_stable", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_wait_after_action", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_json_dump_log", lambda *_args, **_kwargs: "log")
    monkeypatch.setattr(runtime, "write_allure_result", lambda *_args, **_kwargs: "report")

    def run_step(*_args, **_kwargs):
        calls.append(1)
        raise step_error

    monkeypatch.setattr(runtime, "_run_ui_step", run_step)

    assert runtime._impl_execute_ui_case_in_page(
        case,
        page,
        execution_context={"retry_count": 1, "retry_interval_ms": 0},
    )[0] is False
    assert len(calls) == 1



def test_semantic_branch_begins_network_window_before_precheck(monkeypatch):
    order = []
    page = type("Page", (), {"url": "https://example.test/orders", "wait_for_timeout": lambda *_args: None})()
    resolved = SimpleNamespace(
        target=object(),
        used_locator="#submit",
        matched_count=1,
        score=100,
        reasons=("唯一目标",),
        page_identity={"url": page.url, "title": ""},
    )
    step = {
        "action": "click",
        "name": "提交订单",
        "target_profile": {"element": {"stable_attrs": {"id": "submit"}}},
    }
    monkeypatch.setattr(actions, "resolve_target", lambda *_args, **_kwargs: resolved, raising=False)

    def fake_begin(_page, reset=True):
        order.append(("begin", reset))
        return []

    def fake_precheck(_page, _step):
        order.append(("precheck",))
        return True

    monkeypatch.setattr(actions, "begin_network_effect_observation", fake_begin, raising=False)
    monkeypatch.setattr(actions, "effect_already_satisfied", fake_precheck, raising=False)
    monkeypatch.setattr(actions, "_capture_evidence_screenshot", lambda *_args, **_kwargs: "", raising=False)
    monkeypatch.setattr(actions, "_page_text_excerpt", lambda *_args, **_kwargs: "", raising=False)

    actions._sync_compat_globals()
    detail = actions._impl__run_ui_step(page, step, [], 5)

    assert detail["effect_pre_satisfied"] is True
    assert [item[0] for item in order] == ["begin", "precheck"]
    assert order[0][1] is True


def test_retry_round_reset_false_preserves_network_window(monkeypatch):
    order = []
    page = type("Page", (), {"url": "https://example.test/orders", "wait_for_timeout": lambda *_args: None})()
    resolved = SimpleNamespace(
        target=object(),
        used_locator="#submit",
        matched_count=1,
        score=100,
        reasons=("唯一目标",),
        page_identity={"url": page.url, "title": ""},
    )
    step = {
        "action": "click",
        "name": "提交订单",
        "target_profile": {"element": {"stable_attrs": {"id": "submit"}}},
    }
    monkeypatch.setattr(actions, "resolve_target", lambda *_args, **_kwargs: resolved, raising=False)

    def fake_begin(_page, reset=True):
        order.append(("begin", reset))
        return []

    monkeypatch.setattr(actions, "begin_network_effect_observation", fake_begin, raising=False)
    monkeypatch.setattr(actions, "effect_already_satisfied", lambda *_args: True, raising=False)
    monkeypatch.setattr(actions, "_capture_evidence_screenshot", lambda *_args, **_kwargs: "", raising=False)
    monkeypatch.setattr(actions, "_page_text_excerpt", lambda *_args, **_kwargs: "", raising=False)

    actions._sync_compat_globals()
    actions._impl__run_ui_step(page, step, [], 5, execution_context={"_retry_round": True})

    assert order[0][1] is False
