import logging
from datetime import datetime
import json
import os
import queue
from pathlib import Path
import random
import re
import shutil
import string
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, Tuple
from urllib.parse import urljoin, urlparse, urlunparse
from uuid import uuid4


logger = logging.getLogger(__name__)

import requests

from .models import ActionTemplate, ApiCase, Env, LocatorHealLog, UiCase


BASE_DIR = Path(__file__).resolve().parent.parent
REPORT_DIR = BASE_DIR / "reports"
ALLURE_DIR = REPORT_DIR / "allure-results"
SCREENSHOT_DIR = REPORT_DIR / "screenshots"


# ─── 截图验证工具 ──────────────────────────────────────

ERROR_PAGE_PATTERNS = [
    "404 Not Found",
    "500 Internal Server Error",
    "502 Bad Gateway",
    "503 Service Unavailable",
    "504 Gateway Timeout",
    "Whitelabel Error Page",
    "Internal Server Error",
    "An error occurred",
    "Page not found",
    "无法访问此网站",
    "无法访问",
    "页面不存在",
    "系统错误",
    "服务器内部错误",
]


def _quick_screenshot_check(screenshot_path: str) -> dict:
    """
    快速检查截图是否有效。
    返回 {"ok": bool, "reason": str, "checks": dict}
    """
    result = {"ok": True, "reason": "", "checks": {}}
    path = Path(screenshot_path)
    if not path.exists():
        result["ok"] = False
        result["reason"] = "截图文件不存在"
        return result

    size = path.stat().st_size
    result["checks"]["file_size_bytes"] = size

    if size < 2000:
        result["ok"] = False
        result["reason"] = f"截图文件过小 ({size} bytes)，可能为空白页"
        return result

    if size > 50 * 1024 * 1024:
        result["ok"] = False
        result["reason"] = f"截图文件异常过大 ({size // 1024 // 1024}MB)"
        return result

    # 检查截图文件名中是否包含错误内容
    # 如果图片内容有常见错误文本，通过 OCR 检查（高级功能暂不实现）
    # 这里简单检查文件名和时间戳
    return result


def _url_looks_reasonable(url: str, expected_base: str = "") -> bool:
    """
    检查最终 URL 是否合理（非空白、非错误页）。
    仅检查 URL 路径的最后两个段（文件名和父目录），避免误伤正常 URL。
    """
    if not url or url in ("about:blank", "data:", ""):
        return False
    from urllib.parse import urlparse
    parsed = urlparse(url.lower())
    # 只检查 path 的尾段，避免误伤正常路由
    path_segments = [s for s in parsed.path.rstrip("/").split("/") if s]
    tail = path_segments[-2:] if len(path_segments) >= 2 else path_segments[-1:]
    tail_str = "/".join(tail)
    # 整段完全匹配的知名错误页面关键词
    error_tails = ["404", "500", "error", "notfound", "accessdenied", "timeout"]
    if tail_str in error_tails:
        return False
    # 检查文件名的扩展名前部分（如 error.aspx, 404.html）
    for seg in tail:
        base = seg.rsplit(".", 1)[0] if "." in seg else seg
        if base in error_tails:
            return False
    if expected_base and not url.lower().startswith(expected_base.lower().rstrip("/")):
        # 不包含期望 base 说明页面跳转到了预期外的域名
        return False
    return True


def ensure_report_dirs() -> None:
    ALLURE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _browser_executable_candidates() -> list[str]:
    candidates = [
        os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"),
        os.getenv("CHROME_PATH"),
        os.getenv("EDGE_PATH"),
    ]
    # 系统环境变量路径
    for env_name, relative in [
        ("ProgramFiles", r"Google\Chrome\Application\chrome.exe"),
        ("ProgramFiles(x86)", r"Google\Chrome\Application\chrome.exe"),
        ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe"),
        ("ProgramFiles", r"Microsoft\Edge\Application\msedge.exe"),
        ("ProgramFiles(x86)", r"Microsoft\Edge\Application\msedge.exe"),
        ("LOCALAPPDATA", r"Microsoft\Edge\Application\msedge.exe"),
        # 额外常见路径
        ("LOCALAPPDATA", r"Chromium\Application\chrome.exe"),
        ("LOCALAPPDATA", r"Google\Chrome Beta\Application\chrome.exe"),
        ("LOCALAPPDATA", r"Google\Chrome SxS\Application\chrome.exe"),
    ]:
        root = os.getenv(env_name)
        if root:
            candidates.append(str(Path(root) / relative))
    # 环境 PATH 查找
    for command in ["chrome", "chrome.exe", "msedge", "msedge.exe", "chromium", "chromium.exe", "google-chrome", "google-chrome-stable"]:
        found = shutil.which(command)
        if found:
            candidates.append(found)
    # Playwright 内置浏览器路径
    playwright_browsers = os.getenv("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / "AppData" / "Local" / "ms-playwright"))
    for channel_dir in ["chromium", "chrome", "msedge"]:
        p = Path(playwright_browsers) / channel_dir
        if p.is_dir():
            for exe in ["chrome.exe", "chrome-win" / "chrome.exe", "chrome-win64" / "chrome.exe"]:
                full = p / exe
                if full.exists():
                    candidates.append(str(full))

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


def _get_proxy_from_env() -> str | None:
    """从环境变量读取代理地址，优先级：HTTPS_PROXY > HTTP_PROXY > ALL_PROXY"""
    return (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("ALL_PROXY")
        or os.environ.get("all_proxy")
    )


def launch_chromium_browser(playwright: Any, headless: bool = True, proxy: str | None = None) -> Any:
    args = [
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
        "--ignore-certificate-errors",
    ]
    launch_kwargs = {"headless": headless, "args": args}
    proxy = proxy or _get_proxy_from_env()
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}
    errors = []
    # 1) 无参数默认启动（会尝试 Playwright 内置浏览器）
    try:
        return playwright.chromium.launch(**launch_kwargs)
    except Exception as exc:
        errors.append(f"default: {exc}")
    # 2) 指定通道启动
    for channel in ["chrome", "msedge"]:
        try:
            return playwright.chromium.launch(channel=channel, **launch_kwargs)
        except Exception as exc:
            errors.append(f"channel={channel}: {exc}")
    # 3) 逐一路径尝试
    for executable_path in _browser_executable_candidates():
        try:
            return playwright.chromium.launch(executable_path=executable_path, **launch_kwargs)
        except Exception as exc:
            errors.append(f"{Path(executable_path).name}: {exc}")

    # 4) 最终：尝试安装提示
    import subprocess
    suggested_install = f"python -m playwright install chromium"
    raise RuntimeError(
        "浏览器启动失败，未找到可用的 Chrome/Edge/Chromium。\n"
        f"请尝试：\n"
        f"  1. {suggested_install}\n"
        f"  2. 或安装 Chrome/Edge 浏览器\n"
        f"最后 3 个错误：{'; '.join(errors[-3:])}"
    )


def parse_json_value(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        if isinstance(value, str) and len(value) > 0:
            logger.debug("parse_json_value 解析失败，使用 fallback: %s...", value[:200])
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


def _epoch_ms(value: Any, fallback: int) -> int:
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    return fallback


def write_allure_result(
    name: str,
    case_type: str,
    passed: bool,
    log_text: str,
    screenshot_path: str = "",
    started_at: Any = None,
    finished_at: Any = None,
) -> str:
    ensure_report_dirs()
    now_ms = int(time.time() * 1000)
    start_ms = _epoch_ms(started_at, now_ms)
    stop_ms = _epoch_ms(finished_at, now_ms)
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
        else:
            logger.warning("Allure 报告截图文件不存在: %s", screenshot_path)

    payload = {
        "uuid": result_uuid,
        "name": name,
        "fullName": f"{case_type}.{name}",
        "status": status,
        "stage": "finished",
        "start": start_ms,
        "stop": stop_ms,
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
            if key in variables and variables[key] is not None:
                return str(variables[key])
            return ""

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
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "api", passed, log_text)
        return passed, log_text, report_path, extracted_vars
    except Exception as exc:
        log_parts.update({"error": str(exc), "finished_at": datetime.now()})
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "api", False, log_text)
        return False, log_text, report_path, {}


UI_ACTION_LABELS = {
    "goto": "打开页面",
    "input": "输入",
    "click": "点击",
    "select": "选择",
    "check": "勾选",
    "uncheck": "取消勾选",
    "wait": "等待",
    "wait_for_selector": "等待元素",
    "assert_visible": "检查元素可见",
    "assert_url": "检查页面地址",
    "assert_value": "检查输入值",
    "text_assert": "检查页面文案",
    "screenshot": "截图",
}

UI_LOCATOR_REQUIRED = {"input", "click", "wait_for_selector", "text_assert", "select", "check", "uncheck", "assert_visible", "assert_value"}
UI_VALUE_REQUIRED = {"goto", "input", "wait", "text_assert", "select", "assert_url", "assert_value"}
BUILTIN_VAR_NAMES = {"timestamp", "datetime", "date", "uuid", "random_int", "random_str", "random_phone", "random_email"}
LOGIN_URL_MARKERS = ("login", "signin")
LOGIN_TEXT_MARKERS = ("登录", "登入", "登陆", "login", "sign in", "ログイン")
REGISTER_TEXT_MARKERS = ("立即注册", "马上注册", "去注册", "register", "sign up", "新規登録")


class UiStepExecutionError(RuntimeError):
    def __init__(self, message: str, detail: Dict[str, Any]):
        super().__init__(message)
        self.detail = detail


class UiAuthPreparationError(RuntimeError):
    def __init__(self, message: str, trace: list[str]):
        suffix = f"\n登录过程：\n- " + "\n- ".join(trace) if trace else ""
        super().__init__(message + suffix)
        self.message = message
        self.trace = trace


def _mask_variables(variables: Dict[str, Any]) -> Dict[str, Any]:
    sensitive = re.compile(r"(password|passwd|pwd|captcha|token|secret|authorization|auth|密码|验证码)", re.I)
    sensitive_names = {"code", "verify_code", "verification_code", "captcha_code"}
    return {key: ("***" if str(key).lower() in sensitive_names or sensitive.search(str(key)) else value) for key, value in variables.items()}


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _quote_locator_text(value: str) -> str:
    return str(value or "").replace('"', '\\"')


def _step_timeout_ms(step: Dict[str, Any], default_seconds: int, cap_seconds: int = 8) -> int:
    raw = step.get("timeout")
    if raw in (None, ""):
        return min(default_seconds, cap_seconds) * 1000
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return min(default_seconds, cap_seconds) * 1000
    if value <= 0:
        return min(default_seconds, cap_seconds) * 1000
    # < 1000 视为秒（转换为毫秒），≥ 1000 视为毫秒直接使用
    return value * 1000 if value < 1000 else value


def _split_locator_values(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[\r\n]+", str(value or ""))
    result = []
    for item in items:
        text_value = str(item or "").strip()
        if text_value and text_value not in result:
            result.append(text_value)
    return result


def _merge_locator_values(*groups: Iterable[str]) -> list[str]:
    result: list[str] = []
    for group in groups:
        for item in group:
            text_value = str(item or "").strip()
            if text_value and text_value not in result:
                result.append(text_value)
    return result


def _text_locator_value(locator: str) -> str:
    text_value = str(locator or "").strip()
    if text_value.startswith("text="):
        return text_value[5:].strip().strip('"').strip("'")
    match = re.match(r"^(?:button|a|\[role=['\"]?button['\"]?\]):has-text\(['\"](.+?)['\"]\)$", text_value)
    return match.group(1) if match else ""


def _locator_candidates(step: Dict[str, Any]) -> list[str]:
    primary = str(step.get("locator") or "").strip()
    candidates = []
    for item in [primary, *_split_locator_values(step.get("fallback_locators"))]:
        if item and item not in candidates:
            candidates.append(item)
    if primary:
        placeholder_match = re.match(r"^placeholder\s*=\s*(.+)$", primary, flags=re.I)
        if placeholder_match:
            value = _quote_locator_text(placeholder_match.group(1).strip())
            candidates.extend([f'input[placeholder*="{value}"]', f'textarea[placeholder*="{value}"]'])
        name_match = re.match(r"^name\s*=\s*(.+)$", primary, flags=re.I)
        if name_match:
            value = _quote_locator_text(name_match.group(1).strip())
            candidates.extend([f'[name="{value}"]', f'input[name="{value}"]'])
        text_value = _text_locator_value(primary)
        if text_value:
            quoted = _quote_locator_text(text_value)
            candidates.extend(
                [
                    f'button:has-text("{quoted}")',
                    f'a:has-text("{quoted}")',
                    f'[role="button"]:has-text("{quoted}")',
                    f'input[type="button"][value*="{quoted}"]',
                    f'input[type="submit"][value*="{quoted}"]',
                ]
            )
    result = []
    for item in candidates:
        if item and item not in result:
            result.append(item)
    return result


def _classify_ui_error(error: str, step: Dict[str, Any], current_url: str = "") -> Dict[str, Any]:
    error_lower = str(error or "").lower()
    action = step.get("action") or ""
    if "unknown engine" in error_lower or "unexpected token" in error_lower:
        category = "定位器写法错误"
        reason = "locator 写法不符合 Playwright 规则。"
        suggestion = "重新扫描页面 DOM 后生成步骤，或改成 id/name/placeholder/text 这类稳定定位。"
    elif "strict mode violation" in error_lower:
        category = "定位器不唯一"
        reason = "locator 匹配到了多个元素，执行器无法确定要操作哪一个。"
        suggestion = "把 locator 改得更唯一，例如增加 id、name、placeholder 或更精确的按钮文案。"
    elif "waiting for" in error_lower and "timeout" in error_lower:
        category = "定位器找不到"
        reason = "规定时间内没有找到目标元素，可能是页面未进入预期状态、加载慢或定位器失效。"
        suggestion = "先看失败截图确认页面停留位置，再检查前一步操作和 locator。"
    elif "timeout" in error_lower:
        category = "操作超时"
        reason = "页面操作在指定时间内未完成，可能是页面加载慢或元素状态异常。"
        suggestion = "可适当增加超时设置，或检查页面是否有异常弹窗阻塞操作。"
    elif "not visible" in error_lower or "visible" in error_lower and "failed" in error_lower:
        category = "元素不可见/不可点击"
        reason = "元素存在但不可见或不可点击，可能被遮挡、折叠、未滚动到视图内或页面尚未渲染完成。"
        suggestion = "补充展开/等待步骤，或使用更准确的可见元素 locator。"
    elif "assert_url failed" in error:
        category = "页面未跳转或跳转地址不符合预期"
        reason = "执行后当前 URL 和预期不一致。"
        suggestion = "确认提交是否成功、登录态是否有效、预期跳转地址是否正确。"
    elif "text_assert failed" in error:
        category = "文案断言失败"
        reason = "页面实际文案和预期不一致，或当前页面不是预期页面。"
        suggestion = "确认产品文案是否变更，避免把弱文案作为主流程强断言。"
    elif "assert_value failed" in error:
        category = "输入值断言失败"
        reason = "输入框实际值和预期不一致，可能是输入未生效、控件自动格式化或定位到了错误输入框。"
        suggestion = "检查输入框 locator 是否唯一，并确认页面是否会自动格式化输入内容。"
    elif "login" in str(current_url or "").lower() and action != "goto":
        category = "登录态失效"
        reason = "执行时页面停留在登录页，后续业务步骤无法继续。"
        suggestion = "检查运行时账号密码、登录步骤和目标页面是否需要先登录。"
    else:
        category = "未知异常"
        reason = "执行过程中出现未分类异常。"
        suggestion = "结合失败截图、当前 URL 和失败步骤继续判断。"
    return {"category": category, "reason": reason, "suggestion": suggestion}


def _resolve_locator(page: Any, candidates: list[str], timeout_ms: int, state: str = "visible") -> tuple[Any, str, int]:
    errors = []
    for locator in candidates:
        try:
            target = page.locator(locator).first
            target.wait_for(state=state, timeout=timeout_ms)
            count = page.locator(locator).count()
            return target, locator, count
        except Exception as exc:
            errors.append(f"{locator}: {exc}")
            continue
    raise TimeoutError("未找到可用定位器：" + "；".join(errors[-4:]))


def _wait_for_url_contains(page: Any, expected: str, timeout_ms: int, exact: bool = False) -> None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        current = page.url or ""
        if exact:
            if current.rstrip("/") == expected.rstrip("/"):
                return
        else:
            if expected in current:
                return
        page.wait_for_timeout(300)
    mode = "精确匹配" if exact else "包含"
    raise AssertionError(f"assert_url failed: expected {mode} {expected!r}, actual {page.url!r}")


def _guess_login_url(target_url: str | None) -> str:
    raw = str(target_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return ""
    if parsed.fragment and "/" in parsed.fragment:
        hash_prefix = "!/" if parsed.fragment.startswith("!/") else "/"
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", f"{hash_prefix}login"))
    return urlunparse((parsed.scheme, parsed.netloc, "/login", "", "", ""))


def _first_runtime_value(variables: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = str(variables.get(key) or "").strip()
        if value:
            return value
    return ""


def _step_text(step: Dict[str, Any]) -> str:
    values = [step.get("name"), step.get("locator"), step.get("value"), " ".join(_split_locator_values(step.get("fallback_locators")))]
    return " ".join(str(item or "") for item in values).lower()


def _looks_like_login_url(value: Any) -> bool:
    url = str(value or "").strip().lower()
    return any(marker in url for marker in LOGIN_URL_MARKERS)


def _looks_like_login_page(page: Any, expected_url: str = "") -> bool:
    current_url = str(getattr(page, "url", "") or "").lower()
    expected = str(expected_url or "").lower()
    if current_url and current_url != expected and any(marker in current_url for marker in LOGIN_URL_MARKERS):
        return True
    try:
        password_visible = any(
            page.locator(locator).first.is_visible(timeout=300)
            for locator in ['input[type="password"]', 'input[name="password"]']
        )
    except Exception:
        password_visible = False
    if not password_visible:
        return False
    for locator in [
        'button:has-text("登录")',
        '[role="button"]:has-text("登录")',
        "text=登录",
        'input[placeholder*="账号"]',
        'input[placeholder*="邮箱"]',
        'input[placeholder*="手机号"]',
    ]:
        try:
            if page.locator(locator).first.is_visible(timeout=200):
                return True
        except Exception:
            continue
    return False


def _visible_login_error(page: Any) -> str:
    for locator in [
        ".error, .ant-form-item-explain-error, .el-form-item__error, .ant-message-error",
        "text=密码错误",
        "text=账号或密码错误",
        "text=登录失败",
        "text=验证码错误",
    ]:
        try:
            target = page.locator(locator).first
            if target.is_visible(timeout=200):
                text = _normalize_text(target.inner_text(timeout=500))
                if text:
                    return text[:200]
        except Exception:
            continue
    return ""


def _login_loading_visible(page: Any) -> bool:
    for locator in [
        "text=正在加载",
        "text=请稍等",
        ".el-loading-mask",
        ".ant-spin",
        ".loading",
        "[class*='loading']",
    ]:
        try:
            target = page.locator(locator).first
            if target.is_visible(timeout=200):
                return True
        except Exception:
            continue
    return False


def _wait_login_submit_settled(page: Any, timeout_ms: int) -> bool:
    deadline = time.time() + max(timeout_ms, 3000) / 1000
    saw_loading = False
    while time.time() < deadline:
        if not _login_loading_visible(page):
            return True
        saw_loading = True
        page.wait_for_timeout(500)
    return not saw_loading


def _is_login_related_step(step: Dict[str, Any]) -> bool:
    action = str(step.get("action") or "").strip().lower()
    text = _step_text(step)
    if action == "goto" and _looks_like_login_url(step.get("value")):
        return True
    if action == "input" and any(keyword in text for keyword in ["username", "account", "email", "mobile", "phone", "密码", "password", "账号", "邮箱", "手机", "验证码", "captcha", "code"]):
        return True
    if action == "click" and any(keyword in text for keyword in [*LOGIN_TEXT_MARKERS, *REGISTER_TEXT_MARKERS]):
        return True
    if action in {"wait_for_selector", "assert_visible", "text_assert"} and any(keyword in text for keyword in [*LOGIN_TEXT_MARKERS, "验证码", "captcha"]):
        return True
    return False


def _strip_leading_login_steps(steps: list[Dict[str, Any]]) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    prefix_actions = {"input", "click", "check", "uncheck", "wait", "wait_for_selector", "assert_visible", "text_assert"}
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            break
        action = str(step.get("action") or "").strip().lower()
        if action == "goto" and not _looks_like_login_url(step.get("value")):
            prefix = steps[:index]
            if prefix and all(
                isinstance(item, dict) and str(item.get("action") or "").strip().lower() in prefix_actions
                for item in prefix
            ):
                return steps[index:], prefix
            break
    kept: list[Dict[str, Any]] = []
    removed: list[Dict[str, Any]] = []
    stripping = True
    for step in steps:
        if not isinstance(step, dict):
            kept.append(step)
            stripping = False
            continue
        action = str(step.get("action") or "").strip().lower()
        if stripping and (_is_login_related_step(step) or (removed and action == "wait")):
            removed.append(step)
            continue
        if stripping and removed and action != "goto":
            removed.append(step)
            continue
        if action == "goto" and _looks_like_login_url(step.get("value")):
            removed.append(step)
            continue
        kept.append(step)
        stripping = False
    return kept or [{"name": "等待页面加载", "action": "wait_for_selector", "locator": "body"}], removed


BUSINESS_VAR_ALIASES = {
    "customer_id": ("customer_id", "customerId", "customerID"),
    "customer_name": ("customer_name", "customerName"),
    "box_no": ("box_no", "boxNo", "boxCode", "box_number"),
    "location_code": ("location_code", "locationCode", "warehouse_location"),
    "order_no": ("orderNumber", "order_no", "orderNo", "order_sn"),
}


def _first_business_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.I)
        if not match:
            continue
        value = (match.group(1) if match.groups() else match.group(0)).strip(" \t\r\n:" + "\uFF1A,\uFF0C\u3002")
        if value:
            return value[:80]
    return ""


def _business_variables_from_text(text: str) -> Dict[str, Any]:
    variables: Dict[str, Any] = {}
    customer_id = _first_business_match(text, [
        "\\bID\\s*[:\\uFF1A]\\s*([A-Za-z0-9_-]{3,32})",
        "\\b(CUST[-_]?[A-Za-z0-9]{3,24})\\b",
    ])
    if customer_id:
        variables["customer_id"] = customer_id
    customer_name = _first_business_match(text, [
        "\\bID\\s*[:\\uFF1A]\\s*[A-Za-z0-9_-]{3,32}\\s+([^\\s\\d][^\\r\\n]{1,40}?)\\s+(?:20\\d{8,}|[A-Z]{2,}[-_]?\\d|\\u3010)",
    ])
    if customer_name:
        variables["customer_name"] = customer_name
    box_no = _first_business_match(text, [
        "\\b(20\\d{10,}-[A-Za-z0-9_-]{3,}-\\d+)\\b",
        "\\b(BOX[-_]?[A-Z0-9]{4,36})\\b",
    ])
    if box_no:
        variables["box_no"] = box_no
    location_code = _first_business_match(text, [
        "\\u3010([^\\u3011]{2,80})\\u3011",
    ])
    if location_code:
        variables["location_code"] = location_code
    return variables


def _is_generated_sample_value(value: Any) -> bool:
    raw = str(value or "").strip()
    if not raw or raw.upper().startswith("NONEXISTENT"):
        return False
    lower = raw.lower()
    if raw in {"\u5ba2\u6237A", "\u5ba2\u6237B", "\u5ba2\u6237a", "\u5ba2\u6237b"}:
        return True
    return bool(
        re.fullmatch(r"CUST[-_]?\d{3,}", raw, flags=re.I)
        or re.fullmatch(r"CUSTOMER[-_]?\d{3,}", raw, flags=re.I)
        or re.fullmatch(r"ORDER[-_]?\d{3,}", raw, flags=re.I)
        or re.fullmatch(r"BOX[-_]?\d{3,}", raw, flags=re.I)
        or re.fullmatch(r"BX[-_]?\d{4}[-_]\d+", raw, flags=re.I)
        or lower in {"cust123456", "customer123456", "order123456", "box123456", "bx-2023-001"}
    )


def _sample_replacement_for_step(step: Dict[str, Any], variables: Dict[str, Any]) -> str:
    hint_lower = _step_text(step).lower()
    customer_id = str(variables.get("customerId") or variables.get("customer_id") or "").strip()
    customer_name = str(variables.get("customerName") or variables.get("customer_name") or "").strip()
    box_no = str(variables.get("boxNo") or variables.get("box_no") or variables.get("boxCode") or "").strip()
    location_code = str(variables.get("locationCode") or variables.get("location_code") or variables.get("warehouse_location") or "").strip()
    order_no = str(variables.get("orderNumber") or variables.get("orderNo") or variables.get("order_no") or "").strip()
    if any(item in hint_lower for item in ("customer", "client", "\u5ba2\u6237")):
        if "id" in hint_lower or "\u7f16\u53f7" in hint_lower:
            return customer_id or customer_name
        return customer_name or customer_id
    if any(item in hint_lower for item in ("box", "\u7bb1\u53f7", "\u7bb1\u5b50")) and box_no:
        return box_no
    if any(item in hint_lower for item in ("order", "\u8ba2\u5355")) and order_no:
        return order_no
    if any(item in hint_lower for item in ("location", "\u5e93\u4f4d", "\u4ed3\u4f4d")) and location_code:
        return location_code
    return ""


def _replace_sample_tokens(value: Any, replacement: str) -> Any:
    if not isinstance(value, str) or not replacement:
        return value
    result = value
    for token in ("\u5ba2\u6237A", "\u5ba2\u6237B", "CUST123456", "CUSTOMER123456", "ORDER123456", "BOX123456", "BX-2023-001"):
        result = result.replace(token, replacement)
    result = re.sub(r"\bCUST[-_]?\d{3,}\b", replacement, result, flags=re.I)
    result = re.sub(r"\bCUSTOMER[-_]?\d{3,}\b", replacement, result, flags=re.I)
    result = re.sub(r"\bORDER[-_]?\d{3,}\b", replacement, result, flags=re.I)
    result = re.sub(r"\bBOX[-_]?\d{3,}\b", replacement, result, flags=re.I)
    result = re.sub(r"\bBX[-_]?\d{4}[-_]\d+\b", replacement, result, flags=re.I)
    return result


def _merge_inferred_business_variables(variables: Dict[str, Any], inferred: Dict[str, Any]) -> Dict[str, Any]:
    applied: Dict[str, Any] = {}
    for canonical, aliases in BUSINESS_VAR_ALIASES.items():
        value = str(inferred.get(canonical) or "").strip()
        if not value:
            continue
        for alias in aliases:
            current = variables.get(alias)
            if current in (None, "") or _is_generated_sample_value(current):
                variables[alias] = value
                applied[alias] = value
    if "keyword" not in variables or variables.get("keyword") in (None, ""):
        keyword = inferred.get("location_code") or inferred.get("customer_id") or inferred.get("customer_name") or inferred.get("box_no")
        if keyword:
            variables["keyword"] = keyword
            applied["keyword"] = keyword
    return applied


def _stabilize_runtime_steps(steps: list[Dict[str, Any]], variables: Dict[str, Any]) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    normalized: list[Dict[str, Any]] = []
    replacements: list[Dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            normalized.append(step)
            continue
        next_step = dict(step)
        replacement = _sample_replacement_for_step(next_step, variables)
        if replacement and _is_generated_sample_value(next_step.get("value")):
            old_value = next_step.get("value")
            next_step["value"] = replacement
            replacements.append({"step": index, "field": "value", "from": old_value, "to": replacement})
        if replacement:
            old_locator = next_step.get("locator")
            new_locator = _replace_sample_tokens(old_locator, replacement)
            if new_locator != old_locator:
                next_step["locator"] = new_locator
                replacements.append({"step": index, "field": "locator", "from": old_locator, "to": new_locator})
            fallbacks = next_step.get("fallback_locators")
            if isinstance(fallbacks, list):
                new_fallbacks = [_replace_sample_tokens(item, replacement) for item in fallbacks]
                if new_fallbacks != fallbacks:
                    next_step["fallback_locators"] = new_fallbacks
                    replacements.append({"step": index, "field": "fallback_locators", "from": fallbacks, "to": new_fallbacks})
        normalized.append(next_step)
    return normalized, replacements


def _prepare_authenticated_page(page: Any, execution_context: Dict[str, Any], variables: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
    auth = dict(execution_context.get("login_config") or {})
    target_url = str(execution_context.get("target_url") or "").strip()
    login_url = str(auth.get("login_url") or "").strip() or _guess_login_url(target_url)
    username = _first_runtime_value(variables, ["username", "account", "email", "mobile", "phone"])
    password = _first_runtime_value(variables, ["password"])
    code = _first_runtime_value(variables, ["code", "captcha", "captcha_code", "verify_code", "verification_code"])
    trace: list[str] = [f"打开登录页：{login_url}"]
    if not login_url or not username or not password:
        raise UiAuthPreparationError("登录前置失败：缺少登录页 URL、登录账号或登录密码。", trace)

    username_defaults = [
        'input[placeholder="邮箱/手机号"]',
        'input[name="username"]',
        'input[name="account"]',
        'input[name="mobile"]',
        'input[name="email"]',
        'input[type="text"]',
    ]
    password_defaults = [
        'input[placeholder="请输入密码"]',
        'input[type="password"]',
        'input[name="password"]',
    ]
    submit_defaults = [
        'button:has-text("立即登录")',
        '[role="button"]:has-text("立即登录")',
        '.el-button:has-text("立即登录")',
        '[class*="button"]:has-text("立即登录")',
        '[class*="btn"]:has-text("立即登录")',
        '[class*="login"]:has-text("立即登录")',
        'input[type="submit"][value*="立即登录"]',
        "text=立即登录",
        'button[type="submit"]',
        'button:has-text("登录")',
        '[role="button"]:has-text("登录")',
        '.el-button:has-text("登录")',
        '[class*="button"]:has-text("登录")',
        '[class*="btn"]:has-text("登录")',
        '[class*="login"]:has-text("登录")',
        'input[type="submit"][value*="登录"]',
        "text=登录",
    ]
    username_candidates = _merge_locator_values(_split_locator_values(auth.get("username_locator")), username_defaults)
    password_candidates = _merge_locator_values(_split_locator_values(auth.get("password_locator")), password_defaults)
    submit_candidates = _merge_locator_values(_split_locator_values(auth.get("submit_locator")), submit_defaults)
    code_candidates = [
        'input[placeholder*="验证码"]',
        'input[name="code"]',
        'input[name="captcha"]',
        'input[placeholder*="captcha" i]',
    ]


    page.goto(login_url, wait_until="domcontentloaded", timeout=max(timeout_seconds, 10) * 1000)
    page.set_default_timeout(timeout_seconds * 1000)

    username_target, username_locator, _ = _resolve_locator(page, username_candidates, 4000)
    username_target.fill("", timeout=4000)
    username_target.fill(username, timeout=4000)
    trace.append(f"已填写登录账号：{username_locator}")

    password_target, password_locator, _ = _resolve_locator(page, password_candidates, 4000)
    password_target.fill("", timeout=4000)
    password_target.fill(password, timeout=4000)
    trace.append(f"已填写登录密码：{password_locator}")

    if code:
        try:
            code_target, code_locator, _ = _resolve_locator(page, code_candidates, 2000)
            code_target.fill("", timeout=2000)
            code_target.fill(code, timeout=2000)
            trace.append(f"已填写验证码：{code_locator}")
        except Exception:
            trace.append("未定位到验证码输入框，跳过验证码自动填写")

    submit_target, submit_locator, _ = _resolve_locator(page, submit_candidates, 5000)
    try:
        submit_target.scroll_into_view_if_needed(timeout=1000)
    except Exception:
        pass
    submit_target.click(timeout=5000)
    trace.append(f"已点击登录按钮：{submit_locator}")

    success_selector = str(auth.get("success_selector") or "").strip()
    success_url_contains = str(auth.get("success_url_contains") or "").strip()
    def wait_after_submit(label: str) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            page.wait_for_timeout(1500)
        settled = _wait_login_submit_settled(page, max(timeout_seconds, 15) * 1000)
        if not settled:
            trace.append(f"{label}后登录页仍处于加载中")
        trace.append(f"{label}后当前页面：{page.url}")

    wait_after_submit("首次提交")
    if success_selector:
        page.wait_for_selector(success_selector, timeout=max(timeout_seconds, 8) * 1000)
        trace.append(f"检测到登录成功元素：{success_selector}")
    elif success_url_contains:
        _wait_for_url_contains(page, success_url_contains, max(timeout_seconds, 8) * 1000)
        trace.append(f"检测到登录成功地址：{page.url}")
    else:
        if _looks_like_login_page(page, expected_url=login_url):
            # 二次确认：检查页面是否真的还有密码输入框（防止 URL 含 "login" 子串而误判）
            still_has_password = False
            try:
                still_has_password = any(
                    page.locator(l).first.is_visible(timeout=500)
                    for l in ['input[type="password"]', 'input[name="password"]']
                )
            except Exception:
                pass
            if not still_has_password:
                trace.append("页面已无密码输入框，认为登录成功（URL 含 login 关键词但已无登录表单）")
            else:
                try:
                    password_target.press("Enter", timeout=2000)
                    trace.append("首次点击后仍在登录页，已尝试按 Enter 再次提交")
                    wait_after_submit("Enter 提交")
                except Exception as exc:
                    trace.append(f"Enter 提交失败：{str(exc)[:200]}")
        if _looks_like_login_page(page, expected_url=login_url):
            try:
                submit_target.click(timeout=3000, force=True)
                trace.append("Enter 提交后仍在登录页，已尝试强制点击登录按钮")
                wait_after_submit("强制点击")
            except Exception as exc:
                trace.append(f"强制点击失败：{str(exc)[:200]}")
        if _looks_like_login_page(page, expected_url=login_url):
            error_text = _visible_login_error(page)
            detail = f"登录前置失败：提交后仍停留在登录页，当前页面 {page.url}"
            if _login_loading_visible(page):
                detail += "；登录请求一直处于加载中，可能是账号/密码不正确、验证码/二次认证未处理，或登录接口响应异常"
            if error_text:
                detail += f"；页面提示：{error_text}"
                trace.append(f"页面错误提示：{error_text}")
            raise UiAuthPreparationError(detail, trace)
        trace.append(f"登录后当前页面：{page.url}")
    return {"trace": trace, "login_url": login_url, "submit_locator": submit_locator}


def _run_ui_step(page: Any, step: Dict[str, Any], screenshots: list[str], default_timeout: int) -> Dict[str, Any]:
    started = time.time()
    action = str(step.get("action") or "").strip()
    locator = str(step.get("locator") or "").strip()
    value = step.get("value")
    name = str(step.get("name") or UI_ACTION_LABELS.get(action) or action or "未命名步骤")
    timeout_ms = _step_timeout_ms(step, default_timeout)
    candidates = _locator_candidates(step)
    detail: Dict[str, Any] = {
        "name": name,
        "action": action,
        "locator": locator,
        "fallback_locators": [item for item in candidates if item != locator],
        "value": "***" if "password" in name.lower() or "password" in locator.lower() else value,
        "started_at": datetime.now(),
        "status": "running",
        "current_url_before": getattr(page, "url", ""),
        "visible_text_before": _page_text_excerpt(page, limit=800),
    }
    before_shot = _capture_evidence_screenshot(page, "step-before", screenshots)
    if before_shot:
        detail["before_screenshot"] = before_shot

    try:
        if action == "goto":
            if value in (None, ""):
                raise ValueError("goto 步骤缺少 value")
            page.goto(str(value), wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5000))
            except Exception:
                page.wait_for_timeout(500)
        elif action == "wait":
            page.wait_for_timeout(int(value or 1000))
        elif action == "screenshot":
            ensure_report_dirs()
            screenshot = SCREENSHOT_DIR / f"{uuid4()}.png"
            page.screenshot(path=str(screenshot), full_page=True)
            screenshots.append(str(screenshot))
            detail["screenshot"] = str(screenshot)
        elif action == "assert_url":
            exact = bool(step.get("exact", False))
            _wait_for_url_contains(page, str(value or ""), timeout_ms, exact=exact)
        else:
            if action in UI_LOCATOR_REQUIRED and not candidates:
                raise ValueError(f"{action} 步骤缺少 locator")
            last_error = None
            for attempt in range(1, 4):
                try:
                    target, used_locator, matched_count = _resolve_locator(page, candidates, timeout_ms=min(timeout_ms, 5000))
                    detail["used_locator"] = used_locator
                    detail["matched_count"] = matched_count
                    if locator and used_locator != locator:
                        detail["healed"] = True
                        detail["original_locator"] = locator
                        detail["suggested_locator"] = used_locator
                    try:
                        target.scroll_into_view_if_needed(timeout=1500)
                    except Exception:
                        pass
                    if action == "input":
                        try:
                            target.fill("", timeout=timeout_ms)
                            target.fill(str(value or ""), timeout=timeout_ms)
                        except Exception:
                            target.click(timeout=timeout_ms)
                            page.keyboard.press("Control+A")
                            page.keyboard.type(str(value or ""))
                    elif action == "click":
                        target.click(timeout=timeout_ms)
                    elif action == "select":
                        target.select_option(str(value or ""), timeout=timeout_ms)
                    elif action == "check":
                        target.check(timeout=timeout_ms)
                    elif action == "uncheck":
                        target.uncheck(timeout=timeout_ms)
                    elif action == "wait_for_selector":
                        target.wait_for(state="visible", timeout=timeout_ms)
                    elif action == "assert_visible":
                        if not target.is_visible(timeout=timeout_ms):
                            raise AssertionError(f"assert_visible failed: locator {used_locator!r} is not visible")
                    elif action == "assert_value":
                        actual = target.input_value(timeout=timeout_ms)
                        if _normalize_text(value) != _normalize_text(actual):
                            raise AssertionError(f"assert_value failed: expected {value!r}, actual {actual!r}")
                    elif action == "text_assert":
                        text_value = target.inner_text(timeout=timeout_ms)
                        if _normalize_text(value) not in _normalize_text(text_value):
                            raise AssertionError(f"text_assert failed: expected {value!r}, actual {text_value!r}")
                    else:
                        raise ValueError(f"Unsupported UI action: {action}")
                    if attempt > 1:
                        detail["retry_count"] = attempt - 1
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt >= 3:
                        # 自愈尝试：解析定位器失败时尝试自愈
                        try:
                            healed = _heal_locator(page, candidates[0] if candidates else "", str(exc))
                            if healed and healed not in candidates:
                                candidates.insert(0, healed)
                                detail["healed"] = True
                                detail["healed_locator"] = healed
                                # 用新定位器再试一次
                                target, used_locator, matched_count = _resolve_locator(page, candidates, timeout_ms=min(timeout_ms, 5000))
                                detail["used_locator"] = used_locator
                                detail["matched_count"] = matched_count
                                target.scroll_into_view_if_needed(timeout=1500)
                                if action == "input":
                                    try:
                                        target.fill("", timeout=timeout_ms)
                                        target.fill(str(value or ""), timeout=timeout_ms)
                                    except Exception:
                                        target.click(timeout=timeout_ms)
                                        page.keyboard.press("Control+A")
                                        page.keyboard.type(str(value or ""))
                                elif action == "click":
                                    target.click(timeout=timeout_ms)
                                elif action == "select":
                                    target.select_option(str(value or ""), timeout=timeout_ms)
                                elif action == "assert_visible":
                                    if not target.is_visible(timeout=timeout_ms):
                                        raise AssertionError(f"assert_visible failed: locator {used_locator!r} is not visible")
                                elif action == "wait_for_selector":
                                    target.wait_for(state="visible", timeout=timeout_ms)
                                detail["retry_count"] = attempt
                                break
                        except Exception:
                            raise last_error
                        raise
                    page.wait_for_timeout(350 * attempt)
            if last_error and not detail.get("used_locator") and action not in {"goto", "wait", "screenshot", "assert_url"}:
                raise last_error
        detail["status"] = "passed"
        detail["current_url"] = page.url
        detail["current_url_after"] = getattr(page, "url", "")
        detail["visible_text_after"] = _page_text_excerpt(page, limit=800)
        after_shot = _capture_evidence_screenshot(page, "step-after", screenshots)
        if after_shot:
            detail["after_screenshot"] = after_shot
        detail["duration_ms"] = int((time.time() - started) * 1000)
        detail["finished_at"] = datetime.now()
        return detail
    except Exception as exc:
        error_text = str(exc)
        classified = _classify_ui_error(error_text, step, getattr(page, "url", ""))
        detail.update(
            {
                "status": "skipped" if step.get("optional") else "failed",
                "current_url": getattr(page, "url", ""),
                "current_url_after": getattr(page, "url", ""),
                "visible_text_after": _page_text_excerpt(page, limit=800),
                "duration_ms": int((time.time() - started) * 1000),
                "finished_at": datetime.now(),
                "error": error_text,
                **classified,
            }
        )
        failure_shot = _capture_evidence_screenshot(page, "step-failed", screenshots)
        if failure_shot:
            detail["failure_screenshot"] = failure_shot
        if step.get("optional"):
            return detail
        message = f"{name}失败：{classified['category']}。{classified['reason']}"
        raise UiStepExecutionError(message, detail) from exc


def _validate_ui_steps_for_execution(steps: Any) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    issues: list[Dict[str, Any]] = []
    if not isinstance(steps, Iterable) or isinstance(steps, (str, bytes, dict)):
        return [], [{"severity": "error", "message": "UI steps 必须是数组"}]
    normalized: list[Dict[str, Any]] = []
    for index, raw_step in enumerate(steps, start=1):
        if not isinstance(raw_step, dict):
            issues.append({"severity": "error", "step": index, "message": f"第{index}步不是对象"})
            continue
        step = dict(raw_step)
        action = str(step.get("action") or "").strip()
        if action not in UI_ACTION_LABELS:
            issues.append({"severity": "error", "step": index, "message": f"第{index}步 action 不支持：{action or '空'}"})
        if action in UI_LOCATOR_REQUIRED and not _locator_candidates(step):
            issues.append({"severity": "error", "step": index, "message": f"第{index}步缺少 locator"})
        if action in UI_VALUE_REQUIRED and step.get("value") in (None, ""):
            issues.append({"severity": "error", "step": index, "message": f"第{index}步缺少 value"})
        normalized.append(step)
    if normalized and not _case_has_business_assertion(normalized):
        issues.append({
            "severity": "warning",
            "message": "用例缺少业务断言，执行器会跑完整步骤，但不会把结果判定为可信成功",
        })
    return normalized, issues


def execute_ui_case_in_page(
    case: UiCase,
    page: Any,
    runtime_vars: Dict[str, Any] | None = None,
    execution_context: Dict[str, Any] | None = None,
    env: Env | None = None,
) -> Tuple[bool, str, str, str]:
    ensure_report_dirs()
    timeout = case.timeout or 30
    if env:
        variables = merge_variables(env, runtime_vars)
    else:
        variables = builtin_variables()
        if runtime_vars:
            variables.update(runtime_vars)
    raw_steps = parse_json_value(case.steps, [])
    page_url = render_template(case.page_url, variables)
    steps: list[Dict[str, Any]] = []
    validation_issues: list[Dict[str, Any]] = []
    execution_context = dict(execution_context or {})
    removed_login_steps: list[Dict[str, Any]] = []
    login_trace: list[str] = list(execution_context.get("login_trace") or [])
    # 读取重试配置
    retry_count = execution_context.get("retry_count", 2)
    retry_interval_ms = execution_context.get("retry_interval_ms", 1000)

    log_parts: Dict[str, Any] = {
        "case_name": case.case_name,
        "page_url": page_url,
        "steps": steps,
        "timeout": timeout,
        "variables": _mask_variables(variables),
        "validation_issues": validation_issues,
        "step_logs": [],
        "started_at": datetime.now(),
        "retry_config": {"retry_count": retry_count, "retry_interval_ms": retry_interval_ms},
        "auth_context": {
            "login_required": bool(execution_context.get("login_required")),
            "account_profile_id": execution_context.get("account_profile_id"),
            "login_url": (execution_context.get("login_config") or {}).get("login_url") or "",
            "removed_login_step_count": len(removed_login_steps),
        },
    }
    if login_trace:
        log_parts["auth_context"]["login_trace"] = login_trace
    screenshots: list[str] = []
    current_step_index = 0
    current_step: Dict[str, Any] | None = None
    failed_step_detail: Dict[str, Any] | None = None

    try:
        page.set_default_timeout(timeout * 1000)
        if execution_context.get("login_required") and not execution_context.get("preauthenticated"):
            try:
                auth_result = _prepare_authenticated_page(page, execution_context, variables, timeout)
            except UiAuthPreparationError as exc:
                login_trace = list(getattr(exc, 'trace', []) or [])
                log_parts["auth_context"]["login_trace"] = login_trace
                raise
            login_trace = auth_result.get("trace") or []
            log_parts["auth_context"]["login_trace"] = login_trace
            execution_context["preauthenticated"] = True
        if case.page_url:
            page.goto(page_url, wait_until="domcontentloaded")
            _wait_page_stable(page)
        inferred_variables = _business_variables_from_text(_page_text_excerpt(page, limit=12000))
        applied_variables = _merge_inferred_business_variables(variables, inferred_variables)
        steps = render_template(raw_steps, variables)
        if execution_context.get("login_required") or execution_context.get("strip_login_steps"):
            steps, removed_login_steps = _strip_leading_login_steps(steps)
        steps, runtime_replacements = _stabilize_runtime_steps(steps, variables)
        steps, validation_issues = _validate_ui_steps_for_execution(steps)
        log_parts.update(
            {
                "steps": steps,
                "variables": _mask_variables(variables),
                "validation_issues": validation_issues,
                "runtime_seed_variables": applied_variables,
                "runtime_step_replacements": runtime_replacements,
            }
        )
        log_parts["auth_context"]["removed_login_step_count"] = len(removed_login_steps)
        if any(item.get("severity") == "error" for item in validation_issues):
            log_parts.update(
                {
                    "error": "UI steps validation failed: " + "; ".join(item.get("message", "") for item in validation_issues),
                    "error_category": "step_validation_failed",
                    "finished_at": datetime.now(),
                }
            )
            log_text = _json_dump_log(log_parts)
            report_path = write_allure_result(case.case_name, "ui", False, log_text)
            return False, log_text, "", report_path
        for index, step in enumerate(steps, start=1):
            current_step_index = index
            current_step = step if isinstance(step, dict) else {"raw": step}
            # 智能等待：操作前等待页面稳定
            action = (current_step or {}).get("action", "")
            if action in ("click", "input", "select", "check", "uncheck"):
                _wait_page_stable(page, timeout=1500)

            try:
                step_detail = _run_ui_step(page, current_step, screenshots, timeout)
                step_detail["index"] = index
                log_parts["step_logs"].append(step_detail)
                # 智能等待：操作后等待页面响应
                _wait_after_action(page, action)
            except UiStepExecutionError as exc:
                # 失败自动重试
                if retry_count > 0 and action not in ("text_assert", "assert_url", "assert_value", "assert_visible"):
                    retried = False
                    for attempt in range(retry_count):
                        page.wait_for_timeout(retry_interval_ms)
                        _wait_page_stable(page)
                        try:
                            step_detail = _run_ui_step(page, current_step, screenshots, timeout)
                            step_detail["index"] = index
                            step_detail["retry_attempt"] = attempt + 1
                            log_parts["step_logs"].append(step_detail)
                            # 重试成功后截一张确认图，作为"步骤恢复"的证据
                            confirm_shot = SCREENSHOT_DIR / f"retry-confirm-{uuid4()}.png"
                            try:
                                page.screenshot(path=str(confirm_shot), full_page=True)
                                step_detail["retry_confirmation_screenshot"] = str(confirm_shot)
                                screenshots.append(str(confirm_shot))
                            except Exception:
                                pass
                            retried = True
                            break
                        except UiStepExecutionError:
                            continue
                    if retried:
                        continue
                failed_step_detail = exc.detail
                failed_step_detail["index"] = index
                log_parts["step_logs"].append(failed_step_detail)
                raise
        # 最终验证：强制截图 + URL + 截图质量检查
        final_screenshot = SCREENSHOT_DIR / f"{uuid4()}.png"
        try:
            page.screenshot(path=str(final_screenshot), full_page=True)
            screenshots.append(str(final_screenshot))
        except Exception as exc:
            final_screenshot = Path(screenshots[-1]) if screenshots else None

        # 三级验证
        final_url = getattr(page, "url", "")
        screenshot_check = _quick_screenshot_check(str(final_screenshot)) if final_screenshot else {"ok": False, "reason": "无法获取截图"}
        url_ok = _url_looks_reasonable(final_url, _expected_origin(str(case.page_url or "")))
        business_ok, business_issues, business_evidence = _final_business_verification(page, steps, timeout)

        verification_issues = []
        if not url_ok:
            verification_issues.append(f"最终 URL 异常：{final_url}")
        if not screenshot_check["ok"]:
            verification_issues.append(f"截图验证失败：{screenshot_check['reason']}")
        if not business_ok:
            verification_issues.extend(business_issues)

        if verification_issues:
            # 三级验证未通过 → 标记为 failed
            log_parts.update({
                "finished_at": datetime.now(),
                "verification_issues": verification_issues,
                "verification_status": "failed_verification",
                "business_verification": business_evidence,
                "verification_screenshot": str(final_screenshot) if final_screenshot else "",
                "warning": "所有步骤执行通过，但最终验证未通过：" + "; ".join(verification_issues),
            })
            log_text = _json_dump_log(log_parts)
            report_path = write_allure_result(case.case_name, "ui", False, log_text, str(final_screenshot) if final_screenshot else "")
            return False, log_text, str(final_screenshot) if final_screenshot else "", report_path

        log_parts.update({
            "finished_at": datetime.now(),
            "verification": {"screenshot_ok": True, "url_ok": True, "business_ok": True},
            "verification_status": "trusted_passed",
            "business_verification": business_evidence,
            "verification_screenshot": str(final_screenshot) if final_screenshot else "",
        })
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "ui", True, log_text, str(final_screenshot) if final_screenshot else screenshots[-1])
        return True, log_text, str(final_screenshot) if final_screenshot else screenshots[-1], report_path
    except Exception as exc:
        screenshot = ""
        try:
            screenshot_path = SCREENSHOT_DIR / f"{uuid4()}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            screenshot = str(screenshot_path)
        except Exception:
            screenshot = ""
        log_parts.update(
            {
                "error": str(exc),
                "error_category": failed_step_detail.get("category") if failed_step_detail else None,
                "failure_reason": failed_step_detail.get("reason") if failed_step_detail else None,
                "suggestion": failed_step_detail.get("suggestion") if failed_step_detail else None,
                "failed_step_index": current_step_index or None,
                "failed_step": current_step,
                "failed_step_detail": failed_step_detail,
                "current_url": getattr(page, "url", "") if page else "",
                "screenshot": screenshot,
                "auth_context": {**log_parts.get("auth_context", {}), "login_trace": login_trace},
                "finished_at": datetime.now(),
            }
        )
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "ui", False, log_text, screenshot)
        return False, log_text, screenshot, report_path


def execute_ui_cases_batch(
    items: Iterable[Dict[str, Any]],
    on_case_start: Any | None = None,
    on_case_finish: Any | None = None,
    parallelism: int = 1,
) -> list[Tuple[bool, str, str, str]]:
    ensure_report_dirs()
    batch_items = list(items)
    for item in batch_items:
        if item.get("functional_case_id"):
            execution_context = dict(item.get("execution_context") or {})
            execution_context["strip_login_steps"] = True
            item["execution_context"] = execution_context
    results: list[Tuple[bool, str, str, str]] = []
    worker_count = max(1, min(int(parallelism or 1), 3))
    has_scenario_chain = any(
        str((item.get("execution_context") or {}).get("execution_policy") or "").lower() == "scenario_chain"
        for item in batch_items
    )
    if worker_count == 1 and not has_scenario_chain and any(item.get("functional_case_id") for item in batch_items):
        for item in batch_items:
            if on_case_start:
                on_case_start(item)
            case = item["case"]
            execution_context = item.get("execution_context") or {}
            deadline = int(
                execution_context.get("case_timeout_seconds")
                or min(max((getattr(case, "timeout", None) or 30) + 15, 30), 60)
            )
            result = execute_ui_case_with_deadline(
                case,
                item.get("variables"),
                execution_context,
                deadline,
            )
            results.append(result)
            if on_case_finish:
                on_case_finish(item, result)
        return results
    if worker_count > 1:
        indexed_items = list(enumerate(batch_items))
        future_map = {}
        ordered_results: list[Tuple[bool, str, str, str] | None] = [None] * len(indexed_items)
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            for index, item in indexed_items:
                if on_case_start:
                    on_case_start(item)
                future_map[pool.submit(execute_ui_case, item["case"], item.get("variables"), item.get("execution_context"))] = (index, item)
            for future in as_completed(future_map):
                index, item = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    log_text = json.dumps({"error": str(exc), "error_category": "parallel_execution_failed"}, ensure_ascii=False)
                    result = (False, log_text, "", "")
                ordered_results[index] = result
                if on_case_finish:
                    on_case_finish(item, result)
        return [item for item in ordered_results if item is not None]

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        for item in batch_items:
            if on_case_start:
                on_case_start(item)
            result = execute_ui_case(item["case"], item.get("variables"), item.get("execution_context"))
            results.append(result)
            if on_case_finish:
                on_case_finish(item, result)
        return results

    browser = None
    pages: Dict[str, Any] = {}
    contexts: Dict[str, Any] = {}
    try:
        with sync_playwright() as p:
            browser = launch_chromium_browser(p, headless=True)
            for item in batch_items:
                if on_case_start:
                    on_case_start(item)
                execution_context = dict(item.get("execution_context") or {})
                case = item["case"]
                session_key = "guest"
                if execution_context.get("login_required"):
                    functional_case = item.get("functional_case")
                    session_key = str(execution_context.get("session_key") or f"auth:{getattr(functional_case, 'id', case.id)}")
                page = pages.get(session_key)
                if page is None:
                    context = browser.new_context()
                    page = context.new_page()
                    contexts[session_key] = context
                    pages[session_key] = page
                    if execution_context.get("login_required"):
                        execution_context["target_url"] = execution_context.get("target_url") or case.page_url or ""
                        auth_result = _prepare_authenticated_page(page, execution_context, item.get("variables") or {}, case.timeout or 30)
                        execution_context["login_trace"] = auth_result.get("trace") or []
                        execution_context["preauthenticated"] = True
                elif execution_context.get("login_required"):
                    if _looks_like_login_page(page, expected_url=(execution_context.get("login_config") or {}).get("login_url") or ""):
                        auth_result = _prepare_authenticated_page(page, execution_context, item.get("variables") or {}, case.timeout or 30)
                        execution_context["login_trace"] = auth_result.get("trace") or []
                    execution_context["preauthenticated"] = True
                if item.get("functional_case_id"):
                    execution_context["strip_login_steps"] = True
                item["execution_context"] = execution_context
                result = execute_ui_case_in_page(case, page, item.get("variables"), execution_context)
                results.append(result)
                if on_case_finish:
                    on_case_finish(item, result)
    except Exception as exc:
        if isinstance(exc, UiAuthPreparationError) or "登录前置失败" in str(exc):
            raise
        logger.warning("批量 UI 执行中途失败，已完成的 %d 个结果将保留，剩余用例逐一执行: %s", len(results), exc)
        processed_count = len(results)
        for item in batch_items[processed_count:]:
            if on_case_start:
                on_case_start(item)
            result = execute_ui_case(item["case"], item.get("variables"), item.get("execution_context"))
            results.append(result)
            if on_case_finish:
                on_case_finish(item, result)
    finally:
        for page in pages.values():
            try:
                page.close()
            except Exception:
                pass
        for context in contexts.values():
            try:
                context.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass
    return results


def preflight_ui_case(case: UiCase, runtime_vars: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ensure_report_dirs()
    variables = builtin_variables()
    if runtime_vars:
        variables.update(runtime_vars)
    steps = render_template(parse_json_value(case.steps, []), variables)
    page_url = render_template(case.page_url, variables)
    steps, issues = _validate_ui_steps_for_execution(steps)
    raw_text = json.dumps({"page_url": case.page_url, "steps": parse_json_value(case.steps, [])}, ensure_ascii=False)
    required_vars = sorted(set(VAR_PATTERN.findall(raw_text)) - BUILTIN_VAR_NAMES - {f"${key}" for key in BUILTIN_VAR_NAMES})
    missing_vars = [name for name in required_vars if name not in variables or str(variables.get(name, "")).startswith("{{")]
    locator_checks: list[Dict[str, Any]] = []
    auth_risk = False

    if missing_vars:
        issues.append({"severity": "error", "message": "缺少运行时变量：" + "、".join(missing_vars)})
    if any(item.get("severity") == "error" for item in issues):
        return {"status": "missing_variables" if missing_vars else "not_recommended", "issues": issues, "locator_checks": locator_checks, "missing_variables": missing_vars}

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {"status": "not_recommended", "issues": [{"severity": "error", "message": f"Playwright不可用：{exc}"}], "locator_checks": locator_checks}

    browser = None
    try:
        with sync_playwright() as p:
            browser = launch_chromium_browser(p, headless=True)
            page = browser.new_page()
            page.set_default_timeout(8000)
            first_goto = next((step.get("value") for step in steps if step.get("action") == "goto" and step.get("value")), page_url)
            if first_goto:
                page.goto(str(first_goto), wait_until="domcontentloaded", timeout=12000)
                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    page.wait_for_timeout(300)
            auth_risk = "login" in (page.url or "").lower() and "login" not in str(first_goto or "").lower()
            for index, step in enumerate(steps, start=1):
                if step.get("action") not in UI_LOCATOR_REQUIRED:
                    continue
                candidates = _locator_candidates(step)
                check = {"step": index, "name": step.get("name") or UI_ACTION_LABELS.get(step.get("action"), step.get("action")), "locator": step.get("locator"), "status": "failed", "matched_count": 0, "visible": False}
                for locator in candidates:
                    try:
                        count = page.locator(locator).count()
                        visible = count > 0 and page.locator(locator).first.is_visible(timeout=600)
                        if count:
                            check.update({"status": "ok" if visible else "not_visible", "used_locator": locator, "matched_count": count, "visible": visible})
                            break
                    except Exception as exc:
                        check["error"] = str(exc)
                if check["status"] != "ok":
                    issues.append({"severity": "warning", "step": index, "message": f"第{index}步定位器可能不可用：{step.get('locator') or '-'}"})
                locator_checks.append(check)
            browser.close()
            browser = None
    except Exception as exc:
        issues.append({"severity": "warning", "message": f"页面试跑检查未完成：{exc}"})
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass

    warning_count = sum(1 for item in issues if item.get("severity") == "warning")
    if auth_risk:
        status_value = "auth_risk"
    elif missing_vars:
        status_value = "missing_variables"
    elif warning_count:
        status_value = "locator_risk"
    else:
        status_value = "executable"
    return {
        "status": status_value,
        "issues": issues,
        "locator_checks": locator_checks,
        "missing_variables": missing_vars,
        "auth_risk": auth_risk,
        "summary": "可执行" if status_value == "executable" else "存在执行风险，请查看检查详情",
    }


def execute_ui_case(
    case: UiCase,
    runtime_vars: Dict[str, Any] | None = None,
    execution_context: Dict[str, Any] | None = None,
    env: Env | None = None,
) -> Tuple[bool, str, str, str]:
    ensure_report_dirs()
    timeout = case.timeout or 30
    if env:
        variables = merge_variables(env, runtime_vars)
    else:
        variables = builtin_variables()
        if runtime_vars:
            variables.update(runtime_vars)
    steps = render_template(parse_json_value(case.steps, []), variables)
    steps, validation_issues = _validate_ui_steps_for_execution(steps)

    log_parts: Dict[str, Any] = {
        "case_name": case.case_name,
        "page_url": render_template(case.page_url, variables),
        "steps": steps,
        "timeout": timeout,
        "variables": _mask_variables(variables),
        "validation_issues": validation_issues,
        "step_logs": [],
        "started_at": datetime.now(),
    }
    if any(item.get("severity") == "error" for item in validation_issues):
        log_parts.update(
            {
                "error": "UI步骤校验失败：" + "；".join(item.get("message", "") for item in validation_issues),
                "error_category": "步骤结构错误",
                "finished_at": datetime.now(),
            }
        )
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "ui", False, log_text)
        return False, log_text, "", report_path

    screenshots: list[str] = []
    current_step_index = 0
    current_step: Dict[str, Any] | None = None
    failed_step_detail: Dict[str, Any] | None = None

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
            try:
                passed, log_text, screenshot_path, report_path = execute_ui_case_in_page(case, page, runtime_vars, execution_context)
            except Exception as inner_exc:
                # 在 with 块内捕获异常，此时 browser/page 仍存活
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
                    browser = None
                log_parts.update(
                    {
                        "error": str(inner_exc),
                        "error_category": failed_step_detail.get("category") if failed_step_detail else None,
                        "failure_reason": failed_step_detail.get("reason") if failed_step_detail else None,
                        "suggestion": failed_step_detail.get("suggestion") if failed_step_detail else None,
                        "failed_step_index": current_step_index or None,
                        "failed_step": current_step,
                        "failed_step_detail": failed_step_detail,
                        "current_url": getattr(page, "url", "") if page else "",
                        "screenshot": screenshot,
                        "finished_at": datetime.now(),
                    }
                )
                log_text = _json_dump_log(log_parts)
                report_path = write_allure_result(case.case_name, "ui", False, log_text, screenshot)
                return False, log_text, screenshot, report_path
            try:
                browser.close()
            except Exception:
                pass
            browser = None
            return passed, log_text, screenshot_path, report_path
    except Exception as exc:
        # 这里的异常只可能来自 sync_playwright() 或 launch 阶段（在 with 块外）
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
                "error_category": failed_step_detail.get("category") if failed_step_detail else None,
                "failure_reason": failed_step_detail.get("reason") if failed_step_detail else None,
                "suggestion": failed_step_detail.get("suggestion") if failed_step_detail else None,
                "failed_step_index": current_step_index or None,
                "failed_step": current_step,
                "failed_step_detail": failed_step_detail,
                "current_url": getattr(page, "url", "") if page else "",
                "screenshot": screenshot,
                "finished_at": datetime.now(),
            }
        )
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "ui", False, log_text, screenshot)
        return False, log_text, screenshot, report_path


def execute_ui_case_with_deadline(
    case: UiCase,
    runtime_vars: Dict[str, Any] | None,
    execution_context: Dict[str, Any] | None,
    deadline_seconds: int,
) -> Tuple[bool, str, str, str]:
    result_queue: queue.Queue[Tuple[bool, str, str, str] | BaseException] = queue.Queue(maxsize=1)

    def _runner() -> None:
        try:
            result_queue.put(execute_ui_case(case, runtime_vars, execution_context))
        except BaseException as exc:
            result_queue.put(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(max(1, deadline_seconds))
    if thread.is_alive():
        log_text = json.dumps(
            {
                "case_name": case.case_name,
                "page_url": case.page_url,
                "current_url": case.page_url,
                "error": f"功能用例执行超过 {deadline_seconds} 秒仍未结束，已按超时终止本轮等待",
                "error_category": "case_timeout",
                "environment_reason": "case_execution_timeout",
                "failed_step": {"action": "case_timeout", "timeout_seconds": deadline_seconds},
                "suggestion": "缩短或拆分该用例步骤，检查页面是否有长时间加载、弹窗遮挡或定位器一直等待",
                "timeout_seconds": deadline_seconds,
                "finished_at": datetime.now(),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        report_path = write_allure_result(case.case_name, "ui", False, log_text)
        return False, log_text, "", report_path
    if result_queue.empty():
        log_text = json.dumps(
            {
                "case_name": case.case_name,
                "page_url": case.page_url,
                "current_url": case.page_url,
                "error": "功能用例执行线程结束但没有返回结果",
                "error_category": "system_error",
                "failed_step": {"action": "system_error"},
                "finished_at": datetime.now(),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        report_path = write_allure_result(case.case_name, "ui", False, log_text)
        return False, log_text, "", report_path
    result = result_queue.get()
    if isinstance(result, BaseException):
        log_text = json.dumps(
            {
                "case_name": case.case_name,
                "page_url": case.page_url,
                "error": str(result),
                "error_category": "system_error",
                "finished_at": datetime.now(),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        report_path = write_allure_result(case.case_name, "ui", False, log_text)
        return False, log_text, "", report_path
    return result


# ═══════════════════════════════════════════════════════════
# 操作模板匹配
# ═══════════════════════════════════════════════════════════


def _template_match_keywords(text: str, keywords: list[str]) -> int:
    """计算文本与关键词列表的匹配分"""
    text_lower = text.lower()
    score = 0
    for kw in keywords:
        kw_lower = kw.lower().strip()
        if not kw_lower:
            continue
        if kw_lower in text_lower:
            score += 10
            if text_lower.startswith(kw_lower) or text_lower.endswith(kw_lower):
                score += 5
    return score


def match_action_template(
    case_title: str,
    case_steps: str,
    templates: list[ActionTemplate],
) -> ActionTemplate | None:
    """根据用例标题和步骤文本匹配最佳操作模板"""
    if not templates:
        return None
    best_score = 0
    best_template = None
    for template in templates:
        try:
            keywords = json.loads(template.trigger_keywords) if isinstance(template.trigger_keywords, str) else (template.trigger_keywords or [])
        except (json.JSONDecodeError, TypeError):
            keywords = []
        if not keywords:
            continue
        title_score = _template_match_keywords(case_title, keywords) * 2
        steps_score = _template_match_keywords(case_steps or "", keywords)
        total = title_score + steps_score
        if total > best_score:
            best_score = total
            best_template = template
    return best_template if best_score > 0 else None


# ═══════════════════════════════════════════════════════════
# 执行前预检
# ═══════════════════════════════════════════════════════════


def _extract_variables_from_text(text: str) -> set[str]:
    if not text:
        return set()
    return set(re.findall(r"\{\{(\w+)\}\}", text))


def preflight_check(case: UiCase) -> tuple[list[str], list[str]]:
    """执行前预检，返回 (errors, warnings)"""
    errors: list[str] = []
    warnings: list[str] = []

    if not case.steps:
        errors.append("用例没有步骤")
        return errors, warnings

    steps = parse_json_value(case.steps, [])
    if not isinstance(steps, list) or len(steps) == 0:
        errors.append("步骤格式无效或为空")
        return errors, warnings

    page_url = case.page_url or ""
    if page_url:
        try:
            resp = requests.head(page_url, timeout=5, allow_redirects=True)
            if resp.status_code == 405:
                # 部分服务器不支持 HEAD，回退到 GET
                try:
                    resp = requests.get(page_url, timeout=5, allow_redirects=True)
                except Exception:
                    pass
            if resp.status_code >= 500:
                errors.append(f"目标页面返回服务端错误 HTTP {resp.status_code}")
            elif resp.status_code >= 400:
                warnings.append(f"目标页面返回 HTTP {resp.status_code}，可能存在访问问题")
        except requests.ConnectionError:
            errors.append(f"目标页面不可达: {page_url}")
        except Exception as exc:
            warnings.append(f"URL 检查失败: {exc}")

    needed_vars: set[str] = set()
    for step in steps:
        if isinstance(step, dict):
            for field in ("locator", "value", "name"):
                needed_vars |= _extract_variables_from_text(str(step.get(field, "")))

    builtin = {"timestamp", "datetime", "date", "uuid", "random_int", "random_str", "random_phone", "random_email"}
    external_needed = needed_vars - builtin
    if external_needed:
        warnings.append(f"步骤中使用的外部变量（需确保运行时提供）: {', '.join(sorted(external_needed))}")

    try:
        import playwright  # noqa: F401
    except ImportError:
        errors.append("Playwright 未安装，请执行: pip install playwright && python -m playwright install")

    return errors, warnings


# ═══════════════════════════════════════════════════════════
# Locator 自愈
# ═══════════════════════════════════════════════════════════


def _heal_locator(page: Any, failed_locator: str, error_text: str) -> str | None:
    """尝试修复失败的定位器，返回新定位器或 None"""
    heal_candidates: list[str] = []

    # 策略 1: text=xxx → 跳过原始定位器，直接尝试包含匹配 / partial text
    if failed_locator.startswith("text="):
        target_text = failed_locator[5:].strip().strip("\"'")
        if target_text:
            # 转义双引号防止注入到 Playwright 选择器语法中
            safe_text = target_text.replace('"', '\\"')
            try:
                # 先试 :has-text（比 text= 更灵活）
                partial = page.locator(f':has-text("{safe_text}")')
                if partial.count() > 0:
                    heal_candidates.append(f':has-text("{safe_text}")')
                for tag in ["button", "a", "span", "div"]:
                    exact = page.locator(f'{tag}:has-text("{safe_text}")')
                    if exact.count() > 0:
                        heal_candidates.append(f'{tag}:has-text("{safe_text}")')
                # 最后试原始 text= 精确匹配（可能因为 DOM 刷新后重新可用）
                contains = page.locator(f"text={target_text}")
                if contains.count() > 0:
                    heal_candidates.append(f"text={target_text}")
            except Exception:
                pass

    # 策略 2: CSS 选择器 → 简化
    if not failed_locator.startswith("text="):
        simplified = re.sub(r"\.[a-zA-Z][\w-]*", "", failed_locator)
        if simplified != failed_locator:
            try:
                el = page.locator(simplified)
                if el.count() > 0:
                    heal_candidates.append(simplified)
            except Exception:
                pass
        ids = re.findall(r"#([a-zA-Z][\w-]*)", failed_locator)
        if ids:
            try:
                el = page.locator(f"#{ids[-1]}")
                if el.count() > 0:
                    heal_candidates.append(f"#{ids[-1]}")
            except Exception:
                pass

    return heal_candidates[0] if heal_candidates else None


# ═══════════════════════════════════════════════════════════
# 智能等待
# ═══════════════════════════════════════════════════════════


def _wait_page_stable(page: Any, timeout: int = 1500) -> None:
    """等待页面加载稳定"""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception:
        pass
    page.wait_for_timeout(300)


def _wait_after_action(page: Any, action: str) -> None:
    """根据操作类型等待页面响应"""
    if action in ("click", "select", "check", "uncheck"):
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            page.wait_for_timeout(500)
    elif action == "input":
        page.wait_for_timeout(100)
    elif action == "goto":
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            page.wait_for_timeout(500)


def _capture_evidence_screenshot(page: Any, prefix: str, screenshots: list[str]) -> str:
    ensure_report_dirs()
    target = SCREENSHOT_DIR / f"{prefix}-{uuid4()}.png"
    try:
        page.screenshot(path=str(target), full_page=True)
        screenshots.append(str(target))
        return str(target)
    except Exception:
        return ""


def _page_text_excerpt(page: Any, limit: int = 1200) -> str:
    try:
        text = page.locator("body").inner_text(timeout=1200)
    except Exception:
        return ""
    text = _normalize_text(text)
    return text[:limit]


def _expected_origin(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _step_has_business_assertion(step: Dict[str, Any]) -> bool:
    if not isinstance(step, dict):
        return False
    if step.get("action") in {"assert_url", "assert_visible", "assert_value", "text_assert"}:
        return True
    return bool(step.get("assertions") or step.get("success_condition"))


def _case_has_business_assertion(steps: list[Dict[str, Any]]) -> bool:
    return any(_step_has_business_assertion(step) for step in steps if isinstance(step, dict))


def _check_success_condition(page: Any, condition: Any, timeout_ms: int) -> list[str]:
    if not condition:
        return []
    conditions = condition if isinstance(condition, list) else [condition]
    failures: list[str] = []
    for item in conditions:
        if isinstance(item, str):
            item = {"text_contains": item}
        if not isinstance(item, dict):
            continue
        if item.get("url_contains"):
            expected = str(item.get("url_contains") or "")
            if expected not in str(getattr(page, "url", "")):
                failures.append(f"URL 未包含预期片段：{expected}")
        if item.get("url_exact"):
            expected = str(item.get("url_exact") or "").rstrip("/")
            if str(getattr(page, "url", "")).rstrip("/") != expected:
                failures.append(f"URL 未精确匹配：{expected}")
        if item.get("text_contains"):
            expected = str(item.get("text_contains") or "")
            if expected not in _page_text_excerpt(page, limit=8000):
                failures.append(f"页面文本未包含：{expected}")
        selector = item.get("selector_visible") or item.get("locator_visible")
        if selector:
            try:
                page.locator(str(selector)).first.wait_for(state="visible", timeout=timeout_ms)
            except Exception:
                failures.append(f"未看到成功元素：{selector}")
    return failures


def _final_business_verification(page: Any, steps: list[Dict[str, Any]], timeout_seconds: int) -> tuple[bool, list[str], dict[str, Any]]:
    issues: list[str] = []
    assertion_count = sum(1 for step in steps if _step_has_business_assertion(step))
    if assertion_count == 0:
        issues.append("用例缺少业务断言：没有 assert_url/assert_visible/assert_value/text_assert/success_condition，不能判定为可信成功")
    timeout_ms = max(1000, min(timeout_seconds, 12) * 1000)
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        failures = _check_success_condition(page, step.get("success_condition") or step.get("assertions"), timeout_ms)
        issues.extend(f"第{index}步成功条件失败：{item}" for item in failures)
    evidence = {
        "business_assertion_count": assertion_count,
        "final_url": getattr(page, "url", ""),
        "final_text_excerpt": _page_text_excerpt(page),
    }
    return not issues, issues, evidence
