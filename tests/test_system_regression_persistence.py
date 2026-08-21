from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services.system_regression.case_service import (
    CaseServiceError,
    copy_case,
    create_case,
    delete_case,
    ensure_japan_suite,
    list_cases,
    reset_case,
    update_case,
)
from app.system_regression.models import SystemRegressionCase


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


def test_seed_japan_suite_is_idempotent_and_contains_68_cases(db_session):
    first = ensure_japan_suite(db_session)
    second = ensure_japan_suite(db_session)

    assert first.id == second.id
    assert first.suite_key == "japan"
    assert first.name == "日本站"
    cases = list_cases(db_session, suite_key="japan")
    assert len(cases) == 68
    assert len({case.case_key for case in cases}) == 68
    assert all(case.is_system for case in cases)


def test_seed_backfills_formal_expected_stage_for_existing_problem_case(db_session):
    ensure_japan_suite(db_session)
    case = next(
        row
        for row in list_cases(db_session, suite_key="japan")
        if row.case_key == "金额-001"
    )
    expectation = dict(case.expectation)
    expectation.pop("expected_stage", None)
    case.expectation_json = json.dumps(expectation, ensure_ascii=False)
    default_definition = dict(case.default_definition)
    default_expectation = dict(default_definition.get("expectation") or {})
    default_expectation.pop("expected_stage", None)
    default_definition["expectation"] = default_expectation
    case.default_definition_json = json.dumps(default_definition, ensure_ascii=False)
    db_session.commit()

    ensure_japan_suite(db_session)
    db_session.refresh(case)

    assert case.expectation["expected_stage"] == "problem_goods_completed"
    assert case.default_definition["expectation"]["expected_stage"] == "problem_goods_completed"


def test_update_and_reset_system_case_restore_default_snapshot(db_session):
    ensure_japan_suite(db_session)
    original = list_cases(db_session, suite_key="japan")[0]
    original_name = original.name
    original_parameters = original.parameters

    updated = update_case(
        db_session,
        original.id,
        {
            "name": "可编辑回归用例",
            "parameters": {**original_parameters, "other_fee_name": "加固包装费"},
            "enabled": False,
        },
        actor_id=7,
    )

    assert updated.version == 2
    assert updated.user_modified is True
    assert updated.name == "可编辑回归用例"
    assert updated.parameters["other_fee_name"] == "加固包装费"
    assert updated.enabled is False
    assert updated.updated_by == 7

    restored = reset_case(db_session, updated.id, actor_id=8)

    assert restored.version == 3
    assert restored.user_modified is False
    assert restored.name == original_name
    assert restored.parameters == original_parameters
    assert restored.enabled is True
    assert restored.updated_by == 8


def test_copy_creates_custom_case_and_custom_case_cannot_reset(db_session):
    ensure_japan_suite(db_session)
    source = list_cases(db_session, suite_key="japan")[0]

    copied = copy_case(db_session, source.id, actor_id=11)

    assert copied.id != source.id
    assert copied.case_key == "支付-019"
    assert copied.name == f"{source.name}（副本）"
    assert copied.is_system is False
    assert copied.version == 1
    assert copied.created_by == 11
    assert copied.parameters == source.parameters

    with pytest.raises(CaseServiceError, match="自定义用例不支持重置"):
        reset_case(db_session, copied.id, actor_id=11)


def test_list_cases_supports_category_and_enabled_filters(db_session):
    ensure_japan_suite(db_session)
    payment_cases = list_cases(db_session, suite_key="japan", category="payment")
    update_case(db_session, payment_cases[0].id, {"enabled": False}, actor_id=1)

    enabled = list_cases(
        db_session,
        suite_key="japan",
        category="payment",
        enabled=True,
    )
    disabled = list_cases(
        db_session,
        suite_key="japan",
        category="payment",
        enabled=False,
    )

    assert len(enabled) == 17
    assert [case.id for case in disabled] == [payment_cases[0].id]


def test_reseed_refreshes_unmodified_panel_and_keeps_edited_case(db_session):
    ensure_japan_suite(db_session)
    pay = next(row for row in list_cases(db_session, suite_key="japan") if row.case_key == "支付-001")
    edited = next(row for row in list_cases(db_session, suite_key="japan") if row.case_key == "支付-002")
    pay.parameters_json = json.dumps({"payment_mode": "balance"}, ensure_ascii=False)
    db_session.commit()
    update_case(db_session, edited.id, {"name": "我改过的银行支付"}, actor_id=3)

    ensure_japan_suite(db_session)
    db_session.refresh(pay)
    db_session.refresh(edited)

    assert pay.user_modified is False
    assert pay.parameters["items"][0]["offer_price"]["value"] == "10"
    assert edited.user_modified is True
    assert edited.name == "我改过的银行支付"


def test_ensure_japan_suite_migrates_legacy_system_keys(db_session):
    ensure_japan_suite(db_session)
    case = list_cases(db_session, suite_key="japan")[0]
    legacy_key = case.case_key
    case.case_key = "JP-PAY-001"
    db_session.commit()

    ensure_japan_suite(db_session)
    db_session.refresh(case)

    assert case.case_key == legacy_key == "支付-001"


def test_ensure_japan_suite_migrates_legacy_custom_keys(db_session):
    ensure_japan_suite(db_session)
    custom = create_case(db_session, kind="part", name="旧编号用例", actor_id=1)
    custom.case_key = "CUSTOM-PAY-001"
    db_session.commit()

    ensure_japan_suite(db_session)
    db_session.refresh(custom)

    assert custom.case_key == "支付-019"


def test_deleted_system_case_is_not_reseeded(db_session):
    ensure_japan_suite(db_session)
    case = next(row for row in list_cases(db_session, suite_key="japan") if row.case_key == "金额-001")
    delete_case(db_session, case.id)

    ensure_japan_suite(db_session)
    keys = {row.case_key for row in list_cases(db_session, suite_key="japan")}

    assert "金额-001" not in keys
    assert len(keys) == 67


def test_removed_non_money_cases_are_disabled_and_recorded(db_session):
    suite = ensure_japan_suite(db_session)
    db_session.add(
        SystemRegressionCase(
            suite_id=suite.id,
            case_key="拦截-001",
            name="旧拦截用例",
            category="problem_guard",
            runner_kind="problem_guard",
            parameters_json="{}",
            expectation_json="{}",
            tags_json="[]",
            default_definition_json="{}",
            is_system=True,
            enabled=True,
        )
    )
    db_session.commit()
    ensure_japan_suite(db_session)
    all_cases = list_cases(db_session, suite_key="japan")
    removed = {case.case_key for case in all_cases if not case.enabled}
    removed_config = set(json.loads(suite.config_json or "{}").get("removed_case_keys", []))

    assert "拦截-001" in removed
    assert "拦截-001" in removed_config
    assert "流程-007" not in removed
    assert set(suite.config.get("removed_case_keys") or []) >= removed
