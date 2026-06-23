"""
需求测试包工作流状态服务。

不执行任何副作用操作，只聚合现有数据判断流程状态。
供 GET /api/functional-tasks/{task_id}/workflow 接口使用。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from collections import Counter
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from ..models import (
    FunctionalCase,
    FunctionalRun,
    FunctionalScreenshot,
    FunctionalTask,
    FunctionalRequirementNote,
    PageSnapshot,
)
from ..functional_testing import read_axure_text

logger = logging.getLogger(__name__)


# ── 状态常量（与 main.py 一致） ──────────────────────────────
QUALITY_EXECUTABLE = "executable"
QUALITY_UNCHECKED = "unchecked"
QUALITY_AUTH_RISK = "auth_risk"
QUALITY_MISSING_VARIABLES = "missing_variables"
QUALITY_LOCATOR_RISK = "locator_risk"
QUALITY_NEEDS_REVIEW = "needs_review"
QUALITY_NOT_RECOMMENDED = "not_recommended"

STEP_KEYS = ["materials", "cases", "review", "ui_steps", "preflight", "execution", "diagnosis", "conclusion"]
STEP_LABELS = {
    "materials": "需求材料",
    "cases": "AI生成用例",
    "review": "人工确认",
    "ui_steps": "生成UI步骤",
    "preflight": "执行前预检",
    "execution": "自动执行",
    "diagnosis": "失败诊断",
    "conclusion": "测试结论",
}


def build_workflow_status(db: Session, task: FunctionalTask) -> Dict[str, Any]:
    """
    计算测试包的完整工作流状态。
    纯查询聚合，不写数据库。
    """
    # ── 基础数据 ──────────────────────────────────
    cases: List[FunctionalCase] = (
        db.query(FunctionalCase)
        .filter(FunctionalCase.task_id == task.id)
        .order_by(FunctionalCase.id.asc())
        .all()
    )
    runs: List[FunctionalRun] = (
        db.query(FunctionalRun)
        .filter(FunctionalRun.task_id == task.id)
        .order_by(FunctionalRun.id.desc())
        .limit(20)
        .all()
    )
    snapshots: List[PageSnapshot] = (
        db.query(PageSnapshot)
        .filter(PageSnapshot.task_id == task.id)
        .order_by(PageSnapshot.id.desc())
        .all()
    )
    screenshots: List[FunctionalScreenshot] = (
        db.query(FunctionalScreenshot)
        .filter(FunctionalScreenshot.task_id == task.id)
        .all()
    )
    notes: List[FunctionalRequirementNote] = (
        db.query(FunctionalRequirementNote)
        .filter(FunctionalRequirementNote.task_id == task.id)
        .all()
    )
    axure_text = read_axure_text(task.axure_path)

    # ── 逐步骤状态计算 ─────────────────────────────
    steps: List[Dict[str, Any]] = []

    # 1. 需求材料
    materials_ok = _materials_status(task, axure_text, snapshots, screenshots, notes)
    steps.append(materials_ok)

    # 2. AI 生成用例
    cases_ok = _cases_status(cases)
    steps.append(cases_ok)

    # 3. 人工确认
    review_ok = _review_status(cases)
    steps.append(review_ok)

    # 4. 生成 UI 步骤
    ui_steps_ok = _ui_steps_status(cases)
    steps.append(ui_steps_ok)

    # 5. 执行前预检
    preflight_ok = _preflight_status(cases)
    steps.append(preflight_ok)

    # 6. 自动执行
    exec_ok = _execution_status(runs)
    steps.append(exec_ok)

    # 7. 失败诊断
    diag_ok = _diagnosis_status(runs)
    steps.append(diag_ok)

    # 8. 测试结论
    conclusion_ok = _conclusion_status(runs, task.status)
    steps.append(conclusion_ok)

    # ── 聚合指标 ──────────────────────────────────
    total_cases = len(cases)
    approved_cases = sum(1 for c in cases if c.automation_status == "approved")
    draft_cases = sum(1 for c in cases if c.automation_status == "draft")
    needs_review_cases = sum(1 for c in cases if c.automation_status in ("needs_review", "ui_steps_generated"))
    has_ui_steps = sum(1 for c in cases if c.ui_case_id is not None)
    missing_ui_steps = total_cases - has_ui_steps

    quality_counts: Dict[str, int] = Counter()
    for c in cases:
        qs = c.quality_status or QUALITY_UNCHECKED
        quality_counts[qs] += 1

    # ── 建议下一步动作 ─────────────────────────────
    next_actions = _suggest_next_actions(task, cases, quality_counts, total_cases, approved_cases, missing_ui_steps, runs)

    # ── 整体就绪度 ─────────────────────────────────
    readiness_score = _calculate_readiness(steps)

    # ── 当前阶段（找到第一个未完成的步骤） ──────────
    current_stage = _find_current_stage(steps)

    return {
        "task_id": task.id,
        "task_name": task.iteration_name,
        "task_status": task.status,
        "current_stage": current_stage,
        "readiness_score": readiness_score,
        "steps": steps,
        "next_actions": next_actions,
        "summary": {
            "total_cases": total_cases,
            "approved_cases": approved_cases,
            "draft_cases": draft_cases,
            "needs_review_cases": needs_review_cases,
            "has_ui_steps": has_ui_steps,
            "missing_ui_steps": missing_ui_steps,
            "overall_status": task.status,
            "latest_run_result": runs[0].result if runs else "",
            "quality": {
                "executable": quality_counts.get(QUALITY_EXECUTABLE, 0),
                "unchecked": quality_counts.get(QUALITY_UNCHECKED, 0),
                "auth_risk": quality_counts.get(QUALITY_AUTH_RISK, 0),
                "missing_variables": quality_counts.get(QUALITY_MISSING_VARIABLES, 0),
                "locator_risk": quality_counts.get(QUALITY_LOCATOR_RISK, 0),
                "needs_review": quality_counts.get(QUALITY_NEEDS_REVIEW, 0),
                "not_recommended": quality_counts.get(QUALITY_NOT_RECOMMENDED, 0),
            },
        },
        "computed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── 内部步骤状态判断函数 ────────────────────────────────


def _step_result(key: str, status: str, summary: str = "", detail: Any = None) -> Dict[str, Any]:
    return {
        "key": key,
        "label": STEP_LABELS.get(key, key),
        "status": status,  # "done" | "warning" | "blocked" | "pending"
        "summary": summary,
        "detail": detail or {},
    }


def _materials_status(
    task: FunctionalTask,
    axure_text: str,
    snapshots: List[PageSnapshot],
    screenshots: List[FunctionalScreenshot],
    notes: List[FunctionalRequirementNote],
) -> Dict[str, Any]:
    has_axure = bool(task.axure_path and axure_text)
    has_snapshot = len(snapshots) > 0
    has_screenshots = len(screenshots) > 0
    has_requirement = bool((task.requirement_text or "").strip())
    has_context = bool((task.context or "").strip())
    has_notes = len(notes) > 0

    sources = []
    if has_requirement:
        sources.append("需求文本")
    if has_axure:
        sources.append("Axure")
    if has_snapshot:
        sources.append("页面快照")
    if has_screenshots:
        sources.append(f"截图({len(screenshots)}张)")
    if has_notes:
        sources.append("需求备注")

    if not sources:
        return _step_result("materials", "pending", "暂无需求材料，请上传 Axure/截图或填写需求说明")

    if has_snapshot or has_screenshots or has_axure:
        return _step_result("materials", "done", f"已有材料：{'、'.join(sources)}", {"sources": sources})

    return _step_result("materials", "warning", f"仅有关联文本材料：{'、'.join(sources)}，建议上传 Axure 或截图", {"sources": sources})


def _cases_status(cases: List[FunctionalCase]) -> Dict[str, Any]:
    if not cases:
        return _step_result("cases", "pending", "尚未生成测试用例")

    # 区分用户编辑过的用例 vs AI 生成的草稿
    total = len(cases)
    edited = sum(1 for c in cases if c.automation_status == "approved")
    status = "done" if edited >= total * 0.5 else "warning"
    return _step_result("cases", status, f"已生成 {total} 条测试点", {"total": total, "edited": edited})


def _review_status(cases: List[FunctionalCase]) -> Dict[str, Any]:
    if not cases:
        return _step_result("review", "pending", "请先生成测试用例")
    total = len(cases)
    approved = sum(1 for c in cases if c.automation_status == "approved")
    draft = sum(1 for c in cases if c.automation_status in ("draft", "ui_steps_generated", "needs_review"))
    if approved == total:
        return _step_result("review", "done", f"全部 {total} 条用例已确认")
    if approved == 0:
        return _step_result("review", "blocked", f"所有 {total} 条用例均未确认，请逐条或批量确认", {"total": total, "unconfirmed": total})
    return _step_result("review", "warning", f"还有 {draft} 条用例未确认，已确认 {approved}/{total}", {"total": total, "approved": approved, "unconfirmed": draft})


def _ui_steps_status(cases: List[FunctionalCase]) -> Dict[str, Any]:
    if not cases:
        return _step_result("ui_steps", "pending", "请先生成测试用例")
    total = len(cases)
    has_steps = sum(1 for c in cases if c.ui_case_id is not None)
    if has_steps == total:
        return _step_result("ui_steps", "done", f"全部 {total} 条用例已生成 UI 步骤")
    if has_steps == 0:
        return _step_result("ui_steps", "blocked", f"所有 {total} 条用例均缺少 UI 步骤，请批量生成", {"total": total, "missing": total})
    return _step_result(
        "ui_steps", "warning", f"还有 {total - has_steps} 条用例缺少 UI 步骤，已生成 {has_steps}/{total}",
        {"total": total, "has_steps": has_steps, "missing": total - has_steps},
    )


def _preflight_status(cases: List[FunctionalCase]) -> Dict[str, Any]:
    if not cases:
        return _step_result("preflight", "pending", "请先生成测试用例")
    unchecked = sum(1 for c in cases if not c.quality_status or c.quality_status == QUALITY_UNCHECKED)
    executable = sum(1 for c in cases if c.quality_status == QUALITY_EXECUTABLE)
    blocked = sum(1 for c in cases if c.quality_status in (QUALITY_AUTH_RISK, QUALITY_NOT_RECOMMENDED))
    manual = sum(
        1 for c in cases
        if c.quality_status in (QUALITY_NEEDS_REVIEW, QUALITY_MISSING_VARIABLES, QUALITY_LOCATOR_RISK)
    )
    if unchecked == len(cases):
        return _step_result("preflight", "pending", "尚未执行预检，请点击「预检测试包」")
    if executable == len(cases):
        return _step_result("preflight", "done", f"全部 {len(cases)} 条用例预检通过，可自动执行")
    if blocked > 0:
        return _step_result("preflight", "blocked", f"{blocked} 条用例被阻断（登录/步骤缺失），{executable} 条可执行",
                            {"total": len(cases), "executable": executable, "blocked": blocked, "manual": manual})
    return _step_result("preflight", "warning", f"{manual} 条需人工介入，{executable} 条可执行",
                        {"total": len(cases), "executable": executable, "manual": manual, "blocked": blocked})


def _execution_status(runs: List[FunctionalRun]) -> Dict[str, Any]:
    if not runs:
        return _step_result("execution", "pending", "尚未执行测试")
    latest = runs[0]
    total_passed = sum(r.passed_count for r in runs)
    total_failed = sum(r.failed_count for r in runs)
    if latest.result == "running":
        return _step_result("execution", "warning", "测试正在执行中...",
                            {"latest_run_id": latest.id, "result": "running"})
    if latest.result == "passed":
        return _step_result("execution", "done", f"最近一次执行通过（{latest.passed_count} 通过 / {latest.failed_count} 失败）",
                            {"latest_run_id": latest.id, "result": "passed", "passed": latest.passed_count, "failed": latest.failed_count})
    return _step_result("execution", "warning", f"最近一次执行失败（{latest.passed_count} 通过 / {latest.failed_count} 失败），累计失败 {total_failed} 条",
                        {"latest_run_id": latest.id, "result": "failed", "passed": latest.passed_count, "failed": latest.failed_count})


def _diagnosis_status(runs: List[FunctionalRun]) -> Dict[str, Any]:
    failed_runs = [r for r in runs if r.result == "failed"]
    if not failed_runs:
        return _step_result("diagnosis", "pending", "暂无失败的执行记录需要诊断")
    diagnosed = 0
    undiagnosed = 0
    for r in failed_runs:
        log_data = _parse_json(r.log, {})
        if log_data.get("diagnosis"):
            diagnosed += 1
        else:
            undiagnosed += 1
    if undiagnosed == 0 and diagnosed > 0:
        return _step_result("diagnosis", "done", f"已诊断 {diagnosed} 次失败执行")
    if diagnosed > 0:
        return _step_result("diagnosis", "warning", f"已诊断 {diagnosed} 次，还有 {undiagnosed} 次失败待诊断",
                            {"total_failed": len(failed_runs), "diagnosed": diagnosed, "undiagnosed": undiagnosed})
    return _step_result("diagnosis", "warning", f"有 {undiagnosed} 次失败执行待诊断", {"undiagnosed": undiagnosed})


def _conclusion_status(runs: List[FunctionalRun], task_status: str) -> Dict[str, Any]:
    if not runs:
        return _step_result("conclusion", "pending", "请先执行测试")
    if task_status in ("passed", "failed"):
        return _step_result("conclusion", "done", "已有测试结论，可随时刷新", {"status": task_status})
    return _step_result("conclusion", "warning", "请刷新测试结论", {"status": task_status})


# ── 下一步建议 ────────────────────────────────────────


def _suggest_next_actions(
    task: FunctionalTask,
    cases: List[FunctionalCase],
    quality_counts: Dict[str, int],
    total_cases: int,
    approved_cases: int,
    missing_ui_steps: int,
    runs: List[FunctionalRun],
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    failed_ids = [c.id for c in cases if c.test_result == "failed"]
    blocked_auth_ids = [c.id for c in cases if c.test_result == "blocked" and c.quality_status == QUALITY_AUTH_RISK]
    blocked_data_ids = [c.id for c in cases if c.test_result == "blocked" and c.quality_status == QUALITY_MISSING_VARIABLES]
    review_result_ids = [c.id for c in cases if c.test_result == "needs_review" or c.quality_status == QUALITY_NEEDS_REVIEW]

    # 没有用例 → 生成
    if not cases:
        actions.append({
            "key": "generate_cases",
            "label": "AI 生成测试用例",
            "reason": "尚未生成测试用例",
            "target_case_ids": [],
        })
        return actions

    # 未确认的用例 → 确认
    unconfirmed_ids = [c.id for c in cases if c.automation_status not in ("approved",)]
    if unconfirmed_ids:
        actions.append({
            "key": "review_cases",
            "label": f"确认 {len(unconfirmed_ids)} 条待确认用例",
            "reason": f"{len(unconfirmed_ids)} 条用例尚未确认",
            "target_case_ids": unconfirmed_ids[:100],
        })

    # 缺少 UI steps → 生成
    missing_step_ids = [c.id for c in cases if c.automation_status == "approved" and c.ui_case_id is None]
    if missing_step_ids:
        actions.append({
            "key": "generate_ui_steps",
            "label": f"为 {len(missing_step_ids)} 条已确认用例生成 UI 步骤",
            "reason": f"{len(missing_step_ids)} 条已确认用例缺少 UI 步骤",
            "target_case_ids": missing_step_ids[:100],
        })

    # 待预检 → 预检
    unchecked_ids = [c.id for c in cases if not c.quality_status or c.quality_status == QUALITY_UNCHECKED]
    if unchecked_ids:
        actions.append({
            "key": "preflight",
            "label": f"预检 {len(unchecked_ids)} 条用例",
            "reason": f"{len(unchecked_ids)} 条用例尚未执行预检",
            "target_case_ids": unchecked_ids[:100],
        })

    # 可执行 → 执行
    if failed_ids:
        actions.append({
            "key": "check_diagnosis",
            "label": f"查看 {len(failed_ids)} 条失败步骤/截图",
            "reason": "已有用例执行失败，优先定位断言、页面或定位问题",
            "target_case_ids": failed_ids[:100],
        })

    if blocked_auth_ids:
        actions.append({
            "key": "fix_account",
            "label": f"修复 {len(blocked_auth_ids)} 条账号阻断",
            "reason": "账号或登录前置未通过，不能继续执行业务步骤",
            "target_case_ids": blocked_auth_ids[:100],
        })

    if blocked_data_ids:
        actions.append({
            "key": "fix_data",
            "label": f"补充 {len(blocked_data_ids)} 条缺失测试数据",
            "reason": "缺真实业务数据的用例不会试跑，也不会标绿",
            "target_case_ids": blocked_data_ids[:100],
        })

    if review_result_ids:
        actions.append({
            "key": "review_assertions",
            "label": f"确认 {len(review_result_ids)} 条弱断言/缺断言用例",
            "reason": "结果可信度不足，需要补断言或人工确认",
            "target_case_ids": review_result_ids[:100],
        })

    executable_ids = [
        c.id
        for c in cases
        if c.quality_status == QUALITY_EXECUTABLE
        and c.test_result not in ("passed", "failed", "blocked", "needs_review")
    ]
    if executable_ids and quality_counts.get(QUALITY_EXECUTABLE, 0) > 0:
        actions.append({
            "key": "execute",
            "label": f"执行 {len(executable_ids)} 条高可信用例",
            "reason": "预检通过且可自动执行",
            "target_case_ids": executable_ids[:100],
        })

    # 失败待诊断（仅当有失败执行记录时）
    failed_runs_exist = any(r.result == "failed" for r in runs)
    if failed_runs_exist and not failed_ids:
        actions.append({
            "key": "check_diagnosis",
            "label": "查看失败诊断",
            "reason": "检查最近失败原因并修复",
            "target_case_ids": [],
        })

    return actions


# ── 辅助函数 ─────────────────────────────────────────


def _calculate_readiness(steps: List[Dict[str, Any]]) -> int:
    """0-100 就绪度评分"""
    weights = {
        "materials": 10,
        "cases": 15,
        "review": 20,
        "ui_steps": 15,
        "preflight": 10,
        "execution": 15,
        "diagnosis": 5,
        "conclusion": 10,
    }
    score = 0
    for s in steps:
        key = s["key"]
        w = weights.get(key, 10)
        if s["status"] == "done":
            score += w
        elif s["status"] == "warning":
            score += w * 0.5
        # blocked/pending = 0
    return score


def _find_current_stage(steps: List[Dict[str, Any]]) -> str:
    """找到当前所处的阶段 key"""
    for s in steps:
        if s["status"] in ("pending", "blocked"):
            return s["key"]
        if s["status"] == "warning":
            return s["key"]
    return steps[-1]["key"] if steps else "unknown"


def _parse_json(value: Any, fallback: Any = None) -> Any:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value) if value else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback
