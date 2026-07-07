import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from playwright.async_api import async_playwright

from .browser_session import _launch_chromium

_SESSION_TIMEOUT = 30 * 60
_CLEANUP_INTERVAL = 5 * 60
_MAX_EVENTS = 2000


RECORDING_SCRIPT = r"""
(() => {
  if (window.__uiRecorderInstalled) return;
  window.__uiRecorderInstalled = true;

  const trimText = (value, max = 100) => String(value || "").replace(/\s+/g, " ").trim().slice(0, max);
  const cssEscape = (value) => {
    if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(String(value));
    return String(value).replace(/[^a-zA-Z0-9_-]/g, (ch) => `\\${ch}`);
  };
  const quoteCss = (value) => String(value || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  const pushUnique = (items, value) => {
    const text = String(value || "").trim();
    if (text && !items.includes(text)) items.push(text);
  };
  const targetElement = (raw) => {
    if (!raw) return null;
    if (raw.nodeType === Node.ELEMENT_NODE) return raw;
    return raw.parentElement || null;
  };
  const elementText = (el) => {
    if (!el) return "";
    return trimText(el.innerText || el.textContent || el.value || el.getAttribute("title") || "");
  };
  const cssPath = (el) => {
    const parts = [];
    let node = el;
    let depth = 0;
    while (node && node.nodeType === Node.ELEMENT_NODE && node !== document.documentElement && depth < 5) {
      const tag = node.tagName.toLowerCase();
      if (!tag || tag === "body") break;
      let nth = 1;
      let prev = node.previousElementSibling;
      while (prev) {
        if (prev.tagName.toLowerCase() === tag) nth += 1;
        prev = prev.previousElementSibling;
      }
      parts.unshift(`${tag}:nth-of-type(${nth})`);
      node = node.parentElement;
      depth += 1;
    }
    return parts.length ? parts.join(" > ") : "";
  };
  const locatorInfo = (el) => {
    const candidates = [];
    const tag = (el.tagName || "").toLowerCase();
    const dataTestId = el.getAttribute("data-testid");
    const dataTest = el.getAttribute("data-test");
    const id = el.getAttribute("id");
    const name = el.getAttribute("name");
    const placeholder = el.getAttribute("placeholder");
    const ariaLabel = el.getAttribute("aria-label");
    const role = el.getAttribute("role");
    const text = elementText(el);
    if (dataTestId) pushUnique(candidates, `[data-testid="${quoteCss(dataTestId)}"]`);
    if (dataTest) pushUnique(candidates, `[data-test="${quoteCss(dataTest)}"]`);
    if (id) pushUnique(candidates, `#${cssEscape(id)}`);
    if (name) pushUnique(candidates, `[name="${quoteCss(name)}"]`);
    if (placeholder) {
      const base = tag === "textarea" ? "textarea" : "input";
      pushUnique(candidates, `${base}[placeholder="${quoteCss(placeholder)}"]`);
      pushUnique(candidates, `[placeholder="${quoteCss(placeholder)}"]`);
    }
    if (ariaLabel) pushUnique(candidates, `[aria-label="${quoteCss(ariaLabel)}"]`);
    if (text) {
      const quoted = quoteCss(text);
      if (tag === "button") pushUnique(candidates, `button:has-text("${quoted}")`);
      if (tag === "a") pushUnique(candidates, `a:has-text("${quoted}")`);
      if (role) pushUnique(candidates, `[role="${quoteCss(role)}"]:has-text("${quoted}")`);
      pushUnique(candidates, `text="${quoted}"`);
    }
    pushUnique(candidates, cssPath(el));
    return {
      locator: candidates[0] || "",
      fallback_locators: candidates.slice(1),
      text,
      tag,
      input_type: (el.getAttribute("type") || "").toLowerCase(),
    };
  };
  const send = (payload) => {
    try {
      if (typeof window.__recordUiEvent !== "function") return;
      payload.url = window.location.href;
      payload.created_at = new Date().toISOString();
      Promise.resolve(window.__recordUiEvent(payload)).catch(() => {});
    } catch (error) {
      // recorder failure must not affect the target page
    }
  };
  const recordValue = (el, eventType) => {
    const info = locatorInfo(el);
    const tag = info.tag;
    const inputType = info.input_type;
    let action = "input";
    let value = "";
    let checked = undefined;
    if (tag === "select") {
      action = "select";
      value = el.value;
    } else if (tag === "input" && (inputType === "checkbox" || inputType === "radio")) {
      action = el.checked ? "check" : "uncheck";
      checked = Boolean(el.checked);
      value = el.value || "";
    } else if (el.isContentEditable) {
      value = el.innerText || "";
    } else {
      value = el.value || "";
    }
    send({ event_type: eventType, action, value, checked, ...info });
  };

  document.addEventListener("click", (event) => {
    const start = targetElement(event.target);
    const el = start && start.closest('a,button,[role="button"],input,textarea,select,label,summary,[onclick]');
    if (!el) return;
    const tag = (el.tagName || "").toLowerCase();
    const type = (el.getAttribute("type") || "").toLowerCase();
    if ((tag === "input" && (type === "checkbox" || type === "radio")) || tag === "select") return;
    if (tag === "input" || tag === "textarea" || el.isContentEditable) return;
    send({ event_type: "click", action: "click", ...locatorInfo(el) });
  }, true);

  document.addEventListener("input", (event) => {
    const el = targetElement(event.target);
    if (!el) return;
    const tag = (el.tagName || "").toLowerCase();
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (tag === "select" || type === "checkbox" || type === "radio") return;
    if (tag === "input" || tag === "textarea" || el.isContentEditable) recordValue(el, "input");
  }, true);

  document.addEventListener("change", (event) => {
    const el = targetElement(event.target);
    if (!el) return;
    const tag = (el.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable) {
      recordValue(el, "change");
    }
  }, true);

  let lastUrl = window.location.href;
  window.setInterval(() => {
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href;
      send({ event_type: "url_change", action: "url_change", value: lastUrl, locator: "" });
    }
  }, 500);
  send({ event_type: "ready", action: "ready", value: window.location.href, locator: "" });
})();
"""


@dataclass
class _Session:
    playwright: Any
    browser: Any
    context: Any
    page: Any
    project_id: int
    case_name: str
    start_url: str
    user_id: int | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    current_url: str = ""
    last_activity: float = field(default_factory=time.time)


_SESSIONS: dict[str, _Session] = {}
_LOCK = asyncio.Lock()
_cleanup_started = False


def _short_text(value: Any, max_len: int = 1200) -> str:
    text = "" if value is None else str(value)
    return text[:max_len]


def _list_strings(value: Any, max_items: int = 8) -> list[str]:
    if not isinstance(value, list):
      return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(_short_text(text, 500))
        if len(result) >= max_items:
            break
    return result


def _sanitize_event(payload: Any, event_id: int) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    action = str(payload.get("action") or "").strip().lower()
    if action not in {"click", "input", "select", "check", "uncheck", "url_change", "ready"}:
        return None
    event_type = str(payload.get("event_type") or action).strip().lower()
    item = {
        "event_id": event_id,
        "event_type": event_type,
        "action": action,
        "locator": _short_text(payload.get("locator"), 500).strip(),
        "fallback_locators": _list_strings(payload.get("fallback_locators")),
        "value": payload.get("value"),
        "url": _short_text(payload.get("url"), 1000).strip(),
        "text": _short_text(payload.get("text"), 300).strip(),
        "tag": _short_text(payload.get("tag"), 50).strip(),
        "input_type": _short_text(payload.get("input_type"), 50).strip(),
        "checked": payload.get("checked"),
        "created_at": _short_text(payload.get("created_at") or datetime.now().isoformat(), 80),
    }
    if isinstance(item["value"], str):
        item["value"] = _short_text(item["value"], 2000)
    return item


def _append_event(session: _Session, payload: Any) -> None:
    event = _sanitize_event(payload, len(session.events) + 1)
    if not event:
        return
    session.events.append(event)
    if len(session.events) > _MAX_EVENTS:
        del session.events[: len(session.events) - _MAX_EVENTS]
    if event.get("url"):
        session.current_url = str(event["url"])
    session.last_activity = time.time()


def _step_label(action: str, event: dict[str, Any]) -> str:
    text = str(event.get("text") or event.get("locator") or "").strip()
    text = text[:40]
    labels = {
        "click": "点击",
        "input": "输入",
        "select": "选择",
        "check": "勾选",
        "uncheck": "取消勾选",
    }
    return f"{labels.get(action, action)} {text}".strip()


def _event_to_step(event: dict[str, Any]) -> dict[str, Any] | None:
    action = str(event.get("action") or "").strip().lower()
    if action not in {"click", "input", "select", "check", "uncheck"}:
        return None
    locator = str(event.get("locator") or "").strip()
    if not locator:
        return None
    step: dict[str, Any] = {
        "name": _step_label(action, event),
        "action": action,
        "locator": locator,
    }
    fallbacks = _list_strings(event.get("fallback_locators"))
    if fallbacks:
        step["fallback_locators"] = fallbacks
    if action in {"input", "select"}:
        step["value"] = event.get("value", "")
    elif action in {"check", "uncheck"} and event.get("value") not in (None, ""):
        step["value"] = event.get("value")
    return step


def build_ui_steps(
    start_url: str,
    current_url: str = "",
    events: list[dict[str, Any]] | None = None,
    assertion_text: str = "",
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {"name": "打开起始页面", "action": "goto", "value": start_url},
    ]
    last_action_step: dict[str, Any] | None = None
    final_url = current_url or start_url
    for event in events or []:
        if event.get("url"):
            final_url = str(event["url"])
        step = _event_to_step(event)
        if not step:
            continue
        if (
            step["action"] == "input"
            and last_action_step
            and last_action_step.get("action") == "input"
            and last_action_step.get("locator") == step.get("locator")
        ):
            steps[-1] = step
            last_action_step = step
            continue
        steps.append(step)
        last_action_step = step
    text = str(assertion_text or "").strip()
    if text:
        steps.append({"name": "检查页面文案", "action": "text_assert", "locator": "body", "value": text})
    if final_url:
        steps.append({"name": "检查最终地址", "action": "assert_url", "value": final_url, "exact": False})
    return steps


def _public_events(session: _Session) -> list[dict[str, Any]]:
    return [dict(item) for item in session.events]


def _session_payload(session_id: str, session: _Session, assertion_text: str = "") -> dict[str, Any]:
    events = _public_events(session)
    current_url = session.current_url or getattr(session.page, "url", "") or session.start_url
    return {
        "session_id": session_id,
        "status": "recording",
        "project_id": session.project_id,
        "case_name": session.case_name,
        "start_url": session.start_url,
        "current_url": current_url,
        "count": len(events),
        "items": events,
        "preview_steps": build_ui_steps(session.start_url, current_url, events, assertion_text),
    }


async def start_session(project_id: int, case_name: str, start_url: str, user_id: int | None = None) -> str:
    global _cleanup_started
    playwright = await async_playwright().start()
    browser = await _launch_chromium(playwright)
    context = await browser.new_context(ignore_https_errors=True)
    await context.add_init_script(RECORDING_SCRIPT)
    page = await context.new_page()
    session = _Session(
        playwright=playwright,
        browser=browser,
        context=context,
        page=page,
        project_id=project_id,
        case_name=case_name,
        start_url=start_url,
        user_id=user_id,
        current_url=start_url,
    )

    async def record_binding(_source: Any, payload: Any) -> None:
        _append_event(session, payload)

    await page.expose_binding("__recordUiEvent", record_binding)

    def on_frame_navigated(frame: Any) -> None:
        try:
            if frame == page.main_frame:
                _append_event(session, {"action": "url_change", "event_type": "url_change", "url": frame.url, "value": frame.url})
        except Exception:
            return

    page.on("framenavigated", on_frame_navigated)

    async with _LOCK:
        session_id = uuid4().hex
        _SESSIONS[session_id] = session
    if not _cleanup_started:
        _cleanup_started = True
        asyncio.create_task(_cleanup_loop())
    try:
        await page.goto(start_url, wait_until="domcontentloaded")
    except Exception:
        pass
    return session_id


def get_session_state(session_id: str, assertion_text: str = "") -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise ValueError(f"录制会话不存在: {session_id}")
    session.current_url = getattr(session.page, "url", "") or session.current_url
    session.last_activity = time.time()
    return _session_payload(session_id, session, assertion_text)


async def close_session(session_id: str) -> None:
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
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        now = time.time()
        expired: list[str] = []
        async with _LOCK:
            for session_id, session in list(_SESSIONS.items()):
                if now - session.last_activity > _SESSION_TIMEOUT:
                    expired.append(session_id)
        for session_id in expired:
            try:
                await close_session(session_id)
            except Exception:
                pass
