"""Locator 自动自愈服务。

UI 用例执行中 locator 失效时，自动扫描页面 DOM、调用 AI 推断新 locator、
验证后写回用例并继续执行。
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..core.utils import latest_ai_config
from ..functional_testing import call_local_model_json
from ..models import LocatorHealLog, UiCase

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────
_MAX_ELEMENTS = 80        # DOM 提取元素上限
_MAX_TEXT_LEN = 50        # 元素文本截断长度
_AI_TIMEOUT = 30          # AI 调用超时（秒），用户要求"立即修复继续"
_VALIDATION_TIMEOUT = 3000  # locator 验证超时（毫秒）

# action → 允许的标签集合（用于验证 AI 返回的 locator 是否与动作兼容）
_ACTION_TAG_COMPAT: Dict[str, set[str]] = {
    "input": {"input", "textarea"},
    "click": {"button", "a", "input", "select", "option"},
    "check": {"input"},
    "uncheck": {"input"},
    "select": {"select"},
    "text_assert": set(),  # 不限制
    "wait_for_selector": set(),
    "assert_visible": set(),
    "assert_value": {"input", "textarea", "select"},
}

# page.evaluate 提取可交互元素的脚本
_EXTRACT_JS = """
() => {
  const sels = 'button, a, input, textarea, select, [role="button"], [onclick]';
  const esc = s => (s || '').replace(/"/g, '\\\\"').slice(0, %d);
  return Array.from(document.querySelectorAll(sels)).slice(0, %d).map(el => {
    const text = (el.innerText || el.value || '').trim();
    const tag = el.tagName.toLowerCase();
    return {
      tag: tag,
      text: text.slice(0, %d),
      id: el.id || '',
      name: el.name || '',
      class: (typeof el.className === 'string' ? el.className : '').slice(0, 80),
      placeholder: el.placeholder || '',
      type: el.type || '',
      role: el.getAttribute('role') || '',
      locator_candidates: [
        el.id ? '#' + el.id : '',
        el.name ? `[name="${el.name}"]` : '',
        el.placeholder ? `input[placeholder*="${el.placeholder}"]` : '',
        text ? `${tag}:has-text("${esc(text)}")` : ''
      ].filter(Boolean)
    };
  });
}
""" % (_MAX_TEXT_LEN, _MAX_ELEMENTS, _MAX_TEXT_LEN)


# ── DOM 提取 ─────────────────────────────────────────
def _extract_interactive_elements(page: Any) -> list[Dict[str, Any]]:
    """提取页面可交互元素列表。"""
    try:
        result = page.evaluate(_EXTRACT_JS)
        if isinstance(result, list):
            return result
    except Exception as exc:
        logger.warning("提取页面 DOM 失败: %s", exc)
    return []


# ── Prompt 构建 ───────────────────────────────────────
def _mask_sensitive(value: Any, action: str, name: str = "") -> str:
    """脱敏敏感值（密码等）。"""
    text = str(value or "")
    if not text:
        return ""
    if "password" in name.lower() or "password" in action.lower() or "密码" in name:
        return "***"
    return text


def _filter_relevant_elements(failed_locator: str, elements: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """按相关性过滤元素，减少 prompt 体积。

    优先保留与失效 locator 有文本/属性关联的元素。
    """
    if len(elements) <= 30:
        return elements
    # 提取失效 locator 中的关键词
    keywords: set[str] = set()
    for part in failed_locator.replace("#", " ").replace(".", " ").replace("[", " ").replace("]", " ").split():
        part = part.strip().strip("\"'")
        if len(part) >= 2:
            keywords.add(part.lower())

    def _score(e: Dict[str, Any]) -> int:
        score = 0
        text = (e.get("text") or "").lower()
        id_val = (e.get("id") or "").lower()
        name_val = (e.get("name") or "").lower()
        placeholder = (e.get("placeholder") or "").lower()
        for kw in keywords:
            if kw in text or kw in id_val or kw in name_val or kw in placeholder:
                score += 2
        if e.get("tag") in ("button", "a", "input"):
            score += 1
        return score

    return sorted(elements, key=_score, reverse=True)[:30]


def _build_heal_prompt(failed_locator: str, step: Dict[str, Any], elements: list[Dict[str, Any]]) -> str:
    """构建 AI 推断 prompt。"""
    action = step.get("action") or ""
    name = step.get("name") or ""
    step_value = _mask_sensitive(step.get("value"), action, name)
    relevant = _filter_relevant_elements(failed_locator, elements)
    compact = [
        {
            "tag": e.get("tag"),
            "text": e.get("text"),
            "id": e.get("id"),
            "name": e.get("name"),
            "placeholder": e.get("placeholder"),
            "type": e.get("type"),
            "role": e.get("role"),
            "candidates": e.get("locator_candidates", []),
        }
        for e in relevant
    ]
    return (
        f"失效的 locator: {failed_locator}\n"
        f"步骤动作: {action}\n"
        f"步骤值: {step_value}\n"
        f"页面可交互元素列表: {json.dumps(compact, ensure_ascii=False)}\n\n"
        "任务：找出最可能对应的新 locator。只返回 JSON：\n"
        '{"new_locator": "...", "confidence": 0.9, "reason": "简短说明"}'
    )


# ── 验证 ──────────────────────────────────────────────
def _validate_new_locator(page: Any, new_locator: str, step_action: str) -> bool:
    """验证 AI 返回的新 locator 是否唯一、可见、与动作兼容。"""
    if not new_locator or not isinstance(new_locator, str):
        return False
    try:
        loc = page.locator(new_locator)
        if loc.count() != 1:
            return False
        first = loc.first
        if not first.is_visible(timeout=_VALIDATION_TIMEOUT):
            return False
        # 动作兼容性检查
        allowed = _ACTION_TAG_COMPAT.get(step_action)
        if allowed:
            tag = first.evaluate("el => el.tagName.toLowerCase()")
            if tag not in allowed:
                return False
    except Exception:
        return False
    return True


# ── 日志记录 ──────────────────────────────────────────
def _persist_heal_log(
    db: Session,
    case_id: int,
    old_locator: str,
    new_locator: str,
    page_url: str,
    screenshot_path: str,
    step_action: str,
    ai_prompt: str,
    ai_response: str,
    auto_applied: int,
) -> None:
    """写 LocatorHealLog 记录。"""
    log = LocatorHealLog(
        case_id=case_id,
        old_locator=old_locator,
        new_locator=new_locator,
        page_url=page_url or "",
        screenshot_path=screenshot_path or "",
        confirmed=1 if auto_applied else 0,
        step_action=step_action or "",
        ai_prompt=ai_prompt or "",
        ai_response=ai_response or "",
        auto_applied=auto_applied,
        create_time=datetime.now(),
    )
    db.add(log)
    db.commit()


def _fail(
    db: Session, case_id: int, old_locator: str, new_locator: str,
    page_url: str, screenshot_path: str, action: str,
    prompt: str, ai_response: str,
) -> None:
    """统一记录失败日志。"""
    _persist_heal_log(
        db, case_id, old_locator, new_locator, page_url, screenshot_path,
        action, prompt, ai_response, 0,
    )


# ── 核心：写回用例 ────────────────────────────────────
def _apply_heal_to_case(db: Session, case_id: int, old_locator: str, new_locator: str) -> bool:
    """把新 locator 写回用例 steps。"""
    try:
        case = db.get(UiCase, case_id)
        if not case:
            return False
        steps = json.loads(case.steps or "[]")
        if not isinstance(steps, list):
            return False
        now = datetime.now().isoformat()
        changed = False
        for s in steps:
            if isinstance(s, dict) and s.get("locator") == old_locator:
                s["locator"] = new_locator
                s["healed_at"] = now
                changed = True
        if changed:
            case.steps = json.dumps(steps, ensure_ascii=False)
            db.commit()
        return changed
    except Exception as exc:
        logger.warning("Locator 自愈写回用例失败: %s", exc)
        return False


# ── 对外入口 ──────────────────────────────────────────
def auto_heal(
    page: Any,
    case_id: int,
    failed_locator: str,
    step: Dict[str, Any],
    db: Session,
    screenshot_path: str = "",
) -> Optional[str]:
    """AI 自动修复失效 locator。

    返回新 locator 字符串（已验证可用）；失败返回 None。
    """
    action = step.get("action") or ""
    page_url = ""
    try:
        page_url = page.url or ""
    except Exception:
        pass

    config = latest_ai_config(db)
    if not config or not config.base_url or not config.model:
        logger.info("Locator 自愈跳过：未配置 AI")
        return None

    elements = _extract_interactive_elements(page)
    if not elements:
        logger.info("Locator 自愈跳过：页面无可交互元素")
        return None

    prompt = _build_heal_prompt(failed_locator, step, elements)

    # AI 调用
    try:
        result = call_local_model_json(config, prompt, timeout=_AI_TIMEOUT)
    except Exception as exc:
        logger.warning("Locator 自愈 AI 调用失败: %s", exc)
        _fail(db, case_id, failed_locator, "", page_url, screenshot_path, action, prompt, f"AI 调用异常: {exc}")
        return None

    if result is None:
        _fail(db, case_id, failed_locator, "", page_url, screenshot_path, action, prompt, "AI 返回空")
        return None

    ai_raw = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)

    # 解析 AI 返回
    new_locator = ""
    if isinstance(result, dict):
        new_locator = str(result.get("new_locator") or "").strip()
    elif isinstance(result, str):
        new_locator = result.strip()

    if not new_locator:
        _fail(db, case_id, failed_locator, "", page_url, screenshot_path, action, prompt, ai_raw)
        return None

    # 验证
    if not _validate_new_locator(page, new_locator, action):
        logger.info("Locator 自愈验证失败: %s", new_locator)
        _fail(db, case_id, failed_locator, new_locator, page_url, screenshot_path, action, prompt, ai_raw)
        return None

    # 写回用例
    _apply_heal_to_case(db, case_id, failed_locator, new_locator)

    _persist_heal_log(
        db, case_id, failed_locator, new_locator, page_url, screenshot_path,
        action, prompt, ai_raw, 1,
    )
    logger.info("Locator 自愈成功: %s -> %s", failed_locator, new_locator)
    return new_locator
