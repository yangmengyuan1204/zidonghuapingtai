import json
import re
from datetime import datetime
from typing import Any, Dict, Tuple
from urllib.parse import urljoin

import requests

from ..models import ApiCase, Env
from .common import (
    VAR_PATTERN,
    ensure_report_dirs,
    json_dump_log,
    merge_variables,
    parse_json_value,
    render_template,
    write_allure_result,
)


UNRESOLVED_PLACEHOLDER_PATTERN = re.compile(r"\{\{.*?\}\}", re.DOTALL)


def _reject_nonstandard_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _placeholder_tokens(value: Any) -> list[str]:
    tokens: list[str] = []
    if isinstance(value, str):
        tokens.extend(match.group(0) for match in UNRESOLVED_PLACEHOLDER_PATTERN.finditer(value))
    elif isinstance(value, list):
        for item in value:
            tokens.extend(_placeholder_tokens(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            tokens.extend(_placeholder_tokens(key))
            tokens.extend(_placeholder_tokens(item))
    return list(dict.fromkeys(tokens))


def _missing_placeholder_tokens(value: Any, variables: Dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for token in _placeholder_tokens(value):
        supported = VAR_PATTERN.fullmatch(token)
        if supported is None:
            missing.append(token)
            continue
        key = supported.group(1)
        if key not in variables or variables[key] is None:
            missing.append(token)
    return missing


def _parse_assertion_rule(value: Any) -> tuple[Dict[str, Any] | None, tuple[str, str] | None]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, ("assertion_not_configured", "配置错误：未配置断言，请明确配置 status_code 或 contains。")
    if isinstance(value, dict):
        return value, None
    if not isinstance(value, str):
        return None, ("invalid_assertion_json", "配置错误：断言配置必须是 JSON 对象。")
    try:
        parsed = json.loads(value, parse_constant=_reject_nonstandard_json_constant)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, ("invalid_assertion_json", "配置错误：断言 JSON 解析失败，请检查 assert_rule。")
    if not isinstance(parsed, dict):
        return None, ("invalid_assertion_json", "配置错误：断言配置必须是 JSON 对象。")
    return parsed, None


def _configuration_failure(
    case: ApiCase,
    log_parts: Dict[str, Any],
    code: str,
    message: str,
    **details: Any,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    configuration_error = {"code": code, "message": message}
    configuration_error.update({key: value for key, value in details.items() if value})
    log_parts.update(
        {
            "assertions": [
                {
                    "type": "configuration",
                    "code": code,
                    "message": message,
                    "passed": False,
                }
            ],
            "assertion_status": "configuration_error",
            "configuration_error": configuration_error,
            "error": message,
            "finished_at": datetime.now(),
        }
    )
    log_text = json_dump_log(log_parts)
    report_path = write_allure_result(case.case_name, "api", False, log_text)
    return False, log_text, report_path, {}


def _pick_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def extract_response_vars(response: requests.Response, extract_rule: Any) -> Dict[str, Any]:
    if not isinstance(extract_rule, dict):
        return {}
    extracted: Dict[str, Any] = {}
    response_json = None
    for name, path in extract_rule.items():
        if not isinstance(path, str):
            continue
        if path == "text":
            extracted[name] = response.text
            continue
        if path.startswith("header."):
            extracted[name] = response.headers.get(path.removeprefix("header."))
            continue
        json_path = path
        if json_path.startswith("$."):
            json_path = json_path[2:]
        if json_path.startswith("json."):
            json_path = json_path[5:]
        if response_json is None:
            try:
                response_json = response.json()
            except ValueError:
                response_json = {}
        extracted[name] = _pick_path(response_json, json_path)
    return {key: value for key, value in extracted.items() if value is not None}


def build_request_kwargs(headers: Dict[str, Any], params: Any, body: Any, timeout: int, method: str) -> Dict[str, Any]:
    request_headers = dict(headers or {})
    request_kwargs: Dict[str, Any] = {"headers": request_headers, "params": params, "timeout": timeout}
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return request_kwargs

    content_type_key = next((key for key in request_headers if key.lower() == "content-type"), "")
    content_type = str(request_headers.get(content_type_key, "")).lower()
    if isinstance(body, dict) and "multipart/form-data" in content_type:
        if content_type_key:
            request_headers.pop(content_type_key, None)
        request_kwargs["files"] = {key: (None, str(value)) for key, value in body.items()}
    elif isinstance(body, dict) and "application/x-www-form-urlencoded" in content_type:
        request_kwargs["data"] = body
    elif isinstance(body, (dict, list)):
        request_kwargs["json"] = body
    elif body is not None:
        request_kwargs["data"] = body
    return request_kwargs


def execute_api_case(case: ApiCase, env: Env, runtime_vars: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    timeout = max(1, env.timeout or 30)
    variables = merge_variables(env, runtime_vars)
    method = case.method.upper()
    raw_headers = parse_json_value(env.global_headers, {})
    raw_case_headers = parse_json_value(case.headers, {})
    raw_params = parse_json_value(case.params, {})
    raw_body = parse_json_value(case.body, case.body or None)
    raw_target_url = urljoin(env.base_url.rstrip("/") + "/", case.url.lstrip("/"))

    started = datetime.now()
    log_parts: Dict[str, Any] = {
        "request": {
            "method": method,
            "url": raw_target_url,
            "path": case.url,
            "headers": {**raw_headers, **raw_case_headers},
            "params": raw_params,
            "body": raw_body,
            "timeout": timeout,
        },
        "variables": variables,
        "started_at": started,
    }

    assert_rule, assertion_error = _parse_assertion_rule(case.assert_rule)
    if assertion_error:
        return _configuration_failure(case, log_parts, *assertion_error)

    request_fields = {
        "url": env.base_url,
        "path": case.url,
        "query": raw_params,
        "headers": {**raw_headers, **raw_case_headers},
        "body": raw_body,
    }
    assertion_template = assert_rule.get("contains") if assert_rule else None
    missing_by_field = {
        field: _missing_placeholder_tokens(value, variables)
        for field, value in {**request_fields, "assertions": assertion_template}.items()
    }
    missing_by_field = {field: tokens for field, tokens in missing_by_field.items() if tokens}
    if missing_by_field:
        return _configuration_failure(
            case,
            log_parts,
            "unresolved_variables",
            "配置错误：存在未解析的双花括号变量，请补充变量值或修正占位符。",
            fields=list(missing_by_field),
            placeholders=missing_by_field,
        )

    headers = render_template(raw_headers, variables)
    headers.update(render_template(raw_case_headers, variables))
    params = render_template(raw_params, variables)
    body = render_template(raw_body, variables)
    target_url = render_template(raw_target_url, variables)
    rendered_path = render_template(case.url, variables)
    rendered_assertion = render_template(assertion_template, variables) if assertion_template is not None else None
    rendered_fields = {
        "url": target_url,
        "path": rendered_path,
        "query": params,
        "headers": headers,
        "body": body,
        "assertions": rendered_assertion,
    }
    unresolved_by_field = {
        field: _placeholder_tokens(value)
        for field, value in rendered_fields.items()
        if _placeholder_tokens(value)
    }
    if unresolved_by_field:
        return _configuration_failure(
            case,
            log_parts,
            "unresolved_variables",
            "配置错误：最终渲染结果仍包含未解析的双花括号占位符。",
            fields=list(unresolved_by_field),
            placeholders=unresolved_by_field,
        )

    expected_status = assert_rule.get("status_code") if assert_rule else None
    expected_status_code = None
    if expected_status is not None:
        is_integer_status = isinstance(expected_status, int) and not isinstance(expected_status, bool)
        is_numeric_string = isinstance(expected_status, str) and re.fullmatch(r"[0-9]+", expected_status.strip()) is not None
        if not is_integer_status and not is_numeric_string:
            return _configuration_failure(
                case,
                log_parts,
                "invalid_assertion_value",
                "配置错误：status_code 断言必须是有效整数。",
            )
        try:
            expected_status_code = int(expected_status)
        except ValueError:
            return _configuration_failure(
                case,
                log_parts,
                "invalid_assertion_value",
                "配置错误：status_code 断言必须是有效整数。",
            )
    has_contains_assertion = bool(rendered_assertion)
    if expected_status is None and not has_contains_assertion:
        return _configuration_failure(
            case,
            log_parts,
            "no_valid_assertions",
            "配置错误：没有有效断言，请配置 status_code 或非空 contains。",
        )

    log_parts["request"].update(
        {
            "url": target_url,
            "path": rendered_path,
            "headers": headers,
            "params": params,
            "body": body,
        }
    )

    try:
        request_kwargs = build_request_kwargs(headers, params, body, timeout, method)
        response = requests.request(method, target_url, **request_kwargs)
        response_text = response.text[:50000]
        checks = []

        if expected_status is not None:
            ok = response.status_code == expected_status_code
            checks.append({"type": "status_code", "expected": expected_status, "actual": response.status_code, "passed": ok})

        if has_contains_assertion:
            ok = str(rendered_assertion) in response_text
            checks.append({"type": "contains", "expected": rendered_assertion, "passed": ok})

        passed = all(item["passed"] for item in checks)
        extracted_vars = extract_response_vars(response, assert_rule.get("extract", {}))
        log_parts.update(
            {
                "response": {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_text[:50000],
                },
                "assertions": checks,
                "assertion_status": "passed" if passed else "failed",
                "extracted_vars": extracted_vars,
                "finished_at": datetime.now(),
            }
        )
        log_text = json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "api", passed, log_text)
        return passed, log_text, report_path, extracted_vars
    except Exception as exc:
        log_parts.update({"assertion_status": "execution_error", "error": str(exc), "finished_at": datetime.now()})
        log_text = json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "api", False, log_text)
        return False, log_text, report_path, {}
