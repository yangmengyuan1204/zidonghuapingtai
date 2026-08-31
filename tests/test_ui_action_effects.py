from app.services.ui_action_effects import build_retry_policy, infer_effect_profile, sanitize_page_state


def test_infer_effect_profile_detects_dialog_and_url_change():
    profile = infer_effect_profile(
        {
            "before_state": {"url": "https://x.test/orders", "dialogs": []},
            "after_state": {"url": "https://x.test/orders/1", "dialogs": ["订单详情"]},
        }
    )

    assert {item["type"] for item in profile["effects"]} == {"url_change", "dialog_visible"}
    assert profile["required"] is True


def test_input_effect_requires_value_change():
    profile = infer_effect_profile(
        {
            "action": "input",
            "value": "张三",
            "before_state": {"target": {"value": ""}},
            "after_state": {"target": {"value": "张三"}},
        }
    )

    assert profile["effects"] == [{"type": "target_value", "expected": "张三"}]


def test_delete_submit_and_payment_are_not_automatically_retried():
    for text in ("删除", "提交", "提交订单", "确认支付"):
        policy = build_retry_policy({"action": "click", "name": text})
        assert policy == {"safe_retry": False, "max_attempts": 1, "reason": "dangerous_action"}


def test_dangerous_stable_attribute_blocks_retry_even_with_observed_effect():
    policy = build_retry_policy(
        {
            "action": "click",
            "effect_profile": {"required": True, "effects": [{"type": "url_change"}]},
            "target_profile": {
                "element": {
                    "stable_attrs": {"name": "删除"},
                }
            },
        }
    )

    assert policy == {"safe_retry": False, "max_attempts": 1, "reason": "dangerous_action"}


def test_plain_click_without_observed_effect_is_optional_and_low_confidence():
    profile = infer_effect_profile({"action": "click", "before_state": {}, "after_state": {}})

    assert profile == {"schema_version": 1, "effects": [], "required": False, "confidence": 20}


def test_sensitive_input_effect_never_contains_recorded_secret():
    profile = infer_effect_profile(
        {
            "action": "input",
            "input_type": "password",
            "value": "{{password}}",
            "before_state": {"target": {"value": ""}},
            "after_state": {"target": {"value": "do-not-store-me"}},
        }
    )

    assert profile["effects"] == [{"type": "target_value", "expected": "{{password}}"}]
    assert "do-not-store-me" not in str(profile)


def test_sensitive_input_uses_non_secret_value_presence_change():
    profile = infer_effect_profile(
        {
            "action": "input",
            "input_type": "password",
            "value": "{{password}}",
            "sensitive": True,
            "before_state": {"target": {"value": "***", "has_value": False}},
            "after_state": {"target": {"value": "***", "has_value": True}},
        }
    )

    assert profile["effects"] == [{"type": "target_value", "expected": "{{password}}"}]


def test_page_state_url_preserves_spa_fragment_but_removes_tokens():
    state = sanitize_page_state(
        {"url": "https://x.test/#/orders?token=do-not-store&tab=all"}
    )

    assert state["url"] == "https://x.test/#/orders?tab=all"
    assert "do-not-store" not in str(state)
