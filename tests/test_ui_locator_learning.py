import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Project, UiCase, UiCaseRevision, UiLocatorMemory, UiRecordPreflight
from app.routers import projects, ui_cases
from app.services import ui_locator_learning
from app.services.ui_locator_learning import (
    confirm_locator_updates,
    memory_candidates_for_step,
    rollback_case_revision,
)


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_confirmed_locator_update_creates_revision_and_project_memory():
    db = _db()
    case = UiCase(
        project_id=7,
        case_name="订单保存",
        page_url="https://example.test/order/123",
        steps=json.dumps(
            [
                {
                    "action": "click",
                    "locator": "#old",
                    "locator_profile": {
                        "page_key": "https://example.test/order/:id",
                        "fingerprint": {"hash": "abc123"},
                    },
                }
            ],
            ensure_ascii=False,
        ),
        timeout=30,
        status="active",
        create_time=datetime.now(),
    )
    db.add(case)
    db.commit()

    revision = confirm_locator_updates(
        db,
        case.id,
        [{"old_locator": "#old", "new_locator": "#new", "step_index": 1, "strategy": "history"}],
        run_id="run-1",
    )

    db.refresh(case)
    assert json.loads(case.steps)[0]["locator"] == "#new"
    assert revision is not None
    assert json.loads(revision.steps_json)[0]["locator"] == "#old"
    memory = db.query(UiLocatorMemory).one()
    assert memory.project_id == 7
    assert memory.locator == "#new"
    assert memory.success_count == 1
    assert memory_candidates_for_step(db, case.id, json.loads(case.steps)[0]) == ["#new"]


def test_revision_rollback_restores_old_steps_and_keeps_audit_revision():
    db = _db()
    case = UiCase(
        project_id=7,
        case_name="订单保存",
        page_url="https://example.test/order",
        steps=json.dumps([{"action": "click", "locator": "#new"}]),
        timeout=30,
        status="active",
        create_time=datetime.now(),
    )
    db.add(case)
    db.commit()
    revision = UiCaseRevision(
        case_id=case.id,
        source="auto_heal",
        run_id="run-1",
        steps_json=json.dumps([{"action": "click", "locator": "#old"}]),
        create_time=datetime.now(),
    )
    db.add(revision)
    db.commit()

    rollback_case_revision(db, case.id, revision.id)

    db.refresh(case)
    assert json.loads(case.steps)[0]["locator"] == "#old"
    audit = db.query(UiCaseRevision).filter(UiCaseRevision.source == "rollback").one()
    assert json.loads(audit.steps_json)[0]["locator"] == "#new"


def test_locator_memory_success_uses_atomic_identity_upsert():
    db = _db()
    remember = getattr(ui_locator_learning, "remember_locator_success", None)
    assert remember is not None

    remember(db, 7, "https://example.test/order", "fingerprint", "#save", "runtime")
    remember(db, 7, "https://example.test/order", "fingerprint", "#save", "runtime")
    db.commit()

    memory = db.query(UiLocatorMemory).one()
    assert memory.success_count == 2


def test_deleting_ui_case_cleans_revisions_and_bound_preflights():
    db = _db()
    case = UiCase(
        project_id=7,
        case_name="订单保存",
        page_url="https://example.test/order",
        steps="[]",
        timeout=30,
        status="active",
        create_time=datetime.now(),
    )
    db.add(case)
    db.commit()
    db.add(
        UiCaseRevision(
            case_id=case.id,
            source="auto_heal",
            steps_json="[]",
            create_time=datetime.now(),
        )
    )
    db.add(
        UiRecordPreflight(
            run_id="bound-preflight",
            session_id="session-1",
            project_id=7,
            case_id=case.id,
            status="passed",
            steps_json="[]",
            create_time=datetime.now(),
        )
    )
    db.commit()

    ui_cases.delete_ui_case(case.id, db=db, current_user=SimpleNamespace(id=1))

    assert db.query(UiCaseRevision).count() == 0
    assert db.query(UiRecordPreflight).count() == 0


def test_deleting_project_cleans_all_ui_locator_learning_rows():
    db = _db()
    project = Project(name="待删除项目", desc="", create_time=datetime.now())
    db.add(project)
    db.commit()
    case = UiCase(
        project_id=project.id,
        case_name="订单保存",
        page_url="https://example.test/order",
        steps="[]",
        timeout=30,
        status="active",
        create_time=datetime.now(),
    )
    db.add(case)
    db.commit()
    db.add(UiCaseRevision(case_id=case.id, source="auto_heal", steps_json="[]", create_time=datetime.now()))
    db.add(
        UiRecordPreflight(
            run_id="project-preflight",
            session_id="session-project",
            project_id=project.id,
            case_id=case.id,
            status="passed",
            steps_json="[]",
            create_time=datetime.now(),
        )
    )
    db.add(
        UiLocatorMemory(
            project_id=project.id,
            page_key="https://example.test/order",
            fingerprint_hash="project-fingerprint",
            locator="#save",
            success_count=1,
            failure_count=0,
            create_time=datetime.now(),
        )
    )
    db.commit()

    projects.delete_project(project.id, db=db, current_user=SimpleNamespace(id=1))

    assert db.query(UiCaseRevision).count() == 0
    assert db.query(UiRecordPreflight).count() == 0
    assert db.query(UiLocatorMemory).count() == 0


def test_ui_case_router_exposes_revision_list_and_rollback_contracts():
    source = Path("app/routers/ui_cases.py").read_text(encoding="utf-8")

    assert '@router.get("/api/ui-cases/{case_id}/revisions")' in source
    assert '@router.post("/api/ui-cases/{case_id}/revisions/{revision_id}/rollback")' in source
