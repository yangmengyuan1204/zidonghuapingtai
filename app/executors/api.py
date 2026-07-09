from datetime import datetime
from typing import Any, Dict, Tuple
from urllib.parse import urljoin

import requests

from ..models import ApiCase, Env
from .common import (
    ensure_report_dirs,
    json_dump_log,
    merge_variables,
    parse_json_value,
    render_template,
    write_allure_result,
)


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
    headers = render_template(parse_json_value(env.global_headers, {}), variables)
    headers.update(render_template(parse_json_value(case.headers, {}), variables))
    params = render_template(parse_json_value(case.params, {}), variables)
    body = render_template(parse_json_value(case.body, case.body or None), variables)
    assert_rule = parse_json_value(case.assert_rule, {})
    method = case.method.upper()
    target_url = render_template(urljoin(env.base_url.rstrip("/") + "/", case.url.lstrip("/")), variables)

    started = datetime.now()
    log_parts: Dict[str, Any] = {
        "request": {
            "method": method,
            "url": target_url,
            "headers": headers,
            "params": params,
            "body": body,
            "timeout": timeout,
        },
        "variables": variables,
        "started_at": started,
    }

    try:
        request_kwargs = build_request_kwargs(headers, params, body, timeout, method)
        response = requests.request(method, target_url, **request_kwargs)
        response_text = response.text[:50000]
        checks = []

        expected_status = assert_rule.get("status_code") if isinstance(assert_rule, dict) else None
        if expected_status is not None:
            ok = response.status_code == int(expected_status)
            checks.append({"type": "status_code", "expected": expected_status, "actual": response.status_code, "passed": ok})

        contains = assert_rule.get("contains") if isinstance(assert_rule, dict) else None
        if contains:
            contains = render_template(str(contains), variables)
            ok = str(contains) in response_text
            checks.append({"type": "contains", "expected": contains, "passed": ok})

        passed = all(item["passed"] for item in checks) if checks else 200 <= response.status_code < 400
        extracted_vars = extract_response_vars(response, assert_rule.get("extract") if isinstance(assert_rule, dict) else {})
        log_parts.update(
            {
                "response": {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_text[:50000],
                },
                "assertions": checks,
                "extracted_vars": extracted_vars,
                "finished_at": datetime.now(),
            }
        )
        log_text = json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "api", passed, log_text)
        return passed, log_text, report_path, extracted_vars
    except Exception as exc:
        log_parts.update({"error": str(exc), "finished_at": datetime.now()})
        log_text = json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "api", False, log_text)
        return False, log_text, report_path, {}
