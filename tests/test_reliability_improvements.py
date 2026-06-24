import atexit
import base64
import json
import os
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
from app.main import app


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


def test_scan_request_failure_text_accepts_string_dict_and_method():
    assert functional_testing._request_failure_text(SimpleNamespace(failure="net::ERR_ABORTED")) == "net::ERR_ABORTED"
    assert functional_testing._request_failure_text(SimpleNamespace(failure={"errorText": "net::ERR_FAILED"})) == "net::ERR_FAILED"

    class RequestWithFailureMethod:
        def failure(self):
            return {"error": "timeout"}

    assert functional_testing._request_failure_text(RequestWithFailureMethod()) == "timeout"


def test_scan_error_screenshot_skips_closed_page():
    assert functional_testing._page_available_for_screenshot(None) is False
    assert functional_testing._page_available_for_screenshot(SimpleNamespace(is_closed=lambda: True)) is False
    assert functional_testing._page_available_for_screenshot(SimpleNamespace(is_closed=lambda: False)) is True


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

    assert functional_task_router._classify_functional_execution_result(False, "login_required #/login", "executable")[0] == "blocked"
    assert functional_task_router._classify_functional_execution_result(False, "option_not_found", "executable")[0] == "blocked"
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


def test_generated_functional_cases_are_limited_to_high_value_batch():
    payload = {
        "cases": [
            {
                "title": f"case-{index}",
                "precondition": "",
                "steps": ["open page"],
                "expected": "ok",
                "category": "主流程",
                "priority": "P0",
            }
            for index in range(15)
        ]
    }

    cases, questions = functional_testing._normalize_generated_cases(payload)

    assert questions == []
    assert len(cases) == 12
    assert {item["priority"] for item in cases} == {"P0"}


def test_preflight_groups_and_missing_variables_detail():
    cases = [
        {"case_id": 1, "category": "主流程", "quality_status": core_utils.QUALITY_EXECUTABLE},
        {
            "case_id": 2,
            "category": "边界值",
            "quality_status": core_utils.QUALITY_MISSING_VARIABLES,
            "required_seed_keys": ["keyword"],
        },
        {"case_id": 3, "category": "异常流程", "quality_status": core_utils.QUALITY_NEEDS_REVIEW},
    ]

    summary = core_utils.functional_package_preflight_summary(cases)
    groups = core_utils.functional_preflight_case_groups(cases)
    missing = core_utils.functional_missing_variables_detail(cases, {"keyword": "Admin"})

    assert summary["trial_runnable"] == 2
    assert sum(item["total"] for item in groups) == 3
    assert missing == [
        {
            "name": "keyword",
            "affected_case_ids": [2],
            "suggested_value": "Admin",
            "source": "seed",
            "required": True,
        }
    ]


def test_runtime_variables_saved_without_sensitive_values():
    task = SimpleNamespace(context="plain notes")

    saved = functional_task_router._save_functional_runtime_variables(
        task,
        {"keyword": "Admin", "password": "secret", "token": "abc", "empty": ""},
    )

    payload = json.loads(task.context)
    assert saved == {"keyword": "Admin"}
    assert payload["notes"] == "plain notes"
    assert payload["runtime_variables"] == {"keyword": "Admin"}
    assert core_utils.functional_task_runtime_variables(task) == {"keyword": "Admin"}


def test_execute_ui_cases_batch_parallelism_uses_ordered_results(monkeypatch):
    calls = []

    def fake_execute_ui_case(case, variables=None, execution_context=None):
        calls.append(case.id)
        return True, json.dumps({"step_logs": [{"index": 1, "status": "passed"}]}), "", ""

    monkeypatch.setattr(executors, "execute_ui_case", fake_execute_ui_case)
    items = [
        {"case": SimpleNamespace(id=1, case_name="case-1"), "variables": {}, "execution_context": {}},
        {"case": SimpleNamespace(id=2, case_name="case-2"), "variables": {}, "execution_context": {}},
    ]
    started = []
    finished = []

    results = executors.execute_ui_cases_batch(
        items,
        on_case_start=lambda item: started.append(item["case"].id),
        on_case_finish=lambda item, result: finished.append(item["case"].id),
        parallelism=2,
    )

    assert [item[0] for item in results] == [True, True]
    assert started == [1, 2]
    assert sorted(finished) == [1, 2]
    assert sorted(calls) == [1, 2]


def test_functional_repair_plan_only_marks_safe_locator_updates_auto_fixable():
    run = SimpleNamespace(
        id=7,
        log=json.dumps(
            {
                "records": [
                    {
                        "functional_case_id": 3,
                        "ui_case_id": 9,
                        "title": "search",
                        "result": "failed",
                        "result_reason": "assertion_or_page_failure",
                        "log": json.dumps(
                            {
                                "step_logs": [
                                    {
                                        "healed": True,
                                        "original_locator": "#old",
                                        "suggested_locator": "#new",
                                    }
                                ]
                            }
                        ),
                    },
                    {"functional_case_id": 4, "title": "assert", "result": "failed", "result_reason": "assertion_or_page_failure"},
                ]
            }
        ),
    )

    plan = functional_task_router._build_functional_repair_plan(run)

    assert plan["auto_fixable_count"] == 1
    assert plan["repair_items"][0]["fix_type"] == "locator"
    assert plan["repair_items"][0]["locator_updates"] == [{"original_locator": "#old", "suggested_locator": "#new"}]
    assert plan["repair_items"][1]["auto_fixable"] is False


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
