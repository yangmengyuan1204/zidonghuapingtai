import pytest
from app.services.ui_recording_session import (
    _Session,
    _append_event,
    _event_to_step,
    _sanitize_event,
    _source_frame_chain,
    build_ui_steps,
)
from app.executors.runtime import _active_page


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


