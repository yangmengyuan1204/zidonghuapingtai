from __future__ import annotations

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
  const isVisible = (el) => {
    if (!el) return false;
    try {
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
    } catch (error) {
      return false;
    }
  };
  const inspectCandidate = (value, strategy) => {
    let count = null;
    let visible = null;
    try {
      if (!value.startsWith("text=") && !value.includes(":has-text(")) {
        const matches = Array.from(document.querySelectorAll(value));
        count = matches.length;
        visible = matches.some(isVisible);
      }
    } catch (error) {
      count = null;
      visible = null;
    }
    return { value, strategy, count, visible };
  };
  const pushCandidate = (items, value, strategy) => {
    const text = String(value || "").trim();
    if (!text || items.some((item) => item.value === text)) return;
    items.push(inspectCandidate(text, strategy));
  };
  const targetElement = (raw) => {
    if (!raw) return null;
    if (raw.nodeType === Node.ELEMENT_NODE) return raw;
    return raw.parentElement || null;
  };
  const cleanText = (value, max = 40) => String(value || "").replace(/\s+/g, " ").trim().slice(0, max);
  const elementText = (el) => {
    if (!el) return "";
    return cleanText(el.innerText || el.textContent || el.value || el.getAttribute("title") || el.getAttribute("aria-label") || "");
  };
  const isLikelyClickable = (el) => {
    if (!el || el === document.body || el === document.documentElement) return false;
    const tag = (el.tagName || "").toLowerCase();
    if (["a", "button", "select", "summary", "input"].includes(tag)) return true;
    if (el.getAttribute("role") === "button" || el.hasAttribute("onclick")) return true;
    const className = String(el.getAttribute("class") || "");
    if (/\b(btn|button|el-button|ant-btn|tab|item|menu-item|goods|card|cart)\b/i.test(className)) return true;
    try {
      if (window.getComputedStyle(el).cursor === "pointer") return true;
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
    while (node && node.nodeType === Node.ELEMENT_NODE && depth < 4) {
      if (isLikelyClickable(node)) return node;
      node = node.parentElement;
      depth += 1;
    }
    return start;
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
  const buildFrameChain = () => {
    const result = [];
    try {
      let current = window;
      while (current !== current.top && current.frameElement && result.length < 8) {
        const frame = current.frameElement;
        const id = frame.getAttribute("id") || "";
        const name = frame.getAttribute("name") || "";
        const selector = id ? `#${cssEscape(id)}` : (name ? `iframe[name="${quoteCss(name)}"]` : "iframe");
        result.unshift({
          name,
          url: current.location.href,
          selector,
          stable_attrs: {
            id,
            name,
            title: frame.getAttribute("title") || "",
            "data-testid": frame.getAttribute("data-testid") || "",
          },
        });
        current = current.parent;
      }
      return result;
    } catch (error) {
      return result.length ? result : [{ name: "", url: window.location.href, selector: "iframe" }];
    }
  };
  const framePath = () => buildFrameChain();
  const isClickable = (el) => isLikelyClickable(el);
  const stableClassTokens = (el) => String((el && el.getAttribute("class")) || "")
    .split(/\s+/)
    .filter((token) => token && token.length <= 80 && !/\d{4,}|[a-f0-9]{12,}/i.test(token))
    .slice(0, 8);
  const scopeKind = (node) => {
    const tag = (node.tagName || "").toLowerCase();
    const role = (node.getAttribute("role") || "").toLowerCase();
    const classes = String(node.getAttribute("class") || "");
    if (/\bdrawer\b/i.test(classes)) return "drawer";
    if (tag === "dialog" || role === "dialog") return "dialog";
    if (tag === "form" || role === "form") return "form";
    if (tag === "tr" || role === "row") return "table_row";
    if (/\bcard\b/i.test(classes)) return "card";
    if (role === "menu" || tag === "menu") return "menu";
    if (role === "listbox") return "listbox";
    return "";
  };
  const rowHeaders = (row) => {
    const result = {};
    try {
      const table = row.closest("table,[role='table'],[role='grid']");
      const headers = table ? Array.from(table.querySelectorAll("thead th,[role='columnheader']")) : [];
      const cells = Array.from(row.querySelectorAll(":scope > th,:scope > td,:scope > [role='cell'],:scope > [role='gridcell']"));
      headers.slice(0, cells.length).forEach((header, index) => {
        const name = trimText(header.innerText || header.textContent || "", 80);
        const value = trimText(cells[index] && (cells[index].innerText || cells[index].textContent) || "", 160);
        if (name && value) result[name] = value;
      });
    } catch (error) {
      return {};
    }
    return result;
  };
  const scopeName = (node) => {
    const ariaLabel = trimText(node.getAttribute("aria-label") || "", 160);
    if (ariaLabel) return ariaLabel;
    const heading = node.querySelector(":scope > legend,:scope > h1,:scope > h2,:scope > h3,:scope > [role='heading']");
    if (heading) return trimText(heading.innerText || heading.textContent || "", 160);
    try {
      const clone = node.cloneNode(true);
      clone.querySelectorAll("input,textarea,select,[contenteditable],script,style").forEach((child) => child.remove());
      return trimText(clone.textContent || "", 160);
    } catch (error) {
      return "";
    }
  };
  const buildScopeChain = (el) => {
    const nearest = [];
    let node = el && el.parentElement;
    while (node && node !== document.documentElement && nearest.length < 6) {
      const kind = scopeKind(node);
      if (kind) {
        const entry = {
          kind,
          role: trimText(node.getAttribute("role") || "", 80),
          name: scopeName(node),
        };
        if (kind === "table_row") entry.headers = rowHeaders(node);
        nearest.push(entry);
      }
      node = node.parentElement;
    }
    return nearest.reverse();
  };
  const buildNeighborTexts = (el) => {
    const values = [];
    const add = (value) => pushUnique(values, trimText(value, 160));
    try {
      if (el.labels) Array.from(el.labels).forEach((label) => add(label.innerText || label.textContent));
      add(el.previousElementSibling && (el.previousElementSibling.innerText || el.previousElementSibling.textContent));
      add(el.nextElementSibling && (el.nextElementSibling.innerText || el.nextElementSibling.textContent));
      const row = el.closest("tr,[role='row']");
      if (row) Object.entries(rowHeaders(row)).forEach(([name, value]) => { add(name); add(value); });
    } catch (error) {
      return values.slice(0, 8);
    }
    return values.slice(0, 8);
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
    const title = el.getAttribute("title");
    const role = el.getAttribute("role");
    const ariaControls = el.getAttribute("aria-controls");
    const rawText = String(el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
    const isGoodText = rawText && rawText.length <= 40 && !rawText.includes("\n");
    const text = isGoodText ? rawText.slice(0, 40) : "";
    const label = trimText((el.labels && el.labels[0] && (el.labels[0].innerText || el.labels[0].textContent)) || "");
    const accessibleName = trimText(ariaLabel || label || text || title || "");
    const isDynamicId = (val) => !val || /(?:^|\b)(?:el-id|rc-tabs|input-\d+|select-\d+|uid-|guid-|__)/i.test(val) || /\d{4,}/.test(val);

    if (dataTestId) pushCandidate(candidates, `[data-testid="${quoteCss(dataTestId)}"]`, "test_id");
    if (dataTest) pushCandidate(candidates, `[data-test="${quoteCss(dataTest)}"]`, "test_id");
    if (id && !isDynamicId(id)) pushCandidate(candidates, `#${cssEscape(id)}`, "id");
    if (name) pushCandidate(candidates, `[name="${quoteCss(name)}"]`, "name");
    if (placeholder) {
      const base = tag === "textarea" ? "textarea" : "input";
      pushCandidate(candidates, `${base}[placeholder="${quoteCss(placeholder)}"]`, "placeholder");
      pushCandidate(candidates, `[placeholder="${quoteCss(placeholder)}"]`, "placeholder");
    }
    if (ariaLabel) pushCandidate(candidates, `[aria-label="${quoteCss(ariaLabel)}"]`, "aria");
    if (title) pushCandidate(candidates, `[title="${quoteCss(title)}"]`, "title");
    if (text) {
      const quoted = quoteCss(text);
      if (tag === "button") pushCandidate(candidates, `button:has-text("${quoted}")`, "role_text");
      if (tag === "a") pushCandidate(candidates, `a:has-text("${quoted}")`, "role_text");
      if (role) pushCandidate(candidates, `[role="${quoteCss(role)}"]:has-text("${quoted}")`, "role_text");
      pushCandidate(candidates, `text="${quoted}"`, "text");
    }
    const iconEl = el.querySelector("i,svg,[class*='icon']");
    if (iconEl && tag === "button") {
      const iconClass = String(iconEl.getAttribute("class") || "").trim();
      if (iconClass) {
        const firstCls = iconClass.split(/\s+/).find(c => /icon|search|close|btn|submit|cart/i.test(c));
        if (firstCls) pushCandidate(candidates, `button:has(.${cssEscape(firstCls)})`, "icon");
      }
    }
    pushCandidate(candidates, cssPath(el), "css_path");
    const locatorValues = candidates.map((item) => item.value);
    return {
      locator: locatorValues[0] || cssPath(el),
      fallback_locators: locatorValues.slice(1),
      locator_candidates: candidates,
      text: text || cleanText(el.innerText || "", 40),
      tag,
      input_type: (el.getAttribute("type") || "").toLowerCase(),
      role: role || "",
      aria_label: ariaLabel || "",
      accessible_name: accessibleName,
      label,
      placeholder: placeholder || "",
      stable_attrs: {
        data_testid: dataTestId || "",
        data_test: dataTest || "",
        id: !isDynamicId(id) ? id : "",
        name: name || "",
        type: (el.getAttribute("type") || "").toLowerCase(),
        aria_controls: !isDynamicId(ariaControls) ? (ariaControls || "") : "",
      },
      frame_path: framePath(),
    };
  };
  const semanticMatchCount = (el, info) => {
    const semanticName = trimText(info.accessible_name || "", 300);
    if (!semanticName) return null;
    try {
      const selector = info.tag || (info.role ? `[role="${quoteCss(info.role)}"]` : "*");
      return Array.from(document.querySelectorAll(selector)).filter((candidate) => {
        if (info.role && (candidate.getAttribute("role") || "") !== info.role) return false;
        const label = trimText((candidate.labels && candidate.labels[0]
          && (candidate.labels[0].innerText || candidate.labels[0].textContent)) || "");
        const candidateName = trimText(
          candidate.getAttribute("aria-label") || label || candidate.innerText
          || candidate.textContent || candidate.getAttribute("title") || "",
          300,
        );
        return candidateName === semanticName;
      }).length;
    } catch (error) {
      return null;
    }
  };
  const candidateMatchCount = (el, info = locatorInfo(el)) => {
    const semanticCount = semanticMatchCount(el, info);
    if (Number.isInteger(semanticCount)) return semanticCount;
    const candidate = (info.locator_candidates || [])
      .find((item) => item.strategy !== "css_path" && Number.isInteger(item.count));
    return candidate ? candidate.count : null;
  };
  window.__uiRecorderLocatorInfo = locatorInfo;
  window.__uiRecorderClickableElement = clickableElement;
  window.__uiRecorderCaptureTarget = (el) => {
    const info = locatorInfo(el);
    const safeAccessibleName = el.isContentEditable
      ? trimText(el.getAttribute("aria-label") || info.label || info.placeholder || el.getAttribute("title") || "", 300)
      : info.accessible_name;
    return {
      url: window.location.href,
      page_title: document.title || "",
      frame_chain: buildFrameChain(),
      scope_chain: buildScopeChain(el),
      neighbor_texts: buildNeighborTexts(el),
      tag: info.tag,
      input_type: info.input_type,
      role: info.role,
      accessible_name: safeAccessibleName,
      label: info.label,
      placeholder: info.placeholder,
      stable_attrs: info.stable_attrs,
      stable_class_tokens: stableClassTokens(el),
      capabilities: {
        click: isClickable(el),
        input: ["input", "textarea"].includes((el.tagName || "").toLowerCase()) || Boolean(el.isContentEditable),
        select: (el.tagName || "").toLowerCase() === "select",
        check: ["checkbox", "radio"].includes((el.getAttribute("type") || "").toLowerCase()),
      },
      recorded_match_count: candidateMatchCount(el, info),
    };
  };
  const isSensitiveTarget = (el) => {
    if (!el) return false;
    const info = `${el.getAttribute("type") || ""} ${el.getAttribute("name") || ""} ${el.id || ""} ${el.getAttribute("autocomplete") || ""}`;
    return /password|passwd|token|cookie|authorization|secret|密码/i.test(info);
  };
  const captureDialogs = () => {
    const values = [];
    try {
      document.querySelectorAll('dialog[open],[role="dialog"],[aria-modal="true"],.modal,.dialog,.drawer').forEach((node) => {
        if (!isVisible(node)) return;
        const name = trimText(node.getAttribute("aria-label") || scopeName(node) || node.innerText || node.textContent || "", 200);
        if (name && !values.includes(name)) values.push(name);
      });
    } catch (error) {
      return values;
    }
    return values.slice(0, 12);
  };
  const capturePageState = (el) => {
    const target = {};
    if (el) {
      const tag = (el.tagName || "").toLowerCase();
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable) {
        const value = el.isContentEditable ? (el.innerText || "") : (el.value || "");
        const sensitive = isSensitiveTarget(el);
        target.value = sensitive ? "***" : trimText(value, 1000);
        if (sensitive) target.has_value = Boolean(value);
      }
      if (type === "checkbox" || type === "radio") target.checked = Boolean(el.checked);
      target.visible = isVisible(el);
    }
    return {
      url: window.location.href,
      title: document.title || "",
      dialogs: captureDialogs(),
      target,
    };
  };
  const interactionId = () => {
    try {
      if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
    } catch (error) {
      // fall through to a local correlation id
    }
    return `${Date.now()}-${Math.random()}`;
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
  const beforeStates = new WeakMap();
  const rememberBeforeState = (event) => {
    const el = targetElement(event.target);
    if (el) beforeStates.set(el, capturePageState(el));
  };
  document.addEventListener("beforeinput", rememberBeforeState, true);
  document.addEventListener("pointerdown", rememberBeforeState, true);
  document.addEventListener("keydown", rememberBeforeState, true);
  const recordAction = (payload, el, beforeState = null) => {
    const id = interactionId();
    const initial = beforeState || capturePageState(el);
    send({ ...payload, interaction_id: id, before_state: initial });
    window.setTimeout(() => send({
      action: "effect_observation",
      event_type: "effect_observation",
      interaction_id: id,
      after_state: capturePageState(el),
    }), 400);
    window.setTimeout(() => send({
      action: "effect_observation",
      event_type: "effect_observation",
      interaction_id: id,
      after_state: capturePageState(el),
      final: true,
    }), 1200);
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
    const beforeState = beforeStates.get(el) || capturePageState(el);
    recordAction({ event_type: eventType, action, value, checked, ...info, ...window.__uiRecorderCaptureTarget(el) }, el, beforeState);
    beforeStates.set(el, capturePageState(el));
  };

  document.addEventListener("click", (event) => {
    const start = targetElement(event.target);
    const el = clickableElement(start) || start;
    if (!el) return;
    const tag = (el.tagName || "").toLowerCase();
    const type = (el.getAttribute("type") || "").toLowerCase();
    if ((tag === "input" && (type === "checkbox" || type === "radio")) || tag === "select") return;
    if (tag === "input" || tag === "textarea" || el.isContentEditable) return;
    recordAction({ event_type: "click", action: "click", ...locatorInfo(el), ...window.__uiRecorderCaptureTarget(el) }, el);
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

def recording_init_script() -> str:
    return RECORDING_SCRIPT


def repick_script(step_index: int, timeout_ms: int = 120000) -> str:
    index = max(0, int(step_index))
    timeout = max(1000, min(600000, int(timeout_ms)))
    return f"""
(async () => {{
  if (typeof window.__uiRecorderCaptureTarget !== "function") return null;
  const banner = document.createElement("div");
  banner.id = "ui-recorder-repick-banner";
  banner.textContent = "请点击要重新选择的页面元素";
  Object.assign(banner.style, {{
    position: "fixed", top: "16px", left: "50%", transform: "translateX(-50%)",
    zIndex: "2147483647", padding: "10px 18px", borderRadius: "6px",
    color: "#fff", background: "#1677ff", fontSize: "14px", pointerEvents: "none",
  }});
  document.documentElement.appendChild(banner);
  let highlighted = null;
  let previousOutline = "";
  const pickTarget = (raw) => window.__uiRecorderClickableElement
    ? window.__uiRecorderClickableElement(raw)
    : (raw && raw.closest
      ? raw.closest('a,button,[role="button"],input,textarea,select,label,summary,[onclick],[tabindex]') || raw
      : raw);
  const clearHighlight = () => {{
    if (highlighted) highlighted.style.outline = previousOutline;
    highlighted = null;
    previousOutline = "";
  }};
  const onPointerOver = (event) => {{
    const candidate = pickTarget(event.target);
    if (!candidate || candidate === highlighted) return;
    clearHighlight();
    highlighted = candidate;
    previousOutline = candidate.style.outline || "";
    candidate.style.outline = "2px solid #1677ff";
  }};
  const target = await new Promise((resolve, reject) => {{
    let timer = null;
    const cleanup = () => {{
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("pointerover", onPointerOver, true);
      if (timer) clearTimeout(timer);
      clearHighlight();
      banner.remove();
    }};
    const onClick = (event) => {{
      event.preventDefault();
      event.stopImmediatePropagation();
      const selected = pickTarget(event.target);
      cleanup();
      resolve(selected);
    }};
    document.addEventListener("pointerover", onPointerOver, true);
    document.addEventListener("click", onClick, true);
    timer = setTimeout(() => {{
      cleanup();
      reject(new Error("重新选点等待超时"));
    }}, {timeout});
  }});
  const info = window.__uiRecorderLocatorInfo
    ? window.__uiRecorderLocatorInfo(target)
    : {{ locator_candidates: [] }};
  return {{
    step_index: {index},
    locator_candidates: info.locator_candidates || [],
    target_profile_source: window.__uiRecorderCaptureTarget(target),
  }};
}})()
"""
