from types import SimpleNamespace

import pytest

from app.executors.locators import _impl__resolve_locator
from app.services.ui_locator_engine import (
    build_locator_profile,
    ordered_locator_values,
    select_step_page,
    select_step_scope,
)


def test_build_locator_profile_prefers_stable_semantic_candidate_over_dynamic_id():
    profile = build_locator_profile(
        {
            "tag": "button",
            "role": "button",
            "text": "提交订单",
            "id": "button_1723456789012",
            "locator": "#button_1723456789012",
            "locator_candidates": [
                {"value": "#button_1723456789012", "strategy": "id", "count": 1, "visible": True},
                {"value": 'button:has-text("提交订单")', "strategy": "role_text", "count": 1, "visible": True},
            ],
        }
    )

    assert profile["schema_version"] == 2
    assert profile["quality"] == "stable"
    assert profile["candidates"][0]["value"] == 'button:has-text("提交订单")'
    assert profile["candidates"][-1]["dynamic"] is True


def test_unverified_text_candidate_is_risky_and_explains_score():
    profile = build_locator_profile(
        {
            "locator_candidates": [
                {"value": 'button:has-text("保存")', "strategy": "role_text", "count": None, "visible": None},
            ]
        }
    )

    assert profile["quality"] == "risk"
    assert "未验证唯一性" in profile["candidates"][0]["reasons"]


def test_ordered_locator_values_keeps_legacy_fields_and_profile_candidates_unique():
    step = {
        "locator": "#primary",
        "fallback_locators": ["#fallback", "#primary"],
        "locator_profile": {
            "candidates": [
                {"value": "#semantic", "score": 95},
                {"value": "#fallback", "score": 70},
            ]
        },
    }

    assert ordered_locator_values(step) == ["#primary", "#semantic", "#fallback"]


class _FakeLocator:
    def __init__(self, count, visible=True):
        self._count = count
        self.visible = visible

    def wait_for(self, state, timeout):
        if not self.visible:
            raise TimeoutError("hidden")

    def count(self):
        return self._count


class _FakePage:
    def __init__(self, mapping):
        self.mapping = mapping

    def locator(self, value):
        count, visible = self.mapping.get(value, (0, False))
        return _FakeLocator(count, visible)


def test_resolve_locator_rejects_ambiguous_candidate_instead_of_clicking_first():
    page = _FakePage({"text=提交": (2, True), "#unique": (1, True)})

    target, used, count = _impl__resolve_locator(page, ["text=提交", "#unique"], 500)

    assert isinstance(target, _FakeLocator)
    assert used == "#unique"
    assert count == 1


def test_resolve_locator_fails_safely_when_every_candidate_is_ambiguous():
    page = _FakePage({"text=提交": (2, True)})

    with pytest.raises(TimeoutError, match="匹配到 2 个元素"):
        _impl__resolve_locator(page, ["text=提交"], 500)


def test_resolve_locator_waits_for_delayed_unique_candidate():
    class DelayedLocator(_FakeLocator):
        def wait_for(self, state, timeout):
            self._count = 1

    class DelayedPage:
        def locator(self, _value):
            return DelayedLocator(0, True)

    target, used, count = _impl__resolve_locator(DelayedPage(), ["#late"], 500)

    assert isinstance(target, DelayedLocator)
    assert used == "#late"
    assert count == 1


def test_step_context_selects_recorded_tab_and_iframe_scope():
    frame_scope = object()

    class ContextPage:
        def __init__(self):
            self.context = None
            self.seen_selector = ""

        def frame_locator(self, selector):
            self.seen_selector = selector
            return frame_scope

    first = ContextPage()
    second = ContextPage()
    context = SimpleNamespace(pages=[first, second])
    first.context = context
    second.context = context
    step = {
        "page_index": 1,
        "frame_path": [{"selector": 'iframe[name="checkout"]'}],
    }

    selected = select_step_page(first, step)
    scope = select_step_scope(selected, step)

    assert selected is second
    assert scope is frame_scope
    assert second.seen_selector == 'iframe[name="checkout"]'


def test_missing_recorded_tab_fails_safely_instead_of_falling_back_to_main_page():
    page = SimpleNamespace(context=SimpleNamespace(pages=[]), wait_for_timeout=lambda _ms: None)

    with pytest.raises(ValueError, match="标签页"):
        select_step_page(page, {"page_index": 1}, timeout_ms=0)


def test_step_page_prefers_target_profile_identity_to_legacy_page_index():
    class ContextPage:
        def __init__(self, title):
            self.context = None
            self._title = title

        def title(self):
            return self._title

    first = ContextPage("主页")
    popup = ContextPage("支付结果")
    context = SimpleNamespace(pages=[first, popup])
    first.context = popup.context = context

    selected = select_step_page(
        first,
        {"page_index": 0, "target_profile": {"page": {"title": "支付结果"}}},
        timeout_ms=0,
    )

    assert selected is popup
