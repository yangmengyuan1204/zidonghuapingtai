import copy
import itertools
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.services import data_agent_learning as learning_service


@pytest.fixture
def learning_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def sample_factory(learning_db):
    counter = itertools.count(1)

    def create(
        *,
        intent_key="full_flow",
        first_hit=None,
        outcome="verified",
        initial=None,
        final=None,
        corrections=None,
        project_id=1,
        create_time=None,
    ):
        index = next(counter)
        initial_contract = initial or {"variables": {"order_item_num": 1}}
        final_contract = final or copy.deepcopy(initial_contract)
        correction_items = corrections
        if correction_items is None:
            correction_items = [] if first_hit is not False else [
                {
                    "field": "order_item_num",
                    "before": 1,
                    "after": 2,
                    "source": "direct_edit",
                }
            ]
        sample = models.DataAgentLearningSample(
            project_id=project_id,
            session_id=f"metric-session-{index}",
            module_key="order",
            intent_key=intent_key,
            instruction_text=f"metric sample {index}",
            model_candidate_json="{}",
            initial_contract_json=json.dumps(initial_contract, ensure_ascii=False),
            final_contract_json=json.dumps(final_contract, ensure_ascii=False),
            corrections_json=json.dumps(correction_items, ensure_ascii=False),
            outcome=outcome,
            verified=1 if outcome == "verified" else 0,
            fingerprint=f"{index:064x}",
            create_time=create_time or datetime.now(),
        )
        learning_db.add(sample)
        learning_db.commit()
        learning_db.refresh(sample)
        return sample

    return create


def test_first_hit_uses_normalized_execution_contract(sample_factory):
    sample = sample_factory(
        initial={"variables": {"order_item_num": 1}, "target_label": "订单待付款"},
        final={"variables": {"order_item_num": 1}, "target_label": "待付款"},
        outcome="verified",
    )

    assert learning_service.serialize_learning_sample(sample)["first_hit"] is True


def test_serialize_filters_noop_and_display_corrections_and_redacts_secrets(
    sample_factory,
):
    sample = sample_factory(
        corrections=[
            {"field": "order_item_num", "before": 1, "after": 1},
            {"field": "target_label", "before": "订单待付款", "after": "待付款"},
        ],
    )
    sample.instruction_text = "创建订单 token=instruction-secret"
    sample.initial_contract_json = json.dumps(
        {"variables": {"order_item_num": 1}, "password": "contract-secret"}
    )
    sample.final_contract_json = sample.initial_contract_json

    payload = learning_service.serialize_learning_sample(sample)
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["corrections"] == []
    assert payload["first_hit"] is True
    assert "instruction-secret" not in serialized
    assert "contract-secret" not in serialized


def test_serialize_normalizes_historical_correction_field_alias(sample_factory):
    sample = sample_factory(
        corrections=[
            {
                "field": "quantity_per_item",
                "before": 1,
                "after": 2,
                "source": "clarification",
            }
        ]
    )

    payload = learning_service.serialize_learning_sample(sample)

    assert payload["first_hit"] is False
    assert payload["corrections"][0]["field"] == "order_item_num"


def test_serialize_normalizes_wrapped_revision_values_before_comparison(
    sample_factory,
):
    sample = sample_factory(
        corrections=[
            {
                "field": "quantity_per_item",
                "before": {"value": "01", "label": "one", "source": "model"},
                "after": {"value": 1, "label": "一", "source": "direct_edit"},
            }
        ]
    )

    payload = learning_service.serialize_learning_sample(sample)

    assert payload["corrections"] == []
    assert payload["first_hit"] is True


def test_unknown_capability_contract_change_is_not_first_hit(sample_factory):
    sample = sample_factory(
        intent_key="legacy_unknown_script",
        initial={
            "capability_key": "legacy_unknown_script",
            "variables": {"count": 1},
            "summary": "展示说明一",
        },
        final={
            "capability_key": "legacy_unknown_script",
            "variables": {"count": 2},
            "summary": "展示说明二",
        },
    )

    assert learning_service.serialize_learning_sample(sample)["first_hit"] is False


def test_unknown_capability_ignores_recursive_sensitive_and_display_changes(
    sample_factory,
):
    sample = sample_factory(
        intent_key="legacy_unknown_script",
        initial={
            "capability_key": "legacy_unknown_script",
            "variables": {"count": 1, "password": "old-password"},
            "credentials": {"token": "old-token"},
            "summary": "旧说明",
        },
        final={
            "capability_key": "legacy_unknown_script",
            "variables": {"count": 1, "password": "new-password"},
            "credentials": {"token": "new-token"},
            "summary": "新说明",
        },
    )

    payload = learning_service.serialize_learning_sample(sample)
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["first_hit"] is True
    assert "old-password" not in serialized
    assert "new-password" not in serialized
    assert "old-token" not in serialized
    assert "new-token" not in serialized


@pytest.mark.parametrize(
    ("json_field", "issue"),
    [
        ("initial_contract_json", "invalid_initial_contract"),
        ("final_contract_json", "invalid_final_contract"),
        ("corrections_json", "invalid_corrections"),
    ],
)
def test_corrupt_sample_json_is_reported_and_never_first_hit(
    sample_factory, json_field, issue
):
    sample = sample_factory()
    setattr(sample, json_field, "{broken")

    payload = learning_service.serialize_learning_sample(sample)

    assert payload["first_hit"] is False
    assert payload["data_quality"] == "invalid"
    assert issue in payload["data_quality_issues"]


def test_known_capability_normalization_failure_is_not_first_hit(sample_factory):
    sample = sample_factory(
        initial={"variables": {"order_item_num": "not-an-int"}},
        final={"variables": {"order_item_num": "not-an-int"}},
    )

    payload = learning_service.serialize_learning_sample(sample)

    assert payload["first_hit"] is False
    assert payload["data_quality"] == "invalid"
    assert "invalid_execution_contract" in payload["data_quality_issues"]


def test_invalid_correction_field_type_is_not_first_hit(sample_factory):
    sample = sample_factory(
        corrections=[
            {
                "field": "order_item_num",
                "before": {"value": "not-an-int", "label": "旧"},
                "after": {"value": "still-not-an-int", "label": "新"},
            }
        ]
    )

    payload = learning_service.serialize_learning_sample(sample)

    assert payload["first_hit"] is False
    assert payload["data_quality"] == "invalid"
    assert "invalid_correction_value" in payload["data_quality_issues"]


def test_metrics_report_sample_count_pending_and_per_script(
    learning_db, sample_factory
):
    sample_factory(intent_key="full_flow", first_hit=True, outcome="verified")
    sample_factory(intent_key="full_flow", first_hit=False, outcome="verified")
    sample_factory(intent_key="full_flow", first_hit=True, outcome="pending")

    metrics = learning_service.learning_metrics(learning_db, project_id=1, days=30)

    assert metrics["sample_count"] == 3
    assert metrics["verified_count"] == 2
    assert metrics["pending_count"] == 1
    assert metrics["invalid_count"] == 0
    assert metrics["first_hit_count"] == 1
    assert metrics["first_hit_rate"] == 0.5
    assert metrics["by_script"] == [
        {
            "script_key": "full_flow",
            "verified_count": 2,
            "first_hit_count": 1,
            "first_hit_rate": 0.5,
        }
    ]
    assert metrics["by_correction_field"] == [
        {"field": "order_item_num", "count": 1}
    ]


def test_metrics_count_historical_success_and_keep_nonverified_separate(
    learning_db, sample_factory
):
    historical = sample_factory(first_hit=True, outcome="success")
    assert historical.verified == 0
    sample_factory(first_hit=True, outcome="pending")
    sample_factory(first_hit=True, outcome="invalid")

    metrics = learning_service.learning_metrics(learning_db, 1, 7)

    assert metrics["verified_count"] == 1
    assert metrics["pending_count"] == 1
    assert metrics["invalid_count"] == 1
    assert metrics["first_hit_rate"] == 1.0


def test_metrics_with_no_verified_samples_return_none_rate(learning_db, sample_factory):
    sample_factory(outcome="pending")

    metrics = learning_service.learning_metrics(learning_db, 1, 7)

    assert metrics["verified_count"] == 0
    assert metrics["first_hit_count"] == 0
    assert metrics["first_hit_rate"] is None
    assert metrics["by_script"] == []


def test_metrics_keep_bad_verified_sample_out_of_hit_rate(sample_factory, learning_db):
    sample_factory(first_hit=True)
    sample_factory(
        initial={"variables": {"order_item_num": "not-an-int"}},
        final={"variables": {"order_item_num": "not-an-int"}},
    )

    metrics = learning_service.learning_metrics(learning_db, 1, 7)

    assert metrics["sample_count"] == 2
    assert metrics["verified_count"] == 1
    assert metrics["invalid_count"] == 1
    assert metrics["first_hit_count"] == 1
    assert metrics["first_hit_rate"] == 1.0


def test_metrics_enforce_window_and_project_scope(learning_db, sample_factory):
    sample_factory(project_id=2)
    sample_factory(create_time=datetime.now() - timedelta(days=31))

    metrics = learning_service.learning_metrics(learning_db, 1, 30)

    assert metrics["sample_count"] == 0
    with pytest.raises(learning_service.LearningInputError):
        learning_service.learning_metrics(learning_db, 1, 14)


def test_overview_preserves_existing_keys_and_adds_learning_views(learning_db):
    overview = learning_service.get_learning_overview(learning_db, 1)

    assert {
        "candidates",
        "active_rules",
        "recent_versions",
        "recent_reviews",
        "samples",
        "metrics",
    } <= set(overview)
    assert set(overview["metrics"]) == {"days_7", "days_30"}


def test_overview_fully_serializes_only_latest_100_but_metrics_cover_all_samples(
    learning_db, sample_factory, monkeypatch
):
    older = sample_factory(create_time=datetime.now() - timedelta(days=8))
    recent = [
        sample_factory(
            first_hit=False,
            create_time=datetime.now() - timedelta(days=1),
        )
        for _ in range(100)
    ]
    serialized_ids = []
    original_serialize = learning_service.serialize_learning_sample

    def count_serialize(sample):
        serialized_ids.append(sample.id)
        return original_serialize(sample)

    monkeypatch.setattr(learning_service, "serialize_learning_sample", count_serialize)
    sample_selects = []

    def count_sample_selects(_conn, _cursor, statement, _parameters, _context, _many):
        if (
            statement.lstrip().upper().startswith("SELECT")
            and "data_agent_learning_sample" in statement.lower()
        ):
            sample_selects.append(statement)

    event.listen(learning_db.bind, "before_cursor_execute", count_sample_selects)
    try:
        overview = learning_service.get_learning_overview(learning_db, 1)
    finally:
        event.remove(learning_db.bind, "before_cursor_execute", count_sample_selects)

    assert len(sample_selects) == 1
    expected_latest_ids = [item.id for item in reversed(recent)]
    assert serialized_ids == expected_latest_ids
    assert [item["id"] for item in overview["samples"]] == expected_latest_ids
    assert overview["metrics"]["days_7"]["sample_count"] == 100
    assert overview["metrics"]["days_7"]["first_hit_count"] == 0
    assert overview["metrics"]["days_30"]["sample_count"] == 101
    assert overview["metrics"]["days_30"]["first_hit_count"] == 1
