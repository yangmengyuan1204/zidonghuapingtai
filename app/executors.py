from datetime import datetime
import json
import os
from pathlib import Path
import random
import re
import shutil
import string
import time
from typing import Any, Dict, Iterable, Tuple
from urllib.parse import urljoin
from uuid import uuid4

import requests

from .models import ApiCase, Env, UiCase


BASE_DIR = Path(__file__).resolve().parent.parent
REPORT_DIR = BASE_DIR / "reports"
ALLURE_DIR = REPORT_DIR / "allure-results"
SCREENSHOT_DIR = REPORT_DIR / "screenshots"


def ensure_report_dirs() -> None:
    ALLURE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _browser_executable_candidates() -> list[str]:
    candidates = [
        os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"),
        os.getenv("CHROME_PATH"),
        os.getenv("EDGE_PATH"),
    ]
    for env_name, relative in [
        ("ProgramFiles", r"Google\Chrome\Application\chrome.exe"),
        ("ProgramFiles(x86)", r"Google\Chrome\Application\chrome.exe"),
        ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe"),
        ("ProgramFiles", r"Microsoft\Edge\Application\msedge.exe"),
        ("ProgramFiles(x86)", r"Microsoft\Edge\Application\msedge.exe"),
        ("LOCALAPPDATA", r"Microsoft\Edge\Application\msedge.exe"),
    ]:
        root = os.getenv(env_name)
        if root:
            candidates.append(str(Path(root) / relative))
    for command in ["chrome", "chrome.exe", "msedge", "msedge.exe"]:
        found = shutil.which(command)
        if found:
            candidates.append(found)

    result = []
    seen = set()
    for item in candidates:
        if not item:
            continue
        path = str(item)
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        if Path(path).exists():
            result.append(path)
    return result


def launch_chromium_browser(playwright: Any, headless: bool = True) -> Any:
    errors = []
    for launcher in [
        lambda: playwright.chromium.launch(headless=headless),
        lambda: playwright.chromium.launch(channel="chrome", headless=headless),
        lambda: playwright.chromium.launch(channel="msedge", headless=headless),
    ]:
        try:
            return launcher()
        except Exception as exc:
            errors.append(str(exc))

    for executable_path in _browser_executable_candidates():
        try:
            return playwright.chromium.launch(executable_path=executable_path, headless=headless)
        except Exception as exc:
            errors.append(f"{executable_path}: {exc}")

    install_cmd = f'set PLAYWRIGHT_BROWSERS_PATH={BASE_DIR / "ms-playwright"} && python -m playwright install chromium'
    raise RuntimeError(
        "Playwright 浏览器不可用，且未找到可用的本机 Chrome/Edge。"
        f"请执行：{install_cmd}。"
        f"原始错误：{errors[0] if errors else 'unknown'}"
    )


def parse_json_value(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def to_json_text(value: Any, fallback: Any) -> str:
    if value is None:
        value = fallback
    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return json.dumps(fallback, ensure_ascii=False)
        try:
            parsed = json.loads(raw)
            return json.dumps(parsed, ensure_ascii=False)
        except json.JSONDecodeError:
            return value
    return json.dumps(value, ensure_ascii=False)


def write_allure_result(name: str, case_type: str, passed: bool, log_text: str, screenshot_path: str = "") -> str:
    ensure_report_dirs()
    now_ms = int(time.time() * 1000)
    result_uuid = str(uuid4())
    status = "passed" if passed else "failed"
    log_source = f"{result_uuid}-log.txt"
    (ALLURE_DIR / log_source).write_text(log_text or "", encoding="utf-8")

    attachments = [{"name": "log", "source": log_source, "type": "text/plain"}]
    if screenshot_path:
        src = Path(screenshot_path)
        if src.exists():
            screenshot_source = f"{result_uuid}-screenshot.png"
            shutil.copyfile(src, ALLURE_DIR / screenshot_source)
            attachments.append({"name": "screenshot", "source": screenshot_source, "type": "image/png"})

    payload = {
        "uuid": result_uuid,
        "name": name,
        "fullName": f"{case_type}.{name}",
        "status": status,
        "stage": "finished",
        "start": now_ms,
        "stop": now_ms,
        "labels": [{"name": "suite", "value": case_type}],
        "attachments": attachments,
    }
    result_path = ALLURE_DIR / f"{result_uuid}-result.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(result_path)


def _json_dump_log(parts: Dict[str, Any]) -> str:
    return json.dumps(parts, ensure_ascii=False, indent=2, default=str)


VAR_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.$-]+)\s*\}\}")


def builtin_variables() -> Dict[str, Any]:
    now = datetime.now()
    rand = random.randint(100000, 999999)
    uid = str(uuid4())
    generated = {
        "timestamp": int(time.time()),
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "uuid": uid,
        "random_int": rand,
        "random_str": "".join(random.choices(string.ascii_lowercase + string.digits, k=8)),
        "random_phone": f"13{random.randint(100000000, 999999999)}",
        "random_email": f"test_{rand}@example.com",
    }
    generated.update({f"${key}": value for key, value in generated.items()})
    return generated


def render_template(value: Any, variables: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return str(variables.get(key, match.group(0)))

        return VAR_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [render_template(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: render_template(item, variables) for key, item in value.items()}
    return value


def merge_variables(env: Env, runtime_vars: Dict[str, Any] | None = None) -> Dict[str, Any]:
    variables = builtin_variables()
    env_vars = parse_json_value(env.global_vars, {})
    if isinstance(env_vars, dict):
        variables.update(env_vars)
    if runtime_vars:
        variables.update(runtime_vars)
    return variables


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
    timeout = env.timeout or 30
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
        response_text = response.text
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
                    "body": response_text[:10000],
                },
                "assertions": checks,
                "extracted_vars": extracted_vars,
                "finished_at": datetime.now(),
            }
        )
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "api", passed, log_text)
        return passed, log_text, report_path, extracted_vars
    except Exception as exc:
        log_parts.update({"error": str(exc), "finished_at": datetime.now()})
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "api", False, log_text)
        return False, log_text, report_path, {}


def _run_ui_step(page: Any, step: Dict[str, Any], screenshots: list[str]) -> None:
    action = step.get("action")
    locator = step.get("locator")
    value = step.get("value")

    if action == "goto":
        page.goto(value)
    elif action == "input":
        page.fill(locator, str(value or ""))
    elif action == "click":
        page.click(locator)
    elif action == "select":
        page.select_option(locator, str(value or ""))
    elif action == "check":
        page.check(locator)
    elif action == "uncheck":
        page.uncheck(locator)
    elif action == "wait":
        page.wait_for_timeout(int(value or 1000))
    elif action == "wait_for_selector":
        page.wait_for_selector(locator)
    elif action == "assert_visible":
        if not page.locator(locator).first.is_visible():
            raise AssertionError(f"assert_visible failed: locator {locator!r} is not visible")
    elif action == "assert_url":
        current_url = page.url
        if str(value) not in current_url:
            raise AssertionError(f"assert_url failed: expected contains {value!r}, actual {current_url!r}")
    elif action == "assert_value":
        actual = page.locator(locator).input_value()
        if str(value) != str(actual):
            raise AssertionError(f"assert_value failed: expected {value!r}, actual {actual!r}")
    elif action == "text_assert":
        text = page.locator(locator).inner_text()
        if str(value) not in text:
            raise AssertionError(f"text_assert failed: expected {value!r}, actual {text!r}")
    elif action == "screenshot":
        ensure_report_dirs()
        screenshot = SCREENSHOT_DIR / f"{uuid4()}.png"
        page.screenshot(path=str(screenshot), full_page=True)
        screenshots.append(str(screenshot))
    else:
        raise ValueError(f"Unsupported UI action: {action}")


def execute_ui_case(case: UiCase, runtime_vars: Dict[str, Any] | None = None) -> Tuple[bool, str, str, str]:
    ensure_report_dirs()
    timeout = case.timeout or 30
    variables = builtin_variables()
    if runtime_vars:
        variables.update(runtime_vars)
    steps = render_template(parse_json_value(case.steps, []), variables)
    if not isinstance(steps, Iterable) or isinstance(steps, (str, bytes, dict)):
        steps = []

    log_parts: Dict[str, Any] = {
        "case_name": case.case_name,
        "page_url": render_template(case.page_url, variables),
        "steps": steps,
        "timeout": timeout,
        "variables": {key: ("***" if "password" in str(key).lower() else value) for key, value in variables.items()},
        "started_at": datetime.now(),
    }
    screenshots: list[str] = []
    current_step_index = 0
    current_step: Dict[str, Any] | None = None

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        log_parts.update(
            {
                "error": f"Playwright 不可用：{exc}",
                "hint": "请先执行：python -m playwright install",
                "finished_at": datetime.now(),
            }
        )
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "ui", False, log_text)
        return False, log_text, "", report_path

    browser = None
    page = None
    try:
        with sync_playwright() as p:
            browser = launch_chromium_browser(p, headless=True)
            page = browser.new_page()
            page.set_default_timeout(timeout * 1000)
            if case.page_url:
                page.goto(render_template(case.page_url, variables))
            for index, step in enumerate(steps, start=1):
                current_step_index = index
                current_step = step if isinstance(step, dict) else {"raw": step}
                _run_ui_step(page, step, screenshots)
            if not screenshots:
                screenshot = SCREENSHOT_DIR / f"{uuid4()}.png"
                page.screenshot(path=str(screenshot), full_page=True)
                screenshots.append(str(screenshot))
            browser.close()
            browser = None
            log_parts.update({"finished_at": datetime.now()})
            log_text = _json_dump_log(log_parts)
            report_path = write_allure_result(case.case_name, "ui", True, log_text, screenshots[-1])
            return True, log_text, screenshots[-1], report_path
    except Exception as exc:
        screenshot = ""
        if page:
            try:
                screenshot_path = SCREENSHOT_DIR / f"{uuid4()}.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                screenshot = str(screenshot_path)
            except Exception:
                screenshot = ""
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        log_parts.update(
            {
                "error": str(exc),
                "failed_step_index": current_step_index or None,
                "failed_step": current_step,
                "finished_at": datetime.now(),
            }
        )
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "ui", False, log_text, screenshot)
        return False, log_text, screenshot, report_path
