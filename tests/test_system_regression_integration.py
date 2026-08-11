from __future__ import annotations

import json
import inspect

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import TestRecord as RegressionRecordModel
from app.services.system_regression.batch_service import create_batch, execute_batch
from app.services.system_regression.case_service import ensure_japan_suite, list_cases
from app.system_regression.models import SystemRegressionCaseRun
from app.system_regression.projects.japan.runner import CaseRunResult


def test_batch_and_case_run_write_compatible_test_records():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        ensure_japan_suite(db)
        case = list_cases(db, suite_key="japan")[0]
        batch = create_batch(
            db,
            suite_key="japan",
            case_ids=[case.id],
            project_id=7,
            env_id=8,
            actor_id=1,
            context={},
        )

        batch_record = db.query(RegressionRecordModel).filter_by(case_type="data_script", case_id=batch.id).one()
        batch_log = json.loads(batch_record.log)
        assert batch_log["script_key"] == "system_regression"
        assert batch_log["record_scope"] == "batch"
        assert batch_log["batch_no"] == batch.batch_no

        execute_batch(db, batch.id, runner=lambda _case, _context: CaseRunResult(status="passed", order_sn="O-1"))

        run = db.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id).one()
        assert run.compat_record_id is not None
        run_record = db.get(RegressionRecordModel, run.compat_record_id)
        run_log = json.loads(run_record.log)
        assert run_record.result == "passed"
        assert run_log["script_key"] == "system_regression"
        assert run_log["record_scope"] == "case_run"
        assert run_log["case_key"] == case.case_key
        assert run_log["run_id"] == run.id
        db.refresh(batch_record)
        assert batch_record.result == "passed"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_existing_payment_regression_route_remains_registered():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/data-scripts/payment-amount-regression" in paths
    assert "/api/system-regression/batches" in paths


def test_guard_route_uses_dedicated_executor_instead_of_problem_runner():
    from app.routers import system_regression as router_module

    source = inspect.getsource(router_module._build_japan_runner)

    assert "GuardExecutor" in source
    assert "problem_runner.execute(case, context)" not in source
