import hashlib
import json
import logging
import threading
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services import data_factory_agent as agent_service
from app.services import data_agent_learning as learning_service
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


def _candidate_signature(field, after):
    payload = json.dumps(
        {"after": after, "field": field},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{field}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _verified_corrected_sample(
    learning_db,
    *,
    field="order_item_num",
    after=2,
    before=1,
    project_id=1,
    module_key="order",
    intent_key="create",
    instruction="创建两个商品的订单",
    outcome="success",
    verified=1,
    corrections=None,
    initial_contract=None,
    final_contract=None,
):
    sample = _sample(
        project_id=project_id,
        session_id=f"candidate-session-{learning_db.query(models.DataAgentLearningSample).count() + 1}",
        module_key=module_key,
        intent_key=intent_key,
        instruction_text=instruction,
        corrections_json=json.dumps(
            corrections
            if corrections is not None
            else [{"field": field, "before": before, "after": after, "source": "direct_edit"}],
            ensure_ascii=False,
            sort_keys=True,
        ),
        initial_contract_json=json.dumps(initial_contract or {}, ensure_ascii=False, sort_keys=True),
        final_contract_json=json.dumps(final_contract or {}, ensure_ascii=False, sort_keys=True),
        outcome=outcome,
        verified=verified,
        fingerprint=f"{learning_db.query(models.DataAgentLearningSample).count() + 1:064x}",
    )
    learning_db.add(sample)
    learning_db.commit()
    learning_db.refresh(sample)
    return sample


def _regression_goal(*, quantity=1, keyword="衣服"):
    return {
        "mode": "new",
        "target_node": "order_offered",
        "variables": {
            "order_shop_count": 1,
            "order_per_shop": 1,
            "order_item_num": quantity,
            "keyword": keyword,
        },
        "operations": [
            {"id": "operation_1", "type": "advance_order", "target_node": "order_offered"}
        ],
        "intent": {
            "pricing": {
                "mode": "uniform_unit",
                "effective_unit_prices": ["10"],
                "effective_goods_total": str(10 * quantity),
                "requested_goods_total": "",
            }
        },
    }


def _pending_regression_candidate(learning_db, *, secret_instruction=False):
    samples = []
    for index in range(3):
        instruction = (
            f"创建两个商品的订单-token=source-secret-{index}"
            if secret_instruction
            else f"创建两个商品的订单-{index}"
        )
        samples.append(
            _verified_corrected_sample(
                learning_db,
                instruction=instruction,
                initial_contract=_regression_goal(quantity=1, keyword="旧关键词"),
                final_contract=_regression_goal(quantity=2, keyword=f"合法修订-{index}"),
            )
        )
    for sample in samples:
        learning_service.refresh_candidates_for_sample(learning_db, sample)
    learning_db.commit()
    candidate = learning_db.query(models.DataAgentRuleCandidate).one()
    assert candidate.status == "pending_regression"
    return candidate, samples


def _pending_candidate_for_contracts(
    learning_db,
    *,
    field,
    before,
    after,
    initial_contract,
    final_contract,
):
    samples = [
        _verified_corrected_sample(
            learning_db,
            field=field,
            before=before,
            after=after,
            instruction=f"联动合同回归-{field}-{index}",
            initial_contract=initial_contract,
            final_contract=final_contract,
        )
        for index in range(3)
    ]
    for sample in samples:
        learning_service.refresh_candidates_for_sample(learning_db, sample)
    learning_db.commit()
    candidate = learning_db.query(models.DataAgentRuleCandidate).one()
    assert candidate.status == "pending_regression"
    return candidate, samples


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
        instruction=(
            'create order password="pass raw quoted" backend_account=account-inline-raw '
            'account_ciphertext="cipher inline raw" browser_state_encrypted=browser-inline-raw '
            'sensitive_variables={"username": "temp-admin-raw", "otp": "otp-raw-secret"} '
            'Authorization: Bearer bearer-raw '
            'Cookie: sid=cookie-one-raw; csrf=cookie-two-raw'
        ),
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
        "pass raw quoted",
        "cookie-raw",
        "key-raw",
        "session-raw",
        "backend-raw",
        "temporary-account-raw",
        "account-cipher-raw",
        "account-inline-raw",
        "cipher inline raw",
        "browser-inline-raw",
        "temp-admin-raw",
        "otp-raw-secret",
        "cookie-one-raw",
        "cookie-two-raw",
        "bearer-raw",
        "token-raw",
        "event-raw",
    ):
        assert secret not in serialized
    assert "create order" in sample.instruction_text
    assert sanitize_learning_value({"Sensitive_Variables": {"token": "raw"}}) == {
        "Sensitive_Variables": "***"
    }


def test_sanitizer_bounds_depth_collection_and_string_size():
    nested = {"a": {"b": {"c": {"d": {"e": {"f": "too deep"}}}}}}

    assert sanitize_learning_value(nested)["a"]["b"]["c"]["d"]["e"] == "..."
    assert len(sanitize_learning_value(list(range(200)))) == 100
    assert len(sanitize_learning_value("x" * 5000)) == 4000
    assert sanitize_learning_value((1, 2)) == [1, 2]


@pytest.mark.parametrize(
    ("text", "secrets"),
    [
        (
            'prefix sensitive_variables : {"user": "temp user", "nested": ["otp value", {"token": "inner"}]} suffix',
            ("temp user", "otp value", "inner"),
        ),
        (
            'prefix browser_state_encrypted = [{"cookie": "cookie value"}] suffix',
            ("cookie value",),
        ),
        ("prefix password : 'two word password' suffix", ("two word password",)),
    ],
)
def test_string_redaction_consumes_complete_structured_values_and_preserves_business_text(text, secrets):
    sanitized = sanitize_learning_value(text)

    assert sanitized.startswith("prefix ")
    assert sanitized.endswith(" suffix")
    assert all(secret not in sanitized for secret in secrets)


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


def test_fingerprint_is_stable_when_large_dict_insertion_order_changes():
    ascending = {f"field_{index:03}": index for index in range(100)}
    descending = {f"field_{index:03}": index for index in reversed(range(100))}

    assert sample_fingerprint(3, "same", ascending) == sample_fingerprint(3, "same", descending)


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


def test_missing_initial_contract_is_not_replaced_with_final_contract(learning_db):
    session = _agent_session()
    session.initial_contract = {}

    sample = capture_learning_sample(
        learning_db,
        session,
        "succeeded",
        _verified_result(),
    )

    assert json.loads(sample.initial_contract_json) == {}
    assert json.loads(sample.final_contract_json) == session.goal


def test_clarification_revisions_capture_only_changed_learnable_fields(learning_db):
    session = _agent_session()
    session.intent_state = {
        "revisions": [
            {"field": "target_node", "before": {"value": "order_created"}, "after": {"value": "order_offered"}},
            {"field": "item_count", "before": {"value": 2}, "after": {"value": 3}},
            {"field": "quantity_per_item", "before": {"value": 1}, "after": {"value": 4}},
            {
                "field": "pricing",
                "before": {"value": {"mode": "ambiguous", "amount": "500"}},
                "after": {"value": {"mode": "goods_total", "amount": "500"}},
            },
            {
                "field": "pricing",
                "before": {"value": {"mode": "goods_total", "amount": "500"}},
                "after": {"value": {"mode": "goods_total", "amount": "600"}},
            },
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
        },
        {
            "field": "order_per_shop",
            "before": 2,
            "after": 3,
            "source": "clarification",
        },
        {
            "field": "order_item_num",
            "before": 1,
            "after": 4,
            "source": "clarification",
        },
        {
            "field": "pricing",
            "before": {"mode": "ambiguous", "amount": "500"},
            "after": {"mode": "goods_total", "amount": "500"},
            "source": "clarification",
        },
        {
            "field": "pricing",
            "before": {"mode": "goods_total", "amount": "500"},
            "after": {"mode": "goods_total", "amount": "600"},
            "source": "clarification",
        },
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


def test_repeated_matching_corrections_reach_regression_threshold_only_on_third_sample(learning_db):
    expected_statuses = ["collecting", "collecting", "pending_regression"]

    for index, expected_status in enumerate(expected_statuses, start=1):
        sample = _verified_corrected_sample(
            learning_db,
            instruction=f"创建订单并把每件商品数量改成两个-{index}",
        )
        candidates = learning_service.refresh_candidates_for_sample(learning_db, sample)

        assert len(candidates) == 1
        assert candidates[0].occurrence_count == index
        assert candidates[0].status == expected_status
        if index < 3:
            assert candidates[0].regression_json == "{}"

    candidate = learning_db.query(models.DataAgentRuleCandidate).one()
    assert candidate.status != "active"
    assert candidate.rule_key.startswith("order_item_num:")
    assert len(candidate.rule_key.rsplit(":", 1)[1]) == 16


def test_different_after_values_have_independent_signatures_and_counts(learning_db):
    first = _verified_corrected_sample(learning_db, after=2, instruction="每件商品改成两个")
    second = _verified_corrected_sample(learning_db, after=3, instruction="每件商品改成三个")

    learning_service.refresh_candidates_for_sample(learning_db, first)
    learning_service.refresh_candidates_for_sample(learning_db, second)
    candidates = learning_db.query(models.DataAgentRuleCandidate).order_by(models.DataAgentRuleCandidate.rule_key).all()

    assert len(candidates) == 2
    assert candidates[0].rule_key != candidates[1].rule_key
    assert [candidate.occurrence_count for candidate in candidates] == [1, 1]
    assert {json.loads(candidate.proposal_json)["set_fields"]["order_item_num"] for candidate in candidates} == {2, 3}


def test_candidate_counts_are_isolated_by_project_module_and_intent(learning_db):
    scopes = [
        (1, "order", "create"),
        (2, "order", "create"),
        (1, "porder", "create"),
        (1, "order", "update"),
    ]
    for index, (project_id, module_key, intent_key) in enumerate(scopes):
        sample = _verified_corrected_sample(
            learning_db,
            project_id=project_id,
            module_key=module_key,
            intent_key=intent_key,
            instruction=f"隔离样本-{index}",
        )
        learning_service.refresh_candidates_for_sample(learning_db, sample)

    candidates = learning_db.query(models.DataAgentRuleCandidate).all()
    assert {(row.project_id, row.module_key, row.intent_key) for row in candidates} == set(scopes)
    assert {row.occurrence_count for row in candidates} == {1}


@pytest.mark.parametrize(
    ("outcome", "verified", "corrections"),
    [
        ("failure", 0, [{"field": "order_item_num", "before": 1, "after": 2}]),
        ("success", 0, [{"field": "order_item_num", "before": 1, "after": 2}]),
        ("success", 1, []),
    ],
)
def test_ineligible_samples_do_not_refresh_candidates(learning_db, outcome, verified, corrections):
    sample = _verified_corrected_sample(
        learning_db,
        outcome=outcome,
        verified=verified,
        corrections=corrections,
    )

    assert learning_service.refresh_candidates_for_sample(learning_db, sample) == []
    assert learning_db.query(models.DataAgentRuleCandidate).count() == 0


def test_duplicate_correction_and_refresh_count_one_sample_once(learning_db):
    correction = {"field": "order_item_num", "before": 1, "after": 2, "source": "direct_edit"}
    sample = _verified_corrected_sample(learning_db, corrections=[correction, correction])

    first = learning_service.refresh_candidates_for_sample(learning_db, sample)
    second = learning_service.refresh_candidates_for_sample(learning_db, sample)
    candidate = learning_db.query(models.DataAgentRuleCandidate).one()

    assert first[0].id == second[0].id == candidate.id
    assert candidate.occurrence_count == 1
    assert json.loads(candidate.source_sample_ids_json) == [sample.id]


def test_source_ids_and_safe_match_phrases_are_stable_unique_and_bounded(learning_db):
    samples = []
    for index in range(10):
        phrase = "重复安全表达" if index < 2 else f"表达-{index}-token=raw-secret-{index}-" + "长" * 300
        samples.append(_verified_corrected_sample(learning_db, instruction=phrase))

    for sample in reversed(samples):
        learning_service.refresh_candidates_for_sample(learning_db, sample)
    candidate = learning_db.query(models.DataAgentRuleCandidate).one()
    proposal = json.loads(candidate.proposal_json)
    source_ids = json.loads(candidate.source_sample_ids_json)
    serialized = candidate.proposal_json + candidate.source_sample_ids_json + candidate.regression_json

    assert source_ids == sorted({sample.id for sample in samples})
    assert candidate.occurrence_count == len(source_ids) == proposal["source_count"] == 10
    assert proposal["match_phrases"] == sorted(set(proposal["match_phrases"]))
    assert len(proposal["match_phrases"]) <= 8
    assert all(len(phrase) <= 240 for phrase in proposal["match_phrases"])
    assert "raw-secret" not in serialized


@pytest.mark.parametrize(
    "rule",
    [
        {
            "signature": "order_item_num:unsafe",
            "field": "order_item_num",
            "match_phrases": [],
            "set_fields": {"order_item_num": 2},
            "source_count": 1,
            "sql": "select secret",
        },
        {
            "signature": "allow_large_refund:unsafe",
            "field": "allow_large_refund",
            "match_phrases": [],
            "set_fields": {"allow_large_refund": True},
            "source_count": 1,
        },
        {
            "signature": "pricing:unsafe",
            "field": "pricing",
            "match_phrases": [],
            "set_fields": {"pricing": {"mode": "goods_total", "authorization": "Bearer raw"}},
            "source_count": 1,
        },
        {
            "signature": "pricing:unsafe",
            "field": "pricing",
            "match_phrases": [],
            "set_fields": {"pricing": {"mode": "goods_total", "customer_identity": {"account": "raw"}}},
            "source_count": 1,
        },
        {
            "signature": "order_item_num:unsafe",
            "field": "order_item_num",
            "match_phrases": [],
            "set_fields": {"order_item_num": {"permission": {"amount_threshold": 100}}},
            "source_count": 1,
        },
    ],
)
def test_candidate_validator_recursively_rejects_forbidden_fields(rule):
    with pytest.raises(ValueError, match="禁止|不允许"):
        learning_service.validate_candidate_rule(rule)


def test_reducer_mappings_and_safe_pricing_after_create_candidates(learning_db):
    samples = [
        _verified_corrected_sample(learning_db, field="item_count", after=3, instruction="每单三个商品"),
        _verified_corrected_sample(learning_db, field="quantity_per_item", after=4, instruction="每件四个"),
        _verified_corrected_sample(
            learning_db,
            field="pricing",
            before={"mode": "ambiguous", "amount": "500"},
            after={"mode": "goods_total", "amount": "600"},
            instruction="总价六百元",
        ),
    ]

    for sample in samples:
        learning_service.refresh_candidates_for_sample(learning_db, sample)
    proposals = [json.loads(row.proposal_json) for row in learning_db.query(models.DataAgentRuleCandidate).all()]

    assert {proposal["field"] for proposal in proposals} == {"order_per_shop", "order_item_num", "pricing"}
    assert {proposal["field"]: proposal["set_fields"] for proposal in proposals}["pricing"] == {
        "pricing": {"amount": "600", "mode": "goods_total"}
    }
    validated = learning_service.validate_candidate_rule(
        {
            "signature": _candidate_signature("order_item_num", 2),
            "field": "order_item_num",
            "match_phrases": ["每件两个"],
            "set_fields": {"order_item_num": 2},
            "source_count": 3,
        }
    )
    assert validated["set_fields"] == {"order_item_num": 2}


@pytest.mark.parametrize(
    ("field", "after", "expected_pricing"),
    [
        ("offer_price", "88", {"mode": "uniform_unit", "amount": "88"}),
        ("offer_unit_prices", ["10", "20"], {"mode": "per_item_unit", "amounts": ["10", "20"]}),
    ],
)
def test_legacy_price_fields_are_normalized_into_pricing_candidate(
    learning_db,
    field,
    after,
    expected_pricing,
):
    sample = _verified_corrected_sample(learning_db, field=field, after=after)

    candidate = learning_service.refresh_candidates_for_sample(learning_db, sample)[0]
    proposal = json.loads(candidate.proposal_json)

    assert proposal["field"] == "pricing"
    assert proposal["set_fields"] == {"pricing": expected_pricing}
    with pytest.raises(ValueError, match="禁止|不允许"):
        learning_service.validate_candidate_rule(
            {
                "signature": _candidate_signature(field, after),
                "field": field,
                "match_phrases": ["价格纠正"],
                "set_fields": {field: after},
                "source_count": 1,
            }
        )


def test_candidate_validator_rejects_noncanonical_signature():
    with pytest.raises(ValueError, match="signature"):
        learning_service.validate_candidate_rule(
            {
                "signature": "order_item_num:0000000000000000",
                "field": "order_item_num",
                "match_phrases": ["每件两个"],
                "set_fields": {"order_item_num": 2},
                "source_count": 3,
            }
        )


def test_correction_field_and_string_after_are_normalized_before_signature_grouping(learning_db):
    first = _verified_corrected_sample(
        learning_db,
        field=" Quantity_Per_Item ",
        after="  two  ",
        instruction="每件两个-英文表达",
    )
    second = _verified_corrected_sample(
        learning_db,
        field="quantity_per_item",
        after="two",
        instruction="每件两个-规范表达",
    )

    learning_service.refresh_candidates_for_sample(learning_db, first)
    learning_service.refresh_candidates_for_sample(learning_db, second)
    candidate = learning_db.query(models.DataAgentRuleCandidate).one()

    assert candidate.occurrence_count == 2
    assert json.loads(candidate.proposal_json)["set_fields"] == {"order_item_num": "two"}


def test_refresh_rejects_explicit_forbidden_correction_field(learning_db):
    sample = _verified_corrected_sample(
        learning_db,
        field="allow_large_refund",
        after=True,
    )

    with pytest.raises(ValueError, match="禁止字段"):
        learning_service.refresh_candidates_for_sample(learning_db, sample)


@pytest.mark.parametrize("later_status", ["pending_regression", "pending_review", "active", "rejected"])
def test_later_candidate_status_is_never_downgraded_by_new_samples(learning_db, later_status):
    first = _verified_corrected_sample(learning_db, instruction="状态样本-1")
    candidate = learning_service.refresh_candidates_for_sample(learning_db, first)[0]
    candidate.status = later_status
    learning_db.commit()
    second = _verified_corrected_sample(learning_db, instruction="状态样本-2")

    learning_service.refresh_candidates_for_sample(learning_db, second)
    learning_db.refresh(candidate)

    assert candidate.status == later_status
    assert candidate.occurrence_count == 2


def test_capture_automatically_refreshes_candidates_without_changing_goal_normalization(learning_db):
    payload = {
        "status": "ready",
        "goal": {
            "mode": "new",
            "target_node": "order_offered",
            "variables": {"order_item_num": 2},
            "operations": [{"id": "operation_1", "type": "advance_order"}],
        },
    }
    messages = [{"role": "user", "content": "创建订单，每件两个"}]
    normalized_before = agent_service._normalize_goal(payload, messages)

    for index, before in enumerate((1, 3, 4)):
        session = _agent_session(
            session_id=f"automatic-candidate-{index}",
            instruction=f"创建订单，每件两个-{index}",
            goal=payload["goal"],
        )
        session.events.append(
            {
                "kind": "goal_updated",
                "corrections": [
                    {"field": "order_item_num", "before": before, "after": 2, "source": "direct_edit"}
                ],
            }
        )
        capture_learning_sample(learning_db, session, "succeeded", _verified_result())

    candidate = learning_db.query(models.DataAgentRuleCandidate).one()
    assert (candidate.occurrence_count, candidate.status) == (3, "pending_regression")
    assert candidate.status != "active"
    assert agent_service._normalize_goal(payload, messages) == normalized_before


def test_duplicate_capture_does_not_refresh_candidate_twice(learning_db):
    session = _agent_session(instruction="重复 finalize")
    session.events.append(
        {
            "kind": "goal_updated",
            "corrections": [
                {"field": "order_item_num", "before": 1, "after": 2, "source": "direct_edit"},
                {"field": "order_item_num", "before": 1, "after": 2, "source": "direct_edit"},
            ],
        }
    )

    first = capture_learning_sample(learning_db, session, "succeeded", _verified_result())
    second = capture_learning_sample(learning_db, session, "succeeded", _verified_result())
    candidate = learning_db.query(models.DataAgentRuleCandidate).one()

    assert first.id == second.id
    assert candidate.occurrence_count == 1


def test_concurrent_distinct_samples_keep_both_sources_without_lost_candidate_count(tmp_path, monkeypatch):
    database_path = tmp_path / "candidate-concurrency.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 1},
    )
    with engine.begin() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL"))
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    first_session = _agent_session(session_id="concurrent-first", instruction="并发样本一")
    second_session = _agent_session(session_id="concurrent-second", instruction="并发样本二")
    for agent_session, before in ((first_session, 1), (second_session, 3)):
        agent_session.events.append(
            {
                "kind": "goal_updated",
                "corrections": [{"field": "order_item_num", "before": before, "after": 2}],
            }
        )

    first_refresh_entered = threading.Event()
    release_first_refresh = threading.Event()
    original_sample_corrections = learning_service._sample_corrections

    def pause_first_refresh(sample):
        result = original_sample_corrections(sample)
        if threading.current_thread().name == "stale-candidate-refresh" and not first_refresh_entered.is_set():
            first_refresh_entered.set()
            assert release_first_refresh.wait(10)
        return result

    monkeypatch.setattr(learning_service, "_sample_corrections", pause_first_refresh)
    errors = []

    def capture_first():
        db = session_factory()
        try:
            capture_learning_sample(db, first_session, "succeeded", _verified_result())
        except Exception as exc:  # pragma: no cover - asserted through errors
            errors.append(exc)
        finally:
            db.close()

    worker = threading.Thread(target=capture_first, name="stale-candidate-refresh")
    worker.start()
    assert first_refresh_entered.wait(10)
    second_db = session_factory()
    try:
        capture_learning_sample(second_db, second_session, "succeeded", _verified_result())
    except Exception as exc:
        errors.append(exc)
    finally:
        second_db.close()
        release_first_refresh.set()
        worker.join(10)

    verification_db = session_factory()
    try:
        candidate = verification_db.query(models.DataAgentRuleCandidate).one()
        source_ids = json.loads(candidate.source_sample_ids_json)
        assert errors == []
        assert not worker.is_alive()
        assert verification_db.query(models.DataAgentLearningSample).count() == 2
        assert candidate.occurrence_count == len(source_ids) == 2
        assert source_ids == sorted(source_ids)
        assert candidate.status == "collecting"
    finally:
        verification_db.close()
        engine.dispose()


def test_candidate_refresh_failure_preserves_business_record_and_terminal_state(
    learning_db,
    monkeypatch,
    caplog,
):
    session = _agent_session(instruction="候选刷新失败隔离")
    session.events.append(
        {
            "kind": "goal_updated",
            "corrections": [{"field": "order_item_num", "before": 1, "after": 2}],
        }
    )
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

    def fail_candidate_refresh(db, sample):
        raise RuntimeError("raw candidate refresh details")

    monkeypatch.setattr(agent_service, "save_record", save_business_record)
    monkeypatch.setattr(learning_service, "refresh_candidates_for_sample", fail_candidate_refresh)
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
    assert learning_db.get(models.TestRecord, saved.id) is not None
    assert (session.status, session.record_id) == ("succeeded", saved.id)
    assert learning_db.query(models.DataAgentRuleCandidate).count() == 0
    assert "RuntimeError" in caplog.text
    assert "raw candidate refresh details" not in caplog.text


def _proposal(field, after, *phrases):
    return {
        "signature": _candidate_signature(field, after),
        "field": field,
        "match_phrases": list(phrases),
        "set_fields": {field: after},
        "source_count": max(1, len(phrases)),
    }


def test_regression_fixture_helper_expands_and_scores_the_same_80_cases():
    from scripts import evaluate_data_agent_hit_rate as evaluator

    cases = evaluator.expand_fixture_cases()

    assert len(cases) == 80
    assert sum(case["kind"] == "explicit" for case in cases) == 60
    assert sum(case["kind"] == "fixed" for case in cases) == 20
    assert all(
        evaluator.fixture_case_matches(
            evaluator.analyze_without_execution(case["instruction"], case.get("candidate")),
            case,
        )
        for case in cases
    )


def test_candidate_match_normalizes_chinese_whitespace_and_punctuation_conservatively():
    proposal = _proposal("order_item_num", 2, "创建订单，每件两个")

    assert learning_service.candidate_matches_instruction(proposal, "请创建订单 ， 每件两个。")
    assert not learning_service.candidate_matches_instruction(proposal, "创建订单，每件三个")


@pytest.mark.parametrize("phrase", ["", "，。；！？"])
def test_empty_match_phrase_is_rejected(phrase):
    with pytest.raises(ValueError, match="match_phrases"):
        learning_service.validate_candidate_rule(_proposal("order_item_num", 2, phrase))


@pytest.mark.parametrize(
    ("field", "after"),
    [
        ("target_node", "https://unsafe.example/api"),
        ("keyword", "https://unsafe.example/product"),
        ("order_payment_mode", "permission_override"),
    ],
)
def test_candidate_validator_rejects_unsafe_overlay_values(field, after):
    with pytest.raises(ValueError, match="禁止|不允许|合法"):
        learning_service.validate_candidate_rule(_proposal(field, after, "安全短语"))


def test_overlay_is_deep_copy_and_only_changes_mapped_contract_fields():
    goal = _regression_goal(quantity=1)
    goal["customer_ids"] = ["300001"]
    proposal = _proposal("order_item_num", 2, "每件两个")
    original_goal = json.loads(json.dumps(goal, ensure_ascii=False))
    original_proposal = json.loads(json.dumps(proposal, ensure_ascii=False))

    overlaid = learning_service.apply_candidate_overlay(goal, proposal)

    assert overlaid["variables"]["order_item_num"] == 2
    assert overlaid["customer_ids"] == ["300001"]
    assert goal == original_goal
    assert proposal == original_proposal
    assert overlaid is not goal
    assert overlaid["variables"] is not goal["variables"]


def test_target_overlay_updates_only_safe_operation_targets():
    goal = _regression_goal()
    goal["operations"].append(
        {"id": "operation_2", "type": "problem_goods", "target_node": "must-not-change"}
    )

    overlaid = learning_service.apply_candidate_overlay(
        goal,
        _proposal("target_node", "pending_purchase", "做到待拍单"),
    )

    assert overlaid["target_node"] == "pending_purchase"
    assert overlaid["variables"]["stop_after_node"] == "pending_purchase"
    assert overlaid["operations"][0]["target_node"] == "pending_purchase"
    assert overlaid["operations"][1]["target_node"] == "must-not-change"


def test_pricing_overlay_keeps_intent_and_execution_variables_consistent():
    goal = _regression_goal(quantity=2)

    overlaid = learning_service.apply_candidate_overlay(
        goal,
        _proposal("pricing", {"mode": "goods_total", "amount": "60"}, "商品总价60元"),
    )

    assert overlaid["intent"]["pricing"]["mode"] == "goods_total"
    assert overlaid["intent"]["pricing"]["requested_goods_total"] == "60"
    assert overlaid["intent"]["pricing"]["effective_unit_prices"] == ["30"]
    assert overlaid["variables"]["offer_price"] == "30"
    assert "offer_unit_prices" not in overlaid["variables"]


@pytest.mark.parametrize(
    ("field", "after", "operation_key", "expected"),
    [
        ("problem_scope", "all", "scope", "all_candidates"),
        ("problem_refund_quantity", "all", "quantity_refund_mode", "all"),
        ("problem_refund_freight", "all", "freight_refund_mode", "all"),
    ],
)
def test_problem_overlay_updates_existing_problem_contract_only(field, after, operation_key, expected):
    goal = _regression_goal()
    goal["variables"][field] = "keep"
    goal["operations"].append(
        {
            "id": "operation_2",
            "type": "problem_goods",
            "scope": "selected_item",
            "quantity_refund_mode": "keep",
            "freight_refund_mode": "keep",
        }
    )

    overlaid = learning_service.apply_candidate_overlay(goal, _proposal(field, after, "问题产品"))

    assert overlaid["variables"][field] == after
    assert overlaid["operations"][1][operation_key] == expected


def test_clean_regression_reaches_pending_review_without_model_tools_or_activation(
    learning_db,
    monkeypatch,
):
    candidate, samples = _pending_regression_candidate(learning_db)
    payload = {
        "status": "ready",
        "goal": {
            "mode": "new",
            "target_node": "order_offered",
            "variables": {"order_item_num": 2},
        },
    }
    messages = [{"role": "user", "content": "创建订单，每件两个"}]
    normalized_before = agent_service._normalize_goal(payload, messages)

    def fail_external_call(*args, **kwargs):
        raise AssertionError("候选回归不得调用 DeepSeek 或业务工具")

    monkeypatch.setattr(agent_service, "call_local_model_json", fail_external_call)
    monkeypatch.setattr(agent_service, "execute_agent_tool", fail_external_call)

    result = learning_service.run_candidate_regression(learning_db, candidate.id)
    summary = json.loads(result.regression_json)

    assert result.status == "pending_review"
    assert learning_service.regression_passed(summary)
    assert summary == {
        "fixture_total": 80,
        "historical_total": 3,
        "passed": 83,
        "failed": 0,
        "conflicts": 0,
        "failed_case_ids": [],
        "failed_sample_ids": [],
        "conflict_sample_ids": [],
        "source_sample_ids_checked": sorted(sample.id for sample in samples),
        "error_codes": [],
    }
    assert learning_db.query(models.DataAgentRuleVersion).count() == 0
    assert learning_db.query(models.DataAgentRuleReview).count() == 0
    assert agent_service._normalize_goal(payload, messages) == normalized_before


def test_fixture_contract_change_and_broad_phrase_fail_regression(learning_db):
    candidate, _ = _pending_regression_candidate(learning_db)
    proposal = _proposal("order_item_num", 9, "帮我创建订单")
    proposal["source_count"] = 3
    candidate.proposal_json = json.dumps(
        proposal,
        ensure_ascii=False,
        sort_keys=True,
    )
    learning_db.commit()

    result = learning_service.run_candidate_regression(learning_db, candidate.id)
    summary = json.loads(result.regression_json)

    assert result.status == "regression_failed"
    assert summary["failed"] > 0
    assert summary["failed_case_ids"]
    assert summary["conflicts"] > 0


def test_fixed_blocked_case_stays_blocked_and_contract_change_is_rejected(learning_db):
    from scripts import evaluate_data_agent_hit_rate as evaluator

    candidate, _ = _pending_regression_candidate(learning_db)
    proposal = _proposal("target_node", "pending_purchase", "删除订单")
    proposal["source_count"] = 3
    candidate.proposal_json = json.dumps(proposal, ensure_ascii=False, sort_keys=True)
    learning_db.commit()
    blocked_case = next(
        case for case in evaluator.expand_fixture_cases() if case["id"] == "blocked_delete_order"
    )
    baseline = evaluator.analyze_without_execution(blocked_case["instruction"])
    overlaid = {**baseline, "goal": learning_service.apply_candidate_overlay(baseline["goal"], proposal)}

    result = learning_service.run_candidate_regression(learning_db, candidate.id)
    summary = json.loads(result.regression_json)

    assert baseline["status"] == overlaid["status"] == "blocked"
    assert result.status == "regression_failed"
    assert "blocked_delete_order" in summary["failed_case_ids"]


def test_historical_conflict_is_limited_to_candidate_field(learning_db):
    candidate, samples = _pending_regression_candidate(learning_db)
    samples[0].final_contract_json = json.dumps(_regression_goal(quantity=3), ensure_ascii=False)
    learning_db.commit()

    result = learning_service.run_candidate_regression(learning_db, candidate.id)
    summary = json.loads(result.regression_json)

    assert result.status == "regression_failed"
    assert summary["conflict_sample_ids"] == [samples[0].id]
    assert samples[1].id not in summary["conflict_sample_ids"]


def test_missing_source_phrase_coverage_is_a_conflict(learning_db):
    candidate, samples = _pending_regression_candidate(learning_db)
    proposal = json.loads(candidate.proposal_json)
    proposal["match_phrases"] = proposal["match_phrases"][:2]
    candidate.proposal_json = json.dumps(proposal, ensure_ascii=False, sort_keys=True)
    learning_db.commit()

    result = learning_service.run_candidate_regression(learning_db, candidate.id)
    summary = json.loads(result.regression_json)

    assert result.status == "regression_failed"
    assert samples[2].id in summary["conflict_sample_ids"]
    assert summary["source_sample_ids_checked"] == sorted(sample.id for sample in samples)


def test_source_id_count_mismatch_fails_closed(learning_db):
    candidate, samples = _pending_regression_candidate(learning_db)
    candidate.source_sample_ids_json = json.dumps([samples[0].id, samples[1].id])
    learning_db.commit()

    result = learning_service.run_candidate_regression(learning_db, candidate.id)
    summary = json.loads(result.regression_json)

    assert result.status == "regression_failed"
    assert summary["error_codes"] == ["source_coverage_invalid"]


def test_regression_summary_limits_ids_without_reducing_failure_count():
    summary = learning_service._regression_summary(fixture_total=80, historical_total=120)
    summary["failed_sample_ids"] = list(range(1, 121))

    finished = learning_service._finish_summary(summary)

    assert finished["failed"] == 120
    assert len(finished["failed_sample_ids"]) == 100
    assert finished["passed"] == 80


@pytest.mark.parametrize(
    ("proposal_json", "expected_code"),
    [
        ("{malformed-password=raw-secret", "invalid_candidate_json"),
        (
            json.dumps(
                {
                    "signature": "order_item_num:not-canonical",
                    "field": "order_item_num",
                    "match_phrases": ["创建两个商品"],
                    "set_fields": {"order_item_num": 2},
                    "source_count": 3,
                }
            ),
            "invalid_candidate",
        ),
        (
            json.dumps(
                {
                    "signature": "order_item_num:not-canonical",
                    "field": "order_item_num",
                    "match_phrases": ["创建两个商品"],
                    "set_fields": {"order_item_num": {"permission": "raw-secret"}},
                    "source_count": 3,
                }
            ),
            "invalid_candidate",
        ),
    ],
)
def test_invalid_candidate_fails_closed_without_sensitive_error_text(
    learning_db,
    proposal_json,
    expected_code,
):
    candidate, _ = _pending_regression_candidate(learning_db)
    candidate.proposal_json = proposal_json
    learning_db.commit()

    result = learning_service.run_candidate_regression(learning_db, candidate.id)

    assert result.status == "regression_failed"
    assert json.loads(result.regression_json)["error_codes"] == [expected_code]
    assert "raw-secret" not in result.regression_json


def test_corrupt_historical_json_fails_closed_without_content_leak(learning_db):
    candidate, samples = _pending_regression_candidate(learning_db, secret_instruction=True)
    samples[1].initial_contract_json = '{"password":"historical-top-secret"'
    learning_db.commit()

    result = learning_service.run_candidate_regression(learning_db, candidate.id)
    summary = json.loads(result.regression_json)

    assert result.status == "regression_failed"
    assert summary["error_codes"] == ["invalid_sample_json"]
    assert summary["failed_sample_ids"] == [samples[1].id]
    assert "secret" not in result.regression_json.lower()
    assert all("创建" not in str(value) for value in summary.values())


def test_non_pending_candidate_cannot_run_or_change_row(learning_db):
    candidate, _ = _pending_regression_candidate(learning_db)
    candidate.status = "pending_review"
    candidate.regression_json = '{"preserved":true}'
    learning_db.commit()

    with pytest.raises(ValueError, match="pending_regression"):
        learning_service.run_candidate_regression(learning_db, candidate.id)

    learning_db.refresh(candidate)
    assert (candidate.status, candidate.regression_json) == (
        "pending_review",
        '{"preserved":true}',
    )


def test_commit_failure_rolls_back_then_persists_safe_failed_summary(
    learning_db,
    monkeypatch,
):
    candidate, _ = _pending_regression_candidate(learning_db)
    original_commit = learning_db.commit
    attempts = 0

    def fail_first_commit():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transaction-password=raw-secret")
        return original_commit()

    monkeypatch.setattr(learning_db, "commit", fail_first_commit)

    result = learning_service.run_candidate_regression(learning_db, candidate.id)

    assert attempts == 2
    assert result.status == "regression_failed"
    assert json.loads(result.regression_json)["error_codes"] == ["transaction_failed"]
    assert "raw-secret" not in result.regression_json


@pytest.mark.parametrize(
    "reviewed_status",
    ["pending_review", "regression_failed", "approved", "rejected", "active"],
)
def test_new_source_reopens_reviewed_candidate_regression(learning_db, reviewed_status):
    candidate, _ = _pending_regression_candidate(learning_db)
    candidate.status = reviewed_status
    candidate.regression_json = '{"passed":83}'
    learning_db.commit()
    new_sample = _verified_corrected_sample(
        learning_db,
        instruction="创建两个商品的订单-新增来源",
        initial_contract=_regression_goal(quantity=1),
        final_contract=_regression_goal(quantity=2),
    )

    learning_service.refresh_candidates_for_sample(learning_db, new_sample)
    learning_db.refresh(candidate)

    assert candidate.status == "pending_regression"
    assert candidate.occurrence_count == 4
    assert candidate.regression_json == "{}"


def test_duplicate_source_refresh_does_not_reopen_pending_review(learning_db):
    candidate, samples = _pending_regression_candidate(learning_db)
    candidate.status = "pending_review"
    candidate.regression_json = '{"passed":83}'
    learning_db.commit()

    learning_service.refresh_candidates_for_sample(learning_db, samples[0])
    learning_db.refresh(candidate)

    assert candidate.status == "pending_review"
    assert candidate.occurrence_count == 3
    assert candidate.regression_json == '{"passed":83}'


def test_changed_proposal_with_same_sources_reopens_review(learning_db):
    candidate, samples = _pending_regression_candidate(learning_db)
    candidate.status = "pending_review"
    candidate.regression_json = '{"passed":83}'
    proposal = json.loads(candidate.proposal_json)
    proposal["match_phrases"] = ["stale phrase"]
    candidate.proposal_json = json.dumps(proposal, ensure_ascii=False, sort_keys=True)
    learning_db.commit()

    learning_service.refresh_candidates_for_sample(learning_db, samples[0])
    learning_db.refresh(candidate)

    assert candidate.status == "pending_regression"
    assert candidate.regression_json == "{}"


@pytest.mark.parametrize(
    ("json_field", "json_value", "expected_code"),
    [
        ("model_candidate_json", "", "invalid_sample_json"),
        ("corrections_json", "", "invalid_sample_json"),
        ("initial_contract_json", "", "invalid_sample_contract"),
        ("initial_contract_json", "{}", "invalid_sample_contract"),
        ("final_contract_json", "", "invalid_sample_contract"),
        ("final_contract_json", "{}", "invalid_sample_contract"),
    ],
)
def test_empty_historical_json_fails_closed(
    learning_db,
    json_field,
    json_value,
    expected_code,
):
    candidate, samples = _pending_regression_candidate(learning_db)
    setattr(samples[0], json_field, json_value)
    learning_db.commit()

    result = learning_service.run_candidate_regression(learning_db, candidate.id)
    summary = json.loads(result.regression_json)

    assert result.status == "regression_failed"
    assert summary["error_codes"] == [expected_code]
    assert summary["failed_sample_ids"] == [samples[0].id]


def test_target_history_checks_operation_target_touched_by_overlay(learning_db):
    initial = _regression_goal()
    final = _regression_goal()
    final["target_node"] = "pending_purchase"
    final["variables"]["stop_after_node"] = "pending_purchase"
    candidate, samples = _pending_candidate_for_contracts(
        learning_db,
        field="target_node",
        before="order_offered",
        after="pending_purchase",
        initial_contract=initial,
        final_contract=final,
    )

    result = learning_service.run_candidate_regression(learning_db, candidate.id)
    summary = json.loads(result.regression_json)

    assert result.status == "regression_failed"
    assert summary["conflict_sample_ids"] == [sample.id for sample in samples]


def test_pricing_history_checks_execution_variables_touched_by_overlay(learning_db):
    initial = _regression_goal(quantity=2)
    final = _regression_goal(quantity=2)
    final["intent"]["pricing"] = {
        "mode": "goods_total",
        "requested_goods_total": "60",
        "effective_unit_prices": ["30"],
        "effective_goods_total": "60",
        "includes_fees": False,
    }
    final["variables"]["offer_price"] = "999"
    after = {"mode": "goods_total", "amount": "60"}
    candidate, samples = _pending_candidate_for_contracts(
        learning_db,
        field="pricing",
        before={"mode": "uniform_unit", "amount": "10"},
        after=after,
        initial_contract=initial,
        final_contract=final,
    )

    result = learning_service.run_candidate_regression(learning_db, candidate.id)
    summary = json.loads(result.regression_json)

    assert result.status == "regression_failed"
    assert summary["conflict_sample_ids"] == [sample.id for sample in samples]


def test_problem_history_checks_operation_mode_touched_by_overlay(learning_db):
    initial = _regression_goal()
    initial["variables"]["problem_scope"] = "item"
    initial["operations"].append(
        {"id": "operation_2", "type": "problem_goods", "scope": "selected_item"}
    )
    final = json.loads(json.dumps(initial, ensure_ascii=False))
    final["variables"]["problem_scope"] = "all"
    candidate, samples = _pending_candidate_for_contracts(
        learning_db,
        field="problem_scope",
        before="item",
        after="all",
        initial_contract=initial,
        final_contract=final,
    )

    result = learning_service.run_candidate_regression(learning_db, candidate.id)
    summary = json.loads(result.regression_json)

    assert result.status == "regression_failed"
    assert summary["conflict_sample_ids"] == [sample.id for sample in samples]


def test_concurrent_new_sources_reopen_review_once_without_losing_evidence(tmp_path):
    database_path = tmp_path / "candidate-regression-reopen.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 1},
    )
    with engine.begin() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL"))
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    setup_db = session_factory()
    try:
        candidate, _ = _pending_regression_candidate(setup_db)
        candidate.status = "pending_review"
        candidate.regression_json = '{"passed":83}'
        setup_db.commit()
        fourth = _verified_corrected_sample(
            setup_db,
            instruction="并发重开来源-4",
            initial_contract=_regression_goal(quantity=1),
            final_contract=_regression_goal(quantity=2),
        )
        fifth = _verified_corrected_sample(
            setup_db,
            instruction="并发重开来源-5",
            initial_contract=_regression_goal(quantity=1),
            final_contract=_regression_goal(quantity=2),
        )
        source_ids = (fourth.id, fifth.id)
    finally:
        setup_db.close()

    barrier = threading.Barrier(2)
    errors = []

    def refresh_source(sample_id):
        db = session_factory()
        try:
            sample = db.get(models.DataAgentLearningSample, sample_id)
            barrier.wait(10)
            learning_service._refresh_candidates_with_retry(db, sample)
        except Exception as exc:  # pragma: no cover - asserted through errors
            errors.append(exc)
        finally:
            db.close()

    workers = [threading.Thread(target=refresh_source, args=(sample_id,)) for sample_id in source_ids]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(15)

    verification_db = session_factory()
    try:
        candidate = verification_db.query(models.DataAgentRuleCandidate).one()
        assert errors == []
        assert all(not worker.is_alive() for worker in workers)
        assert candidate.status == "pending_regression"
        assert candidate.regression_json == "{}"
        assert candidate.occurrence_count == 5
        assert len(json.loads(candidate.source_sample_ids_json)) == 5
    finally:
        verification_db.close()
        engine.dispose()
