from __future__ import annotations

import json
from typing import Any


class UiAdapterError(ValueError):
    """声明的控件无法用唯一且可验证的方式操作时抛出。"""


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _framework(step: dict[str, Any]) -> str:
    profile = step.get("target_profile") if isinstance(step.get("target_profile"), dict) else {}
    element = profile.get("element") if isinstance(profile.get("element"), dict) else {}
    return _text(element.get("framework")).lower().replace("-", "_")


def _element(step: dict[str, Any]) -> dict[str, Any]:
    profile = step.get("target_profile") if isinstance(step.get("target_profile"), dict) else {}
    value = profile.get("element")
    return value if isinstance(value, dict) else {}


def _unique(locator: Any, description: str) -> Any:
    try:
        count = int(locator.count())
    except Exception as exc:
        raise UiAdapterError(f"无法读取{description}数量: {exc}") from exc
    if count != 1:
        suffix = "不唯一" if count > 1 else "未找到"
        raise UiAdapterError(f"{description}{suffix}（{count} 个）")
    return locator


def _click(target: Any, timeout_ms: int) -> None:
    target.click(timeout=timeout_ms)


def _fill(page: Any, target: Any, value: Any, timeout_ms: int) -> None:
    try:
        target.fill(str(value or ""), timeout=timeout_ms)
    except Exception:
        _click(target, timeout_ms)
        keyboard = getattr(page, "keyboard", None)
        if keyboard is None:
            raise
        keyboard.press("Control+A")
        keyboard.type(str(value or ""))


def _exact_option(popup: Any, selector: str, value: Any) -> Any:
    quoted = json.dumps(_text(value), ensure_ascii=False)
    return _unique(popup.locator(f"{selector}:text-is({quoted})"), "下拉选项")


class _Adapter:
    name = "generic"

    def matches(self, step: dict[str, Any]) -> bool:
        return False

    def execute(self, page: Any, target: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        raise NotImplementedError


class NativeInputAdapter(_Adapter):
    name = "native_input"

    def matches(self, step: dict[str, Any]) -> bool:
        return step.get("action") == "input" and _framework(step) in {"", "native"}

    def execute(self, page: Any, target: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        _fill(page, target, step.get("value"), timeout_ms)
        return {}


class NativeSelectAdapter(_Adapter):
    name = "native_select"

    def matches(self, step: dict[str, Any]) -> bool:
        return step.get("action") == "select" and _framework(step) in {"", "native"}

    def execute(self, page: Any, target: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        target.select_option(str(step.get("value") or ""), timeout=timeout_ms)
        return {}


class NativeCheckAdapter(_Adapter):
    name = "native_check"

    def matches(self, step: dict[str, Any]) -> bool:
        return step.get("action") in {"check", "uncheck"} and _framework(step) in {"", "native"}

    def execute(self, page: Any, target: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        if step.get("action") == "check":
            target.check(timeout=timeout_ms)
        else:
            target.uncheck(timeout=timeout_ms)
        return {}


class ElementPlusSelectAdapter(_Adapter):
    name = "element_plus_select"

    def matches(self, step: dict[str, Any]) -> bool:
        return step.get("action") == "select" and _framework(step) in {"element_plus", "elementplus"}

    def execute(self, page: Any, target: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        _click(target, timeout_ms)
        popup = _unique(page.locator(":is(.el-select-dropdown, [role=\"listbox\"]):visible"), "可见下拉 popup")
        _click(_exact_option(popup, ":is(.el-select-dropdown__item, [role=\"option\"]):visible", step.get("value")), timeout_ms)
        return {}


class ElementPlusDialogAdapter(_Adapter):
    name = "element_plus_dialog"

    def matches(self, step: dict[str, Any]) -> bool:
        return _framework(step) in {"element_plus", "elementplus"} and _text(_element(step).get("kind")).lower() in {"dialog", "drawer"}

    def execute(self, page: Any, target: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        return GenericClickAdapter().execute(page, target, step, timeout_ms)


class ElementPlusDateAdapter(_Adapter):
    name = "element_plus_date"

    def matches(self, step: dict[str, Any]) -> bool:
        kind = _text(_element(step).get("kind")).lower()
        return _framework(step) in {"element_plus", "elementplus"} and step.get("action") in {"input", "select"} and kind in {"date", "date_picker", "datepicker"}

    def execute(self, page: Any, target: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        _fill(page, target, step.get("value"), timeout_ms)
        return {}


class AntSelectAdapter(_Adapter):
    name = "ant_select"

    def matches(self, step: dict[str, Any]) -> bool:
        return step.get("action") == "select" and _framework(step) in {"ant", "antd", "ant_design"}

    def execute(self, page: Any, target: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        _click(target, timeout_ms)
        popup = _unique(page.locator(":is(.ant-select-dropdown, [role=\"listbox\"]):visible"), "可见下拉 popup")
        _click(_exact_option(popup, ":is(.ant-select-item-option, [role=\"option\"]):visible", step.get("value")), timeout_ms)
        return {}


class AntModalAdapter(_Adapter):
    name = "ant_modal"

    def matches(self, step: dict[str, Any]) -> bool:
        return _framework(step) in {"ant", "antd", "ant_design"} and _text(_element(step).get("kind")).lower() in {"dialog", "modal", "drawer"}

    def execute(self, page: Any, target: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        return GenericClickAdapter().execute(page, target, step, timeout_ms)


class AntDateAdapter(_Adapter):
    name = "ant_date"

    def matches(self, step: dict[str, Any]) -> bool:
        kind = _text(_element(step).get("kind")).lower()
        return _framework(step) in {"ant", "antd", "ant_design"} and step.get("action") in {"input", "select"} and kind in {"date", "date_picker", "datepicker"}

    def execute(self, page: Any, target: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        _fill(page, target, step.get("value"), timeout_ms)
        return {}


class GenericClickAdapter(_Adapter):
    name = "generic_click"

    def matches(self, step: dict[str, Any]) -> bool:
        return step.get("action") in {"click", "wait_for_selector", "assert_visible", "assert_value", "text_assert", "extract_text", "extract_value"}

    def execute(self, page: Any, target: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        action = str(step.get("action") or "")
        value = step.get("value")
        if action == "click":
            _click(target, timeout_ms)
        elif action == "wait_for_selector":
            target.wait_for(state="visible", timeout=timeout_ms)
        elif action == "assert_visible":
            if not target.is_visible(timeout=timeout_ms):
                raise AssertionError("assert_visible failed")
        elif action == "assert_value":
            if _text(target.input_value(timeout=timeout_ms)) != _text(value):
                raise AssertionError(f"assert_value failed: expected {value!r}")
        elif action == "text_assert":
            if _text(value) not in _text(target.inner_text(timeout=timeout_ms)):
                raise AssertionError(f"text_assert failed: expected {value!r}")
        elif action == "extract_text":
            return {"extracted_value": target.inner_text(timeout=timeout_ms)}
        elif action == "extract_value":
            return {"extracted_value": target.input_value(timeout=timeout_ms)}
        return {}


ADAPTERS = (
    NativeInputAdapter(),
    NativeSelectAdapter(),
    NativeCheckAdapter(),
    ElementPlusSelectAdapter(),
    ElementPlusDialogAdapter(),
    ElementPlusDateAdapter(),
    AntSelectAdapter(),
    AntModalAdapter(),
    AntDateAdapter(),
    GenericClickAdapter(),
)


def execute_adapted_action(page: Any, resolved: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    """根据录制控件语义选择交互方式，未声明的动作安全失败。"""
    for adapter in ADAPTERS:
        if adapter.matches(step):
            detail = adapter.execute(page, resolved.target, step, timeout_ms)
            return {"adapter": adapter.name, "used_locator": getattr(resolved, "used_locator", ""), **detail}
    raise UiAdapterError(f"没有适用于动作 {step.get('action')!r} 的控件适配器")
