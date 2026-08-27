from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Iterable


_STRATEGY_SCORES = {
    "test_id": 100,
    "aria": 94,
    "role_text": 92,
    "label": 90,
    "name": 86,
    "id": 85,
    "placeholder": 82,
    "text": 72,
    "css": 48,
    "css_path": 20,
}

_DYNAMIC_ID_PATTERNS = (
    re.compile(r"(?:^|[_-])\d{10,}(?:$|[_-])"),
    re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27,}", re.I),
    re.compile(r"(?:^|[_-])[0-9a-f]{12,}(?:$|[_-])", re.I),
    re.compile(r"^(?:ember|react|vue|ng|el|mui)[-_]?\d+$", re.I),
)


def is_dynamic_identifier(value: Any) -> bool:
    text = str(value or "").strip().lstrip("#")
    if not text:
        return False
    return any(pattern.search(text) for pattern in _DYNAMIC_ID_PATTERNS)


def _candidate_dict(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, str):
        value = raw.strip()
        if not value:
            return None
        return {"value": value, "strategy": "css", "count": None, "visible": None}
    if not isinstance(raw, dict):
        return None
    value = str(raw.get("value") or raw.get("locator") or "").strip()
    if not value:
        return None
    return {
        "value": value,
        "strategy": str(raw.get("strategy") or "css").strip() or "css",
        "count": raw.get("count"),
        "visible": raw.get("visible"),
    }


def score_locator_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    result = dict(candidate)
    value = str(result.get("value") or "").strip()
    strategy = str(result.get("strategy") or "css")
    dynamic = strategy == "id" and is_dynamic_identifier(value)
    score = _STRATEGY_SCORES.get(strategy, 45)
    reasons = [f"{strategy} 策略基础分 {score}"]
    if dynamic:
        score = min(score, 30)
        reasons.append("疑似动态 ID，降为低分兜底")
    count = result.get("count")
    if count == 1:
        reasons.append("录制时唯一匹配")
    elif isinstance(count, int):
        score -= 45 if count > 1 else 35
        reasons.append(f"录制时匹配 {count} 个元素，未满足唯一性")
    else:
        score -= 35
        reasons.append("未验证唯一性")
    if result.get("visible") is False:
        score -= 25
        reasons.append("录制时不可见")
    elif result.get("visible") is True:
        reasons.append("录制时可见")
    else:
        reasons.append("可见性未验证")
    if ":nth-of-type(" in value or ":nth-child(" in value:
        score = min(score, 22)
        reasons.append("依赖 DOM 序号，仅作兜底")
    result.update({"dynamic": dynamic, "score": max(0, min(100, int(score))), "reasons": reasons})
    return result


def _unique_candidates(values: Iterable[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for raw in values:
        candidate = _candidate_dict(raw)
        if not candidate or candidate["value"] in seen:
            continue
        seen.add(candidate["value"])
        result.append(score_locator_candidate(candidate))
    return sorted(result, key=lambda item: item["score"], reverse=True)


def _fingerprint_payload(event: dict[str, Any]) -> dict[str, Any]:
    stable_attrs = event.get("stable_attrs") if isinstance(event.get("stable_attrs"), dict) else {}
    return {
        "page_key": str(event.get("page_key") or event.get("url") or "").split("#", 1)[0],
        "frame_path": event.get("frame_path") or [],
        "tag": str(event.get("tag") or ""),
        "type": str(event.get("input_type") or event.get("type") or ""),
        "role": str(event.get("role") or ""),
        "accessible_name": str(event.get("accessible_name") or event.get("aria_label") or "")[:160],
        "label": str(event.get("label") or "")[:160],
        "placeholder": str(event.get("placeholder") or "")[:160],
        "text": str(event.get("text") or "")[:160],
        "stable_attrs": stable_attrs,
    }


def build_locator_profile(event: dict[str, Any]) -> dict[str, Any]:
    raw_candidates = list(event.get("locator_candidates") or [])
    if not raw_candidates:
        primary = str(event.get("locator") or "").strip()
        if primary:
            raw_candidates.append({"value": primary, "strategy": "css"})
        raw_candidates.extend(event.get("fallback_locators") or [])
    candidates = _unique_candidates(raw_candidates)
    top_score = candidates[0]["score"] if candidates else 0
    top_unique = not candidates or candidates[0].get("count") == 1
    top_visible = not candidates or candidates[0].get("visible") is not False
    if top_score >= 80 and top_unique and top_visible:
        quality = "stable"
    elif top_score >= 55 and top_unique and top_visible:
        quality = "weak"
    else:
        quality = "risk"
    fingerprint = _fingerprint_payload(event)
    digest = hashlib.sha256(
        json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 2,
        "page_key": fingerprint["page_key"],
        "frame_path": fingerprint["frame_path"],
        "fingerprint": {**fingerprint, "hash": digest},
        "candidates": candidates,
        "quality": quality,
        "top_score": top_score,
    }


def ordered_locator_values(step: dict[str, Any], memory: Iterable[str] | None = None) -> list[str]:
    result: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)

    add(step.get("locator"))
    profile = step.get("locator_profile")
    if isinstance(profile, dict):
        candidates = profile.get("candidates") or []
        scored = [item for item in candidates if isinstance(item, dict)]
        for item in sorted(scored, key=lambda value: int(value.get("score") or 0), reverse=True):
            add(item.get("value"))
    for item in step.get("fallback_locators") or []:
        add(item)
    for item in memory or []:
        add(item)
    return result


def select_step_page(page: Any, step: dict[str, Any], timeout_ms: int = 5000) -> Any:
    try:
        index = int(step.get("page_index") or 0)
    except (TypeError, ValueError):
        index = 0
    if index <= 0:
        return page
    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    while True:
        try:
            pages = list(getattr(page.context, "pages", []) or [])
            if index < len(pages):
                return pages[index]
        except Exception as exc:
            raise ValueError(f"无法读取录制标签页上下文: {exc}") from exc
        if time.monotonic() >= deadline:
            raise ValueError(f"录制标签页 #{index + 1} 不存在，已安全停止")
        try:
            page.wait_for_timeout(100)
        except Exception:
            time.sleep(0.1)


def select_step_scope(page: Any, step: dict[str, Any]) -> Any:
    scope = page
    for frame in step.get("frame_path") or []:
        if not isinstance(frame, dict):
            continue
        selector = str(frame.get("selector") or "").strip()
        if not selector:
            name = str(frame.get("name") or "").strip().replace('"', '\\"')
            selector = f'iframe[name="{name}"]' if name else "iframe"
        scope = scope.frame_locator(selector)
    return scope
