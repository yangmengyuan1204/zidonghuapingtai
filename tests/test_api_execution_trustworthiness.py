import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import utils
from app.executors import api as api_executor
from app.models import ApiCase, Env, TestRecord as RecordModel
from app.routers import api_cases as api_case_routes
from app.schemas import ApiBatchExecuteRequest, ApiExecuteRequest
from app.services import test_record_reexecution as record_reexecution


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"ok": True}
        self.text = json.dumps(self._payload, ensure_ascii=False)
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        return self._payload


@pytest.fixture
def request_spy(monkeypatch):
    calls = []
    response = {"value": FakeResponse()}

    def fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, "kwargs": kwargs})
        return response["value"]

    monkeypatch.setattr(api_executor, "ensure_report_dirs", lambda: None)
    monkeypatch.setattr(api_executor, "write_allure_result", lambda *args, **kwargs: "memory://report")
    monkeypatch.setattr(api_executor.requests, "request", fake_request)
    return calls, response


@pytest.fixture
def record_db():
    engine = create_engine("sqlite:///:memory:")
    RecordModel.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def make_env(**overrides) -> Env:
    values = {
        "id": 1,
        "project_id": 1,
        "env_name": "trustworthiness-test",
        "base_url": "https://example.invalid",
        "global_headers": "{}",
        "global_vars": "{}",
        "timeout": 5,
    }
    values.update(overrides)
    return Env(**values)


def make_case(**overrides) -> ApiCase:
    values = {
        "id": 101,
        "project_id": 1,
        "env_id": 1,
        "case_name": "trustworthiness-test",
        "method": "GET",
        "url": "/health",
        "headers": "{}",
        "params": "{}",
        "body": None,
        "assert_rule": '{"status_code": 200}',
        "status": "active",
        "create_time": datetime.now(),
    }
    values.update(overrides)
    return ApiCase(**values)


def assert_configuration_failure(result, calls, expected_code: str):
    passed, log_text, report_path, extracted_vars = result
    log = json.loads(log_text)

    assert passed is False
    assert report_path == "memory://report"
    assert extracted_vars == {}
    assert calls == []
    assert log["assertions"] == [
        {
            "type": "configuration",
            "code": expected_code,
            "message": log["configuration_error"]["message"],
            "passed": False,
        }
    ]
    assert log["assertion_status"] == "configuration_error"
    assert log["configuration_error"]["code"] == expected_code
    assert log["configuration_error"]["message"]
    assert log["error"] == log["configuration_error"]["message"]
    return log


def save_failed_record(record_db, case: ApiCase, result):
    passed, log_text, report_path, _ = result
    record = utils.save_record(
        record_db,
        "api",
        case.id,
        passed,
        log_text,
        report_path,
        project_id=case.project_id,
    )
    return record, json.loads(record.log)


def test_invalid_assertion_json_is_configuration_error_without_request(request_spy, record_db):
    calls, _ = request_spy
    case = make_case(assert_rule='{"status_code": 500')

    result = api_executor.execute_api_case(case, make_env())

    log = assert_configuration_failure(result, calls, "invalid_assertion_json")
    record, record_log = save_failed_record(record_db, case, result)
    assert "断言" in log["configuration_error"]["message"]
    assert record.result == "failed"
    assert record_log["configuration_error"] == log["configuration_error"]


@pytest.mark.parametrize(
    "assert_rule",
    ['{"contains": NaN}', '{"contains": Infinity}', '{"contains": -Infinity}'],
)
def test_nonstandard_json_constants_are_rejected_without_request(request_spy, assert_rule):
    calls, _ = request_spy

    result = api_executor.execute_api_case(make_case(assert_rule=assert_rule), make_env())

    assert_configuration_failure(result, calls, "invalid_assertion_json")


def test_missing_variables_in_url_path_query_headers_and_body_do_not_send_request(request_spy, record_db):
    calls, _ = request_spy
    env = make_env(base_url="https://example.invalid/{{url_host}}")
    case = make_case(
        method="POST",
        url="/users/{{path_id}}",
        headers='{"X-Test": "{{ header value }}"}',
        params='{"query": "{{query_id}}"}',
        body='{"value": "{{body_id}}"}',
    )

    result = api_executor.execute_api_case(case, env)

    log = assert_configuration_failure(result, calls, "unresolved_variables")
    assert set(log["configuration_error"]["fields"]) == {"url", "path", "query", "headers", "body"}
    record, _ = save_failed_record(record_db, case, result)
    assert record.result == "failed"


def test_placeholders_introduced_by_variable_values_are_rejected_after_render(request_spy):
    calls, _ = request_spy
    env = make_env(base_url="https://{{base_host}}")
    case = make_case(
        method="POST",
        url="/{{path_value}}",
        headers='{"X-Test": "{{header_value}}"}',
        params='{"query": "{{query_value}}"}',
        body='{"value": "{{body_value}}"}',
    )
    runtime_vars = {
        "base_host": "{{late_url}}",
        "path_value": "{{late_path}}",
        "header_value": "{{ late header }}",
        "query_value": "{{late_query}}",
        "body_value": "{{late_body}}",
    }

    result = api_executor.execute_api_case(case, env, runtime_vars)

    log = assert_configuration_failure(result, calls, "unresolved_variables")
    assert set(log["configuration_error"]["fields"]) == {"url", "path", "query", "headers", "body"}


def test_missing_variable_in_contains_assertion_is_rejected_without_request(request_spy):
    calls, _ = request_spy
    case = make_case(assert_rule='{"contains": "{{expected_text}}"}')

    result = api_executor.execute_api_case(case, make_env())

    log = assert_configuration_failure(result, calls, "unresolved_variables")
    assert log["configuration_error"]["fields"] == ["assertions"]


def test_invalid_status_assertion_is_configuration_error_without_request(request_spy):
    calls, _ = request_spy
    case = make_case(assert_rule='{"status_code": "not-a-status"}')

    result = api_executor.execute_api_case(case, make_env())

    assert_configuration_failure(result, calls, "invalid_assertion_value")


@pytest.mark.parametrize("status_code", [True, 200.5, "200.5", "²", "9" * 5000])
def test_non_integer_status_assertion_is_rejected_without_request(request_spy, status_code):
    calls, _ = request_spy
    case = make_case(assert_rule=json.dumps({"status_code": status_code}))

    result = api_executor.execute_api_case(case, make_env())

    assert_configuration_failure(result, calls, "invalid_assertion_value")


@pytest.mark.parametrize(
    ("assert_rule", "expected_code"),
    [
        (None, "assertion_not_configured"),
        ("", "assertion_not_configured"),
        ("{}", "no_valid_assertions"),
        ('{"extract": {"id": "json.id"}}', "no_valid_assertions"),
        ('{"contains": ""}', "no_valid_assertions"),
    ],
)
def test_missing_or_empty_assertions_are_distinguished_and_do_not_send_request(
    request_spy,
    assert_rule,
    expected_code,
):
    calls, _ = request_spy

    result = api_executor.execute_api_case(make_case(assert_rule=assert_rule), make_env())

    assert_configuration_failure(result, calls, expected_code)


def test_valid_variables_and_status_assertion_still_pass(request_spy):
    calls, response = request_spy
    response["value"] = FakeResponse(201, {"id": "U1"})
    env = make_env(
        global_headers='{"X-Env": "{{env_token}}"}',
        global_vars='{"base_host": "example.invalid", "env_token": "token-1", "prefix": "qa"}',
        base_url="https://{{base_host}}",
    )
    case = make_case(
        method="POST",
        url="/users/{{user_id}}",
        headers='{"X-Case": "{{case_token}}"}',
        params='{"query": "{{prefix}}_{{keyword}}"}',
        body='{"name": "{{prefix}}_{{name}}"}',
        assert_rule='{"status_code": 201}',
    )

    passed, log_text, _, extracted_vars = api_executor.execute_api_case(
        case,
        env,
        {"user_id": "U1", "case_token": "token-2", "keyword": "alice", "name": "Alice"},
    )

    log = json.loads(log_text)
    assert passed is True
    assert extracted_vars == {}
    assert log["assertion_status"] == "passed"
    assert log["assertions"] == [{"type": "status_code", "expected": 201, "actual": 201, "passed": True}]
    assert len(calls) == 1
    assert calls[0]["url"] == "https://example.invalid/users/U1"
    assert calls[0]["kwargs"]["headers"] == {"X-Env": "token-1", "X-Case": "token-2"}
    assert calls[0]["kwargs"]["params"] == {"query": "qa_alice"}
    assert calls[0]["kwargs"]["json"] == {"name": "qa_Alice"}


def test_valid_assertion_failure_still_fails_after_request(request_spy):
    calls, response = request_spy
    response["value"] = FakeResponse(500, {"error": "failed"})

    passed, log_text, _, _ = api_executor.execute_api_case(
        make_case(assert_rule='{"status_code": 200}'),
        make_env(),
    )

    log = json.loads(log_text)
    assert passed is False
    assert len(calls) == 1
    assert log["assertion_status"] == "failed"
    assert log["assertions"][0]["passed"] is False


def test_single_batch_and_record_reexecution_keep_executor_contract(request_spy):
    calls, _ = request_spy
    engine = create_engine("sqlite:///:memory:")
    Env.__table__.create(engine)
    ApiCase.__table__.create(engine)
    RecordModel.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    try:
        env = make_env(id=None)
        db.add(env)
        db.flush()
        case = make_case(id=None, env_id=env.id)
        db.add(case)
        db.commit()

        single = api_case_routes.run_api_case(
            case.id,
            ApiExecuteRequest(env_id=env.id, variables={}),
            db,
            current_user=None,
        )
        batch = api_case_routes.batch_run_api_cases(
            ApiBatchExecuteRequest(case_ids=[case.id], env_id=env.id, variables={}),
            db,
            current_user=None,
        )
        original = RecordModel(
            id=999,
            case_type="api",
            case_id=case.id,
            project_id=case.project_id,
            result="passed",
            log=utils.enrich_log_with_exec_params(
                "{}",
                kind="api_case",
                script_key="api_case",
                target_id=case.id,
                project_id=case.project_id,
                env_id=env.id,
                variables={},
            ),
            report_path="memory://old-report",
            execute_time=datetime.now(),
        )
        rerun = record_reexecution.reexecute_record(db, original, True)

        assert single["result"] == "passed"
        assert batch["passed"] is True
        assert batch["records"][0]["result"] == "passed"
        assert rerun["result"] == "passed"
        assert len(calls) == 3
    finally:
        db.close()
        engine.dispose()
