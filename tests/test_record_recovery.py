import json
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.models import Project, TestRecord as RecordModel
from app.routers import projects
from app.routers import test_records as test_record_routes


def _project(db, name: str) -> Project:
    item = Project(name=name, desc="", create_time=datetime.now())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_project_delete_is_blocked_when_execution_records_exist():
    db = SessionLocal()
    try:
        project = _project(db, "protected-report-project")
        record = RecordModel(
            case_type="api",
            case_id=0,
            project_id=project.id,
            result="passed",
            log="{}",
            report_path="report.json",
            execute_time=datetime.now(),
        )
        db.add(record)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            projects.delete_project(project.id, db=db, current_user=object())

        assert exc_info.value.status_code == 409
        assert db.get(Project, project.id) is not None
        assert db.get(RecordModel, record.id) is not None
    finally:
        db.close()


def test_recover_orphan_reports_is_idempotent_and_skips_invalid_files(tmp_path):
    from app.services.test_record_recovery import recover_orphan_test_records

    db = SessionLocal()
    try:
        project = _project(db, "report-recovery-project")
        existing_path = tmp_path / "existing-result.json"
        existing_path.write_text(
            json.dumps({"uuid": "existing", "name": "已有报告", "status": "passed", "start": 1000}),
            encoding="utf-8",
        )
        db.add(
            RecordModel(
                case_type="api",
                case_id=0,
                project_id=project.id,
                result="passed",
                log="{}",
                report_path=str(existing_path.resolve()),
                execute_time=datetime.now(),
            )
        )
        db.commit()

        orphan_path = tmp_path / "orphan-result.json"
        orphan_path.write_text(
            json.dumps(
                {
                    "uuid": "orphan-1",
                    "name": "历史订单续跑",
                    "fullName": "data_script.历史订单续跑",
                    "status": "failed",
                    "start": 1785300000000,
                    "stop": 1785300005000,
                    "labels": [{"name": "suite", "value": "data_script"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (tmp_path / "broken-result.json").write_text("{broken", encoding="utf-8")

        first = recover_orphan_test_records(db, tmp_path, project.id)
        second = recover_orphan_test_records(db, tmp_path, project.id)

        assert first == {"scanned": 3, "created": 1, "existing": 1, "skipped": 1}
        assert second == {"scanned": 3, "created": 0, "existing": 2, "skipped": 1}
        recovered = db.query(RecordModel).filter(RecordModel.report_path == str(orphan_path.resolve())).one()
        assert recovered.project_id == project.id
        assert recovered.result == "failed"
        assert json.loads(recovered.log)["recovered_from_allure"] is True
    finally:
        db.close()


def test_recovery_endpoint_can_preserve_unknown_project_ownership(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        test_record_routes,
        "recover_orphan_test_records",
        lambda db, project_id: captured.update({"db": db, "project_id": project_id})
        or {"scanned": 0, "created": 0, "existing": 0, "skipped": 0},
    )
    db = object()

    result = test_record_routes.recover_orphan_reports(
        project_id=None,
        db=db,
        current_user=object(),
    )

    assert result["created"] == 0
    assert captured == {"db": db, "project_id": None}
