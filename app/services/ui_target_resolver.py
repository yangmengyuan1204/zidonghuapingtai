from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
import json
import time
from typing import Any, Iterable


MIN_CONFIDENCE = 80
MIN_SCORE_GAP = 10


class TargetResolutionError(ValueError):
    """目标上下文无法唯一且安全地解析时抛出。"""


@dataclass(frozen=True)
class ResolvedTarget:
    target: Any
    used_locator: str
    score: int
    reasons: tuple[str, ...]
    matched_count: int
    page_identity: dict[str, str]


@dataclass(frozen=True)
class _Candidate:
    value: str
    score: int
    source: str
    reasons: tuple[str, ...]


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
}
_ACTION_CAPABILITY = {
    "click": "click",
    "input": "input",
    "select": "select",
    "check": "check",
    "uncheck": "check",
}


def _profile(step: dict[str, Any]) -> dict[str, Any]:
    value = step.get("target_profile")
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _quote_attribute(value: Any) -> str:
    return json.dumps(_text(value), ensure_ascii=False)[1:-1]


def _page_title(page: Any) -> str:
    try:
        title = getattr(page, "title", "")
        return _text(title() if callable(title) else title)
    except Exception:
        return ""


def _page_identity(page: Any) -> dict[str, str]:
    return {"url": _text(getattr(page, "url", "")), "title": _page_title(page)}


def _page_matches(page: Any, identity: dict[str, Any]) -> bool:
    url_pattern = _text(identity.get("url_pattern"))
    title = _text(identity.get("title"))
    if url_pattern and not fnmatchcase(_text(getattr(page, "url", "")), url_pattern):
        return False
    if title and _page_title(page) != title:
        return False
    return bool(url_pattern or title)


def _legacy_page(page: Any, step: dict[str, Any], timeout_ms: int) -> Any:
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
            raise TargetResolutionError(f"无法读取录制标签页上下文: {exc}") from exc
        if time.monotonic() >= deadline:
            raise TargetResolutionError(f"录制标签页 #{index + 1} 不存在，已安全停止")
        _wait(page, 50)


def _wait(page: Any, milliseconds: int) -> None:
    try:
        page.wait_for_timeout(milliseconds)
    except Exception:
        time.sleep(milliseconds / 1000)


def select_profile_page(page: Any, step: dict[str, Any], timeout_ms: int = 5000) -> Any:
    """按 target_profile 的页面身份选择页面；仅无身份时兼容旧 page_index。"""
    identity = _profile(step).get("page")
    identity = identity if isinstance(identity, dict) else {}
    has_identity = any(_text(identity.get(key)) for key in ("url_pattern", "title", "opener_interaction_id"))
    if not has_identity:
        return _legacy_page(page, step, timeout_ms)
    if not _text(identity.get("url_pattern")) and not _text(identity.get("title")):
        raise TargetResolutionError("页面仅记录了不可运行验证的打开来源，已安全停止")

    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    while True:
        try:
            pages = list(getattr(page.context, "pages", []) or [])
        except Exception as exc:
            raise TargetResolutionError(f"无法读取标签页上下文: {exc}") from exc
        matches = [candidate for candidate in pages if _page_matches(candidate, identity)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise TargetResolutionError("页面身份匹配不唯一，已安全停止")
        if time.monotonic() >= deadline:
            raise TargetResolutionError("未找到符合页面身份的标签页，已安全停止")
        _wait(page, 50)


def _frame_selector(frame: dict[str, Any]) -> str:
    selector = _text(frame.get("selector"))
    if selector:
        return selector
    attrs = frame.get("stable_attrs") if isinstance(frame.get("stable_attrs"), dict) else {}
    for key in ("data-testid", "data-test", "id", "name", "title"):
        value = _text(attrs.get(key) if key in attrs else frame.get(key))
        if value:
            return f'iframe[{key}="{_quote_attribute(value)}"]'
    name = _text(frame.get("name"))
    return f'iframe[name="{_quote_attribute(name)}"]' if name else "iframe"


def _safe_count(locator: Any) -> int:
    try:
        return int(locator.count())
    except Exception as exc:
        raise TargetResolutionError(f"无法读取定位器匹配数量: {exc}") from exc


def select_profile_scope(page: Any, step: dict[str, Any], timeout_ms: int = 5000) -> Any:
    """逐层验证 iframe 和语义范围唯一性，绝不以 first/nth 静默消歧。"""
    scope = page
    frames = _profile(step).get("frame_chain")
    if not isinstance(frames, list):
        return scope
    for index, raw in enumerate(frames, start=1):
        if not isinstance(raw, dict):
            continue
        selector = _frame_selector(raw)
        try:
            count = _safe_count(scope.locator(selector))
        except TargetResolutionError:
            raise
        except Exception as exc:
            raise TargetResolutionError(f"iframe第{index}层无法定位: {exc}") from exc
        if count != 1:
            suffix = "匹配不唯一" if count > 1 else "未匹配"
            raise TargetResolutionError(f"iframe第{index}层{suffix}（{count} 个）")
        try:
            scope = scope.frame_locator(selector)
        except Exception as exc:
            raise TargetResolutionError(f"iframe第{index}层无法进入: {exc}") from exc
    scoped, _reason = _select_scope_chain(scope, _profile(step))
    return scoped


def _scope_selector(item: dict[str, Any]) -> str:
    kind = _text(item.get("kind")).lower()
    role = _text(item.get("role"))
    if kind == "table_row":
        base = "tr"
    elif role:
        base = f'[role="{_quote_attribute(role)}"]'
    else:
        selectors = {
            "dialog": '[role="dialog"]',
            "drawer": '[role="dialog"]',
            "form": "form",
            "card": "article",
            "menu": '[role="menu"]',
            "listbox": '[role="listbox"]',
        }
        base = selectors.get(kind, "*")
    attrs = item.get("stable_attrs") if isinstance(item.get("stable_attrs"), dict) else {}
    return base + "".join(f'[{_text(key)}="{_quote_attribute(value)}"]' for key, value in attrs.items() if _text(key) and _text(value))


def _scope_reason(item: dict[str, Any]) -> str:
    headers = item.get("headers")
    if _text(item.get("kind")).lower() == "table_row" and isinstance(headers, dict) and headers:
        header, value = next(iter(headers.items()))
        return f"目标在{_text(header)}={_text(value)}的表格行中唯一匹配"
    return ""


def _apply_scope_filters(locator: Any, item: dict[str, Any]) -> Any:
    values: list[str] = []
    headers = item.get("headers")
    if isinstance(headers, dict):
        values.extend(_text(value) for value in headers.values())
    for key in ("name", "title", "text"):
        value = _text(item.get(key))
        if value:
            values.append(value)
    for value in values:
        locator = locator.filter(has_text=value)
    return locator


def _select_scope_chain(scope: Any, profile: dict[str, Any]) -> tuple[Any, str]:
    reason = ""
    chain = profile.get("scope_chain")
    if not isinstance(chain, list):
        return scope, reason
    for index, raw in enumerate(chain, start=1):
        if not isinstance(raw, dict):
            continue
        try:
            candidate = _apply_scope_filters(scope.locator(_scope_selector(raw)), raw)
            count = _safe_count(candidate)
        except TargetResolutionError:
            raise
        except Exception as exc:
            raise TargetResolutionError(f"范围第{index}层无法定位: {exc}") from exc
        if count != 1:
            suffix = "匹配不唯一" if count > 1 else "未匹配"
            raise TargetResolutionError(f"范围第{index}层{suffix}（{count} 个）")
        scope = candidate
        reason = _scope_reason(raw) or reason
    return scope, reason


def _scope_chain_reason(profile: dict[str, Any]) -> str:
    chain = profile.get("scope_chain")
    if not isinstance(chain, list):
        return ""
    for item in reversed(chain):
        if isinstance(item, dict) and (reason := _scope_reason(item)):
            return reason
    return ""


def _add_candidate(pool: dict[str, _Candidate], value: Any, score: Any, source: str, reason: str) -> None:
    locator = _text(value)
    if not locator:
        return
    try:
        normalized_score = int(score)
    except (TypeError, ValueError):
        normalized_score = 0
    normalized_score = max(0, min(100, normalized_score))
    previous = pool.get(locator)
    candidate = _Candidate(locator, normalized_score, source, (reason,))
    if previous is None or candidate.score > previous.score:
        pool[locator] = candidate
    elif candidate.score == previous.score and reason not in previous.reasons:
        pool[locator] = _Candidate(locator, previous.score, previous.source, previous.reasons + (reason,))


def _element_candidates(profile: dict[str, Any], pool: dict[str, _Candidate]) -> None:
    element = profile.get("element") if isinstance(profile.get("element"), dict) else {}
    attrs = element.get("stable_attrs") if isinstance(element.get("stable_attrs"), dict) else {}
    for key, score in (("data-testid", 100), ("data-test", 98), ("id", 85), ("name", 86)):
        value = _text(attrs.get(key))
        if value:
            selector = f'#{_quote_attribute(value)}' if key == "id" else f'[{key}="{_quote_attribute(value)}"]'
            _add_candidate(pool, selector, score, "target_profile", f"目标稳定属性 {key}")
    role = _text(element.get("role"))
    name = _text(element.get("accessible_name"))
    tag = _text(element.get("tag")).lower()
    if name:
        selector = tag if tag else ("button" if role == "button" else f'[role="{_quote_attribute(role)}"]' if role else "*")
        _add_candidate(pool, f'{selector}:has-text("{_quote_attribute(name)}")', 92, "target_profile", "目标角色与可访问名称")
    placeholder = _text(element.get("placeholder"))
    if placeholder:
        _add_candidate(pool, f'[placeholder="{_quote_attribute(placeholder)}"]', 82, "target_profile", "目标 placeholder")


def _candidate_pool(step: dict[str, Any], memory: Iterable[Any], frozen: bool) -> list[_Candidate]:
    pool: dict[str, _Candidate] = {}
    _add_candidate(pool, step.get("locator"), 70, "legacy", "录制主定位器")
    locator_profile = step.get("locator_profile") if isinstance(step.get("locator_profile"), dict) else {}
    for raw in locator_profile.get("candidates") or []:
        if not isinstance(raw, dict):
            continue
        strategy = _text(raw.get("strategy") or "css")
        _add_candidate(pool, raw.get("value") or raw.get("locator"), raw.get("score", _STRATEGY_SCORES.get(strategy, 48)), "recorded", f"录制候选 {strategy}")
    fallbacks = step.get("fallback_locators") or []
    for value in (fallbacks if isinstance(fallbacks, (list, tuple)) else [fallbacks]):
        _add_candidate(pool, value, 55, "legacy", "录制备用定位器")
    _element_candidates(_profile(step), pool)
    if not frozen:
        for raw in memory or ():
            if isinstance(raw, dict):
                _add_candidate(pool, raw.get("value") or raw.get("locator"), raw.get("score", 65), "memory", "定位记忆候选")
            else:
                _add_candidate(pool, raw, 65, "memory", "定位记忆候选")
        for key in ("ai_locator_candidates", "ai_candidates"):
            raw_candidates = step.get(key) or []
            for raw in (raw_candidates if isinstance(raw_candidates, (list, tuple)) else [raw_candidates]):
                if isinstance(raw, dict):
                    _add_candidate(pool, raw.get("value") or raw.get("locator"), raw.get("score", 60), "ai", "AI 候选")
                else:
                    _add_candidate(pool, raw, 60, "ai", "AI 候选")
    return sorted(pool.values(), key=lambda item: (-item.score, item.value))


def _action_compatible(action: str, profile: dict[str, Any]) -> bool:
    capability = _ACTION_CAPABILITY.get(action)
    if not capability:
        return True
    element = profile.get("element") if isinstance(profile.get("element"), dict) else {}
    capabilities = element.get("capabilities") if isinstance(element.get("capabilities"), dict) else {}
    return capabilities.get(capability) is not False


def _not_obscured(target: Any) -> bool:
    try:
        return bool(target.evaluate("""
            element => {
                const box = element.getBoundingClientRect();
                const top = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
                return !!top && (top === element || element.contains(top) || top.contains(element));
            }
        """))
    except Exception:
        return False


def _stable_box(target: Any) -> bool:
    try:
        first = target.bounding_box()
        second = target.bounding_box()
        if not first or not second:
            return False
        if min(float(first.get("width") or 0), float(first.get("height") or 0)) <= 0:
            return False
        return all(abs(float(first.get(key, 0)) - float(second.get(key, 0))) <= 1 for key in ("x", "y", "width", "height"))
    except Exception:
        return False


def _evaluate_candidate(scope: Any, candidate: _Candidate, profile: dict[str, Any], action: str, timeout_ms: int) -> tuple[Any, tuple[str, ...]] | tuple[None, tuple[str, ...]]:
    reasons = list(candidate.reasons)
    try:
        target = scope.locator(candidate.value)
        try:
            target.wait_for(state="visible", timeout=max(1, min(1500, timeout_ms)))
        except Exception:
            pass
        count = _safe_count(target)
        if count != 1:
            return None, tuple(reasons + [f"匹配 {count} 个元素，要求唯一"])
        visible = bool(target.is_visible())
        enabled = bool(target.is_enabled())
        compatible = _action_compatible(action, profile)
        unobscured = _not_obscured(target)
        stable = _stable_box(target)
    except Exception as exc:
        return None, tuple(reasons + [f"候选无法验证: {exc}"])
    if not visible:
        return None, tuple(reasons + ["目标不可见"])
    if not enabled:
        return None, tuple(reasons + ["目标未启用"])
    if not compatible:
        return None, tuple(reasons + ["目标与动作不兼容"])
    if not unobscured:
        return None, tuple(reasons + ["目标被遮挡"])
    if not stable:
        return None, tuple(reasons + ["目标布局不稳定"])
    return target, tuple(reasons + ["唯一、可见、启用、未遮挡且布局稳定"])


def resolve_target(
    page: Any,
    step: dict[str, Any],
    timeout_ms: int,
    memory: Iterable[Any] = (),
    frozen: bool = False,
) -> ResolvedTarget:
    """统一评估语义、录制、记忆与 AI 候选，只有高置信唯一目标才返回。"""
    profile = _profile(step)
    selected_page = select_profile_page(page, step, timeout_ms)
    scope = select_profile_scope(selected_page, step, timeout_ms)
    scope_reason = _scope_chain_reason(profile)
    action = _text(step.get("action")).lower()
    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    accepted: list[tuple[_Candidate, Any, tuple[str, ...]]] = []
    rejected: list[str] = []
    for candidate in _candidate_pool(step, memory, frozen):
        remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
        target, reasons = _evaluate_candidate(scope, candidate, profile, action, remaining_ms)
        if target is None:
            rejected.append(f"{candidate.value}: {reasons[-1]}")
            continue
        accepted.append((candidate, target, reasons))
    if not accepted:
        detail = "；".join(rejected[-3:])
        raise TargetResolutionError(f"没有安全且唯一的目标候选{('：' + detail) if detail else ''}")
    accepted.sort(key=lambda item: (-item[0].score, item[0].value))
    top_candidate, target, reasons = accepted[0]
    if top_candidate.score < MIN_CONFIDENCE:
        raise TargetResolutionError(f"候选置信度不足：{top_candidate.score} < {MIN_CONFIDENCE}")
    if len(accepted) > 1 and top_candidate.score - accepted[1][0].score < MIN_SCORE_GAP:
        raise TargetResolutionError(f"候选分差不足：{top_candidate.score} 与 {accepted[1][0].score}")
    final_reasons = reasons + ((scope_reason,) if scope_reason else ())
    return ResolvedTarget(
        target=target,
        used_locator=top_candidate.value,
        score=top_candidate.score,
        reasons=final_reasons,
        matched_count=1,
        page_identity=_page_identity(selected_page),
    )
