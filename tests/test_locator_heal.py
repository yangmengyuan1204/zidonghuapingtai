"""Locator 自愈功能 + 关联 API 功能测试。

覆盖：
- _validate_new_locator 验证逻辑（唯一性/可见性/动作兼容）
- _lookup_heal_history / _record_heal_history / update_heal_history_on_success 历史学习闭环
- _build_heal_prompt / _build_compact_prompt / _mask_sensitive / _filter_relevant_elements
- _apply_heal_to_case 写回用例
- _extract_interactive_elements DOM 提取（mock page）
- auto_heal 完整流程（mock page + db + AI config + AI 调用）
- /api/locator-heal-logs 分页 API
- /api/locator-heal-logs/{id}/apply 手动应用 API
- /api/ai-config 自愈字段配置
"""

import atexit
import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

TEST_DB = Path(__file__).resolve().parent / "test_locator_heal.db"


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
os.environ.setdefault("ALLOW_DEFAULT_ADMIN_PASSWORD", "1")

from fastapi.testclient import TestClient

import app.services.locator_heal as locator_heal
from app.core.utils import init_app
from app.database import SessionLocal, get_db
from app.main import app
from app.models import AiConfig, LocatorHealHistory, LocatorHealLog, Project, UiCase, User

# 确保表结构已创建（init_app 会建表 + 轻量迁移补齐 heal 字段）
init_app()


# ── 测试夹具 ──────────────────────────────────────────────


@pytest.fixture()
def db():
    """提供一个独立 session 的 db；每个测试开始前清理自愈相关表避免污染。"""
    session = SessionLocal()
    # 测试前清理（_record_heal_history 内部 commit，无法靠 rollback 隔离）
    for model in (LocatorHealHistory, LocatorHealLog):
        session.query(model).delete()
    session.query(UiCase).delete()
    session.query(AiConfig).delete()
    session.query(Project).filter(Project.name.like("heal-test%")).delete(synchronize_session=False)
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    """FastAPI TestClient，复用 db fixture 的 session。"""
    def _override_get_db():
        try:
            yield db
        finally:
            pass  # 由 db fixture 关闭

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def admin_token(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture()
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def ai_config(db):
    """创建一个 AI 配置。"""
    cfg = AiConfig(
        provider="openai_compatible",
        base_url="https://api.example.com",
        model="gpt-test",
        api_key="sk-test",
        create_time=datetime.now(),
        heal_enabled=1,
        heal_confidence_threshold=0.7,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


@pytest.fixture()
def project(db):
    proj = Project(name="heal-test-proj", desc="", create_time=datetime.now())
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


@pytest.fixture()
def ui_case(db, project):
    """创建一个包含失效 locator 的 UI 用例。"""
    steps = [
        {"action": "click", "name": "登录按钮", "locator": "#old-login-btn", "value": ""},
        {"action": "input", "name": "用户名", "locator": "#username", "value": "testuser"},
    ]
    case = UiCase(
        project_id=project.id,
        case_name="heal-test-case",
        page_url="https://example.test/login",
        steps=json.dumps(steps, ensure_ascii=False),
        create_time=datetime.now(),
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


class FakeLocator:
    """模拟 Playwright Locator。"""

    def __init__(self, count_value: int = 1, visible: bool = True, tag: str = "button"):
        self._count = count_value
        self._visible = visible
        self._tag = tag

    def count(self) -> int:
        return self._count

    @property
    def first(self):
        return self

    def is_visible(self, timeout: float = 0) -> bool:
        return self._visible

    def evaluate(self, expr: str):
        return self._tag


class FakePage:
    """模拟 Playwright Page 对象。"""

    def __init__(self, elements: list[dict] | None = None, locator_count: int = 1, locator_visible: bool = True, locator_tag: str = "button", url: str = "https://example.test/login"):
        self._elements = elements or []
        self._locator_count = locator_count
        self._locator_visible = locator_visible
        self._locator_tag = locator_tag
        self._url = url
        self.evaluate_calls = 0

    @property
    def url(self) -> str:
        return self._url

    def evaluate(self, script: str):
        self.evaluate_calls += 1
        return self._elements

    def locator(self, selector: str):
        return FakeLocator(self._locator_count, self._locator_visible, self._locator_tag)

    def wait_for_load_state(self, state: str, timeout: int = 0):
        return None

    def wait_for_timeout(self, ms: int):
        return None


# ── 1. _validate_new_locator ──────────────────────────────


class TestValidateNewLocator:
    def test_empty_locator_returns_false(self):
        assert locator_heal._validate_new_locator(FakePage(), "", "click") is False
        assert locator_heal._validate_new_locator(FakePage(), None, "click") is False

    def test_non_unique_locator_returns_false(self):
        page = FakePage(locator_count=2)  # 匹配 2 个元素
        assert locator_heal._validate_new_locator(page, "#dup", "click") is False

    def test_invisible_locator_returns_false(self):
        page = FakePage(locator_count=1, locator_visible=False)
        assert locator_heal._validate_new_locator(page, "#hidden", "click") is False

    def test_unique_visible_locator_returns_true(self):
        page = FakePage(locator_count=1, locator_visible=True, locator_tag="button")
        assert locator_heal._validate_new_locator(page, "#ok", "click") is True

    def test_action_tag_incompatible_returns_false(self):
        # click 动作要求 button/a/input/select/option，div 不在内
        page = FakePage(locator_count=1, locator_visible=True, locator_tag="div")
        assert locator_heal._validate_new_locator(page, "#div", "click") is False

    def test_action_tag_compatible_returns_true(self):
        page = FakePage(locator_count=1, locator_visible=True, locator_tag="input")
        assert locator_heal._validate_new_locator(page, "#input", "input") is True

    def test_unrestricted_action_returns_true(self):
        # text_assert 不限制标签
        page = FakePage(locator_count=1, locator_visible=True, locator_tag="div")
        assert locator_heal._validate_new_locator(page, "#div", "text_assert") is True

    def test_quick_mode_does_not_affect_unique_check(self):
        page = FakePage(locator_count=2)
        assert locator_heal._validate_new_locator(page, "#dup", "click", quick=True) is False


# ── 2. 历史学习闭环 ──────────────────────────────────────


class TestHealHistory:
    def test_record_and_lookup(self, db, project):
        old, new = "#old-btn", "#new-btn"
        # 新记录 success_count=0，_lookup_heal_history 不会命中
        locator_heal._record_heal_history(db, project.id, old, new)
        assert locator_heal._lookup_heal_history(db, project.id, old) is None

        # 模拟用例执行成功，更新 success_count
        locator_heal.update_heal_history_on_success(db, old, new)
        assert locator_heal._lookup_heal_history(db, project.id, old) == new

    def test_lookup_prefers_higher_success_count(self, db, project):
        old = "#old"
        # 两条映射，success_count 不同
        locator_heal._record_heal_history(db, project.id, old, "#new1")
        locator_heal._record_heal_history(db, project.id, old, "#new2")
        locator_heal.update_heal_history_on_success(db, old, "#new1")  # success=1
        locator_heal.update_heal_history_on_success(db, old, "#new2")
        locator_heal.update_heal_history_on_success(db, old, "#new2")  # success=2
        assert locator_heal._lookup_heal_history(db, project.id, old) == "#new2"

    def test_record_increments_apply_count(self, db, project):
        old, new = "#a", "#b"
        locator_heal._record_heal_history(db, project.id, old, new)
        locator_heal._record_heal_history(db, project.id, old, new)
        locator_heal._record_heal_history(db, project.id, old, new)
        record = db.query(LocatorHealHistory).filter_by(old_locator=old, new_locator=new).one()
        assert record.apply_count == 3

    def test_lookup_returns_none_when_no_match(self, db, project):
        assert locator_heal._lookup_heal_history(db, project.id, "#nope") is None

    def test_lookup_falls_back_to_null_project(self, db, project):
        old, new = "#old", "#new"
        # project_id=None 的全局映射
        locator_heal._record_heal_history(db, None, old, new)
        locator_heal.update_heal_history_on_success(db, old, new)
        # 用其他 project_id 也能查到
        assert locator_heal._lookup_heal_history(db, project.id, old) == new

    def test_update_success_count_idempotent_when_no_record(self, db):
        # 不存在的映射不应报错
        locator_heal.update_heal_history_on_success(db, "#noold", "#nonew")
        # 不应创建新记录
        assert db.query(LocatorHealHistory).count() == 0


# ── 3. Prompt 构建 ───────────────────────────────────────


class TestPromptBuild:
    def test_mask_sensitive_password_value(self):
        assert locator_heal._mask_sensitive("secret123", "input", "password") == "***"
        assert locator_heal._mask_sensitive("secret123", "input", "用户密码") == "***"
        assert locator_heal._mask_sensitive("secret123", "input_password", "") == "***"

    def test_mask_sensitive_normal_value(self):
        assert locator_heal._mask_sensitive("hello", "input", "username") == "hello"
        assert locator_heal._mask_sensitive("", "input", "username") == ""
        assert locator_heal._mask_sensitive(None, "input", "username") == ""

    def test_build_heal_prompt_contains_required_fields(self):
        step = {"action": "click", "name": "登录", "value": ""}
        elements = [{"tag": "button", "text": "登录", "id": "login-btn", "locator_candidates": ["#login-btn"]}]
        prompt = locator_heal._build_heal_prompt("#old", step, elements)
        assert "#old" in prompt
        assert "click" in prompt
        assert "登录" in prompt
        assert "new_locator" in prompt
        assert "confidence" in prompt

    def test_build_heal_prompt_masks_password(self):
        step = {"action": "input", "name": "password", "value": "mysecret"}
        elements = []
        prompt = locator_heal._build_heal_prompt("#pwd", step, elements)
        assert "mysecret" not in prompt
        assert "***" in prompt

    def test_build_compact_prompt_smaller_than_full(self):
        step = {"action": "click", "name": "btn", "value": ""}
        elements = [{"tag": "button", "text": f"btn{i}", "id": f"id{i}", "name": "", "placeholder": "", "type": "", "role": "", "locator_candidates": [f"#id{i}"]} for i in range(50)]
        full = locator_heal._build_heal_prompt("#old", step, elements)
        compact = locator_heal._build_compact_prompt("#old", step, elements)
        assert len(compact) < len(full)

    def test_filter_relevant_elements_keeps_all_when_small(self):
        elements = [{"tag": "button", "text": "x"}]
        assert locator_heal._filter_relevant_elements("#old", elements) == elements

    def test_filter_relevant_elements_truncates_to_30(self):
        elements = [{"tag": "button", "text": f"btn{i}"} for i in range(50)]
        result = locator_heal._filter_relevant_elements("#old", elements)
        assert len(result) == 30

    def test_filter_relevant_elements_prioritizes_matching(self):
        elements = [
            {"tag": "button", "text": "登录", "id": "", "name": "", "placeholder": ""},
            {"tag": "button", "text": "其他", "id": "", "name": "", "placeholder": ""},
        ]
        result = locator_heal._filter_relevant_elements("#login", elements * 15)  # 30 个
        assert len(result) == 30
        # 含 "login" 关键词的应排在前面
        assert result[0]["text"] == "登录"


# ── 4. 写回用例 ───────────────────────────────────────────


class TestApplyHealToCase:
    def test_apply_replaces_matching_locator(self, db, ui_case):
        old, new = "#old-login-btn", "#new-login-btn"
        changed = locator_heal._apply_heal_to_case(db, ui_case.id, old, new)
        assert changed is True
        db.refresh(ui_case)
        steps = json.loads(ui_case.steps)
        assert steps[0]["locator"] == new
        assert "healed_at" in steps[0]
        # 其他 step 不变
        assert steps[1]["locator"] == "#username"

    def test_apply_returns_false_when_no_match(self, db, ui_case):
        changed = locator_heal._apply_heal_to_case(db, ui_case.id, "#not-exist", "#new")
        assert changed is False

    def test_apply_returns_false_when_case_not_found(self, db):
        changed = locator_heal._apply_heal_to_case(db, 99999, "#old", "#new")
        assert changed is False

    def test_apply_handles_multiple_matching_steps(self, db, project):
        steps = [
            {"action": "click", "locator": "#btn"},
            {"action": "click", "locator": "#btn"},
        ]
        case = UiCase(project_id=project.id, case_name="multi", page_url="", steps=json.dumps(steps), create_time=datetime.now())
        db.add(case)
        db.commit()
        changed = locator_heal._apply_heal_to_case(db, case.id, "#btn", "#new-btn")
        assert changed is True
        db.refresh(case)
        result = json.loads(case.steps)
        assert all(s["locator"] == "#new-btn" for s in result)


# ── 5. _extract_interactive_elements ─────────────────────


class TestExtractElements:
    def test_returns_elements_when_evaluate_succeeds(self):
        elements = [{"tag": "button", "text": "x"}]
        page = FakePage(elements=elements)
        assert locator_heal._extract_interactive_elements(page) == elements

    def test_returns_empty_when_evaluate_raises(self):
        page = FakePage(elements=None)
        page.evaluate = MagicMock(side_effect=Exception("eval failed"))
        # 第一次抛异常 -> 重试 -> 第二次也抛异常 -> 返回 []
        assert locator_heal._extract_interactive_elements(page) == []
        assert page.evaluate.call_count == 2

    def test_retries_when_first_returns_empty(self):
        page = FakePage(elements=[])
        call_count = [0]

        def fake_eval(script):
            call_count[0] += 1
            return [{"tag": "button"}] if call_count[0] > 1 else []

        page.evaluate = fake_eval
        result = locator_heal._extract_interactive_elements(page)
        assert result == [{"tag": "button"}]
        assert call_count[0] == 2


# ── 6. auto_heal 完整流程 ────────────────────────────────


class TestAutoHeal:
    def test_skip_when_no_ai_config(self, db, ui_case, monkeypatch):
        # 不创建 AI 配置
        page = FakePage()
        result = locator_heal.auto_heal(page, ui_case.id, "#old", {"action": "click"}, db)
        assert result is None

    def test_skip_when_heal_disabled(self, db, ui_case, ai_config, monkeypatch):
        ai_config.heal_enabled = 0
        db.commit()
        page = FakePage()
        result = locator_heal.auto_heal(page, ui_case.id, "#old", {"action": "click"}, db)
        assert result is None

    def test_history_hit_skips_ai_call(self, db, ui_case, ai_config, monkeypatch):
        old, new = "#old-login-btn", "#new-btn"
        # 预置历史映射并标记成功
        locator_heal._record_heal_history(db, ui_case.project_id, old, new)
        locator_heal.update_heal_history_on_success(db, old, new)

        # mock AI 调用，确保不被调用
        def _fail_ai(*args, **kwargs):
            raise AssertionError("AI 不应被调用")

        monkeypatch.setattr(locator_heal, "call_local_model_json", _fail_ai)

        # mock 验证返回 True
        page = FakePage(locator_count=1, locator_visible=True, locator_tag="button")
        result = locator_heal.auto_heal(page, ui_case.id, old, {"action": "click", "name": "登录"}, db)
        assert result is not None
        assert result["locator"] == new
        assert result["confidence"] == 1.0
        assert result["reason"] == "历史学习命中"

        # 验证用例已更新
        db.refresh(ui_case)
        steps = json.loads(ui_case.steps)
        assert steps[0]["locator"] == new

        # 验证日志已记录
        log = db.query(LocatorHealLog).filter_by(case_id=ui_case.id).one()
        assert log.auto_applied == 1
        assert log.old_locator == old
        assert log.new_locator == new

    def test_ai_heal_success(self, db, ui_case, ai_config, monkeypatch):
        old = "#old-login-btn"
        new = "#new-btn"
        elements = [{"tag": "button", "text": "登录", "id": "new-btn", "locator_candidates": ["#new-btn"]}]

        def _fake_ai(config, prompt, timeout=30):
            return {"new_locator": new, "confidence": 0.95, "reason": "匹配登录按钮"}

        monkeypatch.setattr(locator_heal, "call_local_model_json", _fake_ai)

        page = FakePage(elements=elements, locator_count=1, locator_visible=True, locator_tag="button")
        result = locator_heal.auto_heal(page, ui_case.id, old, {"action": "click", "name": "登录"}, db)
        assert result is not None
        assert result["locator"] == new
        assert result["confidence"] == 0.95

        # 验证用例已更新
        db.refresh(ui_case)
        steps = json.loads(ui_case.steps)
        assert steps[0]["locator"] == new

        # 验证历史映射已记录（success_count=0，待成功后更新）
        history = db.query(LocatorHealHistory).filter_by(old_locator=old, new_locator=new).one()
        assert history.apply_count == 1
        assert history.success_count == 0

        # 验证日志已记录
        log = db.query(LocatorHealLog).filter_by(case_id=ui_case.id).one()
        assert log.auto_applied == 1
        assert "new_locator" in (log.ai_response or "")

    def test_ai_confidence_below_threshold_not_applied(self, db, ui_case, ai_config, monkeypatch):
        old = "#old-login-btn"
        ai_config.heal_confidence_threshold = 0.8
        db.commit()

        def _fake_ai(config, prompt, timeout=30):
            return {"new_locator": "#low-conf", "confidence": 0.5, "reason": "不确定"}

        monkeypatch.setattr(locator_heal, "call_local_model_json", _fake_ai)

        page = FakePage(elements=[{"tag": "button"}], locator_count=1, locator_visible=True, locator_tag="button")
        result = locator_heal.auto_heal(page, ui_case.id, old, {"action": "click"}, db)
        assert result is None

        # 用例未被更新
        db.refresh(ui_case)
        steps = json.loads(ui_case.steps)
        assert steps[0]["locator"] == old

        # 日志记录了低置信度
        log = db.query(LocatorHealLog).filter_by(case_id=ui_case.id).one()
        assert log.auto_applied == 0

    def test_ai_validation_failure_returns_none(self, db, ui_case, ai_config, monkeypatch):
        old = "#old-login-btn"

        def _fake_ai(config, prompt, timeout=30):
            return {"new_locator": "#bad", "confidence": 0.9}

        monkeypatch.setattr(locator_heal, "call_local_model_json", _fake_ai)

        # locator 匹配 0 个元素 -> 验证失败
        page = FakePage(elements=[{"tag": "button"}], locator_count=0, locator_visible=False)
        result = locator_heal.auto_heal(page, ui_case.id, old, {"action": "click"}, db)
        assert result is None

        # 日志记录了验证失败（new_locator 为空，因为最终失败）
        logs = db.query(LocatorHealLog).filter_by(case_id=ui_case.id).all()
        assert len(logs) >= 1

    def test_ai_returns_non_numeric_confidence_handled(self, db, ui_case, ai_config, monkeypatch):
        old = "#old-login-btn"

        def _fake_ai(config, prompt, timeout=30):
            return {"new_locator": "#new", "confidence": "高"}  # 非数字

        monkeypatch.setattr(locator_heal, "call_local_model_json", _fake_ai)

        page = FakePage(elements=[{"tag": "button"}], locator_count=1, locator_visible=True, locator_tag="button")
        # 不应抛异常，confidence 降级为 0.0，低于阈值 0.7
        result = locator_heal.auto_heal(page, ui_case.id, old, {"action": "click"}, db)
        assert result is None

    def test_ai_call_exception_falls_back_to_compact_retry(self, db, ui_case, ai_config, monkeypatch):
        old = "#old-login-btn"
        call_count = [0]

        def _fake_ai(config, prompt, timeout=30):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("AI 网络错误")
            return {"new_locator": "#new-btn", "confidence": 0.9}

        monkeypatch.setattr(locator_heal, "call_local_model_json", _fake_ai)

        page = FakePage(elements=[{"tag": "button"}], locator_count=1, locator_visible=True, locator_tag="button")
        result = locator_heal.auto_heal(page, ui_case.id, old, {"action": "click"}, db)
        assert result is not None
        assert result["locator"] == "#new-btn"
        assert call_count[0] == 2  # 第一次失败，第二次成功

    def test_ai_returns_empty_string_locator_skipped(self, db, ui_case, ai_config, monkeypatch):
        old = "#old-login-btn"

        def _fake_ai(config, prompt, timeout=30):
            return {"new_locator": "", "confidence": 0.9}

        monkeypatch.setattr(locator_heal, "call_local_model_json", _fake_ai)

        page = FakePage(elements=[{"tag": "button"}], locator_count=1, locator_visible=True, locator_tag="button")
        result = locator_heal.auto_heal(page, ui_case.id, old, {"action": "click"}, db)
        assert result is None

    def test_no_elements_returns_none(self, db, ui_case, ai_config, monkeypatch):
        page = FakePage(elements=[])
        # 让重试也返回空
        page.evaluate = MagicMock(return_value=[])
        result = locator_heal.auto_heal(page, ui_case.id, "#old", {"action": "click"}, db)
        assert result is None


# ── 7. /api/locator-heal-logs API ────────────────────────


class TestHealLogsApi:
    def _create_log(self, db, case_id, old="#old", new="#new", auto_applied=0, confirmed=0):
        log = LocatorHealLog(
            case_id=case_id,
            old_locator=old,
            new_locator=new,
            page_url="https://example.test",
            screenshot_path="",
            confirmed=confirmed,
            create_time=datetime.now(),
            step_action="click",
            ai_prompt="prompt",
            ai_response="response",
            auto_applied=auto_applied,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    def test_list_logs_pagination(self, client, admin_headers, db, ui_case):
        # 创建 25 条日志
        for i in range(25):
            self._create_log(db, ui_case.id, old=f"#old{i}", new=f"#new{i}")
        resp = client.get("/api/locator-heal-logs?page=1&page_size=10", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 25
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert len(data["items"]) == 10

    def test_list_logs_filter_by_case_id(self, client, admin_headers, db, ui_case, project):
        # 创建另一个用例
        other = UiCase(project_id=project.id, case_name="other", page_url="", steps="[]", create_time=datetime.now())
        db.add(other)
        db.commit()
        db.refresh(other)

        self._create_log(db, ui_case.id, old="#a", new="#b")
        self._create_log(db, other.id, old="#c", new="#d")

        resp = client.get(f"/api/locator-heal-logs?case_id={ui_case.id}", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert all(item["case_id"] == ui_case.id for item in data["items"])

    def test_list_logs_includes_ai_fields(self, client, admin_headers, db, ui_case):
        self._create_log(db, ui_case.id)
        resp = client.get("/api/locator-heal-logs", headers=admin_headers)
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "ai_prompt" in item
        assert "ai_response" in item
        assert "step_action" in item
        assert "auto_applied" in item

    def test_apply_log_updates_case_steps(self, client, admin_headers, db, ui_case):
        log = self._create_log(db, ui_case.id, old="#old-login-btn", new="#applied-btn", auto_applied=0)
        resp = client.post(f"/api/locator-heal-logs/{log.id}/apply", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "已应用"

        db.refresh(ui_case)
        steps = json.loads(ui_case.steps)
        assert steps[0]["locator"] == "#applied-btn"

        db.refresh(log)
        assert log.confirmed == 1
        assert log.auto_applied == 1

    def test_apply_log_no_matching_locator(self, client, admin_headers, db, ui_case):
        log = self._create_log(db, ui_case.id, old="#not-matching", new="#new")
        resp = client.post(f"/api/locator-heal-logs/{log.id}/apply", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "未找到匹配的 locator"

    def test_apply_log_empty_new_locator(self, client, admin_headers, db, ui_case):
        log = self._create_log(db, ui_case.id, old="#old", new="", auto_applied=0)
        resp = client.post(f"/api/locator-heal-logs/{log.id}/apply", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "无新 locator，无法应用"

    def test_confirm_log(self, client, admin_headers, db, ui_case):
        log = self._create_log(db, ui_case.id, confirmed=0)
        resp = client.put(f"/api/locator-heal-logs/{log.id}", json={"confirmed": 1}, headers=admin_headers)
        assert resp.status_code == 200
        db.refresh(log)
        assert log.confirmed == 1

    def test_list_logs_unauth_returns_401(self, client, db, ui_case):
        self._create_log(db, ui_case.id)
        resp = client.get("/api/locator-heal-logs")
        assert resp.status_code == 401

    def test_apply_log_requires_admin(self, client, db, ui_case):
        # 创建非管理员用户
        from app.security import hash_password
        from app.models import User
        user = User(username="viewer", password=hash_password("viewer123"), role="viewer", create_time=datetime.now())
        db.add(user)
        db.commit()
        resp = client.post("/api/auth/login", json={"username": "viewer", "password": "viewer123"})
        token = resp.json()["access_token"]
        log = self._create_log(db, ui_case.id)
        resp = client.post(f"/api/locator-heal-logs/{log.id}/apply", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


# ── 8. AI 配置自愈字段 ────────────────────────────────────


class TestAiConfigHealFields:
    def test_get_ai_config_returns_heal_fields(self, client, admin_headers, db):
        cfg = AiConfig(provider="openai_compatible", base_url="https://x", model="m", api_key="k", create_time=datetime.now(), heal_enabled=1, heal_confidence_threshold=0.85)
        db.add(cfg)
        db.commit()
        resp = client.get("/api/ai-config", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["heal_enabled"] == 1
        assert data["heal_confidence_threshold"] == 0.85

    def test_update_ai_config_heal_fields(self, client, admin_headers, db):
        cfg = AiConfig(provider="openai_compatible", base_url="https://x", model="m", api_key="k", create_time=datetime.now())
        db.add(cfg)
        db.commit()
        resp = client.put("/api/ai-config", json={"heal_enabled": 0, "heal_confidence_threshold": 0.9}, headers=admin_headers)
        assert resp.status_code == 200
        db.refresh(cfg)
        assert cfg.heal_enabled == 0
        assert cfg.heal_confidence_threshold == 0.9


# ── 9. 历史学习闭环集成测试 ──────────────────────────────


class TestHealHistoryLoop:
    def test_full_loop_record_success_lookup(self, db, project):
        """模拟完整闭环：记录 → 成功 → 查找命中。"""
        old, new = "#old-btn", "#new-btn"

        # 1. 自愈时记录
        locator_heal._record_heal_history(db, project.id, old, new)
        assert locator_heal._lookup_heal_history(db, project.id, old) is None  # success_count=0

        # 2. 用例执行成功，更新 success_count
        locator_heal.update_heal_history_on_success(db, old, new)

        # 3. 下次自愈时查找命中
        assert locator_heal._lookup_heal_history(db, project.id, old) == new

        # 4. 再次成功，success_count 应为 2
        locator_heal.update_heal_history_on_success(db, old, new)
        record = db.query(LocatorHealHistory).filter_by(old_locator=old, new_locator=new).one()
        assert record.success_count == 2
