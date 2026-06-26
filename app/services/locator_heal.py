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


# page.evaluate 提取可交互元素的脚本
_EXTRACT_JS = """
() => {
  const sels = 'button, a, input, textarea, select, [role="button"], [onclick]';
  return Array.from(document.querySelectorAll(sels)).slice(0, 80).map(el => {
    const text = (el.innerText || el.value || '').trim().slice(0, 50);
    return {
      tag: el.tagName.toLowerCase(),
      text: text,
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
        text ? `${el.tagName.toLowerCase()}:has-text("${text}")` : ''
      ].filter(Boolean)
    };
  });
}
"""


def _extract_interactive_elements(page: Any) -> list[Dict[str, Any]]:
    """提取页面可交互元素列表。"""
    try:
        result = page.evaluate(_EXTRACT_JS)
        if isinstance(result, list):
            return result
    except Exception as exc:
        logger.warning("提取页面 DOM 失败: %s", exc)
    return []


def _build_heal_prompt(failed_locator: str, step: Dict[str, Any], elements: list[Dict[str, Any]]) -> str:
    """构建 AI 推断 prompt。"""
    action = step.get("action") or ""
    step_value = step.get("value") or ""
    # 压缩元素列表，避免 prompt 过长
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
        for e in elements
    ]
    return (
        f"失效的 locator: {failed_locator}\n"
        f"步骤动作: {action}\n"
        f"步骤值: {step_value}\n"
        f"页面可交互元素列表: {json.dumps(compact, ensure_ascii=False)}\n\n"
        "任务：找出最可能对应的新 locator。只返回 JSON：\n"
        '{"new_locator": "...", "confidence": 0.9, "reason": "简短说明"}'
    )


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


def _validate_new_locator(page: Any, new_locator: str, step_action: str) -> bool:
    """验证 AI 返回的新 locator 是否唯一、可见、与动作兼容。"""
    if not new_locator or not isinstance(new_locator, str):
        return False
    try:
        count = page.locator(new_locator).count()
    except Exception:
        return False
    if count != 1:
        return False
    try:
        if not page.locator(new_locator).first.is_visible():
            return False
    except Exception:
        return False
    # 动作兼容性检查
    allowed = _ACTION_TAG_COMPAT.get(step_action)
    if allowed:
        try:
            tag = page.locator(new_locator).first.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            return False
        if tag not in allowed:
            return False
    return True


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
    ai_raw_response = ""
    try:
        result = call_local_model_json(config, prompt, timeout=60)
    except Exception as exc:
        logger.warning("Locator 自愈 AI 调用失败: %s", exc)
        _persist_heal_log(
            db, case_id, failed_locator, "", page_url, screenshot_path,
            action, prompt, f"AI 调用异常: {exc}", 0,
        )
        return None

    if result is None:
        _persist_heal_log(
            db, case_id, failed_locator, "", page_url, screenshot_path,
            action, prompt, "AI 返回空", 0,
        )
        return None

    ai_raw_response = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
    new_locator = ""
    if isinstance(result, dict):
        new_locator = str(result.get("new_locator") or "").strip()
    elif isinstance(result, str):
        new_locator = result.strip()

    if not new_locator:
        _persist_heal_log(
            db, case_id, failed_locator, "", page_url, screenshot_path,
            action, prompt, ai_raw_response, 0,
        )
        return None

    if not _validate_new_locator(page, new_locator, action):
        logger.info("Locator 自愈验证失败: %s", new_locator)
        _persist_heal_log(
            db, case_id, failed_locator, new_locator, page_url, screenshot_path,
            action, prompt, ai_raw_response, 0,
        )
        return None

    # 验证通过：写回用例 steps
    try:
        case = db.get(UiCase, case_id)
        if case:
            steps = json.loads(case.steps or "[]")
            if isinstance(steps, list):
                for s in steps:
                    if isinstance(s, dict) and s.get("locator") == failed_locator:
                        s["locator"] = new_locator
                        s["healed_at"] = datetime.now().isoformat()
                case.steps = json.dumps(steps, ensure_ascii=False)
                db.commit()
    except Exception as exc:
        logger.warning("Locator 自愈写回用例失败: %s", exc)

    _persist_heal_log(
        db, case_id, failed_locator, new_locator, page_url, screenshot_path,
        action, prompt, ai_raw_response, 1,
    )
    logger.info("Locator 自愈成功: %s -> %s", failed_locator, new_locator)
    return new_locator
