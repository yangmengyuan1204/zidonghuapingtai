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
