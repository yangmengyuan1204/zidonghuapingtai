from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.data_scripts.problem_goods import PROBLEM_TYPES
from app.database import SessionLocal, get_db
from app.models import Env, User
from app.security import require_admin
from app.services.system_regression.case_service import (
    CaseServiceError,
    copy_case,
    ensure_japan_suite,
    list_cases,
    reset_case,
    update_case,
)
from app.services.system_regression.batch_service import (
    BatchServiceError,
    create_batch,
    execute_batch,
    request_stop,
    rerun_case,
    resume_run_with_account,
)
from app.services.system_regression.account_service import minister_account_context
from app.services.system_regression.login_context import (
    validate_identity_requirements,
    SystemRegressionLoginContextError,
    resolve_system_regression_login_context,
)
from app.system_regression.models import (
    SystemRegressionBatch,
    SystemRegressionCase,
    SystemRegressionCaseRun,
    SystemRegressionSuite,
)
from app.system_regression.projects.japan.guard_executor import GuardExecutor, LiveGuardDriver
from app.system_regression.projects.japan.guard_runner import GuardRunner
from app.system_regression.projects.japan.payment_runner import PaymentRunner
from app.system_regression.projects.japan.problem_runner import ProblemGoodsRunner
from app.system_regression.projects.japan.runner import JapanRegressionRunner


router = APIRouter(prefix="/api/system-regression", tags=["system-regression"])
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="system-regression")


class RegressionCaseUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    runner_kind: str | None = None
    parameters: dict[str, Any] | None = None
    expectation: dict[str, Any] | None = None
    tags: list[str] | None = None
    enabled: bool | None = None
    sort_order: int | None = None


class RegressionBatchCreate(BaseModel):
    suite_key: str = "japan"
    case_ids: list[int] = Field(default_factory=list)
    project_id: int
    env_id: int
    admin_profile_id: int | None = None
    client_profile_id: int | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class RegressionAccountResume(BaseModel):
    username: str
    password: str


def _serialize_suite(suite: SystemRegressionSuite) -> dict[str, Any]:
    return {
        "id": suite.id,
        "suite_key": suite.suite_key,
        "name": suite.name,
        "enabled": bool(suite.enabled),
        "tolerance_jpy": suite.tolerance_jpy,
        "ledger_wait_seconds": suite.ledger_wait_seconds,
        "timeout_seconds": suite.timeout_seconds,
        "config": suite.config,
    }


def _serialize_case(case: SystemRegressionCase) -> dict[str, Any]:
    expectation = case.expectation
    return {
        "id": case.id,
        "suite_id": case.suite_id,
        "case_key": case.case_key,
        "name": case.name,
        "category": case.category,
        "runner_kind": case.runner_kind,
        "parameters": case.parameters,
        "expectation": expectation,
        "required_identities": list(expectation.get("required_identities") or []),
        "tags": case.tags,
        "is_system": bool(case.is_system),
        "version": case.version,
        "user_modified": bool(case.user_modified),
        "enabled": bool(case.enabled),
        "sort_order": case.sort_order,
        "created_by": case.created_by,
        "updated_by": case.updated_by,
    }


def _business_error(exc: CaseServiceError) -> HTTPException:
    message = str(exc)
    code = status.HTTP_404_NOT_FOUND if message == "回归用例不存在" else status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=message)


def _batch_error(exc: BatchServiceError) -> HTTPException:
    message = str(exc)
    code = status.HTTP_404_NOT_FOUND if "不存在" in message else status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=message)


def _serialize_run(run: SystemRegressionCaseRun) -> dict[str, Any]:
    snapshot = _read_json(run.snapshot_json, {})
    result = _read_json(run.result_json, {})
    execution = snapshot.get("_execution") if isinstance(snapshot.get("_execution"), dict) else {}
    structured_keys = (
        "guard_kind",
        "expected_stage",
        "actual_stage",
        "actor",
        "purchase_record_ids",
        "parameter_snapshot",
        "precondition_evidence",
        "attempted_actions",
        "response_evidence",
        "before_evidence",
        "after_evidence",
        "required_effects",
        "forbidden_effects",
        "allowed_effects",
        "unclassified_effects",
        "business_diffs",
        "failure_reason",
        "side_effects",
        "stage_evidence",
        "write_state",
        "write_request_count",
        "reconciliation",
    )
    structured_evidence = {
        key: result[key]
        for key in structured_keys
        if key in result
    }
    return {
        "id": run.id,
        "batch_id": run.batch_id,
        "case_id": run.case_id,
        "case_key": run.case_key,
        "case_version": run.case_version,
        "source_run_id": run.source_run_id,
        "status": run.status,
        "resume_stage": run.resume_stage or "",
        "order_sn": run.order_sn or "",
        "sorting": run.sorting or "",
        "porder_sn": run.porder_sn or "",
        "problem_goods_id": run.problem_goods_id or "",
        "expected": _read_json(run.expected_json, {}),
        "preview": _read_json(run.preview_json, {}),
        "actual": _read_json(run.actual_json, {}),
        "result": result,
        "error_code": run.error_code or "",
        "error_message": run.error_message or "",
        "execution_id": str(result.get("execution_id") or execution.get("execution_id") or ""),
        "reason_code": str(result.get("reason_code") or run.error_code or ""),
        "structured_evidence": structured_evidence,
    }


def _read_json(value: str | None, fallback: Any) -> Any:
    import json

    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _serialize_batch(db: Session, batch: SystemRegressionBatch, *, include_runs: bool = False) -> dict[str, Any]:
    data = {
        "id": batch.id,
        "batch_no": batch.batch_no,
        "suite_id": batch.suite_id,
        "project_id": batch.project_id,
        "env_id": batch.env_id,
        "status": batch.status,
        "total_count": batch.total_count,
        "passed_count": batch.passed_count,
        "failed_count": batch.failed_count,
        "blocked_count": batch.blocked_count,
        "stop_requested": bool(batch.stop_requested),
    }
    if include_runs:
        runs = (
            db.query(SystemRegressionCaseRun)
            .filter(SystemRegressionCaseRun.batch_id == batch.id)
            .order_by(SystemRegressionCaseRun.id)
            .all()
        )
        data["runs"] = [_serialize_run(run) for run in runs]
    return data


def _build_japan_runner(env: Env, db: Session, project_id: int) -> JapanRegressionRunner:
    problem_runner = ProblemGoodsRunner(
        env,
        account_resolver=lambda _case, _context, _request, refund_cny: minister_account_context(
            db,
            project_id=project_id,
            refund_cny=refund_cny,
        ),
    )

    guard_driver = LiveGuardDriver(env, problem_runner)
    guard_executor = GuardExecutor(guard_driver.prepare, guard_driver.perform)

    return JapanRegressionRunner(
        payment_runner=PaymentRunner(env),
        problem_runner=problem_runner,
        guard_runner=GuardRunner(guard_executor.execute),
    )


def _build_contextual_japan_runner(
    env: Env,
    db: Session,
    project_id: int,
    stored_context: dict[str, Any],
) -> Any:
    requested_login = stored_context.get("system_regression_login") if isinstance(stored_context.get("system_regression_login"), dict) else {}
    required_identities = requested_login.get("required_identities")
    resolution_kwargs = {
        "project_id": project_id,
        "env_id": env.id,
        "context": stored_context,
    }
    if required_identities is not None:
        resolution_kwargs["required_identities"] = required_identities
    login_resolution = resolve_system_regression_login_context(db, **resolution_kwargs)
    runner = _build_japan_runner(env, db, project_id)

    def execute_case(case: dict[str, Any], run_context: dict[str, Any]) -> Any:
        context = dict(run_context)
        context["variables"] = {
            **login_resolution.variables,
            **dict(run_context.get("variables") or {}),
        }
        context["system_regression_login"] = dict(login_resolution.login_context)
        context["system_regression_identity"] = {
            "required_identities": list(required_identities or []),
            "available_identities": list(login_resolution.identity_context.available_identities)
            if getattr(login_resolution, "identity_context", None) is not None
            else list(login_resolution.login_context.get("available_identities") or []),
        }
        result = runner.execute(case, context)
        if hasattr(result, "result") and isinstance(result.result, dict):
            result.result.setdefault("identity_type", list(required_identities or []))
        return result

    return execute_case


def _run_batch_background(batch_id: int) -> None:
    db = SessionLocal()
    try:
        batch = db.get(SystemRegressionBatch, batch_id)
        if batch is None:
            return
        env = db.get(Env, batch.env_id) if batch.env_id else None
        if env is None:
            execute_batch(
                db,
                batch.id,
                runner=lambda _case, _context: {
                    "status": "blocked",
                    "error_code": "missing_env",
                    "error_message": "执行环境不存在",
                },
            )
            return
        stored_context = _read_json(batch.context_json, {})
        execute_batch(
            db,
            batch.id,
            runner=_build_contextual_japan_runner(
                env,
                db,
                int(batch.project_id or 0),
                stored_context,
            ),
        )
    finally:
        db.close()


def queue_batch_execution(batch_id: int) -> None:
    _EXECUTOR.submit(_run_batch_background, batch_id)


def _resume_account_background(run_id: int, username: str, password: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(SystemRegressionCaseRun, run_id)
        batch = db.get(SystemRegressionBatch, run.batch_id) if run else None
        env = db.get(Env, batch.env_id) if batch and batch.env_id else None
        if run is None or batch is None or env is None:
            return
        resume_run_with_account(
            db,
            run.id,
            username=username,
            password=password,
            runner=_build_contextual_japan_runner(
                env,
                db,
                int(batch.project_id or 0),
                _read_json(batch.context_json, {}),
            ),
        )
    finally:
        db.close()


def queue_account_resume(run_id: int, username: str, password: str) -> None:
    _EXECUTOR.submit(_resume_account_background, run_id, username, password)


@router.get("/suites/{suite_key}/cases")
def get_regression_cases(
    suite_key: str,
    category: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    if suite_key != "japan":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回归项目不存在")
    suite = ensure_japan_suite(db)
    cases = list_cases(db, suite_key=suite_key, category=category, enabled=enabled)
    return {
        "suite": _serialize_suite(suite),
        "total": len(cases),
        "cases": [_serialize_case(case) for case in cases],
        "problem_types": [
            {"value": value, "label": label}
            for value, label in PROBLEM_TYPES.items()
        ],
    }


@router.patch("/cases/{case_id}")
def patch_regression_case(
    case_id: int,
    payload: RegressionCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    try:
        case = update_case(db, case_id, changes, actor_id=current_user.id)
    except CaseServiceError as exc:
        raise _business_error(exc) from exc
    return _serialize_case(case)


@router.post("/cases/{case_id}/copy", status_code=status.HTTP_201_CREATED)
def copy_regression_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    try:
        case = copy_case(db, case_id, actor_id=current_user.id)
    except CaseServiceError as exc:
        raise _business_error(exc) from exc
    return _serialize_case(case)


@router.post("/cases/{case_id}/reset")
def reset_regression_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    try:
        case = reset_case(db, case_id, actor_id=current_user.id)
    except CaseServiceError as exc:
        raise _business_error(exc) from exc
    return _serialize_case(case)


@router.post("/batches", status_code=status.HTTP_202_ACCEPTED)
def create_regression_batch(
    payload: RegressionBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    if payload.suite_key == "japan":
        ensure_japan_suite(db)
    context = dict(payload.context or {})
    login_context = dict(context.get("system_regression_login") or {})
    if payload.admin_profile_id is not None:
        login_context["admin_profile_id"] = payload.admin_profile_id
    if payload.client_profile_id is not None:
        login_context["client_profile_id"] = payload.client_profile_id
    context["system_regression_login"] = login_context
    try:
        login_resolution = resolve_system_regression_login_context(
            db,
            project_id=payload.project_id,
            env_id=payload.env_id,
            context=context,
            suite_key=payload.suite_key,
            required_identities=(),
        )
    except SystemRegressionLoginContextError as exc:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=exc.payload)
    if payload.suite_key == "japan":
        all_cases = list_cases(db, suite_key=payload.suite_key, enabled=None if payload.case_ids else True)
        selected_cases = (
            all_cases
            if not payload.case_ids
            else [case for case in all_cases if case.id in {int(value) for value in payload.case_ids}]
        )
        if payload.case_ids and len(selected_cases) != len(set(payload.case_ids)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="选择的用例不属于当前回归项目")
        validation = validate_identity_requirements(
            [
                {"case_key": case.case_key, "expectation": case.expectation}
                for case in selected_cases
            ],
            available_identities=login_resolution.identity_context.available_identities,
        )
        if validation.status == "blocked":
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "status": "blocked",
                    "reason_code": validation.reason_code,
                    "required_identities": list(validation.required_identities),
                    "available_identities": list(validation.available_identities),
                    "missing_identities": list(validation.missing_identities),
                    "precondition_evidence": login_resolution.precondition_evidence,
                    "message": validation.failure_reason,
                },
            )
        login_context["required_identities"] = list(validation.required_identities)
    try:
        context["system_regression_login"] = dict(login_resolution.login_context)
        context["system_regression_login"]["required_identities"] = list(
            login_context.get("required_identities") or login_resolution.login_context.get("required_identities") or []
        )
        batch = create_batch(
            db,
            suite_key=payload.suite_key,
            case_ids=payload.case_ids,
            project_id=payload.project_id,
            env_id=payload.env_id,
            actor_id=current_user.id,
            context=context,
        )
    except BatchServiceError as exc:
        raise _batch_error(exc) from exc
    queue_batch_execution(batch.id)
    return _serialize_batch(db, batch)


@router.get("/batches/{batch_id}")
def get_regression_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    batch = db.get(SystemRegressionBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回归批次不存在")
    return _serialize_batch(db, batch, include_runs=True)


@router.post("/batches/{batch_id}/stop")
def stop_regression_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    try:
        batch = request_stop(db, batch_id)
    except BatchServiceError as exc:
        raise _batch_error(exc) from exc
    return _serialize_batch(db, batch)


@router.post("/runs/{run_id}/rerun", status_code=status.HTTP_202_ACCEPTED)
def rerun_regression_case(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    try:
        run = rerun_case(db, run_id)
    except BatchServiceError as exc:
        raise _batch_error(exc) from exc
    queue_batch_execution(run.batch_id)
    return _serialize_run(run)


@router.post("/runs/{run_id}/resume-account", status_code=status.HTTP_202_ACCEPTED)
def resume_regression_account(
    run_id: int,
    payload: RegressionAccountResume,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    run = db.get(SystemRegressionCaseRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回归执行明细不存在")
    if run.status != "waiting_account":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有等待账号的用例可以恢复")
    queue_account_resume(run.id, payload.username, payload.password)
    return {"id": run.id, "status": "account_resume_queued"}


__all__ = ["router"]
