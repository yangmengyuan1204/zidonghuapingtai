from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_DANGEROUS_ACTION_RE = re.compile(
    r"删除|移除|清空|提交|确认|下单|支付|付款|退款|充值|发布|"
    r"delete|remove|clear\s+all|submit|place\s+order|pay(?:ment)?|refund|publish",
    re.IGNORECASE,
)
_SENSITIVE_KEY_RE = re.compile(r"password|passwd|token|cookie|authorization|secret|密码", re.IGNORECASE)


def _text(value: Any, max_len: int = 1000) -> str:
    return " ".join(str(value or "").split())[:max_len]


def _safe_url(value: Any) -> str:
    url = _text(value, 1000)
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    def cleaned_query(query: str) -> str:
        return urlencode(
            [
                (key, item)
                for key, item in parse_qsl(query, keep_blank_values=True)
                if not _SENSITIVE_KEY_RE.search(key)
            ],
            doseq=True,
        )

    query = cleaned_query(parts.query)
    fragment_path, separator, fragment_query = parts.fragment.partition("?")
    fragment = fragment_path
    if separator:
        safe_fragment_query = cleaned_query(fragment_query)
        if safe_fragment_query:
            fragment = f"{fragment_path}?{safe_fragment_query}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, fragment))


def sanitize_page_url(value: Any) -> str:
    return _safe_url(value)


def _dialogs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for raw in value:
        item = _text(raw, 200)
        if item and item not in result:
            result.append(item)
        if len(result) >= 12:
            break
    return result


def sanitize_page_state(value: Any, *, sensitive: bool = False) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    url = _safe_url(value.get("url"))
    if url:
        result["url"] = url
    title = _text(value.get("title") or value.get("page_title"), 300)
    if title:
        result["title"] = title
    result["dialogs"] = _dialogs(value.get("dialogs"))
    raw_target = value.get("target")
    if isinstance(raw_target, dict):
        target: dict[str, Any] = {}
        if "value" in raw_target:
            target["value"] = "***" if sensitive else _text(raw_target.get("value"), 1000)
        if isinstance(raw_target.get("checked"), bool):
            target["checked"] = raw_target["checked"]
        if isinstance(raw_target.get("visible"), bool):
            target["visible"] = raw_target["visible"]
        if isinstance(raw_target.get("has_value"), bool):
            target["has_value"] = raw_target["has_value"]
        if target:
            result["target"] = target
    return result


def effect_observation_score(event: dict[str, Any], state: dict[str, Any]) -> int:
    before = event.get("before_state") if isinstance(event.get("before_state"), dict) else {}
    score = 0
    if state.get("url") and state.get("url") != before.get("url"):
        score += 4
    before_dialogs = set(_dialogs(before.get("dialogs")))
    after_dialogs = set(_dialogs(state.get("dialogs")))
    score += len(before_dialogs.symmetric_difference(after_dialogs)) * 2
    before_target = before.get("target") if isinstance(before.get("target"), dict) else {}
    after_target = state.get("target") if isinstance(state.get("target"), dict) else {}
    for key in ("value", "checked", "visible", "has_value"):
        if key in after_target and after_target.get(key) != before_target.get(key):
            score += 1
    return score


def infer_effect_profile(event: dict[str, Any]) -> dict[str, Any]:
    has_observed_state = "before_state" in event or "after_state" in event
    before = event.get("before_state") if isinstance(event.get("before_state"), dict) else {}
    after = event.get("after_state") if isinstance(event.get("after_state"), dict) else {}
    effects: list[dict[str, Any]] = []

    before_url = _safe_url(before.get("url"))
    after_url = _safe_url(after.get("url"))
    if after_url and after_url != before_url:
        effects.append({"type": "url_change", "expected": after_url})

    before_dialogs = _dialogs(before.get("dialogs"))
    after_dialogs = _dialogs(after.get("dialogs"))
    for name in before_dialogs:
        if name not in after_dialogs:
            effects.append({"type": "dialog_hidden", "name": name})
    for name in after_dialogs:
        if name not in before_dialogs:
            effects.append({"type": "dialog_visible", "name": name})

    action = _text(event.get("action"), 40).lower()
    before_target = before.get("target") if isinstance(before.get("target"), dict) else {}
    after_target = after.get("target") if isinstance(after.get("target"), dict) else {}
    if action in {"input", "select"} and ("value" in after_target or "has_value" in after_target):
        value_changed = after_target.get("value") != before_target.get("value")
        presence_changed = after_target.get("has_value") != before_target.get("has_value")
        if value_changed or presence_changed:
            expected = event.get("value", after_target.get("value", ""))
            if event.get("sensitive") or _text(event.get("input_type"), 50).lower() == "password":
                expected = event.get("value") if event.get("value") in {"{{password}}", "{{username}}"} else "***"
            effects.append({"type": "target_value", "expected": expected})
    elif action in {"input", "select"} and not has_observed_state and event.get("value") not in (None, ""):
        expected = event.get("value")
        if event.get("sensitive") or _text(event.get("input_type"), 50).lower() == "password":
            expected = event.get("value") if event.get("value") in {"{{password}}", "{{username}}"} else "***"
        effects.append({"type": "target_value", "expected": expected})
    elif action in {"check", "uncheck"} and isinstance(after_target.get("checked"), bool):
        if after_target.get("checked") != before_target.get("checked"):
            effects.append({"type": "target_checked", "expected": after_target["checked"]})

    if effects:
        return {"schema_version": 1, "effects": effects, "required": True, "confidence": 90}
    return {"schema_version": 1, "effects": [], "required": False, "confidence": 20}


def build_retry_policy(step: dict[str, Any]) -> dict[str, Any]:
    action = _text(step.get("action"), 40).lower()

    def _metadata_text(value: Any) -> list[str]:
        if isinstance(value, dict):
            result: list[str] = []
            for key, item in value.items():
                result.append(_text(key, 120))
                result.extend(_metadata_text(item))
            return result
        if isinstance(value, (list, tuple, set)):
            result: list[str] = []
            for item in value:
                result.extend(_metadata_text(item))
            return result
        return [_text(value, 500)] if value not in (None, "") else []

    metadata: list[str] = []
    for key in ("name", "text", "accessibility", "accessible_name", "aria_label", "label", "locator"):
        metadata.extend(_metadata_text(step.get(key)))
    target_profile = step.get("target_profile") if isinstance(step.get("target_profile"), dict) else {}
    metadata.extend(_metadata_text(target_profile.get("element")))
    metadata.extend(_metadata_text(target_profile.get("stable_attrs")))
    description = " ".join(metadata)
    if action == "click" and _DANGEROUS_ACTION_RE.search(description):
        return {"safe_retry": False, "max_attempts": 1, "reason": "dangerous_action"}
    if action in {"input", "select", "check", "uncheck"}:
        return {"safe_retry": True, "max_attempts": 2, "reason": "idempotent_action"}
    effect_profile = step.get("effect_profile") if isinstance(step.get("effect_profile"), dict) else {}
    if action == "click" and effect_profile.get("required") and effect_profile.get("effects"):
        return {"safe_retry": True, "max_attempts": 2, "reason": "observed_effect"}
    if action == "click":
        return {"safe_retry": False, "max_attempts": 1, "reason": "unverified_effect"}
    return {"safe_retry": False, "max_attempts": 1, "reason": "unsupported_action"}
