from __future__ import annotations

import sys
import time
import re
from datetime import datetime

from ..services.ui_locator_engine import select_step_page, select_step_scope


_COMPAT_NAMES = (
    'Any',
    'Dict',
    'Iterable',
    'SCREENSHOT_DIR',
    'UI_ACTION_LABELS',
    'UI_LOCATOR_REQUIRED',
    'UI_VALUE_REQUIRED',
    'UiStepExecutionError',
    '_capture_evidence_screenshot',
    '_case_has_business_assertion',
    '_classify_ui_error',
    '_heal_locator',
    '_locator_candidates',
    '_normalize_text',
    '_page_text_excerpt',
    '_perform_ui_action',
    '_resolve_locator',
    '_step_timeout_ms',
    '_wait_after_action',
    '_wait_for_url_contains',
    '_wait_text_contains',
    'datetime',
    'ensure_report_dirs',
    'time',
    'uuid4',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.executors"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl__perform_ui_action(page: Any, target: Any, action: str, value: Any, used_locator: str, timeout_ms: int) -> None:
    """在已定位的元素上执行 UI 动作（自愈路径复用，涵盖全部 action）。"""
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
        _wait_text_contains(target, value, timeout_ms)
    elif action == "extract_text":
        target.inner_text(timeout=timeout_ms)
    elif action == "extract_value":
        target.input_value(timeout=timeout_ms)


def _impl__run_ui_step(page: Any, step: Dict[str, Any], screenshots: list[str], default_timeout: int, case_id: int = 0, db: Any = None) -> Dict[str, Any]:
    import re
    started = time.time()
    action = str(step.get("action") or "").strip()
    locator = str(step.get("locator") or "").strip()
    value = step.get("value")
    name = str(step.get("name") or UI_ACTION_LABELS.get(action) or action or "未命名步骤")
    timeout_ms = _step_timeout_ms(step, default_timeout)
    page = select_step_page(page, step, timeout_ms=min(timeout_ms, 5000))
    locator_scope = select_step_scope(page, step)
    candidates = _locator_candidates(step)
    if case_id and db is not None:
        try:
            from ..services.ui_locator_learning import memory_candidates_for_step

            for candidate in memory_candidates_for_step(db, case_id, step):
                if candidate and candidate not in candidates:
                    candidates.append(candidate)
        except Exception:
            pass
    detail: Dict[str, Any] = {
        "name": name,
        "action": action,
        "locator": locator,
        "fallback_locators": [item for item in candidates if item != locator],
        "locator_quality": (step.get("locator_profile") or {}).get("quality") if isinstance(step.get("locator_profile"), dict) else "",
        "locator_candidates": (step.get("locator_profile") or {}).get("candidates", []) if isinstance(step.get("locator_profile"), dict) else [],
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
        elif action == "resume_order_flow":
            from ..data_scripts.full_flow import run_resume_order_flow_script
            from ..models import Env
            target_order_sn = ""
            if isinstance(value, dict):
                target_order_sn = str(value.get("order_sn") or "").strip()
            elif isinstance(value, str):
                target_order_sn = value.strip()
            if not target_order_sn:
                text = _page_text_excerpt(page, limit=3000)
                m = re.findall(r"(\d{14,18}-\d+|RO\d+)", text)
                if m:
                    target_order_sn = m[0]
            if not target_order_sn:
                raise ValueError("resume_order_flow 步骤缺少目标订单号 order_sn")

            env = db.get(Env, 1) if db else None
            flow_vars = {
                "account": "12345678990",
                "password": "123456",
                "backend_account": "Y001",
                "backend_password": "xiaolin666@@",
                "order_sn": target_order_sn,
                "warehouse_fill_scope": "current_order",
                "warehouse_sku_count": 1,
                "send_num": 1,
                "require_warehouse_sku_count": True,
                "auto_fill_cart_on_shortage": False,
                "timeout": 45,
            }
            if isinstance(value, dict):
                flow_vars.update(value)
            flow_vars["order_sn"] = target_order_sn

            passed, log_json, report_html, summary = run_resume_order_flow_script(env, flow_vars)
            detail["flow_passed"] = passed
            detail["flow_summary"] = summary
            detail["extracted"] = {
                "order_sn": target_order_sn,
                "porder_sn": summary.get("porder_sn", ""),
                "current_node": summary.get("current_node", "")
            }
            if not passed:
                raise RuntimeError(f"全流程流转失败于节点 {summary.get('current_node')}: {summary.get('reason') or summary.get('error')}")
        else:
            if action in UI_LOCATOR_REQUIRED and not candidates:
                raise ValueError(f"{action} 步骤缺少 locator")
            last_error = None
            for attempt in range(1, 4):
                try:
                    target, used_locator, matched_count = _resolve_locator(locator_scope, candidates, timeout_ms=min(timeout_ms, 15000))
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
                        try:
                            target.click(timeout=min(timeout_ms, 5000))
                        except Exception:
                            try:
                                target.evaluate("el => el.click()")
                            except Exception:
                                target.click(timeout=min(timeout_ms, 3000), force=True)
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
                        _wait_text_contains(target, value, timeout_ms)
                    elif action == "extract_text":
                        if str(used_locator or "").strip().lower() in ("body", "html", ":root"):
                            try:
                                extracted_value = page.evaluate("() => document.body ? (document.body.innerText || document.body.textContent || '') : ''")
                            except Exception:
                                extracted_value = target.text_content(timeout=timeout_ms) or ""
                        else:
                            try:
                                extracted_value = target.inner_text(timeout=timeout_ms)
                            except Exception:
                                try:
                                    extracted_value = target.evaluate("el => el.innerText || el.textContent || ''")
                                except Exception:
                                    extracted_value = target.text_content(timeout=timeout_ms) or ""
                        extract_regex = step.get("regex") or step.get("pattern")
                        if extract_regex:
                            m = re.search(str(extract_regex), str(extracted_value))
                            if m:
                                extracted_value = m.group(1) if m.groups() else m.group(0)
                            else:
                                raise ValueError(f"未能从提取文本中匹配到符合正则 {extract_regex!r} 的内容")
                        extract_key = str(step.get("variable") or step.get("variable_name") or step.get("save_as") or step.get("key") or name or locator or "value")
                        detail["extracted_key"] = extract_key
                        detail["extracted_value"] = extracted_value
                        detail["extracted"] = {extract_key: extracted_value}
                    elif action == "extract_value":
                        extracted_value = target.input_value(timeout=timeout_ms)
                        extract_regex = step.get("regex") or step.get("pattern")
                        if extract_regex:
                            m = re.search(str(extract_regex), str(extracted_value))
                            if m:
                                extracted_value = m.group(1) if m.groups() else m.group(0)
                            else:
                                raise ValueError(f"未能从提取值中匹配到符合正则 {extract_regex!r} 的内容")
                        extract_key = str(step.get("variable") or step.get("variable_name") or step.get("save_as") or step.get("key") or name or locator or "value")
                        detail["extracted_key"] = extract_key
                        detail["extracted_value"] = extracted_value
                        detail["extracted"] = {extract_key: extracted_value}
                    else:
                        raise ValueError(f"Unsupported UI action: {action}")
                    _wait_after_action(page, action)
                    if attempt > 1:
                        detail["retry_count"] = attempt - 1
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt >= 3:
                        # 自愈尝试：解析定位器失败时尝试自愈
                        healed_locator = locator or (candidates[0] if candidates else "")
                        try:
                            healed = _heal_locator(page, healed_locator, str(exc))
                            if healed and healed not in candidates:
                                candidates.insert(0, healed)
                                detail["healed"] = True
                                detail["original_locator"] = healed_locator
                                detail["healed_locator"] = healed
                                target, used_locator, matched_count = _resolve_locator(locator_scope, candidates, timeout_ms=min(timeout_ms, 15000))
                                detail["used_locator"] = used_locator
                                detail["matched_count"] = matched_count
                                _perform_ui_action(page, target, action, value, used_locator, timeout_ms)
                                detail["retry_count"] = attempt
                                break
                        except Exception:
                            # 规则自愈失败，尝试 AI 自愈
                            if case_id and db is not None:
                                try:
                                    from ..services.locator_heal import auto_heal
                                    heal_result = auto_heal(
                                        page, case_id,
                                        healed_locator,
                                        step, db,
                                        screenshot_path=detail.get("before_screenshot") or "",
                                    )
                                    if heal_result:
                                        ai_healed = heal_result["locator"]
                                        if ai_healed and ai_healed not in candidates:
                                            candidates.insert(0, ai_healed)
                                            detail["healed"] = True
                                            detail["original_locator"] = healed_locator
                                            detail["healed_locator"] = ai_healed
                                            detail["ai_healed"] = True
                                            detail["heal_confidence"] = heal_result.get("confidence", 0)
                                            detail["heal_reason"] = heal_result.get("reason", "")
                                            target, used_locator, matched_count = _resolve_locator(locator_scope, candidates, timeout_ms=min(timeout_ms, 15000))
                                            detail["used_locator"] = used_locator
                                            detail["matched_count"] = matched_count
                                            _perform_ui_action(page, target, action, value, used_locator, timeout_ms)
                                            detail["retry_count"] = attempt
                                            break
                                except Exception:
                                    pass
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


def _impl__validate_ui_steps_for_execution(steps: Any) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
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


def _perform_ui_action(page: Any, target: Any, action: str, value: Any, used_locator: str, timeout_ms: int) -> None:
    _sync_compat_globals()
    return _impl__perform_ui_action(page, target, action, value, used_locator, timeout_ms)


def _run_ui_step(page: Any, step: Dict[str, Any], screenshots: list[str], default_timeout: int, case_id: int=0, db: Any=None) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__run_ui_step(page, step, screenshots, default_timeout, case_id, db)


def _validate_ui_steps_for_execution(steps: Any) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    _sync_compat_globals()
    return _impl__validate_ui_steps_for_execution(steps)
