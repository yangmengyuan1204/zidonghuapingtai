import json
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.core.utils import enrich_log_with_exec_params
from app.database import SessionLocal
from app.models import ApiCase, Env, Project, TestRecord as RecordModel, UiCase
from app.services.test_record_reporting import build_test_record_report_fields
from app.services import test_record_reexecution as reexecution


def _project(db, name: str) -> Project:
    item = Project(name=name, desc="", create_time=datetime.now())
    db.add(item)
    db.flush()
    return item


def _record_log(**metadata) -> str:
    return enrich_log_with_exec_params(json.dumps({"status": "done"}), **metadata)


def test_execution_metadata_encrypts_sensitive_variables():
    log_text = _record_log(
        kind="data_script",
        script_key="shopping_cart",
        target_id=88,
        project_id=3,
        env_id=5,
        variables={"customer_id": "1001", "password": "top-secret"},
    )
    assert "top-secret" not in log_text
    payload = json.loads(log_text)
    assert "variables" not in payload["_exec_meta"]
    assert payload["_exec_meta"]["variables_encrypted"]

    record = RecordModel(id=1, case_type="api", case_id=88, project_id=3, log=log_text)
    with SessionLocal() as db:
        context = reexecution.build_reexecute_context(db, record)
    assert context["kind"] == "data_script"
    assert context["variables"] == {"customer_id": "1001"}
    assert context["sensitive_keys"] == ["password"]


def test_data_script_context_keeps_exact_flow_identity():
    log_text = _record_log(
        kind="data_script",
        script_key="full_flow",
        project_id=1,
        env_id=1,
        variables={
            "_data_script_flow_id": "full_flow_copy",
            "_data_script_name": "全流程脚本可根据订单和配送单输入后继续执行",
        },
    )
    record = RecordModel(id=11, case_type="api", case_id=0, project_id=1, log=log_text)
    with SessionLocal() as db:
        context = reexecution.build_reexecute_context(db, record)
        report_fields = build_test_record_report_fields(db, record)

    assert context["script_flow_id"] == "full_flow_copy"
    assert context["script_name"] == "全流程脚本可根据订单和配送单输入后继续执行"
    assert context["script_name_source"] == "flow_metadata"
    assert report_fields["script_name"] == "全流程脚本可根据订单和配送单输入后继续执行"


def test_data_script_report_resolves_logged_interface_name():
    log_text = _record_log(
        kind="data_script",
        script_key="order_quote",
        project_id=1,
        env_id=1,
        variables={"_data_script_name": "订单报价"},
    )
    payload = json.loads(log_text)
    payload.update({"path": "/order.submitOffer", "method": "POST", "steps": [{"script": "订单报价"}]})
    record = RecordModel(id=12, case_type="api", case_id=0, project_id=1, log=json.dumps(payload, ensure_ascii=False))
    with SessionLocal() as db:
        report_fields = build_test_record_report_fields(db, record)

    assert report_fields["script_name"] == "订单报价"
    assert "业务报价提交（POST /order.submitOffer）" in report_fields["interface_names"]


def test_shopping_cart_record_is_not_misclassified_as_api_case():
    record = RecordModel(
        id=2,
        case_type="api",
        case_id=999,
        project_id=1,
        log=_record_log(
            kind="data_script",
            script_key="shopping_cart",
            target_id=999,
            project_id=1,
            env_id=2,
            variables={},
        ),
    )
    with SessionLocal() as db:
        context = reexecution.build_reexecute_context(db, record)
    assert context["kind"] == "data_script"
    assert context["direct_execute"] is False
    assert context["requires_form"] is True


def test_legacy_record_requires_original_entry():
    record = RecordModel(id=3, case_type="api", case_id=1, project_id=1, log="{}")
    with SessionLocal() as db:
        context = reexecution.build_reexecute_context(db, record)
        assert context["available"] is False
        with pytest.raises(HTTPException) as exc_info:
            reexecution.reexecute_record(db, record, True)
    assert exc_info.value.status_code == 409


def test_data_script_cannot_be_executed_directly():
    record = RecordModel(
        id=4,
        case_type="api",
        case_id=0,
        project_id=1,
        log=_record_log(
            kind="data_script",
            script_key="balance_payment",
            project_id=1,
            env_id=2,
            variables={"order_sn": "ORDER-1"},
        ),
    )
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            reexecution.reexecute_record(db, record, True)
    assert exc_info.value.status_code == 409


def test_api_reexecute_rejects_environment_from_other_project(monkeypatch):
    with SessionLocal() as db:
        project = _project(db, "api-project")
        other_project = _project(db, "other-project")
        env = Env(
            project_id=other_project.id,
            env_name="wrong-env",
            base_url="https://example.invalid",
            global_headers="{}",
            global_vars="{}",
            timeout=5,
        )
        db.add(env)
        db.flush()
        case = ApiCase(
            project_id=project.id,
            env_id=env.id,
            case_name="case",
            method="GET",
            url="/health",
            headers="{}",
            params="{}",
            body="",
            assert_rule="{}",
            status="active",
            create_time=datetime.now(),
        )
        db.add(case)
        db.commit()
        record = RecordModel(
            id=5,
            case_type="api",
            case_id=case.id,
            project_id=project.id,
            log=_record_log(
                kind="api_case",
                script_key="api_case",
                target_id=case.id,
                project_id=project.id,
                env_id=env.id,
                variables={},
            ),
        )
        monkeypatch.setattr(
            reexecution,
            "execute_api_case",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("executor must not run")),
        )
        with pytest.raises(HTTPException) as exc_info:
            reexecution.reexecute_record(db, record, True)
    assert exc_info.value.status_code == 400


def test_api_reexecute_allows_env_and_variable_overrides_without_dropping_sensitive_values(monkeypatch):
    captured = {}
    with SessionLocal() as db:
        project = _project(db, "api-override-project")
        original_env = Env(
            project_id=project.id,
            env_name="original-env",
            base_url="https://original.example.invalid",
            global_headers="{}",
            global_vars="{}",
            timeout=5,
        )
        override_env = Env(
            project_id=project.id,
            env_name="override-env",
            base_url="https://override.example.invalid",
            global_headers="{}",
            global_vars="{}",
            timeout=5,
        )
        db.add_all([original_env, override_env])
        db.flush()
        case = ApiCase(
            project_id=project.id,
            env_id=original_env.id,
            case_name="case",
            method="GET",
            url="/health",
            headers="{}",
            params="{}",
            body="",
            assert_rule="{}",
            status="active",
            create_time=datetime.now(),
        )
        db.add(case)
        db.commit()
        override_env_id = override_env.id
        record = RecordModel(
            id=7,
            case_type="api",
            case_id=case.id,
            project_id=project.id,
            log=_record_log(
                kind="api_case",
                script_key="api_case",
                target_id=case.id,
                project_id=project.id,
                env_id=original_env.id,
                variables={"keyword": "old", "obsolete": "remove-me", "password": "secret"},
            ),
        )

        def fake_execute(case_arg, env_arg, variables):
            captured["env_id"] = env_arg.id
            captured["variables"] = variables
            return True, json.dumps({"status": "done"}), "report.json", {}

        monkeypatch.setattr(reexecution, "execute_api_case", fake_execute)
        result = reexecution.reexecute_record(
            db,
            record,
            True,
            env_id=override_env_id,
            variables={"keyword": "new", "page": 2},
        )

    assert result["result"] == "passed"
    assert captured["env_id"] == override_env_id
    assert captured["variables"] == {"keyword": "new", "password": "secret", "page": 2}


def test_ui_reexecute_restores_account_context(monkeypatch):
    captured = {}
    with SessionLocal() as db:
        project = _project(db, "ui-project")
        case = UiCase(
            project_id=project.id,
            case_name="ui-case",
            page_url="https://example.invalid",
            steps="[]",
            timeout=5,
            status="active",
            create_time=datetime.now(),
        )
        db.add(case)
        db.commit()
        record = RecordModel(
            id=6,
            case_type="ui",
            case_id=case.id,
            project_id=project.id,
            log=_record_log(
                kind="ui_case",
                script_key="ui_case",
                target_id=case.id,
                project_id=project.id,
                account_mode="default",
                account_profile_id=7,
                variables={"keyword": "dress", "password": "secret"},
            ),
        )

        def fake_resolve(db_arg, payload, target_type, target_id, project_id, target_url):
            captured["payload"] = payload
            return dict(payload.variables), {"account_profile_id": payload.account_profile_id}

        def fake_execute(case_arg, variables, execution_context, db_session=None):
            captured["execution_context"] = execution_context
            captured["db_session"] = db_session
            return True, json.dumps({"status": "done"}), "", "report.json"

        monkeypatch.setattr(reexecution, "resolve_execution_account", fake_resolve)
        monkeypatch.setattr(reexecution, "execute_ui_case", fake_execute)
        result = reexecution.reexecute_record(db, record, True)

    assert result["result"] == "passed"
    assert captured["payload"].account_mode == "override"
    assert captured["payload"].account_profile_id == 7
    assert captured["payload"].variables["password"] == "secret"
    assert captured["execution_context"]["account_profile_id"] == 7
    assert captured["db_session"] is not None
