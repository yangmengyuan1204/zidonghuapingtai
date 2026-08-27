from __future__ import annotations

import json
import threading
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import UiRecordPreflight


def determine_recorded_case_status(preflight_status: str, steps: list[dict[str, Any]]) -> str:
    if preflight_status != "passed":
        return "draft"
    for step in steps:
        profile = step.get("locator_profile") if isinstance(step, dict) else None
        if isinstance(profile, dict) and profile.get("quality") == "risk":
            return "draft"
    return "active"


def preflight_matches_steps(row: UiRecordPreflight, steps: list[dict[str, Any]]) -> bool:
    try:
        checked_steps = json.loads(row.steps_json or "[]")
    except (TypeError, ValueError):
        return False
    return isinstance(checked_steps, list) and checked_steps == steps


def _progress_step(step: dict[str, Any], index: int) -> dict[str, Any]:
    profile = step.get("locator_profile") if isinstance(step.get("locator_profile"), dict) else {}
    return {
        "index": index,
        "name": step.get("name") or step.get("action") or "步骤",
        "action": step.get("action") or "",
        "locator": step.get("locator") or "",
        "status": "queued",
        "locator_quality": profile.get("quality") or "",
        "locator_candidates": list(profile.get("candidates") or []),
    }


def merge_preflight_progress(report: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(report or {})
    event = str(payload.get("event") or "")
    result["status"] = str(payload.get("status") or result.get("status") or "running")
    if payload.get("total_steps") is not None:
        result["total_steps"] = int(payload.get("total_steps") or 0)
    if event == "prepared":
        raw_steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
        result["steps"] = [
            _progress_step(step if isinstance(step, dict) else {"raw": step}, index)
            for index, step in enumerate(raw_steps, start=1)
        ]
        result["total_steps"] = len(raw_steps)
    steps = list(result.get("steps") or [])
    raw_index = payload.get("index")
    index = int(raw_index) if isinstance(raw_index, int) and raw_index > 0 else 0
    if index:
        while len(steps) < index:
            steps.append(_progress_step({}, len(steps) + 1))
        current = dict(steps[index - 1])
        current["status"] = "running" if event == "step_start" else str(payload.get("status") or current.get("status") or "")
        detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}
        if detail:
            current.update(detail)
            current["index"] = index
        steps[index - 1] = current
        result["steps"] = steps
        result["current_step_index"] = index
    result["completed_steps"] = sum(1 for step in steps if step.get("status") in {"passed", "failed"})
    for key in ("error", "screenshot", "failed_step_index", "failed_step_detail"):
        if payload.get(key) not in (None, ""):
            result[key] = payload.get(key)
    return result


def summarize_preflight_log(passed: bool, log_text: str, screenshot: str = "") -> dict[str, Any]:
    try:
        data = json.loads(log_text or "{}")
    except (TypeError, ValueError):
        data = {"error": str(log_text or "预检执行失败")}
    steps = list(data.get("step_logs") or [])
    failed_detail = data.get("failed_step_detail")
    if isinstance(failed_detail, dict):
        failed_step = dict(failed_detail)
        failed_step.setdefault("index", data.get("failed_step_index"))
        if not steps or steps[-1].get("index") != failed_step.get("index") or steps[-1].get("status") != "failed":
            steps.append(failed_step)
    selected_screenshot = ""
    if isinstance(failed_detail, dict):
        selected_screenshot = str(
            failed_detail.get("failure_screenshot")
            or failed_detail.get("screenshot")
            or ""
        )
    selected_screenshot = selected_screenshot or str(data.get("screenshot") or screenshot or "")
    return {
        "status": "passed" if passed else "failed",
        "steps": steps,
        "failed_step_index": data.get("failed_step_index"),
        "error": data.get("error") or "",
        "error_category": data.get("error_category") or (failed_detail or {}).get("category") or "",
        "current_url": data.get("current_url") or (failed_detail or {}).get("current_url") or "",
        "screenshot": selected_screenshot,
    }


def create_preflight(
    db: Session,
    *,
    session_id: str,
    project_id: int,
    steps: list[dict[str, Any]],
    assertion_text: str,
) -> UiRecordPreflight:
    row = UiRecordPreflight(
        run_id=uuid4().hex,
        session_id=session_id,
        project_id=project_id,
        status="queued",
        assertion_text=assertion_text,
        steps_json=json.dumps(steps, ensure_ascii=False),
        report_json=json.dumps({"status": "queued", "steps": []}, ensure_ascii=False),
        create_time=datetime.now(),
        update_time=datetime.now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _run_preflight_worker(
    run_id: str,
    case_data: dict[str, Any],
    storage_state: dict[str, Any] | None,
) -> None:
    from ..executors import execute_ui_case, to_json_text

    db = SessionLocal()
    try:
        row = db.get(UiRecordPreflight, run_id)
        if not row:
            return
        row.status = "running"
        row.update_time = datetime.now()
        db.commit()

        case = SimpleNamespace(
            id=0,
            project_id=row.project_id,
            case_name=str(case_data.get("case_name") or "录制用例预检"),
            page_url=str(case_data.get("page_url") or ""),
            steps=to_json_text(case_data.get("steps") or [], []),
            timeout=int(case_data.get("timeout") or 30),
            status="draft",
        )
        progress_report: dict[str, Any] = {"status": "running", "steps": []}

        def progress(payload: dict[str, Any]) -> None:
            nonlocal progress_report
            progress_report = merge_preflight_progress(progress_report, payload)
            row.report_json = json.dumps(progress_report, ensure_ascii=False, default=str)
            row.update_time = datetime.now()
            db.commit()

        passed, log_text, screenshot, _report_path = execute_ui_case(
            case,
            execution_context={
                "storage_state": storage_state if isinstance(storage_state, dict) else None,
                "retry_count": 0,
                "headed": False,
                "preflight": True,
            },
            db_session=db,
            progress_callback=progress,
        )
        summary = summarize_preflight_log(passed, log_text, screenshot)
        row.status = summary["status"]
        row.report_json = json.dumps(summary, ensure_ascii=False, default=str)
        row.screenshot = summary.get("screenshot") or ""
        row.error_category = summary.get("error_category") or ""
        row.update_time = datetime.now()
        db.commit()
    except Exception as exc:
        db.rollback()
        row = db.get(UiRecordPreflight, run_id)
        if row:
            row.status = "failed"
            row.report_json = json.dumps(
                {"status": "failed", "error": str(exc), "error_category": "environment_error", "steps": []},
                ensure_ascii=False,
            )
            row.error_category = "environment_error"
            row.update_time = datetime.now()
            db.commit()
    finally:
        db.close()


def launch_preflight(
    row: UiRecordPreflight,
    *,
    case_data: dict[str, Any],
    storage_state: dict[str, Any] | None,
) -> None:
    thread = threading.Thread(
        target=_run_preflight_worker,
        args=(row.run_id, case_data, storage_state),
        daemon=True,
    )
    thread.start()


def serialize_preflight(row: UiRecordPreflight) -> dict[str, Any]:
    try:
        report = json.loads(getattr(row, "report_json", None) or "{}")
    except (TypeError, ValueError):
        report = {}
    return {
        "run_id": row.run_id,
        "session_id": row.session_id,
        "project_id": row.project_id,
        "case_id": row.case_id,
        "status": row.status,
        "report": report,
        "screenshot": getattr(row, "screenshot", None) or report.get("screenshot") or "",
        "error_category": getattr(row, "error_category", None) or report.get("error_category") or "",
        "updated_at": row.update_time.isoformat() if getattr(row, "update_time", None) else "",
    }
