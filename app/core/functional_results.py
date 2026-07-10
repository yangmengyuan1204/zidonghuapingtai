from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    "FUNCTIONAL_TEST_RESULTS",
    "FunctionalCase",
    "FunctionalDataCheckResult",
    "FunctionalDataCheckRule",
    "FunctionalImpactItem",
    "FunctionalRequirementNote",
    "FunctionalRun",
    "FunctionalScreenshot",
    "PageSnapshot",
    "Project",
    "UiCase",
    "account_profile_summary",
    "default_account_profile_for_target",
    "functional_case_credibility_payload",
    "functional_case_credibility_summary",
    "functional_package_preflight_summary",
    "functional_result_counts",
    "functional_task_conclusion_summary",
    "latest_data_check_results_by_rule",
    "normalize_functional_result",
    "serialize",
    "serialize_many",
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


def _impl_normalize_functional_result(value: Any) -> str:
    text_value = str(value or "untested").strip().lower()
    return text_value if text_value in FUNCTIONAL_TEST_RESULTS else "untested"


def _impl_functional_result_counts(items: Iterable[Any], attr_name: str = "test_result") -> Dict[str, int]:
    counts = {key: 0 for key in FUNCTIONAL_TEST_RESULTS}
    total = 0
    for item in items:
        total += 1
        counts[normalize_functional_result(getattr(item, attr_name, None))] += 1
    counts["total"] = total
    return counts


def _impl_latest_data_check_results_by_rule(db: Session, task_id: int) -> Dict[int, FunctionalDataCheckResult]:
    latest: Dict[int, FunctionalDataCheckResult] = {}
    rows = (
        db.query(FunctionalDataCheckResult)
        .filter(FunctionalDataCheckResult.task_id == task_id)
        .order_by(FunctionalDataCheckResult.id.desc())
        .all()
    )
    for row in rows:
        if row.rule_id not in latest:
            latest[row.rule_id] = row
    return latest


def _impl_functional_task_conclusion_summary(db: Session, task: FunctionalTask) -> Dict[str, Any]:
    cases = db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id).all()
    impact_items = db.query(FunctionalImpactItem).filter(FunctionalImpactItem.task_id == task.id).all()
    rules = (
        db.query(FunctionalDataCheckRule)
        .filter(FunctionalDataCheckRule.task_id == task.id, FunctionalDataCheckRule.status != "inactive")
        .all()
    )
    latest_results = latest_data_check_results_by_rule(db, task.id)

    p0_blockers = []
    p1_failures = []
    for case in cases:
        priority = str(case.priority or "P1").upper()
        result = normalize_functional_result(case.test_result)
        if priority == "P0" and result in {"untested", "failed", "blocked"}:
            p0_blockers.append(case.title)
        elif priority == "P1" and result in {"failed", "blocked"}:
            p1_failures.append(case.title)

    impact_failures = [
        item.title
        for item in impact_items
        if normalize_functional_result(item.test_result) in {"failed", "blocked"}
    ]
    data_failures = []
    data_pending = []
    for rule in rules:
        latest = latest_results.get(rule.id)
        if not latest:
            data_pending.append(rule.rule_name)
        elif latest.result != "passed":
            data_failures.append(rule.rule_name)

    reasons = []
    if p0_blockers:
        reasons.append(f"P0 新功能用例未通过或未测试 {len(p0_blockers)} 条")
    if data_failures:
        reasons.append(f"数据核对失败 {len(data_failures)} 条")
    if p1_failures:
        reasons.append(f"P1 新功能用例失败/阻塞 {len(p1_failures)} 条")
    if impact_failures:
        reasons.append(f"关联影响回归失败/阻塞 {len(impact_failures)} 条")
    if data_pending:
        reasons.append(f"还有 {len(data_pending)} 条数据核对未执行")

    if p0_blockers or data_failures:
        decision = "not_recommended"
        decision_text = "不建议上线"
    elif p1_failures or impact_failures:
        decision = "risky"
        decision_text = "有风险上线"
    else:
        decision = "ready"
        decision_text = "可上线"

    return {
        "decision": decision,
        "decision_text": decision_text,
        "summary": "；".join(reasons) if reasons else "新功能、关联影响和数据核对暂无阻断风险",
        "new_feature": {
            "counts": functional_result_counts(cases),
            "p0_blockers": p0_blockers[:10],
            "p1_failures": p1_failures[:10],
        },
        "impact": {
            "counts": functional_result_counts(impact_items),
            "failures": impact_failures[:10],
        },
        "data": {
            "total": len(rules),
            "passed": sum(1 for rule in rules if latest_results.get(rule.id) and latest_results[rule.id].result == "passed"),
            "failed": len(data_failures),
            "pending": len(data_pending),
            "failures": data_failures[:10],
            "pending_rules": data_pending[:10],
        },
    }


def _impl_functional_task_detail(db: Session, task: FunctionalTask) -> Dict[str, Any]:
    data = serialize(task)
    project = db.get(Project, task.project_id)
    data["project_name"] = project.name if project else task.project_id
    data.update(account_profile_summary(default_account_profile_for_target(db, "functional_task", task.id, task.project_id)))
    cases = []
    for case in db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id).order_by(FunctionalCase.id.asc()).all():
        item = serialize(case)
        item.update(account_profile_summary(default_account_profile_for_target(db, "functional_case", case.id, task.project_id)))
        ui_case = db.get(UiCase, case.ui_case_id) if case.ui_case_id else None
        item.update(functional_case_credibility_payload(case, ui_case))
        cases.append(item)
    data["cases"] = cases
    data["snapshots"] = serialize_many(db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).all())
    data["screenshots"] = serialize_many(
        db.query(FunctionalScreenshot).filter(FunctionalScreenshot.task_id == task.id).order_by(FunctionalScreenshot.id.desc()).all()
    )
    data["requirement_notes"] = serialize_many(
        db.query(FunctionalRequirementNote)
        .filter(FunctionalRequirementNote.task_id == task.id)
        .order_by(FunctionalRequirementNote.id.desc())
        .all()
    )
    data["runs"] = serialize_many(db.query(FunctionalRun).filter(FunctionalRun.task_id == task.id).order_by(FunctionalRun.id.desc()).limit(20).all())
    data["impact_items"] = serialize_many(
        db.query(FunctionalImpactItem)
        .filter(FunctionalImpactItem.task_id == task.id)
        .order_by(FunctionalImpactItem.id.asc())
        .all()
    )
    rules = (
        db.query(FunctionalDataCheckRule)
        .filter(FunctionalDataCheckRule.task_id == task.id)
        .order_by(FunctionalDataCheckRule.id.asc())
        .all()
    )
    data_rules = []
    for rule in rules:
        item = serialize(rule)
        latest = (
            db.query(FunctionalDataCheckResult)
            .filter(FunctionalDataCheckResult.rule_id == rule.id)
            .order_by(FunctionalDataCheckResult.id.desc())
            .first()
        )
        item["latest_result"] = serialize(latest) if latest else None
        data_rules.append(item)
    data["data_check_rules"] = data_rules
    data["data_check_results"] = serialize_many(
        db.query(FunctionalDataCheckResult)
        .filter(FunctionalDataCheckResult.task_id == task.id)
        .order_by(FunctionalDataCheckResult.id.desc())
        .limit(20)
        .all()
    )
    data["conclusion"] = functional_task_conclusion_summary(db, task)
    data["preflight_summary"] = functional_package_preflight_summary(cases)
    data["credibility_summary"] = functional_case_credibility_summary(cases)
    return data


normalize_functional_result = _compat_wrapper(_impl_normalize_functional_result)
functional_result_counts = _compat_wrapper(_impl_functional_result_counts)
latest_data_check_results_by_rule = _compat_wrapper(_impl_latest_data_check_results_by_rule)
functional_task_conclusion_summary = _compat_wrapper(_impl_functional_task_conclusion_summary)
functional_task_detail = _compat_wrapper(_impl_functional_task_detail)
