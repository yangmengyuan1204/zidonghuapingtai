from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base


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
