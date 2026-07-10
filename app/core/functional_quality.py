from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    "ASSERTION_ACTIONS",
    "Counter",
    "FAILURE_CATEGORY_LABELS",
    "FUNCTIONAL_CASE_KIND_AUTH_NEGATIVE",
    "FUNCTIONAL_CASE_KIND_BUSINESS_AUTH",
    "FUNCTIONAL_CASE_KIND_MANUAL_ONLY",
    "FUNCTIONAL_TRUSTED_CATEGORIES",
    "GENERIC_EXPECTED_TEXTS",
    "LOCATOR_REQUIRED_ACTIONS",
    "QUALITY_AUTH_RISK",
    "QUALITY_EXECUTABLE",
    "QUALITY_MISSING_VARIABLES",
    "QUALITY_NOT_RECOMMENDED",
    "QUALITY_UNCHECKED",
    "RESULT_CREDIBILITY_LABELS",
    "TRUST_LEVEL_LABELS",
    "UiCase",
    "VALUE_REQUIRED_ACTIONS",
    "_api_assertion_count_from_log",
    "_business_assertion_count_from_log",
    "_check_item",
    "_json_log_payload",
    "case_has_business_assertion",
    "classify_failure_category",
    "datetime",
    "functional_case_kind",
    "json",
    "meaningful_expected_text",
    "parse_case_steps",
    "parse_json_value",
    "re",
    "to_json_text",
)


def _sync_compat_globals() -> None:
    module = sys.modules["app.core.utils"]
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(module, name)


def _compat_wrapper(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        _sync_compat_globals()
        return func(*args, **kwargs)

    return wrapped


def _impl_normalize_variable_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _impl_quality_report_payload(status_value: str, reason: str, issues: list[str] | None = None, **extra: Any) -> Dict[str, Any]:
    payload = {
        "status": status_value,
        "reason": reason,
        "issues": issues or [],
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    payload.update(extra)
    return payload


def _impl_parse_case_steps(raw: Any) -> list[Dict[str, Any]]:
    parsed = parse_json_value(raw or "", [])
    if isinstance(parsed, dict):
        parsed = parsed.get("steps") or parsed.get("actions") or []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _impl_functional_case_ui_payload(db: Session, case: FunctionalCase) -> tuple[UiCase | None, list[Dict[str, Any]]]:
    ui_case = db.get(UiCase, case.ui_case_id) if case.ui_case_id else None
    if not ui_case:
        return None, []
    return ui_case, parse_case_steps(ui_case.steps)


def _impl_functional_case_kind(case: FunctionalCase) -> str:
    text = " ".join([case.title or "", case.precondition or "", case.steps or "", case.expected or "", case.category or ""]).lower()
    auth_negative_markers = [
        "未登录",
        "未登陆",
        "不登录",
        "无账号",
        "unauth",
        "without login",
        "not logged",
        "直接访问",
    ]
    if any(marker in text for marker in auth_negative_markers):
        return FUNCTIONAL_CASE_KIND_AUTH_NEGATIVE
    manual_markers = [
        "网络中断",
        "断网",
        "弱网",
        "权限绕过",
        "已删除",
        "不存在",
        "无效id",
        "无效 id",
        "库存不足",
        "并发",
        "安全",
        "越权",
        "导出",
        "删除",
        "network",
        "permission",
        "deleted",
        "invalid id",
        "stock",
        "concurrency",
        "security",
        "privilege",
        "export",
        "delete",
    ]
    manual_categories = {"权限状态", "数据结果"}
    if str(case.category or "") in manual_categories or any(marker in text for marker in manual_markers):
        return FUNCTIONAL_CASE_KIND_MANUAL_ONLY
    return FUNCTIONAL_CASE_KIND_BUSINESS_AUTH


def _impl_functional_case_auto_trusted(case: FunctionalCase) -> bool:
    if functional_case_kind(case) != FUNCTIONAL_CASE_KIND_BUSINESS_AUTH:
        return False
    category = str(case.category or "")
    text = " ".join([case.title or "", case.steps or "", case.expected or ""]).lower()
    if category in FUNCTIONAL_TRUSTED_CATEGORIES:
        return True
    trusted_markers = ["登录后", "进入", "访问", "查看", "查询", "搜索", "筛选", "点击", "弹窗", "表单", "登记", "列表", "search", "filter"]
    risky_markers = [
        "删除",
        "导出",
        "网络",
        "权限",
        "未登录",
        "不存在",
        "已删除",
        "越权",
        "库存不足",
        "network",
        "permission",
        "deleted",
        "invalid id",
        "security",
        "privilege",
        "export",
        "delete",
    ]
    return any(marker in text for marker in trusted_markers) and not any(marker in text for marker in risky_markers)


def _impl_case_has_business_assertion(case: FunctionalCase, steps: list[Dict[str, Any]]) -> bool:
    for step in steps:
        action = str(step.get("action") or "").strip().lower()
        if action in ASSERTION_ACTIONS:
            locator = str(step.get("locator") or "").strip().lower()
            value = str(step.get("value") or "").strip()
            if action == "text_assert" and locator in {"", "body", "html"} and len(value) < 2:
                continue
            return True
        condition = step.get("success_condition") or step.get("expected") or step.get("assert")
        if isinstance(condition, (dict, list)) and condition:
            return True
        if isinstance(condition, str) and condition.strip():
            return True
    return False


def _impl_meaningful_expected_text(case: FunctionalCase) -> str:
    expected = re.sub(r"\s+", " ", str(case.expected or "")).strip()
    if expected in GENERIC_EXPECTED_TEXTS:
        return ""
    return expected[:160]


def _impl__json_log_payload(value: Any) -> Dict[str, Any]:
    payload = parse_json_value(value, {})
    return payload if isinstance(payload, dict) else {}


def _impl__business_assertion_count_from_log(log_data: Dict[str, Any]) -> int:
    business = log_data.get("business_verification")
    if isinstance(business, dict):
        try:
            return int(business.get("business_assertion_count") or 0)
        except (TypeError, ValueError):
            return 0
    steps = log_data.get("steps")
    if isinstance(steps, list):
        return sum(1 for step in steps if isinstance(step, dict) and str(step.get("action") or "").lower() in ASSERTION_ACTIONS)
    return 0


def _impl__api_assertion_count_from_log(log_data: Dict[str, Any]) -> int:
    assertions = log_data.get("assertions")
    return len(assertions) if isinstance(assertions, list) else 0


def _impl_classify_failure_category(log_data: Dict[str, Any], log_text: str = "") -> str:
    text = json.dumps(log_data, ensure_ascii=False, default=str).lower() if log_data else str(log_text or "").lower()
    error_category = str(log_data.get("error_category") or "").lower() if isinstance(log_data, dict) else ""
    if error_category in {"step_validation_failed", "system_error", "parallel_execution_failed"}:
        return "script_issue"
    if error_category in {"case_timeout", "environment_timeout"}:
        return "environment_issue"
    if any(marker in text for marker in ["locator", "selector", "not visible", "not found element", "定位器", "元素"]):
        return "locator_issue"
    if any(marker in text for marker in ["login_required", "/login", "#/login", "permission", "unauthorized", "forbidden", "登录", "权限", "越权"]):
        return "account_permission_issue"
    if any(marker in text for marker in ["missing_variables", "order_not_found", "not found order", "库存不足", "数据不足", "缺少变量", "缺少真实数据"]):
        return "test_data_issue"
    if any(marker in text for marker in ["timeout", "timed out", "network", "connection", "http 5", "502", "503", "504", "环境"]):
        return "environment_issue"
    if any(marker in text for marker in ["missing_business_assertion", "缺少业务断言", "需求", "needs_review"]):
        return "requirement_unclear"
    if any(marker in text for marker in ["assert", "failed_verification", "断言失败", "验证失败"]):
        return "product_or_assertion"
    return "unknown"


def _impl_test_record_credibility_payload(record: TestRecord) -> Dict[str, Any]:
    log_data = _json_log_payload(record.log)
    case_id = int(record.case_id or 0)
    script_label = str(log_data.get("script") or log_data.get("mode") or "").strip()
    traceability_status = "bound" if case_id > 0 else ("scenario_only" if script_label else "unbound")
    traceability_labels = {
        "bound": "已绑定用例",
        "scenario_only": "仅绑定脚本场景",
        "unbound": "未绑定测试对象",
    }
    warnings: list[str] = []
    if traceability_status != "bound":
        warnings.append("执行记录未绑定具体用例，不能作为强可信通过证据")

    result = str(record.result or "unknown")
    business_assertions = _business_assertion_count_from_log(log_data)
    api_assertions = _api_assertion_count_from_log(log_data)
    verification_status = str(log_data.get("verification_status") or "")
    if result == "passed":
        if record.case_type == "ui":
            trusted = traceability_status == "bound" and verification_status == "trusted_passed" and business_assertions > 0
        elif record.case_type == "api":
            trusted = traceability_status == "bound" and api_assertions > 0
        else:
            trusted = False
        result_credibility = "trusted_passed" if trusted else "weak_passed"
        if not trusted:
            if record.case_type == "ui" and business_assertions <= 0:
                warnings.append("UI 通过缺少业务断言证据，已按弱通过处理")
            if record.case_type == "api" and api_assertions <= 0:
                warnings.append("接口通过缺少显式断言，已按弱通过处理")
    else:
        failure_category = classify_failure_category(log_data, str(record.log or ""))
        result_credibility = "failed_with_reason" if failure_category != "unknown" else "failed_unclassified"

    failure_category = "" if result == "passed" else classify_failure_category(log_data, str(record.log or ""))
    return {
        "traceability_status": traceability_status,
        "traceability_label": traceability_labels.get(traceability_status, traceability_status),
        "test_object_label": script_label or (f"{record.case_type} #{case_id}" if case_id else ""),
        "result_credibility": result_credibility if result in {"passed", "failed"} else ("blocked" if result == "blocked" else "unknown"),
        "result_credibility_label": RESULT_CREDIBILITY_LABELS.get(result_credibility if result in {"passed", "failed"} else result, result),
        "business_assertion_count": business_assertions,
        "api_assertion_count": api_assertions,
        "failure_category": failure_category,
        "failure_category_label": FAILURE_CATEGORY_LABELS.get(failure_category, ""),
        "credibility_warnings": warnings,
        "is_trusted_pass": result == "passed" and result_credibility == "trusted_passed",
        "is_weak_pass": result == "passed" and result_credibility == "weak_passed",
    }


def _impl__check_item(key: str, label: str, passed: bool, warning: str = "") -> Dict[str, Any]:
    return {"key": key, "label": label, "passed": bool(passed), "warning": warning if not passed else ""}


def _impl_functional_case_credibility_payload(case: FunctionalCase, ui_case: UiCase | None = None) -> Dict[str, Any]:
    steps = parse_json_value(ui_case.steps, []) if ui_case else []
    if not isinstance(steps, list):
        steps = []
    quality = case.quality_status or QUALITY_UNCHECKED
    report = _json_log_payload(case.quality_report)
    has_precondition = bool(str(case.precondition or "").strip())
    has_steps = bool(str(case.steps or "").strip()) or bool(steps)
    has_expected = bool(str(case.expected or "").strip()) and bool(meaningful_expected_text(case) or str(case.expected or "").strip())
    has_assertion = case_has_business_assertion(case, steps) if steps else False
    has_test_data = quality != QUALITY_MISSING_VARIABLES and not report.get("required_seed_keys")
    risk_text = " ".join(str(item or "") for item in [case.title, case.category, case.precondition, case.steps, case.expected]).lower()
    covers_risk = any(marker in risk_text for marker in ["权限", "异常", "边界", "无效", "失败", "未登录", "越权", "error", "invalid"])

    checklist = [
        _check_item("precondition", "前置条件", has_precondition, "未写前置条件"),
        _check_item("steps", "操作步骤", has_steps, "未写操作步骤"),
        _check_item("expected", "预期结果", has_expected, "未写明确预期结果"),
        _check_item("business_assertion", "业务断言", has_assertion, "缺少可验证业务断言"),
        _check_item("test_data", "测试数据", has_test_data, "缺少真实测试数据或运行变量"),
        _check_item("risk_case", "权限/异常/边界", covers_risk, "未体现权限、异常或边界风险点"),
    ]
    blocking_failed = [item for item in checklist if item["key"] in {"steps", "expected", "business_assertion", "test_data"} and not item["passed"]]
    if quality == QUALITY_EXECUTABLE and not blocking_failed:
        level = "trusted"
    elif quality in {QUALITY_NOT_RECOMMENDED, QUALITY_AUTH_RISK, QUALITY_MISSING_VARIABLES} or len(blocking_failed) >= 2:
        level = "untrusted"
    else:
        level = "weak"
    issues = [item["warning"] for item in checklist if item["warning"]]
    return {
        "credibility_level": level,
        "credibility_label": TRUST_LEVEL_LABELS[level],
        "self_check": checklist,
        "self_check_warnings": issues,
        "can_be_trusted_pass": level == "trusted",
    }


def _impl_functional_case_credibility_summary(cases: list[Dict[str, Any]]) -> Dict[str, Any]:
    counts = Counter(str(item.get("credibility_level") or "weak") for item in cases)
    return {
        "total": len(cases),
        "trusted": counts.get("trusted", 0),
        "weak": counts.get("weak", 0),
        "untrusted": counts.get("untrusted", 0),
        "trusted_label": TRUST_LEVEL_LABELS["trusted"],
        "weak_label": TRUST_LEVEL_LABELS["weak"],
        "untrusted_label": TRUST_LEVEL_LABELS["untrusted"],
    }


def _impl_ensure_weak_business_assertion(db: Session, case: FunctionalCase, ui_case: UiCase, steps: list[Dict[str, Any]]) -> tuple[list[Dict[str, Any]], bool]:
    expected = meaningful_expected_text(case)
    if not expected or case_has_business_assertion(case, steps):
        return steps, False
    if any(isinstance(step, dict) and step.get("generated_assertion") == "expected_text" for step in steps):
        return steps, False
    next_steps = [dict(step) if isinstance(step, dict) else step for step in steps]
    next_steps.append(
        {
            "name": "自动弱断言",
            "action": "text_assert",
            "locator": "body",
            "value": expected,
            "generated_assertion": "expected_text",
        }
    )
    ui_case.steps = to_json_text(next_steps, [])
    db.flush()
    return next_steps, True


def _impl_case_locator_issues(steps: list[Dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for index, step in enumerate(steps, start=1):
        action = str(step.get("action") or "").strip().lower()
        locator = str(step.get("locator") or "").strip()
        if action in LOCATOR_REQUIRED_ACTIONS and not locator:
            issues.append(f"第{index}步 {action} 缺少 locator")
    return issues


def _impl_case_step_structure_issues(steps: list[Dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for index, step in enumerate(steps, start=1):
        action = str(step.get("action") or "").strip().lower()
        if action in VALUE_REQUIRED_ACTIONS and step.get("value") in (None, ""):
            issues.append(f"第{index}步 {action} 缺少 value")
        if action in LOCATOR_REQUIRED_ACTIONS and not str(step.get("locator") or "").strip():
            issues.append(f"第{index}步 {action} 缺少 locator")
    return issues


normalize_variable_name = _compat_wrapper(_impl_normalize_variable_name)
quality_report_payload = _compat_wrapper(_impl_quality_report_payload)
parse_case_steps = _compat_wrapper(_impl_parse_case_steps)
functional_case_ui_payload = _compat_wrapper(_impl_functional_case_ui_payload)
functional_case_kind = _compat_wrapper(_impl_functional_case_kind)
functional_case_auto_trusted = _compat_wrapper(_impl_functional_case_auto_trusted)
case_has_business_assertion = _compat_wrapper(_impl_case_has_business_assertion)
meaningful_expected_text = _compat_wrapper(_impl_meaningful_expected_text)
_json_log_payload = _compat_wrapper(_impl__json_log_payload)
_business_assertion_count_from_log = _compat_wrapper(_impl__business_assertion_count_from_log)
_api_assertion_count_from_log = _compat_wrapper(_impl__api_assertion_count_from_log)
classify_failure_category = _compat_wrapper(_impl_classify_failure_category)
test_record_credibility_payload = _compat_wrapper(_impl_test_record_credibility_payload)
_check_item = _compat_wrapper(_impl__check_item)
functional_case_credibility_payload = _compat_wrapper(_impl_functional_case_credibility_payload)
functional_case_credibility_summary = _compat_wrapper(_impl_functional_case_credibility_summary)
ensure_weak_business_assertion = _compat_wrapper(_impl_ensure_weak_business_assertion)
case_locator_issues = _compat_wrapper(_impl_case_locator_issues)
case_step_structure_issues = _compat_wrapper(_impl_case_step_structure_issues)
