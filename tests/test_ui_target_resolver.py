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


class _TableRowsLocator(_Locator):
    def __init__(self, header_values, *, header_columns=None, children=None):
        super().__init__(1, children=children)
        self._header_values = header_values
        self._header_columns = header_columns or {name: index for index, name in enumerate(header_values, start=1)}

    def evaluate_all(self, _script, expected_headers):
        columns = {}
        for header in expected_headers:
            column = self._header_columns.get(header)
            if isinstance(column, list) or column is None:
                return [{"eligible": True, "mapping": "ambiguous", "matches": False, "columns": {}}]
            columns[header] = column
        return [{
            "eligible": True,
            "mapping": "mapped",
            "matches": all(self._header_values.get(header) == value for header, value in expected_headers.items()),
            "columns": columns,
        }]


class _FrameChangingLocator(_Locator):
    def __init__(self):
        super().__init__(1)
        self._after_render_frame = False

    def evaluate(self, script, *_args):
        if "requestAnimationFrame" in script:
            self._after_render_frame = True
            return True
        return super().evaluate(script)

    def bounding_box(self):
        x = 4 if self._after_render_frame else 0
        return {"x": x, "y": 0, "width": 10, "height": 10}


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
    row = _TableRowsLocator(
        {"订单号": "A100", "备注": "普通订单"},
        children={'button:has-text("删除")': delete_in_a100},
    )
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


def test_resolver_does_not_match_order_header_against_another_table_column():
    wrong_row = _TableRowsLocator(
        {"订单号": "A200", "备注": "A100"},
        children={'button:has-text("删除")': _Locator(1)},
    )
    page = _Page({"tr": wrong_row, 'button:has-text("删除")': _Locator(1)})
    step = {
        "action": "click",
        "target_profile": {
            "scope_chain": [{"kind": "table_row", "headers": {"订单号": "A100"}}],
            "element": {"role": "button", "accessible_name": "删除", "capabilities": {"click": True}},
        },
    }

    with pytest.raises(TargetResolutionError, match="范围第1层未匹配"):
        resolve_target(page, step, 1000)


def test_resolver_rejects_ambiguous_table_header_mapping():
    row = _TableRowsLocator(
        {"订单号": "A100"},
        header_columns={"订单号": [1, 2]},
        children={'button:has-text("删除")': _Locator(1)},
    )
    page = _Page({"tr": row})
    step = {
        "action": "click",
        "target_profile": {
            "scope_chain": [{"kind": "table_row", "headers": {"订单号": "A100"}}],
            "element": {"role": "button", "accessible_name": "删除", "capabilities": {"click": True}},
        },
    }

    with pytest.raises(TargetResolutionError, match="表头映射不唯一"):
        resolve_target(page, step, 1000)


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


def test_resolver_rejects_target_that_moves_between_render_frames():
    page = _Page({"#delete": _FrameChangingLocator()})
    step = {
        "action": "click",
        "target_profile": {"element": {"stable_attrs": {"id": "delete"}, "capabilities": {"click": True}}},
    }

    with pytest.raises(TargetResolutionError, match="布局不稳定"):
        resolve_target(page, step, 1000)


def test_resolver_rejects_target_when_stability_sampling_exceeds_deadline():
    page = _Page({"#delete": _Locator(1)})
    step = {
        "action": "click",
        "target_profile": {"element": {"stable_attrs": {"id": "delete"}, "capabilities": {"click": True}}},
    }

    with pytest.raises(TargetResolutionError, match="布局不稳定"):
        resolve_target(page, step, 0)


def test_resolver_applies_scope_chain_without_frame_chain():
    save_in_form = _Locator(1)
    form = _Locator(1, children={"#save": save_in_form})
    page = _Page({'form[id="checkout"]': form, "#save": _Locator(2)})
    step = {
        "action": "click",
        "target_profile": {
            "scope_chain": [{"kind": "form", "stable_attrs": {"id": "checkout"}}],
            "element": {"stable_attrs": {"id": "save"}, "capabilities": {"click": True}},
        },
    }

    assert resolve_target(page, step, 1000).target is save_in_form


def test_frozen_resolver_does_not_use_ai_or_new_memory_candidates():
    page = _Page({"#recorded": _Locator(0), "#ai": _Locator(1), "#memory": _Locator(1)})
    step = {
        "action": "click",
        "locator_profile": {"candidates": [{"value": "#recorded", "score": 90}]},
        "ai_locator_candidates": [{"value": "#ai", "score": 99}],
    }

    with pytest.raises(TargetResolutionError):
        resolve_target(page, step, 1000, memory=["#memory"], frozen=True)
