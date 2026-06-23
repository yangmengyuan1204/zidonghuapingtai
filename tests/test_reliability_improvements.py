import atexit
import base64
import json
import os
import pytest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

TEST_DB = Path(__file__).resolve().parent / "test_platform_reliability.db"
# 确保测试退出后清理数据库文件（忽略文件被锁等错误）
def _cleanup_test_db():
    try:
        TEST_DB.unlink(missing_ok=True)
    except Exception:
        pass
atexit.register(_cleanup_test_db)
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB.as_posix()}")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "admin123")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from fastapi.testclient import TestClient

import app.executors as executors
import app.core.utils as core_utils
import app.functional_testing as functional_testing
import app.main as main
import app.routers.functional_tasks as functional_task_router
from app.database import SessionLocal
from app.main import app
from app.models import FunctionalCase, FunctionalTask, UiCase
from app.services.requirement_workflow import build_workflow_status


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def login(client: TestClient, username: str = "admin", password: str = "admin123") -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_deepseek_screenshot_analysis_uses_ocr_material_not_image_url(monkeypatch, tmp_path):
    image_path = tmp_path / "shot.png"
    image_path.write_bytes(PNG_1X1)

    def fail_visual(*args, **kwargs):
        raise AssertionError("visual image_url path must not be called for DeepSeek-only analysis")

    def fake_text_model(config, prompt, timeout=90):
        assert "OCR/图像材料" in prompt
        return {
            "page_summary": "登录页",
            "visible_controls": ["账号", "密码", "登录"],
            "inferred_rules": ["账号密码必填"],
            "questions_for_product": [],
            "suggested_test_points": ["验证登录成功"],
            "needs_manual_confirm": True,
        }

    monkeypatch.setattr(functional_testing, "call_visual_model_json", fail_visual)
    monkeypatch.setattr(functional_testing, "call_local_model_json", fake_text_model)

    task = SimpleNamespace(iteration_name="登录", target_url="https://example.test/login", requirement_text="")
    screenshot = SimpleNamespace(image_path=str(image_path))
    config = SimpleNamespace(provider="openai_compatible", base_url="https://api.deepseek.com", model="deepseek-v4", api_key="x")

    raw = functional_testing.analyze_functional_screenshot(task, screenshot, config)
    assert '"analysis_source": "ocr_deepseek"' in raw
    assert '"ocr_material"' in raw


def test_deepseek_model_name_error_retries_supported_flash(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, status_code, text="", payload=None):
            self.status_code = status_code
            self.text = text
            self._payload = payload or {}
            self.url = "https://api.deepseek.com/v1/chat/completions"

        @property
        def ok(self):
            return 200 <= self.status_code < 300

        def json(self):
            return self._payload

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json["model"])
        if len(calls) == 1:
            return FakeResponse(
                400,
                '{"error":{"message":"The supported API model names are deepseek-v4-pro or deepseek-v4-flash, but you passed deepseek-vl2."}}',
            )
        return FakeResponse(200, payload={"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(functional_testing.requests, "post", fake_post)
    config = SimpleNamespace(provider="openai_compatible", base_url="https://api.deepseek.com", model="deepseek-vl2", api_key="x")

    assert functional_testing.call_local_model_json(config, "生成 JSON") == {"ok": True}
    assert calls == ["deepseek-vl2", "deepseek-v4-flash"]


def test_ocr_numpy_runtime_error_is_compacted():
    raw = (
        "No module named 'paddleocr'; D:\\A_zidonghuapingtai\\.venv_ocr\\Scripts\\python.exe: "
        "paddleocr unavailable: IMPORTANT: PLEASE READ THIS FOR ADVICE! "
        "Importing the numpy C-extensions failed. _multiarray_umath.cp314-win_amd64.pyd"
    )

    message = functional_testing._compact_ocr_error(raw)

    assert "NumPy/PaddleOCR" in message
    assert "IMPORTANT" not in message
    assert "_multiarray_umath" not in message


def test_steps_without_business_assertion_are_not_trusted_success():
    steps = [{"action": "goto", "value": "https://example.test"}, {"action": "click", "locator": "text=提交"}]
    normalized, issues = executors._validate_ui_steps_for_execution(steps)
    assert normalized
    assert any(item.get("severity") == "warning" and "业务断言" in item.get("message", "") for item in issues)

    class FakeBody:
        def inner_text(self, timeout=1200):
            return "提交成功"

    class FakePage:
        url = "https://example.test/result"

        def locator(self, selector):
            return FakeBody()

    ok, verification_issues, evidence = executors._final_business_verification(FakePage(), normalized, 5)
    assert ok is False
    assert evidence["business_assertion_count"] == 0
    assert any("缺少业务断言" in item for item in verification_issues)


def test_expected_text_generates_weak_business_assertion():
    class FakeDb:
        flushed = False

        def flush(self):
            self.flushed = True

    db = FakeDb()
    case = SimpleNamespace(expected="保存成功")
    ui_case = SimpleNamespace(steps="")
    steps = [{"action": "click", "locator": "button:has-text('保存')"}]

    next_steps, generated = core_utils.ensure_weak_business_assertion(db, case, ui_case, steps)

    assert generated is True
    assert db.flushed is True
    assert next_steps[-1]["action"] == "text_assert"
    assert next_steps[-1]["locator"] == "body"
    assert next_steps[-1]["value"] == "保存成功"
    assert "保存成功" in ui_case.steps


def test_functional_execution_result_classifies_blocked_and_review():
    missing_assertion_log = json.dumps(
        {"verification_status": "failed_verification", "business_verification": {"business_assertion_count": 0}},
        ensure_ascii=False,
    )
    assertion_failed_log = json.dumps(
        {
            "current_url": "https://example.test",
            "auth_context": {"login_required": False, "auth_blocked": False},
            "failed_step": {"action": "text_assert", "locator": "body", "value": "__missing__"},
            "error_category": "文案断言失败",
            "error": "text_assert failed: expected text not found",
        },
        ensure_ascii=False,
    )
    login_redirect_log = json.dumps(
        {"current_url": "https://example.test/#/login", "failed_step": {"action": "click"}, "error_category": "定位器找不到"},
        ensure_ascii=False,
    )
    auth_blocked_log = json.dumps(
        {"current_url": "https://example.test", "auth_context": {"auth_blocked": True}, "error_category": "auth_blocked"},
        ensure_ascii=False,
    )

    assert functional_task_router._classify_functional_execution_result(False, "login_required #/login", "executable")[0] == "failed"
    assert functional_task_router._classify_functional_execution_result(False, "option_not_found", "executable")[0] == "blocked"
    assert functional_task_router._classify_functional_execution_result(False, assertion_failed_log, "executable") == ("failed", "assertion_or_page_failure")
    assert functional_task_router._classify_functional_execution_result(False, login_redirect_log, "executable") == ("blocked", "auth_redirected_to_login")
    assert functional_task_router._classify_functional_execution_result(False, auth_blocked_log, "executable") == ("blocked", "auth_blocked")
    assert functional_task_router._classify_functional_execution_result(False, missing_assertion_log, "executable")[0] == "needs_review"
    assert functional_task_router._classify_functional_execution_result(False, "preflight", core_utils.QUALITY_MISSING_VARIABLES)[0] == "blocked"
    assert functional_task_router._classify_functional_execution_result(False, "preflight", core_utils.QUALITY_NEEDS_REVIEW)[0] == "needs_review"


def test_preflight_summary_counts_trial_runnable():
    summary = core_utils.functional_package_preflight_summary(
        [
            {"quality_status": core_utils.QUALITY_EXECUTABLE},
            {"quality_status": core_utils.QUALITY_UNCHECKED},
            {"quality_status": core_utils.QUALITY_MISSING_VARIABLES},
            {"quality_status": core_utils.QUALITY_LOCATOR_RISK},
            {"quality_status": core_utils.QUALITY_NEEDS_REVIEW},
            {"quality_status": core_utils.QUALITY_AUTH_RISK},
            {"quality_status": core_utils.QUALITY_NOT_RECOMMENDED},
        ]
    )

    assert summary["executable"] == 1
    assert summary["trial_runnable"] == 4
    assert summary["manual_check"] == 5
    assert summary["auth_blocked"] == 1


def test_scan_endpoint_returns_trace_without_unbound_scanned(monkeypatch):
    with TestClient(app) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        project = client.post("/api/projects", headers=headers, json={"name": "scan-failure-project", "desc": ""}).json()
        task = client.post(
            "/api/functional-tasks",
            headers=headers,
            json={
                "project_id": project["id"],
                "iteration_name": "scan failure",
                "target_url": "https://example.test",
                "requirement_text": "",
            },
        ).json()

        def fake_scan(*args, **kwargs):
            raise functional_testing.FunctionalScanError("scan failed", ["启动浏览器", "导航失败"])

        monkeypatch.setattr(main, "scan_page_dom", fake_scan)
        response = client.post(f"/api/functional-tasks/{task['id']}/scan-page", headers=headers, json={})

    assert response.status_code == 400
    assert "扫描过程" in response.json()["detail"]
    assert "导航失败" in response.json()["detail"]


def protected_probe(url):
    return {
        "target_url": url,
        "auth_required": True,
        "protected_page_detected": True,
        "current_url": "https://example.test/#/login",
        "login_url": "https://example.test/#/login",
        "probe_error": "",
        "evidence": {"looks_like_login": True},
    }


def root_login_probe(url):
    return {
        "target_url": url,
        "auth_required": True,
        "protected_page_detected": True,
        "current_url": "https://www.saucedemo.com/",
        "login_url": "https://www.saucedemo.com/",
        "probe_error": "",
        "evidence": {"looks_like_login": True, "password_visible": True, "username_visible": True},
    }


def public_probe(url):
    return {
        "target_url": url,
        "auth_required": False,
        "protected_page_detected": False,
        "current_url": url,
        "login_url": "",
        "probe_error": "",
        "evidence": {"looks_like_login": False},
    }


def create_functional_task_for_auth(client, headers, name="auth gate task"):
    project = client.post("/api/projects", headers=headers, json={"name": name, "desc": ""}).json()
    task = client.post(
        "/api/functional-tasks",
        headers=headers,
        json={
            "project_id": project["id"],
            "iteration_name": name,
            "target_url": "https://example.test/#/protected",
            "requirement_text": "",
        },
    ).json()
    return project, task


def test_root_login_page_evidence_detects_protected_page():
    class FakeLocator:
        def __init__(self, selector):
            self.selector = selector

        @property
        def first(self):
            return self

        def is_visible(self, timeout=0):
            selector = self.selector.lower()
            return (
                self.selector == "body"
                or "password" in selector
                or "user" in selector
                or "login" in selector
                or "submit" in selector
            )

        def inner_text(self, timeout=0):
            return "Swag Labs Password for all users: secret_sauce"

    class FakeRootLoginPage:
        url = "https://www.saucedemo.com/"

        def locator(self, selector):
            return FakeLocator(selector)

    evidence = executors._login_page_evidence(FakeRootLoginPage(), expected_url="https://www.saucedemo.com/inventory.html")

    assert evidence["looks_like_login"] is True
    assert evidence["password_visible"] is True
    assert evidence["username_visible"] is True


def test_protected_functional_preflight_without_account_is_blocked(monkeypatch):
    monkeypatch.setattr(core_utils, "probe_target_auth_state", protected_probe)
    with TestClient(app) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        _, task = create_functional_task_for_auth(client, headers, "protected-no-account")

        response = client.post(f"/api/functional-tasks/{task['id']}/preflight-package", headers=headers, json={})

    assert response.status_code == 200
    data = response.json()
    assert data["auth_required"] is True
    assert data["can_execute"] is False
    assert data["login"]["status"] == "blocked"
    assert data["login"]["blocking_reason"] == "account_missing"


def test_preflight_probes_confirmed_case_urls_for_auth(monkeypatch):
    def task_login_public_case_protected(url):
        if str(url).endswith("/dashboard"):
            return {
                "target_url": url,
                "auth_required": True,
                "protected_page_detected": True,
                "current_url": "https://orange.example/auth/login",
                "login_url": "https://orange.example/auth/login",
                "probe_error": "",
                "evidence": {"looks_like_login": True},
            }
        return {
            "target_url": url,
            "auth_required": False,
            "protected_page_detected": False,
            "current_url": url,
            "login_url": "",
            "probe_error": "",
            "evidence": {"looks_like_login": True},
        }

    monkeypatch.setattr(core_utils, "probe_target_auth_state", task_login_public_case_protected)
    with TestClient(app) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        project = client.post("/api/projects", headers=headers, json={"name": "case-url-auth-project", "desc": ""}).json()
        task = client.post(
            "/api/functional-tasks",
            headers=headers,
            json={
                "project_id": project["id"],
                "iteration_name": "case url auth task",
                "target_url": "https://orange.example/auth/login",
                "requirement_text": "",
            },
        ).json()
        ui_case = client.post(
            "/api/ui-cases",
            headers=headers,
            json={
                "project_id": project["id"],
                "case_name": "dashboard protected case",
                "page_url": "https://orange.example/dashboard",
                "steps": [{"action": "text_assert", "locator": "body", "value": "Dashboard"}],
                "timeout": 5,
                "status": "active",
            },
        ).json()
        db = SessionLocal()
        try:
            db.add(
                FunctionalCase(
                    task_id=task["id"],
                    title="dashboard case",
                    precondition="",
                    steps="open dashboard",
                    expected="Dashboard",
                    category="acceptance",
                    priority="P1",
                    automation_status="approved",
                    test_result="untested",
                    ui_case_id=ui_case["id"],
                    quality_status="unchecked",
                    quality_report="",
                    failure_count=0,
                    create_time=datetime.now(),
                )
            )
            db.commit()
        finally:
            db.close()

        response = client.post(f"/api/functional-tasks/{task['id']}/preflight-package", headers=headers, json={})

    assert response.status_code == 200
    data = response.json()
    assert data["login"]["status"] == "blocked"
    assert data["login"]["blocking_reason"] == "account_missing"
    assert any(item["source"] == "case" and item["auth_required"] for item in data["login"]["auth_probe_sources"])
    assert any(item["source"] == "case" and item["auth_required"] for item in data["auth_probe_sources"])


def test_business_username_input_is_not_stripped_as_login_step():
    steps = [
        {"name": "search username", "action": "input", "locator": "input[name='username']", "value": "Admin"},
        {"name": "search", "action": "click", "locator": "button:has-text('Search')"},
    ]
    context = {
        "login_config": {
            "username_locator": "input[name='login_user']",
            "password_locator": "input[name='login_password']",
            "submit_locator": "button[type='submit']",
        }
    }

    kept, removed = executors._strip_leading_login_steps(steps, context)

    assert removed == []
    assert kept[0]["locator"] == "input[name='username']"


def test_configured_leading_login_steps_are_stripped():
    steps = [
        {"action": "goto", "value": "https://orange.example/auth/login"},
        {"action": "input", "locator": "input[name='username']", "value": "Admin"},
        {"action": "input", "locator": "input[name='password']", "value": "admin123"},
        {"action": "click", "locator": "button[type='submit']"},
        {"action": "wait"},
        {"action": "text_assert", "locator": "body", "value": "Dashboard"},
    ]
    context = {
        "login_config": {
            "username_locator": "input[name='username']",
            "password_locator": "input[name='password']",
            "submit_locator": "button[type='submit']",
        }
    }

    kept, removed = executors._strip_leading_login_steps(steps, context)

    assert len(removed) == 5
    assert kept == [{"action": "text_assert", "locator": "body", "value": "Dashboard"}]


def test_task_overall_status_aggregates_all_case_results():
    db = SessionLocal()
    try:
        task = FunctionalTask(
            project_id=9001,
            iteration_name="overall status task",
            requirement_text="",
            axure_path="",
            target_url="https://example.test",
            context="",
            status="passed",
            create_time=datetime.now(),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        db.add_all(
            [
                FunctionalCase(task_id=task.id, title="passed", precondition="", steps="", expected="", category="", priority="P1", automation_status="approved", test_result="passed", ui_case_id=None, quality_status="executable", quality_report="", failure_count=0, create_time=datetime.now()),
                FunctionalCase(task_id=task.id, title="failed", precondition="", steps="", expected="", category="", priority="P1", automation_status="approved", test_result="failed", ui_case_id=None, quality_status="executable", quality_report="", failure_count=0, create_time=datetime.now()),
                FunctionalCase(task_id=task.id, title="blocked", precondition="", steps="", expected="", category="", priority="P1", automation_status="approved", test_result="blocked", ui_case_id=None, quality_status="missing_variables", quality_report="", failure_count=0, create_time=datetime.now()),
            ]
        )
        db.commit()

        assert functional_task_router._functional_task_overall_status(db, task.id, fallback="passed") == "failed"
    finally:
        db.close()


def test_passed_record_current_url_uses_business_verification_final_url():
    log_data = {
        "business_verification": {"final_url": "https://orange.example/dashboard"},
        "step_logs": [{"current_url_after": "https://orange.example/old"}],
    }

    assert functional_task_router._record_current_url_from_log(log_data) == "https://orange.example/dashboard"


def test_workflow_next_actions_do_not_repeat_passed_trusted_cases():
    db = SessionLocal()
    try:
        task = FunctionalTask(
            project_id=9002,
            iteration_name="workflow actions task",
            requirement_text="",
            axure_path="",
            target_url="https://example.test",
            context="",
            status="failed",
            create_time=datetime.now(),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        ui_case = UiCase(project_id=9002, case_name="passed ui", page_url="https://example.test", steps="[]", timeout=5, status="active", create_time=datetime.now())
        db.add(ui_case)
        db.commit()
        db.refresh(ui_case)
        passed_case = FunctionalCase(task_id=task.id, title="trusted passed", precondition="", steps="", expected="", category="", priority="P1", automation_status="approved", test_result="passed", ui_case_id=ui_case.id, quality_status="executable", quality_report="", failure_count=0, create_time=datetime.now())
        failed_case = FunctionalCase(task_id=task.id, title="failed case", precondition="", steps="", expected="", category="", priority="P1", automation_status="approved", test_result="failed", ui_case_id=ui_case.id, quality_status="executable", quality_report="", failure_count=1, create_time=datetime.now())
        db.add_all([passed_case, failed_case])
        db.commit()
        db.refresh(passed_case)
        passed_case_id = passed_case.id

        workflow = build_workflow_status(db, task)
    finally:
        db.close()

    action_keys = [item["key"] for item in workflow["next_actions"]]
    execute_actions = [item for item in workflow["next_actions"] if item["key"] == "execute"]
    assert "check_diagnosis" in action_keys
    assert all(passed_case_id not in item.get("target_case_ids", []) for item in execute_actions)


def test_root_login_protected_page_without_account_blocks_execution(monkeypatch):
    monkeypatch.setattr(core_utils, "probe_target_auth_state", root_login_probe)
    with TestClient(app) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        _, task = create_functional_task_for_auth(client, headers, "root-login-no-account")

        preflight = client.post(f"/api/functional-tasks/{task['id']}/preflight-package", headers=headers, json={})
        response = client.post(
            f"/api/functional-tasks/{task['id']}/execute-async",
            headers=headers,
            json={"force": True},
        )

    assert preflight.status_code == 200
    data = preflight.json()
    assert data["auth_required"] is True
    assert data["can_execute"] is False
    assert data["login"]["blocking_reason"] == "account_missing"
    assert response.status_code == 400


def test_protected_functional_preflight_with_multiple_accounts_requires_binding(monkeypatch):
    monkeypatch.setattr(core_utils, "probe_target_auth_state", protected_probe)
    with TestClient(app) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        project, task = create_functional_task_for_auth(client, headers, "protected-ambiguous-account")
        for index in range(2):
            client.post(
                "/api/test-accounts",
                headers=headers,
                json={
                    "project_id": project["id"],
                    "profile_name": f"账号{index}",
                    "variables": {"username": f"user{index}"},
                    "sensitive_variables": {"password": "secret"},
                    "status": "active",
                },
            )

        response = client.post(f"/api/functional-tasks/{task['id']}/preflight-package", headers=headers, json={})

    assert response.status_code == 200
    data = response.json()
    assert data["login"]["status"] == "blocked"
    assert data["login"]["blocking_reason"] == "account_ambiguous"
    assert len(data["login"]["candidate_profiles"]) >= 2


def test_force_execute_cannot_bypass_missing_password(monkeypatch):
    monkeypatch.setattr(core_utils, "probe_target_auth_state", protected_probe)
    with TestClient(app) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        project, task = create_functional_task_for_auth(client, headers, "protected-missing-password")
        client.post(
            "/api/test-accounts",
            headers=headers,
            json={
                "project_id": project["id"],
                "profile_name": "缺密码账号",
                "variables": {"username": "user-no-password"},
                "sensitive_variables": {},
                "status": "active",
            },
        )

        response = client.post(
            f"/api/functional-tasks/{task['id']}/execute-async",
            headers=headers,
            json={"force": True},
        )

    assert response.status_code == 400
    assert "登录前置缺失" in response.json()["detail"]


def test_account_preflight_blocks_missing_login_locators(monkeypatch):
    monkeypatch.setattr(core_utils, "probe_target_auth_state", protected_probe)
    with TestClient(app) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        project, task = create_functional_task_for_auth(client, headers, "protected-missing-locators")
        client.post(
            "/api/test-accounts",
            headers=headers,
            json={
                "project_id": project["id"],
                "profile_name": "missing locators account",
                "variables": {"username": "standard_user"},
                "sensitive_variables": {"password": "secret_sauce"},
                "login_url": "https://www.saucedemo.com/",
                "status": "active",
            },
        )

        response = client.post(f"/api/functional-tasks/{task['id']}/preflight-package", headers=headers, json={})

    assert response.status_code == 200
    login_status = response.json()["login"]
    assert login_status["status"] == "blocked"
    assert login_status["blocking_reason"] == "missing_credentials"
    assert {"username_locator", "password_locator", "submit_locator"}.issubset(set(login_status["missing_credentials"]))


def test_force_execute_missing_variables_records_blocked_without_browser(monkeypatch):
    monkeypatch.setattr(core_utils, "probe_target_auth_state", public_probe)
    batch_calls = []

    def fake_batch(items, on_case_start=None, on_case_finish=None):
        batch_calls.append(list(items))
        return []

    monkeypatch.setattr(functional_task_router, "execute_ui_cases_batch", fake_batch)
    with TestClient(app) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        project = client.post("/api/projects", headers=headers, json={"name": "missing-data-force-project", "desc": ""}).json()
        task = client.post(
            "/api/functional-tasks",
            headers=headers,
            json={
                "project_id": project["id"],
                "iteration_name": "missing data force",
                "target_url": "https://example.test",
                "requirement_text": "",
            },
        ).json()
        ui_case = client.post(
            "/api/ui-cases",
            headers=headers,
            json={
                "project_id": project["id"],
                "case_name": "搜索客户缺变量",
                "page_url": "https://example.test/search?q={{customerId}}",
                "steps": [
                    {"action": "goto", "value": "https://example.test/search?q={{customerId}}"},
                    {"action": "text_assert", "locator": "body", "value": "Example"},
                ],
                "timeout": 5,
                "status": "active",
            },
        ).json()
        db = SessionLocal()
        try:
            case = FunctionalCase(
                task_id=task["id"],
                title="搜索客户缺少真实数据",
                precondition="",
                steps="搜索客户 {{customerId}}",
                expected="Example",
                category="acceptance",
                priority="P1",
                automation_status="approved",
                test_result="untested",
                ui_case_id=ui_case["id"],
                quality_status="unchecked",
                quality_report="",
                failure_count=0,
                create_time=datetime.now(),
            )
            db.add(case)
            db.commit()
        finally:
            db.close()

        preflight = client.post(f"/api/functional-tasks/{task['id']}/preflight-package", headers=headers, json={})
        assert preflight.status_code == 200
        assert preflight.json()["counts"]["data_missing"] == 1
        assert preflight.json()["trial_count"] == 0

        response = client.post(f"/api/functional-tasks/{task['id']}/execute-async", headers=headers, json={"force": True})
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        final = {}
        for _ in range(30):
            final = client.get(f"/api/functional-executions/{job_id}", headers=headers).json()
            if final.get("status") != "running":
                break

    assert batch_calls == []
    assert final["status"] == "blocked"
    assert final["blocked_count"] == 1
    assert final["failed_count"] == 0
    record = final["records"][0]
    assert record["result"] == "blocked"
    assert record["result_reason"] == "data_missing"
    assert record["blocked_type"] == "data"
    assert "customerId" in record["missing_variables"]


def test_fill_action_is_normalized_to_input():
    steps, issues = executors._validate_ui_steps_for_execution(
        [
            {"action": "fill", "locator": "#first-name", "value": "Test"},
            {"action": "text_assert", "locator": "body", "value": "OK"},
        ]
    )

    assert [item for item in issues if item.get("severity") == "error"] == []
    assert steps[0]["action"] == "input"
    assert steps[0]["original_action"] == "fill"


def test_batch_ui_execution_uses_isolated_contexts(monkeypatch):
    pytest.importorskip("playwright.sync_api")
    created_contexts = []
    seen_pages = []

    class FakePage:
        def __init__(self, context_id):
            self.context_id = context_id

        def close(self):
            pass

    class FakeContext:
        def __init__(self, context_id):
            self.context_id = context_id

        def new_page(self):
            return FakePage(self.context_id)

        def close(self):
            pass

    class FakeBrowser:
        def new_context(self):
            context_id = len(created_contexts) + 1
            created_contexts.append(context_id)
            return FakeContext(context_id)

        def close(self):
            pass

    def fake_execute(case, page, runtime_vars=None, execution_context=None, env=None):
        seen_pages.append((case.id, page.context_id, (execution_context or {}).get("session_policy")))
        return True, json.dumps({"session_policy": (execution_context or {}).get("session_policy")}), "", ""

    monkeypatch.setattr(executors, "launch_chromium_browser", lambda playwright, headless=True: FakeBrowser())
    monkeypatch.setattr(executors, "execute_ui_case_in_page", fake_execute)

    items = [
        {"case": SimpleNamespace(id=1, case_name="case 1", page_url="https://example.test", steps="[]", timeout=5), "execution_context": {}},
        {"case": SimpleNamespace(id=2, case_name="case 2", page_url="https://example.test", steps="[]", timeout=5), "execution_context": {}},
    ]

    results = executors.execute_ui_cases_batch(items)

    assert [item[0] for item in results] == [True, True]
    assert created_contexts == [1, 2]
    assert seen_pages == [(1, 1, "isolated_per_case"), (2, 2, "isolated_per_case")]


def test_executor_blocks_business_steps_when_target_redirects_to_login():
    class FakeLocator:
        def __init__(self, selector):
            self.selector = selector

        @property
        def first(self):
            return self

        def is_visible(self, timeout=0):
            return self.selector == "body" or "password" in self.selector.lower() or "登录" in self.selector

        def inner_text(self, timeout=0):
            return "RAKUMART 登录 立即登录 请输入密码"

    class FakeLoginPage:
        url = "https://example.test/#/login"

        def set_default_timeout(self, timeout):
            pass

        def goto(self, url, wait_until="domcontentloaded", timeout=None):
            self.url = "https://example.test/#/login"

        def wait_for_load_state(self, state, timeout=0):
            pass

        def wait_for_timeout(self, timeout):
            pass

        def locator(self, selector):
            return FakeLocator(selector)

        def screenshot(self, path, full_page=True):
            Path(path).write_bytes(PNG_1X1)

    case = SimpleNamespace(
        id=10001,
        case_name="受保护页面搜索",
        page_url="https://example.test/#/protected",
        steps=json.dumps([{"action": "click", "locator": "button:has-text('搜索')"}], ensure_ascii=False),
        timeout=5,
    )

    passed, log_text, _, _ = executors.execute_ui_case_in_page(case, FakeLoginPage(), {}, {})
    log_data = json.loads(log_text)

    assert passed is False
    assert log_data["error_category"] == "auth_blocked"
    assert "登录前置失败" in log_data["error"]
    assert log_data["auth_context"]["auth_blocked"] is True
