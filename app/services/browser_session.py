"""实时浏览器录制会话服务。

启动可见 Chromium（async_playwright），用户在其中操作时实时捕获 XHR/fetch 接口请求，
停止后把事件转成 HAR 兼容格式，复用 har_recorder 链路沉淀为 RecordedFlow。
"""

import asyncio
import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from playwright.async_api import async_playwright

# 静态资源后缀过滤
_STATIC_EXT = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ico", ".ttf", ".otf")
# 会话最大空闲时长（30 分钟）
_SESSION_TIMEOUT = 30 * 60
# 清理任务扫描间隔（5 分钟）
_CLEANUP_INTERVAL = 5 * 60
_SAFE_HEADER_NAMES = {"accept", "content-type", "x-requested-with"}
_SENSITIVE_FIELD_NAMES = {
    "access_token", "auth_code", "authorization", "captcha", "captcha_code", "code", "compute_token",
    "cookie", "mobile", "mobile_no", "mobile_number", "mobile_phone", "otp", "passwd", "password",
    "phone", "phone_no", "phone_number", "pwd", "refresh_token", "sms_captcha", "sms_code", "tel",
    "telephone", "token", "user_token", "usertoken", "validation_code", "verification_code", "verify_code",
}
_REDACTED = "[REDACTED]"
_MAX_CAPTURE_TEXT = 100_000


def _normalize_field_name(name: Any) -> str:
    text = str(name or "").strip().replace("-", "_")
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text).lower()


def _is_sensitive_field(name: Any) -> bool:
    text = _normalize_field_name(name)
    return text in _SENSITIVE_FIELD_NAMES or text == "code" or text.endswith(("_code", "_password", "_token"))


def sanitize_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in (headers or {}).items():
        lowered = str(name).strip().lower()
        if lowered in _SAFE_HEADER_NAMES:
            result[lowered] = str(value)[:1000]
    return result


def sanitize_mapping(value: Any, *, depth: int = 0) -> Any:
    if depth >= 8:
        return "[MAX_DEPTH]"
    if isinstance(value, dict):
        return {
            str(key): (_REDACTED if _is_sensitive_field(key) else sanitize_mapping(item, depth=depth + 1))
            for key, item in list(value.items())[:200]
        }
    if isinstance(value, list):
        return [sanitize_mapping(item, depth=depth + 1) for item in value[:200]]
    if isinstance(value, str):
        return value[:_MAX_CAPTURE_TEXT]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:_MAX_CAPTURE_TEXT]


def sanitize_body(text: str, content_type: str) -> str:
    raw = str(text or "")[:_MAX_CAPTURE_TEXT]
    lowered = str(content_type or "").lower()
    if not raw:
        return ""
    if "json" in lowered:
        parsed = _try_parse_json(raw)
        return json.dumps(sanitize_mapping(parsed), ensure_ascii=False) if parsed is not None else "[INVALID_JSON_OMITTED]"
    if "application/x-www-form-urlencoded" in lowered:
        pairs = parse_qsl(raw, keep_blank_values=True)
        sanitized = [(key, _REDACTED if _is_sensitive_field(key) else value[:_MAX_CAPTURE_TEXT]) for key, value in pairs]
        return urlencode(sanitized)
    return "[UNSUPPORTED_BODY_OMITTED]"


def sanitize_response_body(text: str, content_type: str) -> Any:
    raw = str(text or "")[:_MAX_CAPTURE_TEXT]
    if "json" not in str(content_type or "").lower():
        return "[NON_JSON_RESPONSE_OMITTED]" if raw else ""
    parsed = _try_parse_json(raw)
    return sanitize_mapping(parsed) if parsed is not None else "[INVALID_JSON_RESPONSE_OMITTED]"


def sanitize_url(url: str) -> tuple[str, dict[str, str]]:
    parsed = urlsplit(str(url or ""))
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    safe_pairs = [(key, _REDACTED if _is_sensitive_field(key) else value[:1000]) for key, value in pairs]
    safe_query = urlencode(safe_pairs)
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    safe_netloc = f"{hostname}:{port}" if port is not None else hostname
    safe_url = urlunsplit((parsed.scheme, safe_netloc, parsed.path, safe_query, ""))
    return safe_url, dict(safe_pairs)


class _Session:
    """单个录制会话的运行时状态。"""

    def __init__(self, playwright: Any, browser: Any, context: Any, page: Any) -> None:
        self.playwright = playwright
        self.browser = browser
        self.context = context
        self.page = page
        self.events: list[dict] = []
        self.state = "login_ready"
        self.last_activity: float = time.time()


_SESSIONS: dict[str, _Session] = {}
_LOCK = asyncio.Lock()
_cleanup_started = False


def _browser_executable_candidates() -> list[str]:
    """收集系统可用的 Chrome/Edge/Chromium 可执行文件路径。"""
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
        ("LOCALAPPDATA", r"Chromium\Application\chrome.exe"),
    ]:
        root = os.getenv(env_name)
        if root:
            candidates.append(str(Path(root) / relative))
    for command in ["chrome", "chrome.exe", "msedge", "msedge.exe", "chromium", "chromium.exe"]:
        found = shutil.which(command)
        if found:
            candidates.append(found)
    playwright_browsers = os.getenv(
        "PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / "AppData" / "Local" / "ms-playwright")
    )
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


async def _launch_chromium(playwright: Any) -> Any:
    """启动 headed Chromium，按 default → channel → executable_path 顺序尝试。"""
    args = ["--no-sandbox", "--disable-gpu", "--ignore-certificate-errors"]
    launch_kwargs = {"headless": False, "args": args}
    errors: list[str] = []
    # 1) 默认启动（Playwright 内置浏览器）
    try:
        return await playwright.chromium.launch(**launch_kwargs)
    except Exception as exc:
        errors.append(f"default: {exc}")
    # 2) 指定通道启动
    for channel in ["chrome", "msedge"]:
        try:
            return await playwright.chromium.launch(channel=channel, **launch_kwargs)
        except Exception as exc:
            errors.append(f"channel={channel}: {exc}")
    # 3) 逐一路径尝试
    for executable_path in _browser_executable_candidates():
        try:
            return await playwright.chromium.launch(executable_path=executable_path, **launch_kwargs)
        except Exception as exc:
            errors.append(f"{Path(executable_path).name}: {exc}")
    raise RuntimeError(
        "浏览器启动失败，未找到可用的 Chrome/Edge/Chromium。"
        f" 最后错误：{'; '.join(errors[-3:])}"
    )


def _is_static_resource(url: str) -> bool:
    """判断 URL 是否为静态资源（按后缀过滤）。"""
    try:
        path = urlsplit(url).path.lower()
    except Exception:
        path = url.lower()
    return path.endswith(_STATIC_EXT)


def _is_interesting_request(request: Any) -> bool:
    """过滤静态资源与非 XHR/fetch 请求。"""
    url = request.url or ""
    if not url.lower().startswith(("http://", "https://")):
        return False
    if _is_static_resource(url):
        return False
    try:
        resource_type = (request.resource_type or "").lower()
    except Exception:
        resource_type = ""
    # 仅捕获 XHR/fetch 类请求
    if resource_type not in ("xhr", "fetch"):
        return False
    return True


def _try_parse_json(text: str):
    """尝试 JSON 解析，失败返回 None。"""
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def get_session_state(session_id: str) -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")
    return {"session_id": session_id, "status": session.state, "event_count": len(session.events)}


def start_checkpoint(session_id: str) -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")
    session.events.clear()
    session.state = "capturing"
    session.last_activity = time.time()
    return get_session_state(session_id)


def stop_checkpoint(session_id: str) -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")
    session.state = "frozen"
    session.last_activity = time.time()
    return get_session_state(session_id)


def _on_request_sync(session: _Session, request: Any) -> None:
    """同步处理 request 事件：收集请求信息追加到事件列表。"""
    if session.state != "capturing":
        return
    if not _is_interesting_request(request):
        return
    try:
        try:
            raw_headers = dict(request.headers) if request.headers else {}
        except Exception:
            raw_headers = {}
        try:
            post_data = request.post_data or ""
        except Exception:
            post_data = ""
        safe_url, safe_query = sanitize_url(request.url or "")
        content_type = str(raw_headers.get("content-type") or raw_headers.get("Content-Type") or "")
        event = {
            "method": request.method or "GET",
            "url": safe_url,
            "path": urlsplit(safe_url).path or "",
            "query": safe_query,
            "headers": sanitize_headers(raw_headers),
            "body": sanitize_body(post_data, content_type),
            "response_status": None,
            "response_body": None,
            "started_at": datetime.now().isoformat(),
            "_request_id": id(request),
        }
        session.events.append(event)
        session.last_activity = time.time()
    except Exception:
        return


async def _on_response_async(session: _Session, response: Any) -> None:
    """异步处理 response 事件：补充响应状态与响应体。"""
    try:
        request = response.request
        request_id = id(request)
        event: dict | None = None
        # 从后往前找（事件按时间顺序追加）
        for ev in reversed(session.events):
            if ev.get("_request_id") == request_id:
                event = ev
                break
        if not event:
            return
        event["response_status"] = response.status
        try:
            # 限制 10 秒，避免大响应或流式响应阻塞
            response_headers = dict(response.headers) if response.headers else {}
            content_type = str(response_headers.get("content-type") or response_headers.get("Content-Type") or "")
            text = await asyncio.wait_for(response.text(), timeout=10)
            event["response_body"] = sanitize_response_body(text, content_type)
        except Exception:
            event["response_body"] = ""
        session.last_activity = time.time()
    except Exception:
        return


def _register_handlers(session: _Session) -> None:
    """在 page 上挂 request/response 事件监听。"""

    def on_request(request: Any) -> None:
        _on_request_sync(session, request)

    def on_response(response: Any) -> None:
        # 异步处理 response.text()，确保不阻塞事件循环
        try:
            asyncio.ensure_future(_on_response_async(session, response))
        except RuntimeError:
            # 无运行中的事件循环时跳过（理论上不会发生）
            pass

    session.page.on("request", on_request)
    session.page.on("response", on_response)


async def start_session(start_url: str) -> str:
    """启动可见浏览器并打开起始页，返回 session_id。"""
    global _cleanup_started
    pw = await async_playwright().start()
    browser = await _launch_chromium(pw)
    context = await browser.new_context()
    page = await context.new_page()
    session = _Session(pw, browser, context, page)
    _register_handlers(session)
    async with _LOCK:
        session_id = uuid4().hex
        _SESSIONS[session_id] = session
    # 启动清理任务（仅一次）
    if not _cleanup_started:
        _cleanup_started = True
        asyncio.create_task(_cleanup_loop())
    # 跳转到起始页
    try:
        await page.goto(start_url, wait_until="domcontentloaded")
    except Exception:
        # 跳转失败不阻塞会话创建，用户可手动 navigate
        pass
    return session_id


async def navigate_session(session_id: str, url: str) -> None:
    """会话内跳转到新 URL。"""
    async with _LOCK:
        session = _SESSIONS.get(session_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")
    await session.page.goto(url, wait_until="domcontentloaded")
    session.last_activity = time.time()


def get_events(session_id: str) -> list[dict]:
    """返回会话事件列表副本（去掉内部字段）。"""
    session = _SESSIONS.get(session_id)
    if not session:
        return []
    result = []
    for ev in session.events:
        copy = {k: v for k, v in ev.items() if not k.startswith("_")}
        result.append(copy)
    return result


async def close_session(session_id: str) -> None:
    """关闭会话：按相反顺序关闭 page/context/browser/playwright，异常吞掉。"""
    async with _LOCK:
        session = _SESSIONS.pop(session_id, None)
    if not session:
        return
    for closer in (session.page.close, session.context.close, session.browser.close, session.playwright.stop):
        try:
            await closer()
        except Exception:
            pass


async def _cleanup_loop() -> None:
    """后台清理任务：每 5 分钟扫描，超 30 分钟未活动的会话自动关闭。"""
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        now = time.time()
        expired: list[str] = []
        async with _LOCK:
            for sid, session in list(_SESSIONS.items()):
                if now - session.last_activity > _SESSION_TIMEOUT:
                    expired.append(sid)
        for sid in expired:
            try:
                await close_session(sid)
            except Exception:
                pass
