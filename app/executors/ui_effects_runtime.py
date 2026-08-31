from __future__ import annotations

import json
import time
from typing import Any


class UiEffectTimeout(TimeoutError):
    """动作未在共享等待窗口内产生录制时观察到的结果。"""


def begin_network_effect_observation(page: Any) -> list[dict[str, Any]]:
    """在动作触发前记录响应摘要，供网络结果 effect 在同一轮中验证。"""
    records = getattr(page, "_ui_network_results", None)
    if not isinstance(records, list):
        records = []
        try:
            setattr(page, "_ui_network_results", records)
        except Exception:
            return records
    if getattr(page, "_ui_network_observer_registered", False):
        return records

    def record(response: Any) -> None:
        request = getattr(response, "request", None)
        item = {
            "url": getattr(response, "url", ""),
            "status": getattr(response, "status", ""),
            "ok": getattr(response, "ok", ""),
            "method": getattr(request, "method", ""),
        }
        records.append(item)
        if len(records) > 100:
            del records[:-100]

    try:
        page.on("response", record)
        setattr(page, "_ui_network_observer_registered", True)
    except Exception:
        pass
    return records


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _effects(step: dict[str, Any]) -> list[dict[str, Any]]:
    profile = step.get("effect_profile") if isinstance(step.get("effect_profile"), dict) else {}
    return [item for item in profile.get("effects", []) if isinstance(item, dict)]


def _profile_required(step: dict[str, Any]) -> bool:
    profile = step.get("effect_profile") if isinstance(step.get("effect_profile"), dict) else {}
    return bool(profile.get("required"))


def _count(locator: Any) -> int:
    try:
        return int(locator.count())
    except Exception:
        return 0


def _visible(locator: Any) -> bool:
    count = _count(locator)
    if count != 1:
        return False
    try:
        return bool(locator.is_visible())
    except Exception:
        return True


def _stable_selector(step: dict[str, Any]) -> str:
    locator = _text(step.get("locator"))
    if locator:
        return locator
    profile = step.get("target_profile") if isinstance(step.get("target_profile"), dict) else {}
    element = profile.get("element") if isinstance(profile.get("element"), dict) else {}
    attrs = element.get("stable_attrs") if isinstance(element.get("stable_attrs"), dict) else {}
    for key in ("data-testid", "data-test", "id", "name"):
        value = _text(attrs.get(key))
        if value:
            return f"#{json.dumps(value, ensure_ascii=False)[1:-1]}" if key == "id" else f'[{key}={json.dumps(value, ensure_ascii=False)}]'
    return ""


def _effect_locator(page: Any, step: dict[str, Any], effect: dict[str, Any], default: str = "") -> Any | None:
    selector = _text(effect.get("locator")) or _stable_selector(step) or default
    if not selector:
        return None
    try:
        return page.locator(selector)
    except Exception:
        return None


def _dialog_locator(page: Any, name: Any) -> Any | None:
    selector = ":is([role=\"dialog\"], .el-dialog, .el-drawer, .ant-modal, .ant-drawer):visible"
    label = _text(name)
    if label:
        selector += f":has-text({json.dumps(label, ensure_ascii=False)})"
    try:
        return page.locator(selector)
    except Exception:
        return None


def _url_matches(actual: Any, expected: Any) -> bool:
    actual_text, expected_text = _text(actual), _text(expected)
    if not expected_text:
        return False
    return actual_text == expected_text or actual_text.startswith(expected_text + "?") or actual_text.startswith(expected_text + "#")


def _network_matches(page: Any, expected: Any) -> bool:
    records = getattr(page, "_ui_network_results", None) or getattr(page, "ui_network_results", None) or []
    if not isinstance(records, (list, tuple)):
        return False
    expected = expected if isinstance(expected, dict) else {"url": expected}
    for item in records:
        if not isinstance(item, dict):
            continue
        if all(_text(item.get(key)) == _text(value) for key, value in expected.items() if value not in (None, "")):
            return True
    return False


def _matches(page: Any, step: dict[str, Any], effect: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    kind = _text(effect.get("type")).lower()
    expected = effect.get("expected")
    if kind in {"url_change", "url", "url_matches"}:
        actual = getattr(page, "url", "")
        return _url_matches(actual, expected), {"type": kind, "expected": expected, "actual": actual}
    if kind in {"tab_opened", "tab_visible", "tab_url"}:
        pages = list(getattr(getattr(page, "context", None), "pages", []) or [])
        if kind == "tab_opened" and isinstance(expected, int):
            ok = len(pages) >= expected
        elif expected:
            ok = any(_url_matches(getattr(item, "url", ""), expected) for item in pages)
        else:
            ok = len(pages) > 1
        return ok, {"type": kind, "expected": expected, "actual_page_count": len(pages)}
    if kind in {"dialog_visible", "drawer_visible"}:
        locator = _dialog_locator(page, effect.get("name"))
        return bool(locator and _visible(locator)), {"type": kind, "name": effect.get("name")}
    if kind in {"dialog_hidden", "drawer_hidden"}:
        locator = _dialog_locator(page, effect.get("name"))
        return not locator or _count(locator) == 0 or not _visible(locator), {"type": kind, "name": effect.get("name")}
    if kind in {"element_visible", "element_hidden", "element_enabled", "element_disabled"}:
        locator = _effect_locator(page, step, effect)
        visible = bool(locator and _visible(locator))
        if kind == "element_visible":
            ok = visible
        elif kind == "element_hidden":
            ok = not visible
        else:
            try:
                enabled = bool(locator and locator.is_enabled())
            except Exception:
                enabled = False
            ok = enabled if kind == "element_enabled" else not enabled
        return ok, {"type": kind, "locator": _text(effect.get("locator"))}
    if kind in {"target_value", "value_changed", "selected_value"}:
        locator = _effect_locator(page, step, effect)
        try:
            actual = locator.input_value() if locator else None
        except Exception:
            actual = None
        return _text(actual) == _text(expected), {"type": kind, "expected": expected, "actual": actual}
    if kind in {"target_checked", "checked"}:
        locator = _effect_locator(page, step, effect)
        try:
            actual = bool(locator.is_checked()) if locator else None
        except Exception:
            actual = None
        return actual is bool(expected), {"type": kind, "expected": expected, "actual": actual}
    if kind in {"table_row_added", "table_row_deleted", "table_row_updated"}:
        locator = _effect_locator(page, step, effect, "tr")
        count = _count(locator) if locator else 0
        ok = count > 0 if kind != "table_row_deleted" else count == 0
        return ok, {"type": kind, "matched_count": count}
    if kind in {"toast_visible", "toast_hidden", "toast"}:
        message = _text(effect.get("message") or effect.get("name") or expected)
        selector = ":is([role=\"alert\"], .el-message, .el-notification, .ant-message-notice, .ant-notification-notice):visible"
        if message:
            selector += f":has-text({json.dumps(message, ensure_ascii=False)})"
        locator = _effect_locator(page, step, {"locator": selector})
        visible = bool(locator and _visible(locator))
        return (not visible if kind == "toast_hidden" else visible), {"type": kind, "message": message}
    if kind in {"network_result", "network_complete"}:
        return _network_matches(page, expected or effect.get("request")), {"type": kind, "expected": expected or effect.get("request")}
    return False, {"type": kind or "unknown", "reason": "unsupported_effect"}


def effect_already_satisfied(page: Any, step: dict[str, Any]) -> bool:
    effects = _effects(step)
    return bool(effects) and all(_matches(page, step, effect)[0] for effect in effects)


def wait_for_effect_profile(page: Any, step: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    effects = _effects(step)
    if not effects:
        return {"required": _profile_required(step), "effects": [], "satisfied": True}
    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    last_details: list[dict[str, Any]] = []
    while True:
        checks = [_matches(page, step, effect) for effect in effects]
        last_details = [detail for _ok, detail in checks]
        if all(ok for ok, _detail in checks):
            return {"required": _profile_required(step), "effects": last_details, "satisfied": True}
        if time.monotonic() >= deadline:
            break
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            break
        try:
            page.wait_for_timeout(min(100, remaining_ms))
        except Exception:
            time.sleep(min(0.1, remaining_ms / 1000))
    raise UiEffectTimeout(f"动作结果未在 {max(0, timeout_ms)}ms 内满足: {last_details}")
