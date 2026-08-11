from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from sqlalchemy.orm import Session

from app.database import safe_commit
from app.models import TestRecord
from app.system_regression.common.execution import dump_runtime_json, sanitize_secrets
from app.system_regression.models import (
    SystemRegressionBatch,
    SystemRegressionCase,
    SystemRegressionCaseRun,
    SystemRegressionSuite,
)
from app.system_regression.projects.japan.runner import CaseRunResult

from .account_service import use_temporary_credentials


class BatchServiceError(ValueError):
    pass


def _snapshot(case: SystemRegressionCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "case_key": case.case_key,
        "name": case.name,
        "category": case.category,
        "runner_kind": case.runner_kind,
        "parameters": case.parameters,
        "expectation": case.expectation,
        "tags": case.tags,
        "version": case.version,
    }


def create_batch(
    db: Session,
    *,
    suite_key: str,
    case_ids: Sequence[int],
    project_id: int | None,
    env_id: int | None,
    actor_id: int | None,
    context: Mapping[str, Any] | None,
) -> SystemRegressionBatch:
    suite = db.query(SystemRegressionSuite).filter(SystemRegressionSuite.suite_key == suite_key).first()
    if suite is None:
        raise BatchServiceError("回归项目不存在")
    query = db.query(SystemRegressionCase).filter(SystemRegressionCase.suite_id == suite.id)
    if case_ids:
        query = query.filter(SystemRegressionCase.id.in_([int(value) for value in case_ids]))
    else:
        query = query.filter(SystemRegressionCase.enabled == True)  # noqa: E712
    cases = query.order_by(SystemRegressionCase.sort_order, SystemRegressionCase.id).all()
    if not cases:
        raise BatchServiceError("至少选择一条回归用例")
    if case_ids and len({case.id for case in cases}) != len(set(case_ids)):
        raise BatchServiceError("选择的用例不属于当前回归项目")

    batch = SystemRegressionBatch(
        batch_no=f"SYSREG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6].upper()}",
        suite_id=suite.id,
        project_id=project_id,
        env_id=env_id,
        status="pending",
        total_count=len(cases),
        context_json=dump_runtime_json(dict(context or {})),
        created_by=actor_id,
    )
    db.add(batch)
    db.flush()
    batch_record = TestRecord(
        case_type="data_script",
        case_id=batch.id,
        project_id=project_id,
        result="pending",
        log=dump_runtime_json(
            {
                "script_key": "system_regression",
                "record_scope": "batch",
                "batch_id": batch.id,
                "batch_no": batch.batch_no,
                "suite_key": suite_key,
            }
        ),
        screenshot="",
        report_path="",
        execute_time=datetime.now(),
    )
    db.add(batch_record)
    db.flush()
    stored_context = json.loads(batch.context_json or "{}")
    stored_context["_compat_record_id"] = batch_record.id
    batch.context_json = dump_runtime_json(stored_context)
    case_parameters = dict(stored_context.get("case_parameters") or {})
    frozen_variables = sanitize_secrets(dict(stored_context.get("variables") or {}))
    for case in cases:
        snapshot = _snapshot(case)
        overrides = case_parameters.get(str(case.id), case_parameters.get(case.id, {}))
        if isinstance(overrides, Mapping):
            snapshot["parameters"] = {
                **dict(snapshot.get("parameters") or {}),
                **dict(overrides),
            }
        parameter_snapshot = {
            "parameters": dict(snapshot.get("parameters") or {}),
            "variables": frozen_variables,
        }
        snapshot["_execution"] = {
            "execution_id": uuid4().hex,
            "batch_id": batch.id,
            "case_id": case.id,
            "parameter_snapshot": parameter_snapshot,
            "current_step": "pending",
            "completed_actions": [],
            "purchase_record_ids": [],
            "before_evidence": {},
            "last_write": {"state": "not_started", "idempotent": False},
        }
        db.add(
            SystemRegressionCaseRun(
                batch_id=batch.id,
                case_id=case.id,
                case_key=case.case_key,
                case_version=case.version,
                status="pending",
                snapshot_json=dump_runtime_json(snapshot),
            )
        )
    safe_commit(db)
    db.refresh(batch)
    return batch


def _invoke_runner(runner: Any, case: Mapping[str, Any], context: Mapping[str, Any]) -> CaseRunResult:
    result = runner(case, context) if callable(runner) else runner.execute(case, context)
    if isinstance(result, CaseRunResult):
        return result
    if is_dataclass(result):
        return CaseRunResult(**asdict(result))
    if isinstance(result, Mapping):
        return CaseRunResult(**dict(result))
    raise TypeError("执行器返回值必须是结构化结果")


def checkpoint_run(
    db: Session,
    run_id: int,
    checkpoint: Mapping[str, Any],
) -> SystemRegressionCaseRun:
    run = db.get(SystemRegressionCaseRun, run_id)
    if run is None:
        raise BatchServiceError("回归执行明细不存在")
    current = json.loads(run.result_json or "{}")
    current["execution_state"] = sanitize_secrets(dict(checkpoint))
    run.result_json = dump_runtime_json(current)
    if checkpoint.get("order_sn") not in (None, ""):
        run.order_sn = str(checkpoint["order_sn"])
    if checkpoint.get("problem_goods_id") not in (None, ""):
        run.problem_goods_id = str(checkpoint["problem_goods_id"])
    if checkpoint.get("current_step") not in (None, ""):
        run.resume_stage = str(checkpoint["current_step"])
    run.update_time = datetime.now()
    safe_commit(db)
    db.refresh(run)
    return run


def _save_run_result(run: SystemRegressionCaseRun, result: CaseRunResult) -> None:
    persisted = json.loads(run.result_json or "{}")
    execution_state = persisted.get("execution_state")
    run.status = result.status
    run.resume_stage = result.resume_stage or None
    run.order_sn = result.order_sn or None
    run.sorting = result.sorting or None
    run.porder_sn = result.porder_sn or None
    run.problem_goods_id = result.problem_goods_id or None
    run.expected_json = dump_runtime_json(result.expected)
    run.preview_json = dump_runtime_json(result.preview)
    run.actual_json = dump_runtime_json(result.actual)
    result_payload = dict(result.result)
    snapshot = json.loads(run.snapshot_json or "{}")
    expectation = snapshot.get("expectation") if isinstance(snapshot.get("expectation"), Mapping) else {}
    required_identities = expectation.get("required_identities")
    if isinstance(required_identities, (list, tuple)) and "identity_type" not in result_payload:
        result_payload["identity_type"] = list(required_identities)
    if isinstance(execution_state, Mapping) and "execution_state" not in result_payload:
        result_payload["execution_state"] = dict(execution_state)
    if result.reason_code and "reason_code" not in result_payload:
        result_payload["reason_code"] = result.reason_code
    run.result_json = dump_runtime_json(result_payload)
    run.error_code = result.error_code or None
    run.error_message = result.error_message or None
    if result.status not in {"waiting_account", "running", "pending"}:
        run.end_time = datetime.now()
    run.update_time = datetime.now()


def _save_compat_run_record(
    db: Session,
    batch: SystemRegressionBatch,
    run: SystemRegressionCaseRun,
) -> None:
    payload = {
        "script_key": "system_regression",
        "record_scope": "case_run",
        "batch_id": batch.id,
        "batch_no": batch.batch_no,
        "run_id": run.id,
        "case_key": run.case_key,
        "order_sn": run.order_sn or "",
        "porder_sn": run.porder_sn or "",
        "problem_goods_id": run.problem_goods_id or "",
        "error_code": run.error_code or "",
        "error_message": run.error_message or "",
    }
    record = db.get(TestRecord, run.compat_record_id) if run.compat_record_id else None
    if record is None:
        record = TestRecord(
            case_type="data_script",
            case_id=run.case_id,
            project_id=batch.project_id,
            result=run.status,
            log=dump_runtime_json(payload),
            screenshot="",
            report_path="",
            execute_time=datetime.now(),
        )
        db.add(record)
        db.flush()
        run.compat_record_id = record.id
    else:
        record.result = run.status
        record.log = dump_runtime_json(payload)
        record.execute_time = datetime.now()


def _refresh_batch_counts(db: Session, batch: SystemRegressionBatch) -> None:
    statuses = [row[0] for row in db.query(SystemRegressionCaseRun.status).filter(SystemRegressionCaseRun.batch_id == batch.id).all()]
    batch.total_count = len(statuses)
    batch.passed_count = statuses.count("passed")
    batch.failed_count = statuses.count("failed")
    batch.blocked_count = statuses.count("blocked") + statuses.count("waiting_account")
    if batch.stop_requested or (statuses and all(status == "stopped" for status in statuses)):
        batch.status = "stopped"
    elif "waiting_account" in statuses:
        batch.status = "waiting_account"
    elif any(status in {"pending", "running"} for status in statuses):
        batch.status = "running"
    elif any(status in {"failed", "blocked"} for status in statuses):
        batch.status = "failed"
    else:
        batch.status = "passed"
    if not any(status in {"pending", "running"} for status in statuses):
        batch.end_time = datetime.now()
    batch.update_time = datetime.now()
    context = json.loads(batch.context_json or "{}")
    record_id = context.get("_compat_record_id")
    record = db.get(TestRecord, int(record_id)) if record_id else None
    if record is not None:
        record.result = batch.status
        record.log = dump_runtime_json(
            {
                "script_key": "system_regression",
                "record_scope": "batch",
                "batch_id": batch.id,
                "batch_no": batch.batch_no,
                "status": batch.status,
                "total_count": batch.total_count,
                "passed_count": batch.passed_count,
                "failed_count": batch.failed_count,
                "blocked_count": batch.blocked_count,
            }
        )
        record.execute_time = datetime.now()


def execute_batch(db: Session, batch_id: int, *, runner: Any) -> SystemRegressionBatch:
    batch = db.get(SystemRegressionBatch, batch_id)
    if batch is None:
        raise BatchServiceError("回归批次不存在")
    batch.status = "running"
    batch.start_time = batch.start_time or datetime.now()
    safe_commit(db)
    runs = (
        db.query(SystemRegressionCaseRun)
        .filter(SystemRegressionCaseRun.batch_id == batch.id, SystemRegressionCaseRun.status == "pending")
        .order_by(SystemRegressionCaseRun.id)
        .all()
    )
    base_context = json.loads(batch.context_json or "{}")
    for run in runs:
        db.refresh(batch)
        if batch.stop_requested:
            run.status = "stopped"
            run.end_time = datetime.now()
            safe_commit(db)
            continue
        run.status = "running"
        run.start_time = datetime.now()
        safe_commit(db)
        snapshot = json.loads(run.snapshot_json)
        persisted = json.loads(run.result_json or "{}")
        execution_state = persisted.get("execution_state") if isinstance(persisted.get("execution_state"), dict) else {}
        execution = snapshot.get("_execution") if isinstance(snapshot.get("_execution"), dict) else {}
        try:
            result = _invoke_runner(
                runner,
                snapshot,
                {
                    **base_context,
                    "batch_no": batch.batch_no,
                    "batch_id": batch.id,
                    "run_id": run.id,
                    "execution_id": str(execution.get("execution_id") or ""),
                    "resume_stage": run.resume_stage or "",
                    "execution_state": execution_state,
                    "checkpoint": lambda value, run_id=run.id: checkpoint_run(db, run_id, value),
                },
            )
        except Exception as exc:
            result = CaseRunResult(status="blocked", error_code="precondition_error", error_message=str(exc))
        _save_run_result(run, result)
        _save_compat_run_record(db, batch, run)
        safe_commit(db)
    _refresh_batch_counts(db, batch)
    safe_commit(db)
    db.refresh(batch)
    return batch


def request_stop(db: Session, batch_id: int) -> SystemRegressionBatch:
    batch = db.get(SystemRegressionBatch, batch_id)
    if batch is None:
        raise BatchServiceError("回归批次不存在")
    batch.stop_requested = True
    batch.status = "stopped"
    now = datetime.now()
    for run in db.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id, status="pending").all():
        run.status = "stopped"
        run.end_time = now
    batch.end_time = now
    safe_commit(db)
    db.refresh(batch)
    return batch


def _interrupted_write_state(run: SystemRegressionCaseRun) -> tuple[str, bool]:
    payload = json.loads(run.result_json or "{}")
    execution_state = payload.get("execution_state") if isinstance(payload.get("execution_state"), dict) else {}
    last_write = execution_state.get("last_write") if isinstance(execution_state.get("last_write"), dict) else {}
    state = str(last_write.get("state") or "indeterminate")
    if state not in {"confirmed_written", "confirmed_not_written", "indeterminate"}:
        state = "indeterminate"
    return state, bool(last_write.get("idempotent"))


def reconcile_interrupted_runs(db: Session) -> int:
    runs = db.query(SystemRegressionCaseRun).filter(SystemRegressionCaseRun.status == "running").all()
    batch_ids = {run.batch_id for run in runs}
    for run in runs:
        write_state, idempotent = _interrupted_write_state(run)
        if write_state == "confirmed_written":
            run.status = "pending"
            run.resume_stage = "result_verification"
            run.error_code = "write_confirmed_after_restart"
            run.error_message = "服务重启前写操作已确认成功，将从结果验证阶段恢复"
            run.end_time = None
        elif write_state == "confirmed_not_written" and idempotent:
            run.status = "pending"
            run.error_code = "safe_retry_after_restart"
            run.error_message = "服务重启前已确认未写入，目标动作声明为可安全重试"
            run.end_time = None
        elif write_state == "confirmed_not_written":
            run.status = "blocked"
            run.error_code = "write_not_confirmed_non_idempotent"
            run.error_message = "已确认写操作未落库，但该动作未声明为可安全重试"
            run.end_time = datetime.now()
        else:
            run.status = "blocked"
            run.error_code = "unknown_write_state"
            run.error_message = "服务重启时写操作状态不确定，禁止自动重复执行"
            run.end_time = datetime.now()
    for batch_id in batch_ids:
        batch = db.get(SystemRegressionBatch, batch_id)
        if batch is not None:
            _refresh_batch_counts(db, batch)
    safe_commit(db)
    return len(runs)


def recover_interrupted_runs_on_startup() -> int:
    from app.database import SessionLocal

    db = SessionLocal()
    batch_ids: list[int] = []
    try:
        recovered_count = reconcile_interrupted_runs(db)
        batch_ids = [
            int(value[0])
            for value in (
                db.query(SystemRegressionCaseRun.batch_id)
                .filter(
                    SystemRegressionCaseRun.status == "pending",
                    SystemRegressionCaseRun.error_code.in_(
                        {"write_confirmed_after_restart", "safe_retry_after_restart"}
                    ),
                )
                .distinct()
                .all()
            )
        ]
    finally:
        db.close()
    if batch_ids:
        from app.routers.system_regression import queue_batch_execution

        for batch_id in batch_ids:
            queue_batch_execution(batch_id)
    return recovered_count


def rerun_case(db: Session, source_run_id: int) -> SystemRegressionCaseRun:
    source = db.get(SystemRegressionCaseRun, source_run_id)
    if source is None:
        raise BatchServiceError("回归执行明细不存在")
    rerun = SystemRegressionCaseRun(
        batch_id=source.batch_id,
        case_id=source.case_id,
        case_key=source.case_key,
        case_version=source.case_version,
        source_run_id=source.id,
        status="pending",
        snapshot_json=source.snapshot_json,
    )
    db.add(rerun)
    batch = db.get(SystemRegressionBatch, source.batch_id)
    if batch is not None:
        batch.total_count += 1
        batch.status = "pending"
        batch.stop_requested = False
        batch.end_time = None
    safe_commit(db)
    db.refresh(rerun)
    return rerun


def resume_run_with_account(
    db: Session,
    run_id: int,
    *,
    username: str,
    password: str,
    runner: Any,
) -> SystemRegressionCaseRun:
    run = db.get(SystemRegressionCaseRun, run_id)
    if run is None:
        raise BatchServiceError("回归执行明细不存在")
    if run.status != "waiting_account":
        raise BatchServiceError("只有等待账号的用例可以恢复")
    batch = db.get(SystemRegressionBatch, run.batch_id)
    if batch is None:
        raise BatchServiceError("回归批次不存在")
    snapshot = json.loads(run.snapshot_json)
    base_context = json.loads(batch.context_json or "{}")
    persisted = json.loads(run.result_json or "{}")
    execution_state = persisted.get("execution_state") if isinstance(persisted.get("execution_state"), dict) else {}
    execution = snapshot.get("_execution") if isinstance(snapshot.get("_execution"), dict) else {}
    run.status = "running"
    run.update_time = datetime.now()
    safe_commit(db)

    def continue_run(credentials: dict[str, str]) -> Mapping[str, Any]:
        variables = {**dict(base_context.get("variables") or {}), **credentials}
        result = _invoke_runner(
            runner,
            snapshot,
            {
                **base_context,
                "variables": variables,
                "batch_no": batch.batch_no,
                "batch_id": batch.id,
                "run_id": run.id,
                "execution_id": str(execution.get("execution_id") or ""),
                "order_sn": run.order_sn or "",
                "problem_goods_id": run.problem_goods_id or "",
                "resume_stage": run.resume_stage or "",
                "execution_state": execution_state,
                "checkpoint": lambda value: checkpoint_run(db, run.id, value),
                "temporary_account_override": True,
            },
        )
        return asdict(result)

    try:
        sanitized = use_temporary_credentials(
            username=username,
            password=password,
            continuation=continue_run,
        )
        result = CaseRunResult(**sanitized)
    except Exception as exc:
        result = CaseRunResult(
            status="waiting_account",
            resume_stage=run.resume_stage or "",
            error_code="account_login_failed",
            error_message=str(exc),
        )
    _save_run_result(run, result)
    _save_compat_run_record(db, batch, run)
    _refresh_batch_counts(db, batch)
    safe_commit(db)
    db.refresh(run)
    return run


__all__ = [
    "BatchServiceError",
    "checkpoint_run",
    "create_batch",
    "execute_batch",
    "reconcile_interrupted_runs",
    "recover_interrupted_runs_on_startup",
    "request_stop",
    "resume_run_with_account",
    "rerun_case",
]
