from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import AiConfig
from app.routers import ai_config as ai_config_router


def _login(client: TestClient, username: str = "admin", password: str = "admin123") -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _replace_config(**values) -> AiConfig:
    db = SessionLocal()
    try:
        db.query(AiConfig).delete()
        config = AiConfig(
            provider=values.get("provider", "openai_compatible"),
            base_url=values.get("base_url", "https://old.example.test"),
            model=values.get("model", "old-model"),
            api_key=values.get("api_key", "existing-secret"),
            create_time=datetime.now(),
            heal_enabled=1,
            heal_confidence_threshold=0.7,
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        db.expunge(config)
        return config
    finally:
        db.close()


def _config_snapshot() -> tuple[str, str, str, str]:
    db = SessionLocal()
    try:
        config = db.query(AiConfig).order_by(AiConfig.id.desc()).first()
        assert config is not None
        return config.provider, config.base_url, config.model, config.api_key
    finally:
        db.close()


def test_blank_api_key_preserves_existing_global_secret():
    _replace_config()

    with TestClient(app) as client:
        response = client.put(
            "/api/ai-config",
            headers=_login(client),
            json={"model": "new-model", "api_key": ""},
        )

    assert response.status_code == 200
    assert _config_snapshot() == (
        "openai_compatible",
        "https://old.example.test",
        "new-model",
        "existing-secret",
    )


def test_global_connection_test_uses_form_values_without_persisting(monkeypatch):
    _replace_config()
    captured = {}

    def fake_model_call(config, prompt, timeout=90):
        captured["provider"] = config.provider
        captured["base_url"] = config.base_url
        captured["model"] = config.model
        captured["api_key"] = config.api_key
        captured["prompt"] = prompt
        captured["timeout"] = timeout
        return {"ok": True}

    monkeypatch.setattr(ai_config_router, "call_local_model_json", fake_model_call, raising=False)
    before = _config_snapshot()

    with TestClient(app) as client:
        response = client.post(
            "/api/ai-config/test",
            headers=_login(client),
            json={
                "provider": "openai_compatible",
                "base_url": "https://candidate.example.test",
                "model": "candidate-model",
                "api_key": "candidate-secret",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "message": "连接成功",
        "model": "candidate-model",
    }
    assert captured["base_url"] == "https://candidate.example.test"
    assert captured["model"] == "candidate-model"
    assert captured["api_key"] == "candidate-secret"
    assert _config_snapshot() == before


def test_frontend_has_one_global_ai_config_entry_and_no_module_aliases():
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    config_path = Path("static/ai-config.js")
    assert config_path.exists(), "缺少唯一的全局AI配置前端模块"
    config_js = config_path.read_text(encoding="utf-8")
    requirement_pack_js = Path("static/requirement-pack.js").read_text(encoding="utf-8")
    verification_js = Path("static/requirement-verification.js").read_text(encoding="utf-8")
    index_html = Path("static/index.html").read_text(encoding="utf-8")

    assert 'id="globalAiConfigBtn"' in app_js
    assert "window.GlobalAiConfig.mount" in app_js
    assert "全局 AI 配置" in config_js
    assert 'id="aiConfigBtn"' not in app_js
    assert "openAiConfigForm" not in app_js
    assert 'id="aiConfigBtn"' not in requirement_pack_js
    assert "openAiConfigForm" not in requirement_pack_js
    assert "verificationAiConfig" not in verification_js
    assert "openAiConfigForm" not in verification_js
    assert '/static/ai-config.js?' in index_html
