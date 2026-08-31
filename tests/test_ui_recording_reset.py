import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.data_scripts.registry import SCRIPT_REGISTRY
from app.models import Env, Project, UiRecordProjectConfig
from app.services.ui_recording_reset import execute_recording_reset, resolve_reset_templates


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def config(db):
    project = Project(id=1, name="录制测试项目", desc="", create_time=datetime.now())
    env = Env(id=8, project_id=1, env_name="测试环境", base_url="https://example.test")
    row = UiRecordProjectConfig(
        project_id=1,
        reset_script_key="shopping_cart",
        reset_env_id=8,
        reset_variables_json=json.dumps({"sku": "demo-sku"}),
        verification_rounds=2,
        max_repair_attempts=3,
        create_time=datetime.now(),
    )
    db.add_all([project, env, row])
    db.commit()
    return row


def test_reset_executes_registered_script_and_flattens_outputs(monkeypatch, db, config):
    monkeypatch.setitem(
        SCRIPT_REGISTRY,
        "shopping_cart",
        {
            "name": "购物车",
            "func": lambda _env, _vars: (True, "ok", "", {"order": {"sn": "A100"}}),
        },
    )
    monkeypatch.setattr(
        "app.services.ui_recording_reset.data_script_variables",
        lambda _db, variables, _project_id: dict(variables),
    )

    result = execute_recording_reset(db, config)

    assert result.passed is True
    assert result.runtime_variables["reset.order.sn"] == "A100"
    assert resolve_reset_templates("订单 ${reset.order.sn}", result.raw_outputs) == "订单 A100"


def test_reset_failure_stops_before_browser_execution(monkeypatch, db, config):
    monkeypatch.setitem(
        SCRIPT_REGISTRY,
        "shopping_cart",
        {
            "name": "购物车",
            "func": lambda _env, _vars: (False, "业务初始化失败", "", {}),
        },
    )
    monkeypatch.setattr(
        "app.services.ui_recording_reset.data_script_variables",
        lambda _db, variables, _project_id: dict(variables),
    )

    result = execute_recording_reset(db, config)

    assert result.passed is False
    assert "业务初始化失败" in result.error


def test_reset_report_masks_sensitive_outputs(monkeypatch, db, config):
    monkeypatch.setitem(
        SCRIPT_REGISTRY,
        "shopping_cart",
        {
            "name": "购物车",
            "func": lambda _env, _vars: (
                True,
                "token=top-secret",
                "",
                {"order": {"sn": "A100"}, "token": "top-secret", "password": "p@ss"},
            ),
        },
    )
    monkeypatch.setattr(
        "app.services.ui_recording_reset.data_script_variables",
        lambda _db, variables, _project_id: dict(variables),
    )

    result = execute_recording_reset(db, config)

    assert result.raw_outputs["token"] == "top-secret"
    assert result.public_report["outputs"]["token"] == "***"
    assert result.public_report["outputs"]["password"] == "***"
    assert "top-secret" not in result.public_report["log"]


def test_resolve_reset_templates_rejects_missing_variables():
    with pytest.raises(ValueError, match="缺少数据重置变量：reset.order.sn"):
        resolve_reset_templates("订单 ${reset.order.sn}", {})


def test_resolve_reset_templates_preserves_non_string_values():
    outputs = {"count": 3, "items": ["A", "B"]}

    assert resolve_reset_templates({"count": "${reset.count}", "items": "${reset.items}"}, outputs) == {
        "count": 3,
        "items": ["A", "B"],
    }
