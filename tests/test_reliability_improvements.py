import atexit
import base64
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
import app.functional_testing as functional_testing
import app.main as main
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
