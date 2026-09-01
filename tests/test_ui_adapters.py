from types import SimpleNamespace

import pytest

from app.executors.ui_adapters import UiAdapterError, execute_adapted_action
from app.executors.ui_effects_runtime import (
    begin_network_effect_observation,
    effect_already_satisfied,
    wait_for_effect_profile,
)


class _Target:
    def __init__(self):
        self.clicked = False
        self.value = ""
        self.checked = False

    def click(self, timeout=0, **_kwargs):
        self.clicked = True

    def fill(self, value, timeout=0):
        self.value = value

    def select_option(self, value, timeout=0):
        self.value = value

    def check(self, timeout=0):
        self.checked = True

    def uncheck(self, timeout=0):
        self.checked = False

    def is_visible(self, timeout=0):
        return True

    def is_enabled(self):
        return True

    def input_value(self, timeout=0):
        return self.value

    def is_checked(self, timeout=0):
        return self.checked


class _Options:
    def __init__(self, page, values):
        self._page = page
        self._values = list(values)

    def count(self):
        return len(self._values)

    def click(self, timeout=0):
        if len(self._values) != 1:
            raise RuntimeError("ambiguous option")
        self._page.clicked_option = self._values[0]


class _Popup:
    def __init__(self, page, options):
        self._page = page
        self._options = options

    def count(self):
        return 1

    def locator(self, selector):
        expected = selector.rsplit('"', 2)[1] if ':text-is(' in selector else ""
        return _Options(self._page, [value for value in self._options if value == expected])


class _Popups:
    def __init__(self, page, popup_count):
        self._page = page
        self._popup_count = popup_count

    def count(self):
        return self._popup_count

    def locator(self, selector):
        return _Popup(self._page, self._page.options).locator(selector)


class _FakePage:
    def __init__(self, *, popup_count=1, options=("上海",)):
        self.popup_count = popup_count
        self.options = options
        self.clicked_option = ""
        self.dialog_visible = True
        self.url = "https://example.test/orders"
        self.target = _Target()

    def locator(self, selector):
        if "listbox" in selector or "select-dropdown" in selector or "ant-select-dropdown" in selector:
            return _Popups(self, self.popup_count)
        if "dialog" in selector or "modal" in selector:
            return _VisibleLocator(self.dialog_visible)
        return self.target

    def wait_for_timeout(self, _milliseconds):
        return None


class _VisibleLocator:
    def __init__(self, visible):
        self.visible = visible

    def count(self):
        return int(self.visible)

    def is_visible(self, timeout=0):
        return self.visible


@pytest.fixture
def fake_page():
    return _FakePage()


@pytest.fixture
def resolved(fake_page):
    return SimpleNamespace(target=fake_page.target, used_locator="#city", matched_count=1)


def test_element_plus_select_uses_visible_listbox_option(fake_page, resolved):
    detail = execute_adapted_action(fake_page, resolved, {
        "action": "select", "value": "上海", "target_profile": {"element": {"framework": "element_plus"}},
    }, 1000)

    assert detail["adapter"] == "element_plus_select"
    assert fake_page.clicked_option == "上海"


def test_element_plus_select_rejects_multiple_visible_popups(resolved):
    page = _FakePage(popup_count=2)
    resolved.target = page.target

    with pytest.raises(UiAdapterError, match="popup.*不唯一"):
        execute_adapted_action(page, resolved, {
            "action": "select", "value": "上海", "target_profile": {"element": {"framework": "element_plus"}},
        }, 1000)


def test_effect_precheck_prevents_duplicate_submit(fake_page):
    step = {"action": "click", "effect_profile": {"effects": [{"type": "dialog_hidden", "name": "提交订单"}]}}
    fake_page.dialog_visible = False

    assert effect_already_satisfied(fake_page, step) is True


def test_wait_for_effect_profile_uses_single_deadline(fake_page):
    step = {"effect_profile": {"required": True, "effects": [{"type": "dialog_hidden", "name": "提交订单"}]}}
    fake_page.dialog_visible = False

    assert wait_for_effect_profile(fake_page, step, 1000)["satisfied"] is True


def test_dangerous_click_without_observed_effect_fails_closed():
    step = {
        "action": "click",
        "name": "确认支付",
        "effect_profile": {"required": False, "effects": []},
    }

    with pytest.raises(TimeoutError, match="危险操作缺少可验证结果"):
        wait_for_effect_profile(_FakePage(), step, 100)


def test_target_value_effect_reuses_resolved_iframe_target():
    top_level_target = _Target()
    iframe_target = _Target()
    iframe_target.value = "上海"
    page = _FakePage()
    page.target = top_level_target
    resolved = SimpleNamespace(target=iframe_target, used_locator="#city")
    step = {
        "action": "select",
        "locator": "#city",
        "effect_profile": {
            "required": True,
            "effects": [{"type": "target_value", "expected": "上海"}],
        },
    }

    assert wait_for_effect_profile(page, step, 100, resolved=resolved)["satisfied"] is True


def test_target_value_effect_with_explicit_locator_still_reuses_resolved_iframe_target():
    top_level_target = _Target()
    iframe_target = _Target()
    iframe_target.value = "上海"
    page = _FakePage()
    page.target = top_level_target
    resolved = SimpleNamespace(target=iframe_target, used_locator="#city")
    step = {
        "action": "select",
        "locator": "#city",
        "effect_profile": {
            "required": True,
            "effects": [{"type": "target_value", "locator": "#city", "expected": "上海"}],
        },
    }

    assert wait_for_effect_profile(page, step, 100, resolved=resolved)["satisfied"] is True


def test_explicit_effect_locator_uses_recorded_iframe_scope():
    top_level_status = _Target()
    iframe_action = _Target()
    iframe_status = _Target()
    iframe_status.value = "已保存"

    class _FrameScope:
        def locator(self, selector):
            assert selector == "#status"
            return iframe_status

    class _IframeLocator:
        def count(self):
            return 1

    class _IframePage(_FakePage):
        def locator(self, selector):
            if selector == 'iframe[name="editor"]':
                return _IframeLocator()
            if selector == "#status":
                return top_level_status
            return super().locator(selector)

        def frame_locator(self, selector):
            assert selector == 'iframe[name="editor"]'
            return _FrameScope()

    page = _IframePage()
    resolved = SimpleNamespace(target=iframe_action, used_locator="#save")
    step = {
        "action": "click",
        "locator": "#save",
        "target_profile": {"frame_chain": [{"name": "editor"}]},
        "effect_profile": {
            "required": True,
            "effects": [{"type": "target_value", "locator": "#status", "expected": "已保存"}],
        },
    }

    assert wait_for_effect_profile(page, step, 0, resolved=resolved)["satisfied"] is True


def test_sensitive_target_value_effect_never_returns_or_raises_actual_secret():
    secret = "otp-987654"
    page = _FakePage()
    page.target.value = secret
    step = {
        "action": "input",
        "locator": "input[name='otp']",
        "sensitive": True,
        "effect_profile": {
            "required": True,
            "effects": [{"type": "target_value", "expected": secret}],
        },
    }

    detail = wait_for_effect_profile(page, step, 100)
    assert secret not in repr(detail)

    page.target.value = "wrong-secret"
    with pytest.raises(TimeoutError) as exc_info:
        wait_for_effect_profile(page, step, 0)
    assert secret not in str(exc_info.value)
    assert "wrong-secret" not in str(exc_info.value)


def test_network_effect_observation_records_responses_before_wait():
    class _Request:
        method = "POST"

    class _Response:
        url = "https://example.test/api/orders"
        status = 201
        ok = True
        request = _Request()

    class _Page:
        def on(self, event, callback):
            assert event == "response"
            self.callback = callback

        def wait_for_timeout(self, _milliseconds):
            return None

    page = _Page()
    begin_network_effect_observation(page)
    page.callback(_Response())

    detail = wait_for_effect_profile(page, {
        "effect_profile": {"effects": [{
            "type": "network_result",
            "expected": {"url": "https://example.test/api/orders", "status": 201, "method": "POST"},
        }]},
    }, 100)

    assert detail["satisfied"] is True

def test_network_window_reset_discards_stale_records():
    class _Page:
        def __init__(self):
            self._ui_network_results = [
                {"url": "https://example.test/stale", "status": 200, "ok": True, "method": "GET"},
            ]
            self._ui_network_observer_registered = True

        def on(self, _event, _callback):
            raise AssertionError("should not re-register observer")

        def wait_for_timeout(self, _milliseconds):
            return None

    page = _Page()
    begin_network_effect_observation(page, reset=True)

    assert page._ui_network_results == []


def test_retry_round_preserves_network_records():
    class _Page:
        def __init__(self):
            self._ui_network_results = [
                {"url": "https://example.test/api/orders", "status": 201, "ok": True, "method": "POST"},
            ]
            self._ui_network_observer_registered = True

        def on(self, _event, _callback):
            raise AssertionError("should not re-register observer")

        def wait_for_timeout(self, _milliseconds):
            return None

    page = _Page()
    begin_network_effect_observation(page, reset=False)

    assert len(page._ui_network_results) == 1


def test_network_wait_rejects_stale_records_after_window_reset():
    class _Page:
        def __init__(self):
            self._ui_network_results = [
                {"url": "https://example.test/api/orders", "status": 201, "ok": True, "method": "POST"},
            ]
            self._ui_network_observer_registered = True

        def on(self, _event, _callback):
            raise AssertionError("should not re-register observer")

        def wait_for_timeout(self, _milliseconds):
            return None

    page = _Page()
    begin_network_effect_observation(page, reset=True)

    with pytest.raises(TimeoutError):
        wait_for_effect_profile(page, {
            "effect_profile": {"effects": [{
                "type": "network_result",
                "expected": {"url": "https://example.test/api/orders", "status": 201, "method": "POST"},
            }]},
        }, 100)
