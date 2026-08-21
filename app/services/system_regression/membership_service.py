from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from app.data_scripts.cart_support import _api_path, _api_success, _configure_client_api_paths
from app.data_scripts.data_script_shared import _auth_headers
from app.vendor.piliangtianjiagouwuche import RakumartClient


MEMBERSHIP_FIXED = "fixed"
MEMBERSHIP_REGULAR = "regular"
PREVIEW_RATE_FIXED = Decimal("21.10")
PREVIEW_RATE_REGULAR = Decimal("21.20")
DEFAULT_REGULAR_SERVICE_RATE = Decimal("0.05")
_FIXED_LEVEL_NAMES = frozenset({"定額会員", "定额会员", "VIP", "SVIP"})


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _rate_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def empty_membership(*, reason: str = "") -> dict[str, Any]:
    return {
        "kind": "",
        "level_name": "",
        "level_id": "",
        "level_type": "",
        "service_rate": "",
        "preview_cny_to_jpy": "",
        "source": "",
        "reason": reason,
    }


def public_membership(membership: Mapping[str, Any] | None) -> dict[str, Any]:
    row = dict(membership or empty_membership())
    return {
        "kind": _text(row.get("kind")),
        "level_name": _text(row.get("level_name")),
        "level_id": _text(row.get("level_id")),
        "level_type": _text(row.get("level_type")),
        "service_rate": _text(row.get("service_rate")),
        "preview_cny_to_jpy": _text(row.get("preview_cny_to_jpy")),
        "source": _text(row.get("source")),
        "reason": _text(row.get("reason")),
    }


def _is_fixed_level(level_name: str, level_type: Any) -> bool:
    if str(level_type).strip() in {"1", "true", "True"}:
        return True
    compact = level_name.strip()
    if compact in _FIXED_LEVEL_NAMES:
        return True
    return compact.upper() in {"VIP", "SVIP"}


def parse_user_info_membership(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    root = payload if isinstance(payload, Mapping) else {}
    data = root.get("data") if isinstance(root.get("data"), Mapping) else root
    if not isinstance(data, Mapping):
        return empty_membership(reason="会员信息格式无效")
    level = data.get("level") if isinstance(data.get("level"), Mapping) else {}
    current = level.get("currentLevel") if isinstance(level.get("currentLevel"), Mapping) else {}
    level_name = _text(current.get("level_name") or data.get("level_name"))
    level_type = current.get("level_type")
    if level_type in (None, "") and data.get("level_type") not in (None, ""):
        level_type = data.get("level_type")
    level_id = current.get("id")
    if level_id in (None, ""):
        level_id = data.get("level_id")
    fixed = _is_fixed_level(level_name, level_type)
    service_rate = _decimal(data.get("current_service_rate"))
    if service_rate is None:
        service_rate = _decimal(current.get("service_rate"))
    if service_rate is None:
        service_rate = Decimal("0") if fixed else DEFAULT_REGULAR_SERVICE_RATE
    preview = format(PREVIEW_RATE_FIXED, ".2f") if fixed else format(PREVIEW_RATE_REGULAR, ".2f")
    return {
        "kind": MEMBERSHIP_FIXED if fixed else MEMBERSHIP_REGULAR,
        "level_name": level_name,
        "level_id": _text(level_id),
        "level_type": _text(level_type),
        "service_rate": _rate_text(service_rate),
        "preview_cny_to_jpy": preview,
        "source": "client_user_info",
        "reason": "",
    }


def inspect_logged_in_membership(client: Any, variables: Mapping[str, Any] | None = None) -> dict[str, Any]:
    values = dict(variables or {})
    session = getattr(client, "session", None)
    headers = dict(getattr(session, "headers", {}) or {})
    token = _text(headers.get("clienttoken") or headers.get("ClientToken") or headers.get("userToken"))
    if token and session is not None:
        session.headers.update(_auth_headers(token))
    path = _api_path(values, "client_user_info", "/client/user.info")
    try:
        payload = client.post_form(path, {})
    except Exception:
        return empty_membership(reason="会员信息拉取失败")
    if not isinstance(payload, Mapping):
        return empty_membership(reason="会员信息拉取失败")
    if not _api_success(payload):
        return empty_membership(reason=_text(payload.get("msg")) or "会员信息拉取失败")
    parsed = parse_user_info_membership(payload)
    if not parsed.get("kind"):
        parsed["reason"] = parsed.get("reason") or "未能识别会员档"
    return parsed


def inspect_membership_from_env(env: Any, variables: Mapping[str, Any] | None = None) -> dict[str, Any]:
    values = dict(variables or {})
    account = _text(values.get("account"))
    password = _text(values.get("password"))
    if not account or not password:
        return empty_membership(reason="缺少前台账号，无法识别会员档")
    base_url = _text(getattr(env, "base_url", "") or values.get("base_url"))
    if not base_url:
        return empty_membership(reason="执行环境没有站点地址，无法识别会员档")
    timeout = int(values.get("timeout") or getattr(env, "timeout", None) or 25) or 25
    client = RakumartClient(base_url.rstrip("/"), timeout)
    _configure_client_api_paths(client, values)
    try:
        client.login(account, password, _text(values.get("client_tool") or "1") or "1")
    except Exception:
        return empty_membership(reason="前台登录失败，无法识别会员档")
    return inspect_logged_in_membership(client, values)


def apply_membership_to_variables(variables: dict[str, Any], membership: Mapping[str, Any] | None) -> dict[str, Any]:
    row = public_membership(membership)
    if not row.get("kind"):
        return variables
    variables["membership_kind"] = row["kind"]
    variables["membership_level_name"] = row["level_name"]
    variables["membership_preview_cny_to_jpy"] = row["preview_cny_to_jpy"]
    if variables.get("service_rate") in (None, "") and row.get("service_rate") != "":
        variables["service_rate"] = row["service_rate"]
    return variables
