import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
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
  const isLikelyClickable = (el) => {
    if (!el || el === document.body || el === document.documentElement) return false;
    const text = elementText(el);
    const className = String(el.getAttribute("class") || "");
    const dataAction = el.getAttribute("data-action") || el.getAttribute("data-click");
    if (dataAction) return true;
    if (el.getAttribute("aria-haspopup") || el.getAttribute("tabindex")) return true;
    if (/\b(btn|button|link|login|search|cart|submit|open|trigger|action)\b/i.test(className)) return true;
    try {
      if (window.getComputedStyle(el).cursor === "pointer" && text && text.length <= 100) return true;
    } catch (error) {
      return false;
    }
    return false;
  };
  const clickableElement = (start) => {
    if (!start) return null;
    const native = start.closest('a,button,[role="button"],input,textarea,select,label,summary,[onclick],[tabindex]');
    if (native) return native;
    let node = start;
    let depth = 0;
    while (node && node.nodeType === Node.ELEMENT_NODE && depth < 6) {
      if (isLikelyClickable(node)) return node;
      node = node.parentElement;
      depth += 1;
    }
    return null;
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
    const startText = elementText(start);
    const el = clickableElement(start) || (startText && startText.length <= 100 ? start : null);
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
    account_profile_id: int | None = None
    learning_session_id: str = ""
    persistent: bool = False
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
    if action not in {"click", "input", "select", "check", "uncheck", "url_change", "ready", "checkpoint"}:
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
    if action == "checkpoint":
        item.update(
            {
                "field_name": _short_text(payload.get("field_name"), 300),
                "actual_value": _short_text(payload.get("actual_value"), 1000),
                "value_type": _short_text(payload.get("value_type"), 40),
                "currency": _short_text(payload.get("currency"), 20),
                "relation": _short_text(payload.get("relation"), 80),
                "locator_candidates": _list_strings(payload.get("locator_candidates"), 12),
            }
        )
    if isinstance(item["value"], str):
        item["value"] = _short_text(item["value"], 2000)
    sensitive_text = " ".join(
        str(item.get(key) or "") for key in ("locator", "text", "input_type")
    ).lower()
    sensitive = bool(
        item.get("input_type") == "password"
        or any(word in sensitive_text for word in ("password", "passwd", "token", "cookie", "authorization", "验证码", "captcha", "密码"))
    )
    if item.get("action") == "input" and any(word in sensitive_text for word in ("username", "account", "mobile", "phone", "email", "账号", "手机号", "邮箱")):
        item["value"] = "{{username}}"
        sensitive = True
    elif item.get("action") == "input" and sensitive:
        item["value"] = "{{password}}" if item.get("input_type") == "password" or "密码" in sensitive_text else "***"
    elif isinstance(item.get("value"), str):
        item["value"] = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "***手机号***", item["value"])
    item["sensitive"] = sensitive
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
    if session.learning_session_id:
        try:
            from ..database import SessionLocal
            from ..models import VerificationLearningEvent, VerificationLearningSession

            db = SessionLocal()
            try:
                if db.get(VerificationLearningSession, session.learning_session_id):
                    db.add(
                        VerificationLearningEvent(
                            session_id=session.learning_session_id,
                            event_type=str(event.get("event_type") or "action"),
                            action=str(event.get("action") or ""),
                            payload_json=json.dumps(event, ensure_ascii=False, default=str),
                            sensitive=1 if event.get("sensitive") else 0,
                            create_time=datetime.now(),
                        )
                    )
                    learning = db.get(VerificationLearningSession, session.learning_session_id)
                    if learning:
                        learning.current_url = session.current_url
                        learning.update_time = datetime.now()
                    db.commit()
            finally:
                db.close()
        except Exception:
            pass


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


def _significant_url_change(previous_url: str, next_url: str) -> bool:
    if not next_url or next_url == previous_url:
        return False
    try:
        prev = urlsplit(previous_url)
        nxt = urlsplit(next_url)
    except Exception:
        return next_url != previous_url
    return (prev.scheme, prev.netloc, prev.path, prev.query) != (nxt.scheme, nxt.netloc, nxt.path, nxt.query)


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
    last_flow_url = start_url
    pending_goto_url = ""
    for event in events or []:
        if event.get("url"):
            final_url = str(event["url"])
        if str(event.get("action") or "").strip().lower() == "url_change":
            next_url = str(event.get("value") or event.get("url") or "").strip()
            if _significant_url_change(last_flow_url, next_url):
                pending_goto_url = next_url
                last_flow_url = next_url
            continue
        step = _event_to_step(event)
        if not step:
            continue
        if pending_goto_url and step.get("action") in {"input", "select", "check", "uncheck"}:
            if steps[-1].get("action") != "goto" or steps[-1].get("value") != pending_goto_url:
                steps.append({"name": "打开跳转页面", "action": "goto", "value": pending_goto_url})
            pending_goto_url = ""
            last_action_step = None
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
        "account_profile_id": session.account_profile_id,
        "current_url": current_url,
        "count": len(events),
        "items": events,
        "preview_steps": build_ui_steps(session.start_url, current_url, events, assertion_text),
    }


async def _attach_page_recorder(session: _Session, page: Any) -> None:
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


async def start_session(
    project_id: int,
    case_name: str,
    start_url: str,
    user_id: int | None = None,
    storage_state: dict[str, Any] | None = None,
    account_profile_id: int | None = None,
    preferred_session_id: str | None = None,
    persistent: bool = False,
    persist_learning_events: bool = True,
) -> str:
    global _cleanup_started
    playwright = await async_playwright().start()
    browser = await _launch_chromium(playwright)
    context_options: dict[str, Any] = {"ignore_https_errors": True}
    if isinstance(storage_state, dict) and isinstance(storage_state.get("cookies"), list):
        context_options["storage_state"] = storage_state
    context = await browser.new_context(**context_options)
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
        account_profile_id=account_profile_id,
        current_url=start_url,
        learning_session_id=str(preferred_session_id or "") if persist_learning_events else "",
        persistent=bool(persistent),
    )

    await _attach_page_recorder(session, page)

    def on_new_page(new_page: Any) -> None:
        asyncio.create_task(_attach_page_recorder(session, new_page))

    context.on("page", on_new_page)

    async with _LOCK:
        session_id = str(preferred_session_id or uuid4().hex)
        if persist_learning_events:
            session.learning_session_id = session_id
        _SESSIONS[session_id] = session
    if not _cleanup_started:
        _cleanup_started = True
        asyncio.create_task(_cleanup_loop())
    try:
        await page.goto(start_url, wait_until="domcontentloaded")
    except Exception:
        pass
    return session_id


async def get_session_storage_state(session_id: str) -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if not session:
        return {}
    try:
        value = await session.context.storage_state()
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


async def begin_checkpoint_selection(session_id: str) -> None:
    session = _SESSIONS.get(session_id)
    if not session:
        raise ValueError(f"录制会话不存在: {session_id}")
    await session.page.evaluate(
        r"""
        () => {
          if (window.__verificationCheckpointSelecting) return;
          window.__verificationCheckpointSelecting = true;
          const clean = (value, max = 300) => String(value || '').replace(/\s+/g, ' ').trim().slice(0, max);
          const quote = (value) => String(value || '').replace(/\\/g, "\\\\").replace(/"/g, '\\"');
          const locator = (el) => {
            const testid = el.getAttribute('data-testid');
            if (testid) return `[data-testid="${quote(testid)}"]`;
            if (el.id) return `#${CSS.escape(el.id)}`;
            if (el.getAttribute('name')) return `[name="${quote(el.getAttribute('name'))}"]`;
            const text = clean(el.innerText || el.textContent || el.value, 100);
            if (text) return `text="${quote(text)}"`;
            return el.tagName.toLowerCase();
          };
          const handler = (event) => {
            event.preventDefault();
            event.stopImmediatePropagation();
            const el = event.target?.nodeType === Node.ELEMENT_NODE ? event.target : event.target?.parentElement;
            if (!el) return;
            document.removeEventListener('click', handler, true);
            window.__verificationCheckpointSelecting = false;
            const cell = el.closest('td,th');
            const row = el.closest('tr');
            const previous = cell?.previousElementSibling;
            const next = cell?.nextElementSibling;
            const own = clean(el.innerText || el.textContent || el.value);
            const previousText = clean(previous?.innerText || previous?.textContent || previous?.value);
            const nextText = clean(next?.innerText || next?.textContent || next?.value);
            let fieldName = previousText || clean(el.getAttribute('aria-label') || el.getAttribute('name')) || own;
            let actualValue = previousText ? own : (nextText || own);
            if (row) {
              const cells = Array.from(row.querySelectorAll(':scope > th,:scope > td')).map((node) => clean(node.innerText || node.textContent || node.value));
              const index = cell ? cells.indexOf(clean(cell.innerText || cell.textContent || cell.value)) : -1;
              if (index >= 0 && index + 1 < cells.length && own === cells[index]) {
                fieldName = own;
                actualValue = cells[index + 1];
              }
            }
            window.__recordUiEvent({
              event_type: 'checkpoint_selection',
              action: 'checkpoint',
              field_name: fieldName,
              actual_value: actualValue,
              value_type: /(?:¥|￥|円|元|\d[\d,]*\.\d{2})/.test(actualValue) ? 'money' : 'text',
              currency: /円|JPY/i.test(actualValue) ? 'JPY' : (/元|￥|CNY/i.test(actualValue) ? 'CNY' : ''),
              relation: cell ? 'table_key_value' : 'nearby_value',
              locator_candidates: [locator(el)],
              locator: locator(el),
              text: own,
              url: location.href,
              created_at: new Date().toISOString()
            });
          };
          document.addEventListener('click', handler, true);
        }
        """
    )
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
                if not session.persistent and now - session.last_activity > _SESSION_TIMEOUT:
                    expired.append(session_id)
        for session_id in expired:
            try:
                await close_session(session_id)
            except Exception:
                pass
