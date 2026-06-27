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
from ..models import LocatorHealHistory, LocatorHealLog, UiCase

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────
_MAX_ELEMENTS = 80        # DOM 提取元素上限
_MAX_TEXT_LEN = 50        # 元素文本截断长度
_AI_TIMEOUT = 30          # AI 调用超时（秒），用户要求"立即修复继续"
_VALIDATION_TIMEOUT = 3000  # locator 验证超时（毫秒）
_SHADOW_DEPTH = 3         # Shadow DOM 递归深度上限
_PAGE_STABLE_TIMEOUT = 2000  # 页面稳定等待（毫秒）

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

# page.evaluate 提取可交互元素的脚本（含 Shadow DOM 穿透 + 多语言 selector）
_EXTRACT_JS = """
() => {
  const sels = 'button, a, input, textarea, select, [role="button"], [onclick], [class*="btn"], [class*="button"]';
  const esc = s => (s || '').replace(/"/g, '\\\\"').slice(0, %d);
  function deepQueryAll(root, selector, depth) {
    if (depth < 0) return [];
    let results = Array.from(root.querySelectorAll(selector));
    try {
      for (const el of root.querySelectorAll('*')) {
        if (el.shadowRoot) {
          results = results.concat(deepQueryAll(el.shadowRoot, selector, depth - 1));
        }
      }
    } catch(e) {}
    return results;
  }
  const all = deepQueryAll(document, sels, %d).slice(0, %d);
  const seen = new Set();
  return all.filter(el => {
    const key = el.tagName + '|' + (el.id||'') + '|' + (el.name||'') + '|' + (el.innerText||'').slice(0,20);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).map(el => {
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
""" % (_MAX_TEXT_LEN, _SHADOW_DEPTH, _MAX_ELEMENTS, _MAX_TEXT_LEN)


# ── DOM 提取 ─────────────────────────────────────────
def _wait_page_stable(page: Any, timeout: int = _PAGE_STABLE_TIMEOUT) -> None:
    """等待页面加载稳定（SPA 动态渲染）。"""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        page.wait_for_timeout(300)


def _extract_interactive_elements(page: Any) -> list[Dict[str, Any]]:
    """提取页面可交互元素列表（含动态等待重试）。"""
    try:
        result = page.evaluate(_EXTRACT_JS)
        if isinstance(result, list) and result:
            return result
    except Exception as exc:
        logger.warning("提取页面 DOM 失败: %s", exc)
    # 元素为空时等待页面稳定后重试 1 次
    _wait_page_stable(page)
    try:
        result = page.evaluate(_EXTRACT_JS)
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


# ── 历史学习 ──────────────────────────────────────────
def _lookup_heal_history(db: Session, project_id: int | None, old_locator: str) -> str | None:
    """从历史映射表中查找已验证的新 locator。"""
    try:
        q = db.query(LocatorHealHistory).filter(
            LocatorHealHistory.old_locator == old_locator,
            LocatorHealHistory.success_count > 0,
        )
        if project_id:
            q = q.filter(
                (LocatorHealHistory.project_id == project_id) | (LocatorHealHistory.project_id.is_(None))
            )
        record = q.order_by(LocatorHealHistory.success_count.desc()).first()
        if record:
            logger.info("历史学习命中: %s -> %s (success=%d)", old_locator, record.new_locator, record.success_count)
            return record.new_locator
    except Exception as exc:
        logger.warning("历史学习查询失败: %s", exc)
    return None


def _record_heal_history(db: Session, project_id: int | None, old_locator: str, new_locator: str) -> None:
    """记录 / 更新历史映射。"""
    try:
        existing = db.query(LocatorHealHistory).filter(
            LocatorHealHistory.old_locator == old_locator,
            LocatorHealHistory.new_locator == new_locator,
        ).first()
        if existing:
            existing.apply_count = (existing.apply_count or 0) + 1
            existing.last_used = datetime.now()
            db.commit()
        else:
            record = LocatorHealHistory(
                project_id=project_id,
                old_locator=old_locator,
                new_locator=new_locator,
                apply_count=1,
                success_count=0,
                last_used=datetime.now(),
                create_time=datetime.now(),
            )
            db.add(record)
            db.commit()
    except Exception as exc:
        logger.warning("历史学习记录失败: %s", exc)


def update_heal_history_on_success(db: Session, old_locator: str, new_locator: str) -> None:
    """用例执行成功后调用，更新 success_count。"""
    try:
        record = db.query(LocatorHealHistory).filter(
            LocatorHealHistory.old_locator == old_locator,
            LocatorHealHistory.new_locator == new_locator,
        ).first()
        if record:
            record.success_count = (record.success_count or 0) + 1
            record.last_used = datetime.now()
            db.commit()
    except Exception as exc:
        logger.warning("历史学习更新 success_count 失败: %s", exc)


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
def _validate_new_locator(page: Any, new_locator: str, step_action: str, quick: bool = False) -> bool:
    """验证 AI 返回的新 locator 是否唯一、可见、与动作兼容。

    quick=True 时使用短超时（历史学习命中场景，元素理应已存在）。
    """
    if not new_locator or not isinstance(new_locator, str):
        return False
    timeout = 800 if quick else _VALIDATION_TIMEOUT
    try:
        loc = page.locator(new_locator)
        if loc.count() != 1:
            return False
        first = loc.first
        if not first.is_visible(timeout=timeout):
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


# ── 精简 prompt（重试时使用） ─────────────────────────
def _build_compact_prompt(failed_locator: str, step: Dict[str, Any], elements: list[Dict[str, Any]]) -> str:
    """精简 prompt（仅 tag+text），用于 AI 重试。"""
    action = step.get("action") or ""
    name = step.get("name") or ""
    step_value = _mask_sensitive(step.get("value"), action, name)
    compact = [
        {"tag": e.get("tag"), "text": e.get("text"), "id": e.get("id")}
        for e in elements[:20]
    ]
    return (
        f"失效 locator: {failed_locator}\n"
        f"动作: {action}\n"
        f"元素: {json.dumps(compact, ensure_ascii=False)}\n"
        '只返回 JSON: {"new_locator": "...", "confidence": 0.9}'
    )


# ── 对外入口 ──────────────────────────────────────────
def auto_heal(
    page: Any,
    case_id: int,
    failed_locator: str,
    step: Dict[str, Any],
    db: Session,
    screenshot_path: str = "",
) -> Optional[Dict[str, Any]]:
    """AI 自动修复失效 locator。

    返回 dict: {"locator": 新locator, "confidence": 0.9, "reason": "..."}；失败返回 None。
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

    # 检查自愈开关
    heal_enabled = getattr(config, "heal_enabled", 1)
    if not heal_enabled:
        logger.info("Locator 自愈跳过：已关闭")
        return None

    # 查询用例（复用，避免后续重复查询）
    case_obj = None
    project_id = None
    try:
        case_obj = db.get(UiCase, case_id)
        if case_obj:
            project_id = case_obj.project_id
    except Exception:
        pass

    # 历史学习：先查已验证的映射，命中则跳过 AI（<10ms）
    cached = _lookup_heal_history(db, project_id, failed_locator)
    if cached and _validate_new_locator(page, cached, action, quick=True):
        _apply_heal_to_case(db, case_id, failed_locator, cached)
        _record_heal_history(db, project_id, failed_locator, cached)
        _persist_heal_log(
            db, case_id, failed_locator, cached, page_url, screenshot_path,
            action, "历史学习命中", "历史映射", 1,
        )
        logger.info("Locator 历史学习命中: %s -> %s", failed_locator, cached)
        return {"locator": cached, "confidence": 1.0, "reason": "历史学习命中"}

    threshold = getattr(config, "heal_confidence_threshold", 0.7) or 0.7

    elements = _extract_interactive_elements(page)
    if not elements:
        logger.info("Locator 自愈跳过：页面无可交互元素")
        return None

    # 两次尝试：标准 prompt → 精简 prompt
    prompts = [
        _build_heal_prompt(failed_locator, step, elements),
        _build_compact_prompt(failed_locator, step, elements),
    ]

    last_ai_raw = ""
    for attempt_idx, prompt in enumerate(prompts):
        try:
            result = call_local_model_json(config, prompt, timeout=_AI_TIMEOUT)
        except Exception as exc:
            logger.warning("Locator 自愈 AI 调用失败(第%d次): %s", attempt_idx + 1, exc)
            last_ai_raw = f"AI 调用异常: {exc}"
            continue

        if result is None:
            last_ai_raw = "AI 返回空"
            continue

        ai_raw = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        last_ai_raw = ai_raw

        # 解析 AI 返回
        new_locator = ""
        confidence = 0.0
        reason = ""
        if isinstance(result, dict):
            new_locator = str(result.get("new_locator") or "").strip()
            try:
                confidence = float(result.get("confidence") or 0)
            except (ValueError, TypeError):
                confidence = 0.0
            reason = str(result.get("reason") or "")
        elif isinstance(result, str):
            new_locator = result.strip()

        if not new_locator:
            continue

        # 验证 locator 有效性
        if not _validate_new_locator(page, new_locator, action):
            logger.info("Locator 自愈验证失败(第%d次): %s", attempt_idx + 1, new_locator)
            # 记录验证失败日志（仅最后一次）
            if attempt_idx == len(prompts) - 1:
                _fail(db, case_id, failed_locator, new_locator, page_url, screenshot_path, action, prompt, ai_raw)
            continue

        # confidence 阈值检查
        if confidence < threshold:
            logger.info("Locator 自愈 confidence %.2f < 阈值 %.2f，仅记录不自动应用", confidence, threshold)
            _persist_heal_log(
                db, case_id, failed_locator, new_locator, page_url, screenshot_path,
                action, prompt, ai_raw, 0,
            )
            return None

        # 验证通过 + confidence 达标：写回用例
        _apply_heal_to_case(db, case_id, failed_locator, new_locator)
        _record_heal_history(db, project_id, failed_locator, new_locator)

        _persist_heal_log(
            db, case_id, failed_locator, new_locator, page_url, screenshot_path,
            action, prompt, ai_raw, 1,
        )
        logger.info("Locator 自愈成功(第%d次): %s -> %s (confidence=%.2f)", attempt_idx + 1, failed_locator, new_locator, confidence)
        return {"locator": new_locator, "confidence": confidence, "reason": reason}

    # 两次尝试均失败
    _fail(db, case_id, failed_locator, "", page_url, screenshot_path, action, prompts[0], last_ai_raw)
    return None
