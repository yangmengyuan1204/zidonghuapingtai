from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services.system_regression.batch_service import (
    checkpoint_run,
    create_batch,
    execute_batch,
    reconcile_interrupted_runs,
    request_stop,
    rerun_case,
)
from app.services.system_regression.case_service import ensure_japan_suite, list_cases
from app.system_regression.models import SystemRegressionCaseRun
from app.system_regression.projects.japan.runner import CaseRunResult


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_create_batch_snapshots_selected_cases(db_session):
    ensure_japan_suite(db_session)
    cases = list_cases(db_session, suite_key="japan")[:2]

    batch = create_batch(
        db_session,
        suite_key="japan",
        case_ids=[case.id for case in cases],
        project_id=10,
        env_id=20,
        actor_id=1,
        context={"variables": {"customer_id": 3}},
    )

    runs = db_session.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id).order_by(SystemRegressionCaseRun.id).all()
    assert batch.status == "pending"
    assert batch.total_count == 2
    assert [run.case_key for run in runs] == [case.case_key for case in cases]
    assert json.loads(runs[0].snapshot_json)["version"] == cases[0].version
    assert json.loads(runs[0].snapshot_json)["_execution"]["execution_id"]
    assert "password" not in batch.context_json.lower()


def test_create_batch_freezes_per_case_parameter_overrides(db_session):
    ensure_japan_suite(db_session)
    case = list_cases(db_session, suite_key="japan")[0]

    batch = create_batch(
        db_session,
        suite_key="japan",
        case_ids=[case.id],
        project_id=10,
        env_id=20,
        actor_id=1,
        context={
            "variables": {"customer_id": "300001"},
            "case_parameters": {str(case.id): {"payment_mode": "bank"}},
        },
    )
    run = db_session.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id).one()
    snapshot = json.loads(run.snapshot_json)

    assert snapshot["parameters"]["payment_mode"] == "bank"
    assert snapshot["_execution"]["parameter_snapshot"]["parameters"]["payment_mode"] == "bank"


def test_two_batches_have_isolated_execution_ids_and_parameters(db_session):
    ensure_japan_suite(db_session)
    case = list_cases(db_session, suite_key="japan")[0]

    first = create_batch(
        db_session,
        suite_key="japan",
        case_ids=[case.id],
        project_id=1,
        env_id=1,
        actor_id=1,
        context={"case_parameters": {str(case.id): {"payment_mode": "balance"}}},
    )
    second = create_batch(
        db_session,
        suite_key="japan",
        case_ids=[case.id],
        project_id=1,
        env_id=1,
        actor_id=1,
        context={"case_parameters": {str(case.id): {"payment_mode": "bank"}}},
    )
    first_run = db_session.query(SystemRegressionCaseRun).filter_by(batch_id=first.id).one()
    second_run = db_session.query(SystemRegressionCaseRun).filter_by(batch_id=second.id).one()
    first_snapshot = json.loads(first_run.snapshot_json)
    second_snapshot = json.loads(second_run.snapshot_json)

    assert first_snapshot["_execution"]["execution_id"] != second_snapshot["_execution"]["execution_id"]
    assert first_snapshot["parameters"]["payment_mode"] == "balance"
    assert second_snapshot["parameters"]["payment_mode"] == "bank"


def test_execute_batch_continues_after_failed_and_waiting_account(db_session):
    ensure_japan_suite(db_session)
    cases = list_cases(db_session, suite_key="japan")[:4]
    batch = create_batch(
        db_session,
        suite_key="japan",
        case_ids=[case.id for case in cases],
        project_id=10,
        env_id=20,
        actor_id=1,
        context={},
    )
    outcomes = iter(
        [
            CaseRunResult(status="passed"),
            CaseRunResult(status="failed", error_code="amount_mismatch"),
            CaseRunResult(status="waiting_account", resume_stage="purchase_process"),
            CaseRunResult(status="passed"),
        ]
    )

    execute_batch(db_session, batch.id, runner=lambda _case, _context: next(outcomes))

    db_session.refresh(batch)
    statuses = [
        row.status
        for row in db_session.query(SystemRegressionCaseRun)
        .filter_by(batch_id=batch.id)
        .order_by(SystemRegressionCaseRun.id)
        .all()
    ]
    assert statuses == ["passed", "failed", "waiting_account", "passed"]
    assert batch.status == "waiting_account"
    assert (batch.passed_count, batch.failed_count, batch.blocked_count) == (2, 1, 1)


def test_stop_marks_not_started_runs_without_overwriting_finished(db_session):
    ensure_japan_suite(db_session)
    cases = list_cases(db_session, suite_key="japan")[:3]
    batch = create_batch(db_session, suite_key="japan", case_ids=[case.id for case in cases], project_id=1, env_id=1, actor_id=1, context={})
    first = db_session.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id).order_by(SystemRegressionCaseRun.id).first()
    first.status = "passed"
    db_session.commit()

    stopped = request_stop(db_session, batch.id)

    statuses = [row.status for row in db_session.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id).order_by(SystemRegressionCaseRun.id)]
    assert stopped.status == "stopped"
    assert statuses == ["passed", "stopped", "stopped"]


def test_reconcile_interrupted_running_run_does_not_repeat_unknown_write(db_session):
    ensure_japan_suite(db_session)
    case = list_cases(db_session, suite_key="japan")[0]
    batch = create_batch(db_session, suite_key="japan", case_ids=[case.id], project_id=1, env_id=1, actor_id=1, context={})
    run = db_session.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id).one()
    run.status = "running"
    run.resume_stage = "problem_submit"
    db_session.commit()

    count = reconcile_interrupted_runs(db_session)

    db_session.refresh(run)
    assert count == 1
    assert run.status == "blocked"
    assert run.error_code == "unknown_write_state"


def test_reconcile_interrupted_runs_preserves_waiting_account(db_session):
    ensure_japan_suite(db_session)
    case = list_cases(db_session, suite_key="japan")[0]
    batch = create_batch(db_session, suite_key="japan", case_ids=[case.id], project_id=1, env_id=1, actor_id=1, context={})
    run = db_session.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id).one()
    run.status = "waiting_account"
    run.error_code = "minister_account_required"
    db_session.commit()

    assert reconcile_interrupted_runs(db_session) == 0
    db_session.refresh(run)
    assert run.status == "waiting_account"
    assert run.error_code == "minister_account_required"


def test_checkpoint_persists_execution_progress_without_changing_snapshot(db_session):
    ensure_japan_suite(db_session)
    case = list_cases(db_session, suite_key="japan")[0]
    batch = create_batch(db_session, suite_key="japan", case_ids=[case.id], project_id=1, env_id=1, actor_id=1, context={})
    run = db_session.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id).one()
    original_snapshot = run.snapshot_json

    checkpoint_run(
        db_session,
        run.id,
        {
            "current_step": "guard.purchase_deal.before",
            "order_sn": "O-1",
            "problem_goods_id": "P-1",
            "purchase_record_ids": ["R-1"],
            "completed_actions": ["precondition_created"],
            "last_write": {"state": "confirmed_written", "idempotent": False},
        },
    )

    db_session.refresh(run)
    state = json.loads(run.result_json)["execution_state"]
    assert run.snapshot_json == original_snapshot
    assert state["current_step"] == "guard.purchase_deal.before"
    assert state["purchase_record_ids"] == ["R-1"]
    assert run.order_sn == "O-1"
    assert run.problem_goods_id == "P-1"


@pytest.mark.parametrize(
    ("write_state", "idempotent", "expected_status", "expected_reason"),
    [
        ("confirmed_written", False, "pending", "write_confirmed_after_restart"),
        ("confirmed_not_written", True, "pending", "safe_retry_after_restart"),
        ("confirmed_not_written", False, "blocked", "write_not_confirmed_non_idempotent"),
        ("indeterminate", False, "blocked", "unknown_write_state"),
    ],
)
def test_reconcile_interrupted_run_uses_persisted_write_state(
    db_session,
    write_state,
    idempotent,
    expected_status,
    expected_reason,
):
    ensure_japan_suite(db_session)
    case = list_cases(db_session, suite_key="japan")[0]
    batch = create_batch(db_session, suite_key="japan", case_ids=[case.id], project_id=1, env_id=1, actor_id=1, context={})
    run = db_session.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id).one()
    run.status = "running"
    run.result_json = json.dumps(
        {
            "execution_state": {
                "current_step": "guard.purchase_deal.after",
                "last_write": {"state": write_state, "idempotent": idempotent},
            }
        }
    )
    db_session.commit()

    assert reconcile_interrupted_runs(db_session) == 1
    db_session.refresh(run)
    assert run.status == expected_status
    assert run.error_code == expected_reason
    if write_state == "confirmed_written":
        assert run.resume_stage == "result_verification"


def test_lifespan_recovers_interrupted_system_regression_runs(monkeypatch):
    import app.main as main_module
    import app.services.system_regression.batch_service as batch_service
    import app.services.verification_runtime_v2 as verification_runtime

    events = []
    monkeypatch.setattr(main_module, "init_app", lambda: events.append("init"))
    monkeypatch.setattr(
        verification_runtime,
        "recover_unfinished_runs",
        lambda: events.append("verification"),
    )
    monkeypatch.setattr(
        batch_service,
        "recover_interrupted_runs_on_startup",
        lambda: events.append("system_regression"),
        raising=False,
    )

    async def enter_lifespan():
        async with main_module.lifespan(main_module.app):
            events.append("yield")

    asyncio.run(enter_lifespan())

    assert events == ["init", "verification", "system_regression", "yield"]


def test_rerun_case_creates_linked_pending_run(db_session):
    ensure_japan_suite(db_session)
    case = list_cases(db_session, suite_key="japan")[0]
    batch = create_batch(db_session, suite_key="japan", case_ids=[case.id], project_id=1, env_id=1, actor_id=1, context={})
    source = db_session.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id).one()
    source.status = "failed"
    db_session.commit()

    rerun = rerun_case(db_session, source.id)

    assert rerun.id != source.id
    assert rerun.source_run_id == source.id
    assert rerun.status == "pending"
    assert rerun.snapshot_json == source.snapshot_json
