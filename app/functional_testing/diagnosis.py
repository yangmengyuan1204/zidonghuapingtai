from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'AiConfig',
    'Any',
    'Dict',
    'FunctionalRun',
    '_failure_reason_and_actions',
    '_infer_failed_step',
    '_load_json_object',
    '_locator_from_error',
    '_step_text',
    'call_local_model_json',
    'json',
    're',
    'rule_diagnose_failure',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.functional_testing"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl__load_json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _impl__step_text(step: Any) -> str:
    if not isinstance(step, dict):
        return str(step or "未知步骤")
    if step.get("name"):
        return str(step.get("name"))
    action = step.get("action") or "未知动作"
    locator = step.get("locator")
    value = step.get("value")
    parts = [f"动作：{action}"]
    if locator:
        parts.append(f"定位：{locator}")
    if value not in (None, ""):
        parts.append(f"值：{value}")
    return "，".join(parts)


def _impl__locator_from_error(error: str) -> str:
    patterns = [
        r"locator\((?:'|\")(.+?)(?:'|\")\)",
        r"locator\s+['\"](.+?)['\"]",
        r"locator\s+(.+?)\s+(?:is not visible|failed)",
    ]
    for pattern in patterns:
        match = re.search(pattern, error)
        if match:
            return match.group(1)
    return ""


def _impl__infer_failed_step(ui_log: Dict[str, Any], error: str) -> tuple[Any, int | None]:
    detail = ui_log.get("failed_step_detail")
    if isinstance(detail, dict):
        return detail, detail.get("index") if isinstance(detail.get("index"), int) else ui_log.get("failed_step_index")
    step = ui_log.get("failed_step")
    index = ui_log.get("failed_step_index")
    if step:
        return step, index if isinstance(index, int) else None
    steps = ui_log.get("steps") if isinstance(ui_log.get("steps"), list) else []
    locator = _locator_from_error(error)
    if locator:
        for pos, item in enumerate(steps, start=1):
            if isinstance(item, dict) and item.get("locator") == locator:
                return item, pos
    action_hints = [
        ("text_assert failed", "text_assert"),
        ("assert_visible failed", "assert_visible"),
        ("assert_url failed", "assert_url"),
        ("assert_value failed", "assert_value"),
    ]
    for error_text, action in action_hints:
        if error_text in error:
            for pos, item in enumerate(steps, start=1):
                if isinstance(item, dict) and item.get("action") == action:
                    return item, pos
    return None, None


def _impl__failure_reason_and_actions(error: str, failed_step: Any) -> tuple[str, str, list[str]]:
    if isinstance(failed_step, dict) and failed_step.get("category"):
        return (
            str(failed_step.get("category") or "用例执行异常"),
            str(failed_step.get("reason") or "执行器已定位到失败步骤，但没有更多原因。"),
            [str(failed_step.get("suggestion") or "查看失败截图和步骤日志继续排查")],
        )
    error_lower = error.lower()
    locator = _locator_from_error(error)
    if "unknown engine" in error_lower:
        return (
            "定位写法不符合 Playwright 规则",
            "用例里的 locator 写法无法被 Playwright 识别，例如 placeholder=xxx 不是当前执行器支持的选择器写法。",
            ["把 locator 改成 CSS 写法，例如 input[placeholder=\"邮箱/手机号\"]", "重新扫描页面 DOM 后重新生成 UI 步骤", "优先使用 id、name、data-testid 这类稳定定位"],
        )
    if "playwright 不可用" in error or "greenlet" in error_lower or "browser" in error_lower and "executable" in error_lower:
        return (
            "执行环境异常",
            "本机 Playwright、浏览器或 Python 依赖不可用，用例还没有真正跑到页面步骤。",
            ["先修复本地运行环境，再重跑该用例", "检查 Chromium/Chrome/Edge 是否可启动", "确认服务启动使用的是同一个稳定 Python 虚拟环境"],
        )
    if "timeout" in error_lower or "waiting for" in error_lower:
        target = f"：{locator}" if locator else ""
        return (
            f"页面元素等待超时{target}",
            "页面在规定时间内没有出现目标元素，常见原因是页面没有进入预期状态、定位不准确、加载慢或前一步点击没有生效。",
            ["打开失败截图确认当前页面停在哪一步", "确认前一步操作后页面是否应该出现该元素", "优先用稳定 locator，必要时增加等待或改成更准确的步骤"],
        )
    if "text_assert failed" in error:
        return (
            "页面文案断言失败",
            "实际页面文本和用例预期不一致，可能是预期写错、页面文案变更，或当前页面不是目标页面。",
            ["查看失败截图和实际页面文案", "确认产品需求中的文案是否已变更", "如果只是标题/说明类文案，不建议作为主流程强断言"],
        )
    if "assert_url failed" in error:
        return (
            "页面跳转结果不符合预期",
            "执行后 URL 没有跳到预期地址，可能是提交失败、权限/登录状态异常，或预期跳转地址写错。",
            ["检查当前 URL 和失败截图", "确认前置账号、验证码、测试数据是否有效", "确认需求里成功后的跳转页面"],
        )
    if "assert_value failed" in error:
        return (
            "输入值校验失败",
            "输入框中的实际值和预期值不一致，可能是输入未生效、控件格式化了内容，或定位到了错误输入框。",
            ["确认输入框 locator 是否唯一", "检查页面是否自动格式化输入内容", "必要时先 assert_visible 再 input"],
        )
    if "strict mode violation" in error_lower:
        return (
            "元素定位不唯一",
            "当前 locator 匹配到了多个元素，Playwright 无法判断应该操作哪一个。",
            ["改用更唯一的定位方式，如 id、name、placeholder 或更精确的 text", "避免使用过宽泛的 input/button 定位"],
        )
    if "not visible" in error_lower:
        return (
            "目标元素不可见",
            "元素存在但当前不可见，可能被弹窗遮挡、在折叠区域内、还未渲染完成或需要滚动。",
            ["查看截图确认元素是否被遮挡", "补充点击展开、滚动或等待步骤", "确认当前页面状态是否符合预期"],
        )
    return (
        "用例执行异常",
        "执行过程中出现异常，需要结合失败截图、当前页面和用例步骤继续判断。",
        ["先查看失败截图确认页面状态", "检查失败步骤的 locator 和测试数据", "必要时把页面 DOM 重新扫描后重新生成步骤"],
    )


def _impl_rule_diagnose_failure(run: FunctionalRun) -> Dict[str, Any]:
    run_log = _load_json_object(run.log)
    records = run_log.get("records") if isinstance(run_log.get("records"), list) else []
    failed_records = [item for item in records if isinstance(item, dict) and item.get("result") != "passed"]
    passed_count = run_log.get("passed_count") or run.passed_count or 0
    failed_count = run_log.get("failed_count") or run.failed_count or len(failed_records)
    failed_cases = []
    for record in failed_records:
        ui_log = _load_json_object(record.get("log"))
        error = ui_log.get("error") or record.get("error") or "未记录具体错误"
        failed_step, failed_step_no = _infer_failed_step(ui_log, error)
        failure, likely_reason, suggested_actions = _failure_reason_and_actions(error, failed_step)
        failed_cases.append(
            {
                "case_title": record.get("title") or ui_log.get("case_name") or "未知用例",
                "record_id": record.get("record_id"),
                "failed_step_no": failed_step_no,
                "failed_step": _step_text(failed_step) if failed_step else "未能从日志中定位到具体步骤",
                "failure": failure,
                "likely_reason": likely_reason,
                "suggested_actions": suggested_actions,
                "error_detail": error,
                "screenshot": record.get("screenshot") or ui_log.get("screenshot") or "",
            }
        )
    summary = f"本次执行共通过 {passed_count} 条，失败 {failed_count} 条。"
    if failed_cases:
        summary += f" 需要优先处理：{failed_cases[0]['case_title']}。"
    return {
        "summary": summary,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "failed_cases": failed_cases,
        "overall_suggestions": [
            "先按失败用例逐条查看截图，确认页面实际停留位置。",
            "优先检查失败步骤的定位和前置数据，不要先改业务代码。",
            "如果页面结构改过，建议重新扫描页面 DOM 后重新生成 UI 步骤。",
        ],
    }


def _impl_diagnose_failure(run: FunctionalRun, config: AiConfig | None) -> str:
    rule_payload = rule_diagnose_failure(run)
    prompt = f"""
你是一名资深软件测试工程师，请把下面的自动化失败日志整理成测试人员容易理解的诊断。
要求：
1. 明确指出哪一条用例失败；
2. 明确指出失败在第几步、该步骤做了什么；
3. 用测试视角解释失败现象、可能原因；
4. 给出可执行的下一步排查建议；
5. 只输出合法 JSON，字段保持为：summary、passed_count、failed_count、failed_cases、overall_suggestions。

规则初步诊断：
{json.dumps(rule_payload, ensure_ascii=False, indent=2)}

原始日志：
{(run.log or "")[:16000]}
"""
    try:
        payload = call_local_model_json(config, prompt)
        if isinstance(payload, dict) and payload.get("failed_cases") is not None:
            return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception as exc:
        rule_payload["model_warning"] = f"本地模型诊断失败，已使用规则诊断：{exc}"
        return json.dumps(rule_payload, ensure_ascii=False, indent=2)
    rule_payload["model_warning"] = "本地模型未返回可识别的诊断结构，已使用规则诊断。"
    return json.dumps(rule_payload, ensure_ascii=False, indent=2)


def _load_json_object(value: Any) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__load_json_object(value)

def _step_text(step: Any) -> str:
    _sync_compat_globals()
    return _impl__step_text(step)

def _locator_from_error(error: str) -> str:
    _sync_compat_globals()
    return _impl__locator_from_error(error)

def _infer_failed_step(ui_log: Dict[str, Any], error: str) -> tuple[Any, int | None]:
    _sync_compat_globals()
    return _impl__infer_failed_step(ui_log, error)

def _failure_reason_and_actions(error: str, failed_step: Any) -> tuple[str, str, list[str]]:
    _sync_compat_globals()
    return _impl__failure_reason_and_actions(error, failed_step)

def rule_diagnose_failure(run: FunctionalRun) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl_rule_diagnose_failure(run)

def diagnose_failure(run: FunctionalRun, config: AiConfig | None) -> str:
    _sync_compat_globals()
    return _impl_diagnose_failure(run, config)
