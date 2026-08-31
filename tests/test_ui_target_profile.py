from app.services.ui_recording_capture import recording_init_script, repick_script
from app.services.ui_target_profile import build_target_profile


def test_target_profile_keeps_dialog_table_row_and_element_semantics():
    profile = build_target_profile({
        "url": "https://example.test/orders?ts=123",
        "page_title": "订单管理",
        "frame_chain": [],
        "scope_chain": [
            {"kind": "dialog", "role": "dialog", "name": "删除订单"},
            {"kind": "table_row", "headers": {"订单号": "A100"}},
        ],
        "tag": "button",
        "role": "button",
        "accessible_name": "删除",
        "stable_attrs": {"data-testid": "delete-order"},
        "capabilities": {"click": True, "input": False},
    })

    assert profile["page"]["url_pattern"] == "https://example.test/orders*"
    assert profile["page"]["title"] == "订单管理"
    assert profile["scope_chain"][1]["headers"]["订单号"] == "A100"
    assert profile["element"]["accessible_name"] == "删除"
    assert profile["quality"] == "stable"


def test_target_profile_marks_unscoped_repeated_text_as_risk():
    profile = build_target_profile({
        "tag": "button", "role": "button", "accessible_name": "删除",
        "recorded_match_count": 4, "scope_chain": [], "stable_attrs": {},
    })

    assert profile["quality"] == "risk"


def test_target_profile_does_not_treat_input_type_as_stable_identity():
    profile = build_target_profile({
        "tag": "input",
        "input_type": "text",
        "accessible_name": "收货人",
        "stable_attrs": {"type": "text"},
        "recorded_match_count": 1,
    })

    assert profile["quality"] == "weak"


def test_target_profile_does_not_copy_sensitive_input_values():
    profile = build_target_profile({
        "tag": "input",
        "input_type": "password",
        "value": "secret-value",
        "raw_value": "secret-value",
        "default_value": "secret-value",
        "sensitive": True,
        "neighbor_texts": ["密码", "secret-value"],
        "scope_chain": [{"kind": "form", "name": "secret-value"}],
        "stable_attrs": {"name": "password"},
        "capabilities": {"input": True},
    })

    assert "secret-value" not in str(profile)


def test_target_profile_redacts_unsignaled_contenteditable_input_value():
    profile = build_target_profile({
        "action": "input",
        "tag": "div",
        "value": "private-note",
        "raw_value": "private-note",
        "accessible_name": "private-note",
        "neighbor_texts": ["private-note"],
        "capabilities": {"input": True},
    })

    assert "private-note" not in str(profile)


def test_target_profile_redacts_short_sensitive_values_inside_semantic_text():
    profile = build_target_profile({
        "action": "input",
        "tag": "input",
        "value": "123",
        "raw_value": "123",
        "accessible_name": "PIN: 123",
        "neighbor_texts": ["输入 123"],
    })

    assert "123" not in str(profile)


def test_target_profile_falls_back_to_server_frame_path_when_capture_chain_is_empty():
    profile = build_target_profile({
        "url": "https://example.test/orders",
        "frame_chain": [],
        "frame_path": [{
            "name": "checkout",
            "url": "https://pay.test/frame?ts=123",
            "stable_attrs": {"title": "支付框架"},
        }],
        "tag": "button",
    })

    assert profile["frame_chain"][0]["name"] == "checkout"
    assert profile["frame_chain"][0]["url_pattern"] == "https://pay.test/frame*"
    assert profile["frame_chain"][0]["stable_attrs"]["title"] == "支付框架"


def test_target_profile_keeps_stable_spa_route_parts_in_url_pattern():
    query_profile = build_target_profile({"url": "https://example.test/?page=orders&ts=123"})
    hash_profile = build_target_profile({"url": "https://example.test/#/orders?ts=123"})

    assert query_profile["page"]["url_pattern"] == "https://example.test/*page=orders*"
    assert hash_profile["page"]["url_pattern"] == "https://example.test/#/orders*"


def test_target_profile_filters_sensitive_keys_from_query_url_pattern():
    profile = build_target_profile({
        "url": "https://example.test/orders?token=tok-123&status=paid&code=code-456",
    })

    assert profile["page"]["url_pattern"] == "https://example.test/orders*status=paid*"
    assert "tok-123" not in str(profile)
    assert "code-456" not in str(profile)


def test_target_profile_filters_sensitive_keys_from_fragment_query_url_pattern():
    profile = build_target_profile({
        "url": "https://example.test/#/orders?access_token=frag-token&tab=history&password=frag-pass",
    })

    assert profile["page"]["url_pattern"] == "https://example.test/#/orders*tab=history*"
    assert "frag-token" not in str(profile)
    assert "frag-pass" not in str(profile)


def test_target_profile_normalizes_sensitive_query_key_names_but_keeps_business_code():
    profile = build_target_profile({
        "url": (
            "https://example.test/orders?accessToken=access-value&access-token=hyphen-value"
            "&auth_token=auth-value&clientSecret=client-value&session_token=session-value"
            "&jwt=jwt-value&order_code=ORD-100"
        ),
    })

    assert profile["page"]["url_pattern"] == "https://example.test/orders*order_code=ORD-100*"
    for value in (
        "access-value",
        "hyphen-value",
        "auth-value",
        "client-value",
        "session-value",
        "jwt-value",
    ):
        assert value not in str(profile)


def test_target_profile_rejects_dynamic_aria_controls_as_stable_identity():
    profile = build_target_profile({
        "tag": "button",
        "accessible_name": "选择",
        "stable_attrs": {"aria-controls": "el-id-1234-5"},
        "recorded_match_count": 1,
    })

    assert "aria-controls" not in profile["element"]["stable_attrs"]
    assert profile["quality"] == "weak"


def test_recording_scripts_publish_semantic_capture_and_repick_contract():
    init_script = recording_init_script()
    pick_script = repick_script(7)

    assert "window.__uiRecorderCaptureTarget" in init_script
    assert "buildScopeChain" in init_script
    assert "neighbor_texts" in init_script
    assert "stable_class_tokens" in init_script
    assert "recorded_match_count" in init_script
    assert "semanticMatchCount" in init_script
    assert "url: window.location.href" in init_script
    assert "tag: info.tag" in init_script
    assert "id: !isDynamicId(id) ? id :" in init_script
    assert "step_index: 7" in pick_script
    assert "target_profile_source" in pick_script
    assert "__uiRecorderClickableElement" in pick_script
    assert "pointerover" in pick_script
    assert "ui-recorder-repick-banner" in pick_script
