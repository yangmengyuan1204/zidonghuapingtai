from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.database import Base
from app.main import app
from app.models import Env, Project, UiRecordProjectConfig
from app.security import require_admin
from app.services.ui_recording_config import save_recording_config, serialize_recording_config


def test_recording_config_table_is_independent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert "ui_record_project_config" in inspect(engine).get_table_names()


def test_recording_config_rejects_env_from_other_project():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Project(id=1, name="A", desc="", create_time=datetime.now()),
            Project(id=2, name="B", desc="", create_time=datetime.now()),
            Env(id=9, project_id=2, env_name="B测试", base_url="https://b.test"),
        ])
        db.commit()

        with pytest.raises(ValueError, match="环境不存在或不属于当前项目"):
            save_recording_config(db, 1, {
                "reset_script_key": "shopping_cart",
                "reset_env_id": 9,
                "reset_variables": {},
                "max_repair_attempts": 3,
            })


def test_recording_config_serialization_returns_only_allowed_saved_values(monkeypatch):
    monkeypatch.setattr(
        "app.services.ui_recording_config.data_script_catalog",
        lambda _db, _project_id: [{"script_type": "shopping_cart", "name": "购物车", "risk_level": "normal"}],
    )
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Project(id=1, name="A", desc="", create_time=datetime.now()),
            Env(id=8, project_id=1, env_name="A测试", base_url="https://a.test"),
        ])
        db.commit()
        save_recording_config(db, 1, {
            "reset_script_key": "shopping_cart",
            "reset_env_id": 8,
            "reset_variables": {"sku": "demo-sku"},
            "max_repair_attempts": 9,
        })

        response = serialize_recording_config(db, 1)

    assert response == {
        "project_id": 1,
        "config": {
            "reset_script_key": "shopping_cart",
            "reset_env_id": 8,
            "reset_variables": {"sku": "demo-sku"},
            "verification_rounds": 2,
            "max_repair_attempts": 5,
        },
        "available_scripts": [{"script_type": "shopping_cart", "name": "购物车", "risk_level": "normal"}],
    }


def test_recording_config_rejects_sensitive_reset_variables():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Project(id=1, name="A", desc="", create_time=datetime.now()),
            Env(id=8, project_id=1, env_name="A测试", base_url="https://a.test"),
        ])
        db.commit()

        with pytest.raises(ValueError, match="重置参数不能保存密码、令牌或Cookie"):
            save_recording_config(db, 1, {
                "reset_script_key": "shopping_cart",
                "reset_env_id": 8,
                "reset_variables": {"password": "not-persisted"},
            })


def test_recording_config_routes_require_admin():
    routes = [
        route for route in app.routes
        if route.path == "/api/ui-record/projects/{project_id}/config"
    ]

    assert {"GET", "PUT"} == {method for route in routes for method in route.methods - {"HEAD", "OPTIONS"}}
    for route in routes:
        assert require_admin in [dependency.call for dependency in route.dependant.dependencies]
