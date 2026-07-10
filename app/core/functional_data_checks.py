from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    "Decimal",
    "FunctionalDataCheckResult",
    "InvalidOperation",
    "compare_data_check_values",
    "datetime",
    "extract_response_value",
    "full_data_check_url",
    "guarded_proxy_request",
    "json",
    "lookup_nested_value",
    "normalize_compare_text",
    "normalize_decimal_value",
    "normalize_json_fields",
    "parse_json_value",
    "re",
    "require_non_blank_text",
    "runtime_main_attr",
    "urljoin",
    "urlparse",
)


def _sync_compat_globals() -> None:
    module = sys.modules["app.core.utils"]
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(module, name)


def _compat_wrapper(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        _sync_compat_globals()
        return func(*args, **kwargs)

    return wrapped


def _impl_normalize_data_check_payload(data: Dict[str, Any], require_name: bool = False) -> Dict[str, Any]:
    if require_name or "rule_name" in data:
        require_non_blank_text(data, "rule_name", "核对规则名称")
    if "check_type" in data and data["check_type"]:
        data["check_type"] = str(data["check_type"]).strip()
    data = normalize_json_fields(data)
    if "api_method" in data and data["api_method"]:
        data["api_method"] = str(data["api_method"]).upper()
    return data


def _impl_full_data_check_url(task: FunctionalTask, api_url: str) -> str:
    raw = (api_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return raw
    base = urlparse(task.target_url or "")
    origin = f"{base.scheme}://{base.netloc}" if base.scheme and base.netloc else ""
    return urljoin(origin.rstrip("/") + "/", raw.lstrip("/")) if origin else raw


def _impl_lookup_nested_value(payload: Any, path: str) -> Any:
    if not path or path in {"json", "$"}:
        return payload
    current = payload
    parts = [part for part in path.replace("[", ".").replace("]", "").split(".") if part and part != "json"]
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return None
    return current


def _impl_extract_response_value(response: requests.Response, value_path: str | None) -> Any:
    path = (value_path or "json").strip()
    if path == "status_code":
        return response.status_code
    if path.lower().startswith("header."):
        return response.headers.get(path.split(".", 1)[1], "")
    if path == "text":
        return response.text
    try:
        payload = response.json()
    except Exception:
        payload = response.text
    return lookup_nested_value(payload, path)


def _impl_normalize_compare_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value if value is not None else "")).strip()


def _impl_normalize_decimal_value(value: Any) -> Decimal | None:
    text_value = str(value if value is not None else "").strip()
    text_value = re.sub(r"[^\d.\-]", "", text_value.replace(",", ""))
    if not text_value:
        return None
    try:
        return Decimal(text_value).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _impl_compare_data_check_values(rule: FunctionalDataCheckRule, page_value: Any, api_value: Any) -> tuple[bool, str]:
    compare_rule = parse_json_value(rule.compare_rule, {})
    expected_value = rule.expected_value if rule.expected_value not in (None, "") else None
    check_type = rule.check_type or "page_api_consistency"

    left = page_value
    right = api_value
    if check_type == "amount_quantity":
        left_amount = normalize_decimal_value(left)
        right_amount = normalize_decimal_value(right)
        expected_amount = normalize_decimal_value(expected_value) if expected_value is not None else None
        if left_amount is None or right_amount is None:
            return False, "金额/数量无法转换为数字"
        if expected_amount is not None:
            passed = left_amount == expected_amount and right_amount == expected_amount
            return passed, f"页面={left_amount}，接口={right_amount}，预期={expected_amount}"
        return left_amount == right_amount, f"页面={left_amount}，接口={right_amount}"

    if check_type == "status_flow":
        mapping = {}
        if isinstance(compare_rule, dict):
            mapping = compare_rule.get("status_mapping") or compare_rule.get("mapping") or {}
        if isinstance(mapping, dict):
            left = mapping.get(str(left), left)
            right = mapping.get(str(right), right)

    left_text = normalize_compare_text(left)
    right_text = normalize_compare_text(right)
    if expected_value is not None:
        expected_text = normalize_compare_text(expected_value)
        passed = left_text == expected_text and right_text == expected_text
        return passed, f"页面={left_text}，接口={right_text}，预期={expected_text}"
    return left_text == right_text, f"页面={left_text}，接口={right_text}"


def _impl_execute_functional_data_check_rule(db: Session, task: FunctionalTask, rule: FunctionalDataCheckRule) -> FunctionalDataCheckResult:
    page_value = rule.page_value or ""
    api_value: Any = ""
    result = "blocked"
    message = ""
    detail: Dict[str, Any] = {}
    try:
        url = full_data_check_url(task, rule.api_url or "")
        if not url:
            raise RuntimeError("接口 URL 不能为空")
        headers = parse_json_value(rule.api_headers, {})
        body_value = parse_json_value(rule.api_body, {})
        body_text = "" if (rule.api_method or "GET").upper() == "GET" else json.dumps(body_value, ensure_ascii=False)
        proxy_request = runtime_main_attr("guarded_proxy_request", guarded_proxy_request)
        response = proxy_request(rule.api_method or "GET", url, headers if isinstance(headers, dict) else {}, body_text, 20)
        api_value = extract_response_value(response, rule.api_value_path)
        passed, message = compare_data_check_values(rule, page_value, api_value)
        result = "passed" if passed else "failed"
        detail = {
            "status_code": response.status_code,
            "api_url": url,
            "api_value_path": rule.api_value_path,
            "compare_type": rule.check_type,
        }
    except Exception as exc:
        message = str(exc)
        detail = {"error": str(exc)}

    record = FunctionalDataCheckResult(
        task_id=task.id,
        rule_id=rule.id,
        result=result,
        page_value=str(page_value),
        api_value=json.dumps(api_value, ensure_ascii=False, default=str) if isinstance(api_value, (dict, list)) else str(api_value),
        message=message,
        detail=json.dumps(detail, ensure_ascii=False, default=str),
        execute_time=datetime.now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


normalize_data_check_payload = _compat_wrapper(_impl_normalize_data_check_payload)
full_data_check_url = _compat_wrapper(_impl_full_data_check_url)
lookup_nested_value = _compat_wrapper(_impl_lookup_nested_value)
extract_response_value = _compat_wrapper(_impl_extract_response_value)
normalize_compare_text = _compat_wrapper(_impl_normalize_compare_text)
normalize_decimal_value = _compat_wrapper(_impl_normalize_decimal_value)
compare_data_check_values = _compat_wrapper(_impl_compare_data_check_values)
execute_functional_data_check_rule = _compat_wrapper(_impl_execute_functional_data_check_rule)
