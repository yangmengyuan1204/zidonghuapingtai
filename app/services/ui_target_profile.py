from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SCOPE_KINDS = {"dialog", "drawer", "form", "table_row", "card", "menu", "listbox"}
_STABLE_ATTR_ALIASES = {
    "data-testid": "data-testid",
    "data_testid": "data-testid",
    "data-test": "data-test",
    "data_test": "data-test",
    "id": "id",
    "name": "name",
    "title": "title",
    "type": "type",
    "aria-controls": "aria-controls",
    "aria_controls": "aria-controls",
}
_DYNAMIC_QUERY_KEYS = {
    "_",
    "cache_bust",
    "cachebuster",
    "nonce",
    "random",
    "request_id",
    "t",
    "timestamp",
    "ts",
}
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "code",
    "id_token",
    "key",
    "nonce",
    "password",
    "passwd",
    "pass",
    "refresh_token",
    "secret",
    "signature",
    "sig",
    "token",
}


def _text(value: Any, max_len: int) -> str:
    return " ".join(str(value or "").split())[:max_len]


def _strings(value: Any, max_items: int = 8, max_len: int = 160) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for raw in value:
        item = _text(raw, max_len)
        if item and item not in result:
            result.append(item)
        if len(result) >= max_items:
            break
    return result


def _stable_attrs(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for raw_key, normalized_key in _STABLE_ATTR_ALIASES.items():
        item = _text(value.get(raw_key), 300)
        if normalized_key in {"id", "aria-controls"} and _is_dynamic_identifier(item):
            continue
        if item:
            result[normalized_key] = item
    return result


def _is_dynamic_identifier(value: str) -> bool:
    return bool(
        value
        and (
            re.search(r"(?:^|\b)(?:el-id|rc-tabs|input-\d+|select-\d+|uid-|guid-|__)", value, re.I)
            or re.search(r"\d{4,}", value)
        )
    )


def _url_pattern(value: Any) -> str:
    url = _text(value, 1000)
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    base = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    def cleaned_query(query: str) -> tuple[str, bool]:
        pairs = parse_qsl(query, keep_blank_values=True)
        kept = [
            (key, item)
            for key, item in pairs
            if key.lower() not in _DYNAMIC_QUERY_KEYS
            and key.lower() not in _SENSITIVE_QUERY_KEYS
        ]
        return urlencode(kept, doseq=True), len(kept) != len(pairs)

    query, query_changed = cleaned_query(parts.query)
    result = base
    if query and query_changed:
        result = f"{result}*{query}*"
    elif query:
        result = f"{result}?{query}"
    elif parts.query:
        result = f"{result}*"
    if parts.fragment:
        fragment_path, separator, fragment_query = parts.fragment.partition("?")
        cleaned_fragment_query, fragment_changed = cleaned_query(fragment_query)
        fragment = fragment_path
        if separator and cleaned_fragment_query and fragment_changed:
            fragment = f"{fragment}*{cleaned_fragment_query}*"
        elif separator and cleaned_fragment_query:
            fragment = f"{fragment}?{cleaned_fragment_query}"
        elif separator:
            fragment = f"{fragment}*"
        result = f"{result}#{fragment}"
    return result


def _frame_chain(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        item: dict[str, Any] = {
            "name": _text(raw.get("name"), 160),
            "url_pattern": _url_pattern(raw.get("url") or raw.get("url_pattern")),
            "selector": _text(raw.get("selector"), 500),
        }
        attrs = _stable_attrs(raw.get("stable_attrs"))
        if attrs:
            item["stable_attrs"] = attrs
        neighbor_texts = _strings(raw.get("neighbor_texts"), max_items=4)
        if neighbor_texts:
            item["neighbor_texts"] = neighbor_texts
        result.append(item)
        if len(result) >= 8:
            break
    return result


def _scope_chain(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        kind = _text(raw.get("kind"), 40).lower()
        if kind not in _SCOPE_KINDS:
            continue
        item: dict[str, Any] = {"kind": kind}
        for key, limit in (("role", 80), ("name", 160), ("title", 160), ("text", 160)):
            text = _text(raw.get(key), limit)
            if text:
                item[key] = text
        attrs = _stable_attrs(raw.get("stable_attrs"))
        if attrs:
            item["stable_attrs"] = attrs
        if kind == "table_row" and isinstance(raw.get("headers"), dict):
            headers: dict[str, str] = {}
            for header, cell in list(raw["headers"].items())[:20]:
                header_text = _text(header, 80)
                cell_text = _text(cell, 160)
                if header_text and cell_text:
                    headers[header_text] = cell_text
            if headers:
                item["headers"] = headers
        result.append(item)
        if len(result) >= 6:
            break
    return result


def _capabilities(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return {
        key: bool(value.get(key))
        for key in ("click", "input", "select", "check")
        if isinstance(value.get(key), bool)
    }


def _sensitive_values(event: dict[str, Any]) -> list[str]:
    sensitive = (
        bool(event.get("sensitive"))
        or _text(event.get("input_type"), 50).lower() == "password"
        or _text(event.get("action"), 40).lower() == "input"
    )
    if not sensitive:
        return []
    result: list[str] = []
    for key in ("value", "raw_value", "default_value"):
        value = event.get(key)
        if not isinstance(value, str):
            continue
        text = value.strip()
        if text and text not in {"***", "{{password}}", "{{username}}"} and text not in result:
            result.append(text)
    return result


def _redact_sensitive(value: Any, secrets: list[str]) -> Any:
    if not secrets:
        return value
    if isinstance(value, str):
        result = value
        for secret in secrets:
            if secret in result:
                result = result.replace(secret, "")
        return result.strip()
    if isinstance(value, list):
        return [item for raw in value if (item := _redact_sensitive(raw, secrets)) not in ("", None, [], {})]
    if isinstance(value, dict):
        return {key: _redact_sensitive(item, secrets) for key, item in value.items()}
    return value


def sanitize_target_event(event: dict[str, Any]) -> dict[str, Any]:
    frame_source = event.get("frame_chain")
    if not isinstance(frame_source, list) or not frame_source:
        frame_source = event.get("frame_path")
    match_count = event.get("recorded_match_count")
    return {
        "page_title": _text(event.get("page_title"), 300),
        "opener_interaction_id": _text(event.get("opener_interaction_id"), 160),
        "frame_chain": _frame_chain(frame_source),
        "scope_chain": _scope_chain(event.get("scope_chain")),
        "neighbor_texts": _strings(event.get("neighbor_texts")),
        "stable_class_tokens": _strings(event.get("stable_class_tokens"), max_len=80),
        "capabilities": _capabilities(event.get("capabilities")),
        "recorded_match_count": match_count if isinstance(match_count, int) and match_count >= 0 else None,
    }


def build_target_profile(event: dict[str, Any]) -> dict[str, Any]:
    source = sanitize_target_event(event)
    stable_attrs = _stable_attrs(event.get("stable_attrs"))
    scope_chain = source["scope_chain"]
    match_count = source["recorded_match_count"]
    element = {
        "tag": _text(event.get("tag"), 50).lower(),
        "type": _text(event.get("input_type") or stable_attrs.get("type"), 50).lower(),
        "role": _text(event.get("role"), 80),
        "accessible_name": _text(event.get("accessible_name"), 300),
        "label": _text(event.get("label"), 300),
        "placeholder": _text(event.get("placeholder"), 300),
        "stable_attrs": stable_attrs,
        "stable_class_tokens": source["stable_class_tokens"],
        "capabilities": source["capabilities"],
    }
    stable_identity = any(key in stable_attrs for key in ("data-testid", "data-test", "id", "name", "aria-controls"))
    if match_count is not None and match_count > 1 and not scope_chain:
        quality = "risk"
    elif stable_identity and (match_count in (None, 0, 1) or bool(scope_chain)):
        quality = "stable"
    elif match_count == 1 and (element["accessible_name"] or element["label"] or element["placeholder"]):
        quality = "weak"
    else:
        quality = "risk"
    profile = {
        "schema_version": 1,
        "page": {
            "url_pattern": _url_pattern(event.get("url")),
            "title": source["page_title"],
            "opener_interaction_id": source["opener_interaction_id"],
        },
        "frame_chain": source["frame_chain"],
        "scope_chain": scope_chain,
        "element": element,
        "neighbor_texts": source["neighbor_texts"],
        "quality": quality,
    }
    return _redact_sensitive(profile, _sensitive_values(event))
