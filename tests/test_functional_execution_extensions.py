import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

TEST_DB = Path(__file__).resolve().parent / "test_platform_reliability.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB.as_posix()}")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "admin123")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import app.executors as executors
import app.main as main
import app.routers.functional_tasks as functional_task_router
from app.main import app


def login(client: TestClient, username: str = "admin", password: str = "admin123") -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_classifies_environment_setup_and_teardown():
    environment_log = json.dumps({"error_category": "environment", "environment_reason": "http_status=503"})
    setup_log = json.dumps({"error_category": "setup_failed", "failed_step": {"action": "goto", "_phase": "setup"}})
    teardown_log = json.dumps({"error_category": "teardown_failed", "failed_step": {"action": "click", "_phase": "teardown"}})

    assert functional_task_router._classify_functional_execution_result(False, environment_log, "executable") == ("blocked", "environment")
    assert functional_task_router._classify_functional_execution_result(False, setup_log, "executable") == ("blocked", "setup_failed")
    assert functional_task_router._classify_functional_execution_result(False, teardown_log, "executable") == ("needs_review", "teardown_failed")


def test_extract_step_variables_from_text():
    class FakeLocator:
        @property
        def first(self):
            return self

        def inner_text(self, timeout=0):
            return "new account id: ACC-10086"

    class FakePage:
        url = "https://example.test/accounts/ACC-10086"

        def locator(self, selector):
            return FakeLocator()

    variables = {}
    extracted, sources = executors._extract_step_variables(
        FakePage(),
        {"locator": "body", "extract": [{"name": "new_account_id", "source": "text", "pattern": r"(ACC-\d+)"}]},
        {"used_locator": "body"},
        variables,
    )

    assert extracted == {"new_account_id": "ACC-10086"}
    assert variables["new_account_id"] == "ACC-10086"
    assert sources[0]["name"] == "new_account_id"


def test_scenario_chain_shares_extracted_variables(monkeypatch):
    pytest.importorskip("playwright.sync_api")
    created_contexts = []
    seen = []

    class FakePage:
        def close(self):
            pass

    class FakeContext:
        def new_page(self):
            return FakePage()

        def close(self):
            pass

    class FakeBrowser:
        def new_context(self):
            created_contexts.append("context")
            return FakeContext()

        def close(self):
            pass

    def fake_execute(case, page, runtime_vars=None, execution_context=None, env=None):
        seen.append((case.id, dict(runtime_vars or {}), (execution_context or {}).get("session_policy")))
        if case.id == 1:
            return True, json.dumps({"extracted_variables": {"new_account_id": "ACC-10086"}, "execution_policy": "scenario_chain"}), "", ""
        return True, json.dumps({"execution_policy": "scenario_chain"}), "", ""

    monkeypatch.setattr(executors, "launch_chromium_browser", lambda playwright, headless=True: FakeBrowser())
    monkeypatch.setattr(executors, "execute_ui_case_in_page", fake_execute)

    items = [
        {"case": SimpleNamespace(id=1, case_name="open", page_url="https://example.test", steps="[]", timeout=5), "variables": {}, "execution_context": {"execution_policy": "scenario_chain"}},
        {"case": SimpleNamespace(id=2, case_name="transfer", page_url="https://example.test", steps="[]", timeout=5), "variables": {}, "execution_context": {"execution_policy": "scenario_chain"}},
    ]

    results = executors.execute_ui_cases_batch(items)

    assert [item[0] for item in results] == [True, True]
    assert created_contexts == ["context"]
    assert seen[0][2] == "scenario_chain"
    assert seen[1][1]["new_account_id"] == "ACC-10086"


def test_verify_login_endpoint_uses_temporary_credentials(monkeypatch):
    captured = {}

    def fake_probe(target_url, variables, login_url=""):
        captured.update({"target_url": target_url, "variables": variables, "login_url": login_url})
        return {
            "success": True,
            "recommended_config": {"username_locator": "#user", "password_locator": "#pass", "submit_locator": "#login"},
            "final_url": "https://example.test/home",
            "screenshot": "",
            "failure_reason": "",
        }

    monkeypatch.setattr(main, "probe_login_configuration", fake_probe)
    with TestClient(app) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/api/test-accounts/verify-login",
            headers=headers,
            json={
                "target_url": "https://example.test/login",
                "variables": {"username": "demo"},
                "sensitive_variables": {"password": "secret"},
            },
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured["target_url"] == "https://example.test/login"
    assert captured["variables"]["username"] == "demo"
    assert captured["variables"]["password"] == "secret"
