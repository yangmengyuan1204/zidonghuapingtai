import pytest
from app.services.ui_recording_session import _sanitize_event, build_ui_steps, _event_to_step
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


