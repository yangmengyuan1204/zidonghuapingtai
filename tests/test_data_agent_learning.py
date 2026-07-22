import json
import logging
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services import data_factory_agent as agent_service
from app.services.data_agent_learning import (
    capture_learning_sample,
    sample_fingerprint,
    sanitize_learning_value,
)


EXPECTED_TABLES = {
    "DataAgentLearningSample": "data_agent_learning_sample",
    "DataAgentRuleCandidate": "data_agent_rule_candidate",
    "DataAgentRuleVersion": "data_agent_rule_version",
    "DataAgentRuleReview": "data_agent_rule_review",
}

REQUIRED_ROW_VALUES = {
    "DataAgentLearningSample": {
        "project_id": 1,
        "session_id": "session-required",
        "module_key": "shopping_cart",
        "intent_key": "add_item",
        "instruction_text": "add one item",
        "model_candidate_json": "{}",
        "initial_contract_json": "{}",
        "final_contract_json": "{}",
        "corrections_json": "[]",
        "outcome": "success",
        "verified": 0,
        "fingerprint": "b" * 64,
        "create_time": datetime.now(),
    },
    "DataAgentRuleCandidate": {
        "project_id": 1,
        "module_key": "shopping_cart",
        "intent_key": "add_item",
        "rule_key": "cart.required",
        "proposal_json": "{}",
        "source_sample_ids_json": "[]",
        "occurrence_count": 0,
        "regression_json": "{}",
        "status": "collecting",
        "create_time": datetime.now(),
    },
    "DataAgentRuleVersion": {
        "candidate_id": 1,
        "project_id": 1,
        "scope": "project",
        "rule_key": "cart.required",
        "version": 1,
        "rule_json": "{}",
        "status": "draft",
        "create_time": datetime.now(),
    },
    "DataAgentRuleReview": {
        "candidate_id": 1,
        "user_id": 2,
        "action": "approve",
        "reason": "",
        "create_time": datetime.now(),
    },
}

NULL_CONSTRAINT_CASES = tuple(
    (model_name, column_name)
    for model_name, values in REQUIRED_ROW_VALUES.items()
    for column_name in values
)


def _model(name):
    assert hasattr(models, name), f"missing ORM model: {name}"
    return getattr(models, name)


@pytest.fixture
def learning_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _sample(**overrides):
    values = {
        "project_id": 1,
        "session_id": "session-1",
        "module_key": "shopping_cart",
        "intent_key": "add_item",
        "instruction_text": "add one item",
        "outcome": "success",
        "fingerprint": "a" * 64,
        "create_time": datetime.now(),
    }
    values.update(overrides)
    return _model("DataAgentLearningSample")(**values)


def _candidate(**overrides):
    values = {
        "project_id": 1,
        "module_key": "shopping_cart",
        "intent_key": "add_item",
        "rule_key": "cart.add_item",
        "proposal_json": "{}",
        "source_sample_ids_json": "[]",
        "create_time": datetime.now(),
    }
    values.update(overrides)
    return _model("DataAgentRuleCandidate")(**values)


def _rule_version(**overrides):
    values = {
        "candidate_id": 1,
        "project_id": 1,
        "scope": "project",
        "rule_key": "cart.add_item",
        "version": 1,
        "rule_json": "{}",
        "status": "draft",
        "create_time": datetime.now(),
    }
    values.update(overrides)
    return _model("DataAgentRuleVersion")(**values)


@pytest.mark.parametrize(("class_name", "table_name"), EXPECTED_TABLES.items())
def test_learning_model_and_table_names_exist(class_name, table_name):
    model = _model(class_name)

    assert model.__tablename__ == table_name


def test_init_app_creates_all_learning_tables(monkeypatch):
    from app.core import utils

    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(utils, "engine", engine)
    monkeypatch.setattr(utils, "get_db", lambda: iter((session_factory(),)))
    monkeypatch.setattr(utils, "ensure_report_dirs", lambda: None)
    monkeypatch.setattr(utils, "migrate_legacy_plaintext_passwords", lambda db: None)
    monkeypatch.setattr(utils, "normalize_api_case_names", lambda db: None)
    monkeypatch.setattr(utils, "ensure_data_script_api_cases", lambda db: None)
    monkeypatch.setattr(utils, "ensure_oem_data_script_api_cases", lambda db: None)
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "admin123")
    monkeypatch.setenv("ALLOW_DEFAULT_ADMIN_PASSWORD", "1")

    try:
        utils.init_app()
        table_names = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert set(EXPECTED_TABLES.values()) <= table_names


def test_sample_fingerprint_is_unique(learning_db):
    learning_db.add_all([_sample(), _sample(session_id="session-2")])

    with pytest.raises(IntegrityError):
        learning_db.commit()


def test_candidate_business_identity_is_unique(learning_db):
    learning_db.add_all([_candidate(), _candidate(proposal_json='{"version": 2}')])

    with pytest.raises(IntegrityError):
        learning_db.commit()


def test_rule_version_identity_is_unique(learning_db):
    learning_db.add_all([_rule_version(), _rule_version(candidate_id=2)])

    with pytest.raises(IntegrityError):
        learning_db.commit()


def test_only_one_active_rule_per_project_scope_and_key(learning_db):
    learning_db.add_all(
        [
            _rule_version(status="active"),
            _rule_version(candidate_id=2, version=2, status="active"),
        ]
    )

    with pytest.raises(IntegrityError):
        learning_db.commit()


def test_non_active_history_can_coexist_across_versions(learning_db):
    learning_db.add_all(
        [
            _rule_version(status="retired"),
            _rule_version(candidate_id=2, version=2, status="retired"),
        ]
    )

    learning_db.commit()

    assert learning_db.query(_model("DataAgentRuleVersion")).count() == 2


def test_global_and_project_active_rules_are_isolated(learning_db):
    learning_db.add_all(
        [
            _rule_version(project_id=0, scope="global", status="active"),
            _rule_version(candidate_id=2, project_id=7, scope="project", status="active"),
        ]
    )

    learning_db.commit()

    assert learning_db.query(_model("DataAgentRuleVersion")).count() == 2


def test_rule_version_scope_rejects_unknown_values(learning_db):
    learning_db.add(_rule_version(scope="tenant"))

    with pytest.raises(IntegrityError):
        learning_db.commit()


def test_defaults_and_nullable_contract(learning_db):
    sample = _sample()
    candidate = _candidate(rule_key="cart.default")
    version = _rule_version(project_id=None, rule_key="cart.default")
    review_model = _model("DataAgentRuleReview")
    review = review_model(
        candidate_id=1,
        user_id=2,
        action="approve",
        create_time=datetime.now(),
    )
    learning_db.add_all([sample, candidate, version, review])

    learning_db.commit()

    assert (
        sample.model_candidate_json,
        sample.initial_contract_json,
        sample.final_contract_json,
        sample.corrections_json,
        sample.verified,
    ) == ("{}", "{}", "{}", "[]", 0)
    assert (candidate.occurrence_count, candidate.regression_json, candidate.status, candidate.update_time) == (
        0,
        "{}",
        "collecting",
        None,
    )
    assert version.project_id == 0
    assert (review.rule_version_id, review.reason) == (None, "")

    assert not _model("DataAgentLearningSample").__table__.c.instruction_text.nullable
    assert not _model("DataAgentRuleCandidate").__table__.c.source_sample_ids_json.nullable
    assert _model("DataAgentRuleCandidate").__table__.c.update_time.nullable
    assert _model("DataAgentRuleVersion").__table__.c.activated_at.nullable
    assert _model("DataAgentRuleReview").__table__.c.rule_version_id.nullable


@pytest.mark.parametrize(("model_name", "column_name"), NULL_CONSTRAINT_CASES)
def test_database_rejects_explicit_null_for_required_fields(learning_db, model_name, column_name):
    model = _model(model_name)
    values = dict(REQUIRED_ROW_VALUES[model_name])
    required_columns = {
        column.name
        for column in model.__table__.columns
        if not column.nullable and not column.primary_key
    }
    assert set(values) == required_columns
    values[column_name] = None

    with pytest.raises(IntegrityError):
        learning_db.execute(model.__table__.insert().values(**values))
        learning_db.commit()
    learning_db.rollback()


def _agent_session(
    *,
    session_id="learning-session",
    instruction="创建一个订单",
    goal=None,
    confirmed=True,
    status="running",
):
    goal = goal or {
        "mode": "new",
        "target_node": "order_offered",
        "variables": {"order_item_num": 1},
        "operations": [{"id": "operation_1", "type": "advance_order"}],
    }
    return agent_service.AgentSessionState(
        id=session_id,
        user_id=1,
        project_id=1,
        env_id=1,
        status=status,
        messages=[{"role": "user", "content": instruction}],
        goal=goal,
        initial_contract=goal,
        events=([{"kind": "confirmation"}] if confirmed else []),
    )


def _verified_result():
    return {
        "operation_results": {
            "operation_1": {
                "status": "completed",
                "verification": {"actual_node": "order_offered"},
            }
        }
    }


def test_confirmed_succeeded_and_verified_session_becomes_positive_sample(learning_db):
    sample = capture_learning_sample(
        learning_db,
        _agent_session(),
        "succeeded",
        _verified_result(),
    )

    assert (sample.outcome, sample.verified) == ("success", 1)


@pytest.mark.parametrize(
    ("confirmed", "result"),
    [
        (False, _verified_result()),
        (True, {}),
        (True, {"verification": {"passed": False}}),
    ],
)
def test_succeeded_without_confirmation_or_actual_verification_is_failure(
    learning_db,
    confirmed,
    result,
):
    sample = capture_learning_sample(
        learning_db,
        _agent_session(confirmed=confirmed),
        "succeeded",
        result,
    )

    assert (sample.outcome, sample.verified) == ("failure", 0)


@pytest.mark.parametrize("final_status", ["failed", "blocked", "cancelled"])
def test_non_success_terminal_status_never_becomes_positive(learning_db, final_status):
    sample = capture_learning_sample(
        learning_db,
        _agent_session(),
        final_status,
        _verified_result(),
    )

    assert (sample.outcome, sample.verified) == ("failure", 0)


def test_capture_accepts_explicit_verification_test_seam(learning_db):
    sample = capture_learning_sample(
        learning_db,
        _agent_session(goal={"mode": "new", "operations": []}),
        "succeeded",
        {"verification": {"passed": True}},
    )

    assert (sample.outcome, sample.verified) == ("success", 1)


def test_recursive_redaction_removes_sensitive_keys_and_string_assignments(learning_db):
    goal = {
        "mode": "new",
        "target_node": "order_offered",
        "variables": {
            "nested": {"Api_Key": "key-raw", "safe": ["cookie=session-raw"]},
            "backend_account": "temporary-account-raw",
            "backend_password": "backend-raw",
            "account_ciphertext": "account-cipher-raw",
        },
        "operations": [],
        "note": "Authorization: Bearer bearer-raw; token: token-raw",
    }
    session = _agent_session(
        instruction="password=pass-raw cookie: cookie-raw 创建订单",
        goal=goal,
    )
    session.events.append(
        {
            "kind": "goal_updated",
            "corrections": [
                {
                    "field": "target_node",
                    "before": "token=event-raw",
                    "after": "order_offered",
                    "source": "direct_edit",
                }
            ],
        }
    )

    sample = capture_learning_sample(
        learning_db,
        session,
        "succeeded",
        {"verification": {"passed": True}},
    )
    serialized = " ".join(
        (
            sample.instruction_text,
            sample.model_candidate_json,
            sample.initial_contract_json,
            sample.final_contract_json,
            sample.corrections_json,
        )
    )

    for secret in (
        "pass-raw",
        "cookie-raw",
        "key-raw",
        "session-raw",
        "backend-raw",
        "temporary-account-raw",
        "account-cipher-raw",
        "bearer-raw",
        "token-raw",
        "event-raw",
    ):
        assert secret not in serialized
    assert sanitize_learning_value({"Sensitive_Variables": {"token": "raw"}}) == {
        "Sensitive_Variables": "***"
    }


def test_sanitizer_bounds_depth_collection_and_string_size():
    nested = {"a": {"b": {"c": {"d": {"e": {"f": "too deep"}}}}}}

    assert sanitize_learning_value(nested)["a"]["b"]["c"]["d"]["e"] == "..."
    assert len(sanitize_learning_value(list(range(200)))) == 100
    assert len(sanitize_learning_value("x" * 5000)) == 4000
    assert sanitize_learning_value((1, 2)) == [1, 2]


def test_fingerprint_uses_sanitized_stable_payload():
    first = sample_fingerprint(
        3,
        "创建订单 token=first-secret",
        {"b": 2, "a": 1, "password": "first-password"},
    )
    second = sample_fingerprint(
        3,
        "创建订单 token=second-secret",
        {"password": "second-password", "a": 1, "b": 2},
    )

    assert first == second
    assert len(first) == 64


def test_duplicate_capture_returns_existing_sample(learning_db):
    session = _agent_session()

    first = capture_learning_sample(learning_db, session, "succeeded", _verified_result())
    second = capture_learning_sample(learning_db, session, "succeeded", _verified_result())

    assert first.id == second.id
    assert learning_db.query(models.DataAgentLearningSample).count() == 1


def test_direct_goal_edit_records_only_changed_allowed_fields():
    goal = {
        "mode": "new",
        "target_node": "order_offered",
        "target_label": "后台订单报价完成",
        "variables": {
            "order_shop_count": 1,
            "order_per_shop": 2,
            "order_item_num": 1,
            "offer_price": "10",
        },
        "intent": {"pricing": {}},
        "operations": [],
    }
    session = _agent_session(goal=goal, status="awaiting_confirmation")
    agent_service._SESSIONS[session.id] = session
    try:
        agent_service.update_agent_goal(
            session.id,
            session.user_id,
            {"order_shop_count": 1, "order_item_num": "3", "backend_password": "raw"},
        )
    finally:
        agent_service._SESSIONS.pop(session.id, None)

    assert session.events[-1]["corrections"] == [
        {
            "field": "order_item_num",
            "before": 1,
            "after": 3,
            "source": "direct_edit",
        }
    ]


def test_initial_contract_remains_first_confirmable_goal_after_direct_edit(learning_db):
    goal = {
        "mode": "new",
        "target_node": "order_offered",
        "target_label": "后台订单报价完成",
        "variables": {"order_shop_count": 1, "order_per_shop": 2, "order_item_num": 1},
        "intent": {"pricing": {}},
        "operations": [],
    }
    session = _agent_session(goal=goal, status="awaiting_confirmation")
    agent_service._SESSIONS[session.id] = session
    try:
        agent_service.update_agent_goal(session.id, session.user_id, {"order_item_num": 4})
        sample = capture_learning_sample(
            learning_db,
            session,
            "succeeded",
            {"verification": {"passed": True}},
        )
    finally:
        agent_service._SESSIONS.pop(session.id, None)

    initial = json.loads(sample.initial_contract_json)
    final = json.loads(sample.final_contract_json)
    assert initial["variables"]["order_item_num"] == 1
    assert final["variables"]["order_item_num"] == 4


def test_clarification_revisions_capture_only_changed_learnable_fields(learning_db):
    session = _agent_session()
    session.intent_state = {
        "revisions": [
            {"field": "target_node", "before": {"value": "order_created"}, "after": {"value": "order_offered"}},
            {"field": "order_item_num", "before": 1, "after": 1},
            {"field": "backend_password", "before": "old-secret", "after": "new-secret"},
            {"before": "missing", "after": "field"},
        ]
    }

    sample = capture_learning_sample(
        learning_db,
        session,
        "succeeded",
        _verified_result(),
    )

    assert json.loads(sample.corrections_json) == [
        {
            "field": "target_node",
            "before": "order_created",
            "after": "order_offered",
            "source": "clarification",
        }
    ]


def test_finalize_learning_failure_preserves_business_record_and_terminal_state(
    learning_db,
    monkeypatch,
    caplog,
):
    session = _agent_session()
    agent_service._SESSIONS[session.id] = session
    saved = models.TestRecord(
        case_type="api",
        case_id=0,
        project_id=1,
        result="passed",
        log="{}",
        report_path="",
        execute_time=datetime.now(),
    )

    def save_business_record(db, *args, **kwargs):
        db.add(saved)
        db.commit()
        db.refresh(saved)
        return saved

    class LearningCommitError(RuntimeError):
        pass

    monkeypatch.setattr(agent_service, "save_record", save_business_record)
    original_commit = learning_db.commit
    commit_calls = 0

    def fail_learning_commit():
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 2:
            raise LearningCommitError("secret exception body")
        return original_commit()

    monkeypatch.setattr(learning_db, "commit", fail_learning_commit)
    try:
        with caplog.at_level(logging.ERROR, logger="app.services.data_factory_agent"):
            agent_service._finalize_session(
                learning_db,
                session.id,
                "succeeded",
                _verified_result(),
                None,
            )
    finally:
        agent_service._SESSIONS.pop(session.id, None)

    learning_db.expire_all()
    assert commit_calls == 2
    assert learning_db.get(models.TestRecord, saved.id) is not None
    assert (session.status, session.record_id) == ("succeeded", saved.id)
    assert "LearningCommitError" in caplog.text
    assert "secret exception body" not in caplog.text


def test_learning_state_is_not_exposed_by_session_serializer():
    session = _agent_session()

    payload = agent_service._serialize_session(session)

    assert "initial_contract" not in payload
    assert "learning_sample" not in payload
