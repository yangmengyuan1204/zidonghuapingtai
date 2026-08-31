from types import SimpleNamespace

import pytest

from app.services.ui_target_resolver import (
    TargetResolutionError,
    resolve_target,
    select_profile_page,
    select_profile_scope,
)


class _Locator:
    def __init__(self, count=0, *, visible=True, enabled=True, text="", box=True, children=None, obscured=False):
        self._count = count
        self._visible = visible
        self._enabled = enabled
        self._text = text
        self._box = box
        self._children = children or {}
        self._obscured = obscured

    def count(self):
        return self._count

    def wait_for(self, state="visible", timeout=0):
        if state == "visible" and not self._visible:
            raise TimeoutError("hidden")

    def is_visible(self):
        return self._visible

    def is_enabled(self):
        return self._enabled

    def bounding_box(self):
        return {"x": 0, "y": 0, "width": 10, "height": 10} if self._box else None

    def inner_text(self):
        return self._text

    def locator(self, value):
        return self._children.get(value, _Locator())

    def filter(self, **kwargs):
        return self

    def nth(self, _index):
        return self

    def evaluate(self, _script):
        return not self._obscured


class _Page:
    def __init__(self, mapping, *, frame_scopes=None, url="https://example.test/orders", title="Orders"):
        self.mapping = mapping
        self.frame_scopes = frame_scopes or {}
        self.url = url
        self._title = title
        self.context = SimpleNamespace(pages=[self])

    def title(self):
        return self._title

    def locator(self, value):
        return self.mapping.get(value, _Locator())

    def frame_locator(self, selector):
        return self.frame_scopes[selector]


def test_resolver_constrains_duplicate_delete_button_to_order_row():
    delete_in_a100 = _Locator(1)
    row = _Locator(1, text="订单号 A100 删除", children={'button:has-text("删除")': delete_in_a100})
    page = _Page({"tr": row, 'button:has-text("删除")': _Locator(2)})
    step = {
        "action": "click",
        "target_profile": {
            "page": {"url_pattern": "*/orders"},
            "frame_chain": [],
            "scope_chain": [{"kind": "table_row", "headers": {"订单号": "A100"}}],
            "element": {"role": "button", "accessible_name": "删除", "capabilities": {"click": True}},
        },
    }
    result = resolve_target(page, step, 1000)
    assert result.matched_count == 1
    assert result.reasons[-1] == "目标在订单号=A100的表格行中唯一匹配"


def test_resolver_rejects_close_scores_instead_of_clicking():
    page = _Page({'button:has-text("保存")': _Locator(1), '#save': _Locator(1)})
    step = {
        "action": "click",
        "target_profile": {
            "element": {"role": "button", "accessible_name": "保存", "stable_attrs": {"id": "save"}, "capabilities": {"click": True}}
        },
        "locator_profile": {"candidates": [{"value": 'button:has-text("保存")', "strategy": "role_text", "score": 90}, {"value": "#save", "strategy": "id", "score": 89}]},
    }
    with pytest.raises(TargetResolutionError, match="候选分差不足"):
        resolve_target(page, step, 1000)


def test_resolver_uses_page_identity_before_page_index():
    first = _Page({}, title="主页")
    second = _Page({}, title="支付结果")
    context = SimpleNamespace(pages=[first, second])
    first.context = second.context = context
    step = {"page_index": 0, "target_profile": {"page": {"title": "支付结果"}}}
    assert select_profile_page(first, step, 1000) is second


def test_resolver_requires_each_frame_chain_level_to_be_unique():
    inner_selector = "iframe[name=inner]"
    outer_scope = _Locator(children={inner_selector: _Locator(2)})
    page = _Page(
        {"iframe[name=outer]": _Locator(1)},
        frame_scopes={"iframe[name=outer]": outer_scope},
    )
    step = {"target_profile": {"frame_chain": [{"selector": "iframe[name=outer]"}, {"selector": "iframe[name=inner]"}]}}
    with pytest.raises(TargetResolutionError, match="iframe第2层匹配不唯一"):
        select_profile_scope(page, step, 1000)


def test_resolver_rejects_obscured_target_before_action():
    page = _Page({"#delete": _Locator(1, obscured=True)})
    step = {
        "action": "click",
        "target_profile": {"element": {"stable_attrs": {"id": "delete"}, "capabilities": {"click": True}}},
    }

    with pytest.raises(TargetResolutionError, match="被遮挡"):
        resolve_target(page, step, 1000)


def test_frozen_resolver_does_not_use_ai_or_new_memory_candidates():
    page = _Page({"#recorded": _Locator(0), "#ai": _Locator(1), "#memory": _Locator(1)})
    step = {
        "action": "click",
        "locator_profile": {"candidates": [{"value": "#recorded", "score": 90}]},
        "ai_locator_candidates": [{"value": "#ai", "score": 99}],
    }

    with pytest.raises(TargetResolutionError):
        resolve_target(page, step, 1000, memory=["#memory"], frozen=True)
