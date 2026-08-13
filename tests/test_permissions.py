import atexit
import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace

TEST_DB = Path(__file__).resolve().parent / "test_platform.db"
# 确保测试退出后清理数据库文件（忽略文件被锁等错误）
def _cleanup_test_db():
    try:
        TEST_DB.unlink(missing_ok=True)
    except Exception:
        pass
atexit.register(_cleanup_test_db)
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "admin123"
os.environ["SECRET_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient

import app.executors as executors
import app.data_scripts as data_scripts
import app.main as main
import app.routers.data_scripts as data_script_router
from app.database import SessionLocal
from app.main import app


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)

ORDER_OPTION_LIST = [
    {"id": 78, "name": "详细检品", "name_translate": "詳細検品", "price": 4, "price_type": 1, "unit": "%", "checked": False},
    {"id": 79, "name": "针检", "name_translate": "通常検針サービス", "price": "0.80", "price_type": 0, "unit": "元", "checked": False},
    {"id": 80, "name": "X线针检", "name_translate": "X線検針サービス", "price": "1.00", "price_type": 0, "unit": "元", "checked": False},
    {"id": 81, "name": "X线针检往返运费", "name_translate": "X線検針会社までの国内往復送料", "price": "0.00", "price_type": 0, "unit": "元", "checked": False},
    {"id": 82, "name": "做布标", "name_translate": "織りネーム作成", "price": "0.40", "price_type": 0, "unit": "元", "checked": False},
    {"id": 83, "name": "取布标", "name_translate": "織りネーム外し", "price": 0.8, "price_type": 0, "unit": "元", "checked": False},
    {"id": 84, "name": "缝布标", "name_translate": "織りネーム縫い付け", "price": 1, "price_type": 0, "unit": "元", "checked": False},
    {"id": 85, "name": "做水洗标", "name_translate": "洗濯タグ作成", "price": "0.16", "price_type": 0, "unit": "元", "checked": False},
    {"id": 86, "name": "取水洗标", "name_translate": "洗濯タグ外し", "price": "0.80", "price_type": 0, "unit": "元", "checked": False},
    {"id": 87, "name": "缝水洗标", "name_translate": "洗濯タグ縫付け", "price": "1.00", "price_type": 0, "unit": "元", "checked": False},
    {"id": 88, "name": "做吊牌", "name_translate": "下げ札作成", "price": "0.12", "price_type": 0, "unit": "元", "checked": False},
    {"id": 89, "name": "挂吊牌", "name_translate": "下げ札取り付け", "price": 0.5, "price_type": 0, "unit": "元", "checked": False},
    {"id": 90, "name": "做贴纸", "name_translate": "LOGOシール作成", "price": "0.27", "price_type": 0, "unit": "元", "checked": False},
    {"id": 91, "name": "贴贴纸", "name_translate": "LOGOシール貼り付け", "price": "0.50", "price_type": 0, "unit": "元", "checked": False},
    {"id": 92, "name": "压缩包装操作费", "name_translate": "圧縮包装*圧縮袋別途費用", "price": "1.00", "price_type": 0, "unit": "元", "checked": False},
    {"id": 93, "name": "压缩袋费用", "name_translate": "圧縮袋", "price": "0.00", "price_type": 0, "unit": "元", "checked": False},
]


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_normal_user_cannot_create_project():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        response = client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"username": "normal_for_test", "password": "123456", "role": "normal"},
        )
        assert response.status_code in (200, 400)

        normal_token = login(client, "normal_for_test", "123456")
        blocked = client.post(
            "/api/projects",
            headers={"Authorization": f"Bearer {normal_token}"},
            json={"name": "blocked", "desc": ""},
        )
        assert blocked.status_code == 403


def test_legacy_plaintext_password_is_migrated_and_login_keeps_working():
    username = "legacy_plaintext_user"
    password = "legacy-pass-123"
    db = SessionLocal()
    try:
        db.query(main.User).filter(main.User.username == username).delete(synchronize_session=False)
        db.add(main.User(username=username, password=password, role="normal", create_time=main.datetime.now()))
        db.commit()
        main.migrate_legacy_plaintext_passwords(db)
        user = db.query(main.User).filter(main.User.username == username).first()
        assert user is not None
        assert user.password != password
        assert main.verify_password(password, user.password)
    finally:
        db.close()

    with TestClient(app) as client:
        token = login(client, username, password)
        assert token


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = __import__("json").dumps(payload, ensure_ascii=False)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


def create_project_env(client: TestClient, headers: dict, name: str = "data-script-customer-project"):
    project = client.post("/api/projects", headers=headers, json={"name": name, "desc": ""}).json()
    env = client.post(
        "/api/envs",
        headers=headers,
        json={
            "project_id": project["id"],
            "env_name": f"{name}-env",
            "base_url": "https://example.test",
            "global_headers": {},
            "global_vars": {},
            "timeout": 30,
        },
    ).json()
    return project, env


def test_action_template_crud_and_test_run(monkeypatch):
    def fake_execute_ui_case(ui_case, variables):
        steps = json.loads(ui_case.steps)
        assert steps[0]["action"] == "click"
        return True, "template-ok", "", "template-report"

    monkeypatch.setattr(executors, "execute_ui_case", fake_execute_ui_case)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        project = client.post("/api/projects", headers=headers, json={"name": "template-project", "desc": ""}).json()

        missing_project = client.post(
            "/api/action-templates",
            headers=headers,
            json={"project_id": 999999, "name": "missing-project-template", "steps": []},
        )
        created = client.post(
            "/api/action-templates",
            headers=headers,
            json={
                "project_id": project["id"],
                "name": "login-template",
                "description": "login action",
                "trigger_keywords": ["login"],
                "steps": [{"action": "click", "locator": "#submit"}],
                "variables": {"account": "alice"},
                "locator_fallbacks": {"#submit": ["button[type=submit]"]},
            },
        )

        assert missing_project.status_code == 400
        assert created.status_code == 200
        template = created.json()
        assert template["trigger_keywords"] == ["login"]
        assert template["steps"][0]["locator"] == "#submit"

        updated = client.put(
            f"/api/action-templates/{template['id']}",
            headers=headers,
            json={"name": "login-template-v2", "trigger_keywords": ["sign in"], "steps": [{"action": "click", "locator": "#go"}]},
        )
        run_result = client.get(f"/api/action-templates/{template['id']}/test-run", headers=headers)

    assert updated.status_code == 200
    assert updated.json()["name"] == "login-template-v2"
    assert updated.json()["trigger_keywords"] == ["sign in"]
    assert run_result.status_code == 200
    assert run_result.json()["passed"] is True


def test_api_case_rejects_cross_project_env_on_create_and_update():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        project_1, env_1 = create_project_env(client, headers, "api-case-project-1")
        project_2, env_2 = create_project_env(client, headers, "api-case-project-2")

        cross_create = client.post(
            "/api/api-cases",
            headers=headers,
            json={
                "project_id": project_1["id"],
                "env_id": env_2["id"],
                "case_name": "cross-project-env",
                "method": "GET",
                "url": "/health",
                "headers": {},
                "params": {},
                "body": "",
                "assert_rule": {},
                "status": "active",
            },
        )
        valid = client.post(
            "/api/api-cases",
            headers=headers,
            json={
                "project_id": project_1["id"],
                "env_id": env_1["id"],
                "case_name": "same-project-env",
                "method": "GET",
                "url": "/health",
                "headers": {},
                "params": {},
                "body": "",
                "assert_rule": {},
                "status": "active",
            },
        )
        cross_env_update = client.put(
            f"/api/api-cases/{valid.json()['id']}",
            headers=headers,
            json={"env_id": env_2["id"]},
        )
        cross_project_update = client.put(
            f"/api/api-cases/{valid.json()['id']}",
            headers=headers,
            json={"project_id": project_2["id"]},
        )

    assert cross_create.status_code == 400
    assert valid.status_code == 200
    assert cross_env_update.status_code == 400
    assert cross_project_update.status_code == 400


def test_api_case_list_supports_optional_pagination_without_breaking_legacy_response():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        project, env = create_project_env(client, headers, "api-case-pagination")
        created_ids = []
        for index in range(3):
            response = client.post(
                "/api/api-cases",
                headers=headers,
                json={
                    "project_id": project["id"],
                    "env_id": env["id"],
                    "case_name": f"pagination-{index}",
                    "method": "GET",
                    "url": f"/pagination/{index}",
                    "headers": {},
                    "params": {},
                    "body": "",
                    "assert_rule": {},
                    "status": "active",
                },
            )
            assert response.status_code == 200
            created_ids.append(response.json()["id"])

        legacy = client.get(
            "/api/api-cases",
            headers=headers,
            params={"project_id": project["id"]},
        )
        paged = client.get(
            "/api/api-cases",
            headers=headers,
            params={"project_id": project["id"], "page": 2, "page_size": 2},
        )

    assert legacy.status_code == 200
    assert [item["id"] for item in legacy.json()] == list(reversed(created_ids))
    assert paged.status_code == 200
    assert paged.json() == {
        "total": 3,
        "page": 2,
        "page_size": 2,
        "items": [{**legacy.json()[-1]}],
    }


def test_api_case_library_vue_frontend_uses_pagination_and_chinese_disabled_status():
    view = Path("frontend/src/views/ApiCasesView.vue").read_text(encoding="utf-8")
    api_module = Path("frontend/src/api/modules/apiCases.js").read_text(encoding="utf-8")

    assert "const pageSize = 20" in view
    assert "rows.value = resp.items || []" in view
    assert "disabled: '停用'" in view
    assert "qs.set('page_size', params.pageSize)" in api_module


def test_vue_execution_actions_open_prefilled_dialogs_before_executing():
    api_cases_view = Path("frontend/src/views/ApiCasesView.vue").read_text(encoding="utf-8")
    records_view = Path("frontend/src/views/RecordsView.vue").read_text(encoding="utf-8")
    records_api = Path("frontend/src/api/modules/records.js").read_text(encoding="utf-8")

    assert ':visible="runVisible"' in api_cases_view
    assert "runValues.value =" in api_cases_view
    assert "async function submitRun(data)" in api_cases_view
    assert "apiCasesApi.executeApiCase(runningItem.value.id, payload)" in api_cases_view
    assert ':visible="rerunVisible"' in records_view
    assert "rerunValues.value =" in records_view
    assert "JSON.stringify(context.variables || {}, null, 2)" in records_view
    assert "recordsApi.confirmReexecute(rerunningItem.value.id, payload)" in records_view
    assert "export function confirmReexecute(id, overrides = {})" in records_api


def test_vue_protected_routes_render_inside_app_shell():
    app_vue = Path("frontend/src/App.vue").read_text(encoding="utf-8")

    assert "import AppShell from './components/AppShell.vue'" in app_vue
    assert "const route = useRoute()" in app_vue
    assert '<AppShell v-if="routeReady && !route.meta.public" />' in app_vue
    assert '<router-view v-else-if="routeReady" />' in app_vue
    assert "const routeReady = computed(() => route.matched.length > 0)" in app_vue


def test_env_delete_rejects_referenced_api_cases():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        project, env = create_project_env(client, headers, "env-delete-project")
        created = client.post(
            "/api/api-cases",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_id": env["id"],
                "case_name": "env-delete-guard",
                "method": "GET",
                "url": "/health",
                "headers": {},
                "params": {},
                "body": "",
                "assert_rule": {},
                "status": "active",
            },
        )
        deleted = client.delete(f"/api/envs/{env['id']}", headers=headers)
        envs = client.get("/api/envs", headers=headers, params={"project_id": project["id"]})

    assert created.status_code == 200
    assert deleted.status_code == 400
    assert any(item["id"] == env["id"] for item in envs.json())


def test_dashboard_counts_project_scoped_records_without_case_ids():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        project = client.post("/api/projects", headers=headers, json={"name": "dashboard-record-project", "desc": ""}).json()

        db = SessionLocal()
        try:
            record = main.TestRecord(
                case_type="api",
                case_id=0,
                project_id=project["id"],
                result="passed",
                log="{}",
                screenshot="",
                report_path="",
                execute_time=main.datetime.now(),
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            record_id = record.id
        finally:
            db.close()

        records = client.get("/api/test-records", headers=headers, params={"project_id": project["id"], "case_type": "api"})
        dashboard = client.get("/api/dashboard", headers=headers, params={"project_id": project["id"]})

    assert records.status_code == 200
    assert records.json()["total"] == 1
    assert dashboard.status_code == 200
    assert dashboard.json()["record_count"] == 1
    assert dashboard.json()["latest_records"][0]["id"] == record_id


def test_core_config_rejects_invalid_inputs():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}

        blank_project = client.post("/api/projects", headers=headers, json={"name": "   ", "desc": ""})
        project = client.post("/api/projects", headers=headers, json={"name": "validation-project", "desc": ""}).json()
        blank_env = client.post(
            "/api/envs",
            headers=headers,
            json={"project_id": project["id"], "env_name": "", "base_url": "", "global_headers": {}, "global_vars": {}, "timeout": 30},
        )
        negative_timeout = client.post(
            "/api/envs",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_name": "bad-timeout-env",
                "base_url": "https://example.test",
                "global_headers": {},
                "global_vars": {},
                "timeout": -1,
            },
        )
        env = client.post(
            "/api/envs",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_name": "validation-env",
                "base_url": "https://example.test",
                "global_headers": {},
                "global_vars": {},
                "timeout": 30,
            },
        ).json()
        invalid_method = client.post(
            "/api/api-cases",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_id": env["id"],
                "case_name": "invalid-method",
                "method": "BREW",
                "url": "/health",
                "headers": {},
                "params": {},
                "body": "",
                "assert_rule": {},
                "status": "active",
            },
        )

    assert blank_project.status_code == 400
    assert blank_env.status_code == 400
    assert negative_timeout.status_code == 400
    assert invalid_method.status_code == 400


def test_batch_api_execution_passes_extracted_variables(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, "kwargs": kwargs})
        if method == "POST":
            assert kwargs["json"]["name"] == "qa_alice"
            return FakeResponse(201, {"data": {"id": "U123"}})
        assert url.endswith("/users/U123")
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr(executors.requests, "request", fake_request)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}

        project = client.post("/api/projects", headers=headers, json={"name": "造数项目", "desc": ""}).json()
        env = client.post(
            "/api/envs",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_name": "测试环境",
                "base_url": "https://example.test",
                "global_headers": {},
                "global_vars": {"prefix": "qa"},
                "timeout": 30,
            },
        ).json()
        case_1 = client.post(
            "/api/api-cases",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_id": env["id"],
                "case_name": "创建用户",
                "method": "POST",
                "url": "/users",
                "headers": {},
                "params": {},
                "body": {"name": "{{prefix}}_{{username}}"},
                "assert_rule": {"status_code": 201, "extract": {"user_id": "json.data.id"}},
                "status": "active",
            },
        ).json()
        case_2 = client.post(
            "/api/api-cases",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_id": env["id"],
                "case_name": "查询用户",
                "method": "GET",
                "url": "/users/{{user_id}}",
                "headers": {},
                "params": {},
                "body": "",
                "assert_rule": {"status_code": 200},
                "status": "active",
            },
        ).json()

        result = client.post(
            "/api/api-cases/batch-execute",
            headers=headers,
            json={"case_ids": [case_1["id"], case_2["id"]], "variables": {"username": "alice"}},
        )

    assert result.status_code == 200
    assert result.json()["variables"]["user_id"] == "U123"
    assert [call["method"] for call in calls] == ["POST", "GET"]


def test_purchase_to_shelf_with_order_sn_runs_target_order_not_chain(monkeypatch):
    calls = []

    def fake_direct(env, variables):
        calls.append(("direct", dict(variables)))
        return True, '{"summary": {"mode": "direct"}}', "", {"mode": "direct", "order_sn": variables.get("order_sn")}

    def fake_chain(env, variables):
        calls.append(("chain", dict(variables)))
        return True, '{"summary": {"mode": "chain"}}', "", {"mode": "chain"}

    monkeypatch.setattr(main, "run_purchase_to_shelf_script", fake_direct)
    monkeypatch.setattr(main, "run_purchase_to_shelf_chain", fake_chain)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        project = client.post("/api/projects", headers=headers, json={"name": "purchase-target-project", "desc": ""}).json()
        env = client.post(
            "/api/envs",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_name": "purchase-target-env",
                "base_url": "https://example.test",
                "global_headers": {},
                "global_vars": {},
                "timeout": 30,
            },
        ).json()
        response = client.post(
            "/api/data-scripts/purchase-to-shelf",
            headers=headers,
            json={
                "env_id": env["id"],
                "variables": {
                    "order_sn": "ORDER-001",
                    "link_quote_balance_before_shelf": True,
                    "auto_quote_and_pay": True,
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["summary"]["mode"] == "direct"
    assert [item[0] for item in calls] == ["direct"]


def test_data_script_rejects_env_from_other_project(monkeypatch):
    calls = []

    def fake_shopping_cart(env, variables):
        calls.append((env.id, variables))
        return True, "{}", "", {}

    monkeypatch.setattr(main, "run_shopping_cart_script", fake_shopping_cart)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        project, _ = create_project_env(client, headers, "data-script-project-a")
        _, other_env = create_project_env(client, headers, "data-script-project-b")
        response = client.post(
            "/api/data-scripts/shopping-cart",
            headers=headers,
            json={"project_id": project["id"], "env_id": other_env["id"], "variables": {}},
        )

    assert response.status_code == 400
    assert calls == []


def test_data_script_record_saves_project_and_filters_records(monkeypatch):
    def fake_balance_payment(env, variables):
        return True, "balance-payment-log", "", {"payment_type": "balance"}

    monkeypatch.setattr(main, "run_balance_payment_script", fake_balance_payment)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        project, env = create_project_env(client, headers, "data-script-record-project")
        other_project, _ = create_project_env(client, headers, "data-script-record-other")
        response = client.post(
            "/api/data-scripts/balance-payment",
            headers=headers,
            json={"project_id": project["id"], "env_id": env["id"], "variables": {}},
        )
        records = client.get(
            "/api/test-records",
            headers=headers,
            params={"project_id": project["id"], "case_type": "api"},
        )
        other_records = client.get(
            "/api/test-records",
            headers=headers,
            params={"project_id": other_project["id"], "case_type": "api"},
        )

    assert response.status_code == 200
    record = response.json()
    assert record["project_id"] == project["id"]
    records_data = records.json()["items"]
    other_records_data = other_records.json()["items"]
    assert any(item["id"] == record["id"] and item["project_id"] == project["id"] for item in records_data)
    assert all(item["id"] != record["id"] for item in other_records_data)


def test_data_script_builtin_cases_bind_to_japan_project():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        assert admin_token

    db = SessionLocal()
    try:
        project = main.find_data_script_project(db)
        assert project is not None
        assert project.name == main.DATA_SCRIPT_PROJECT_NAME
        for item in main.DATA_SCRIPT_API_CASES:
            case = main.find_data_script_api_case(db, item, project.id)
            assert case is not None
            assert case.project_id == project.id
            env = db.get(main.Env, case.env_id)
            assert env is not None
            assert env.project_id == project.id
    finally:
        db.close()


def test_data_script_customer_id_derives_frontend_account(monkeypatch):
    calls = []

    def fake_shopping_cart(env, variables):
        calls.append(dict(variables))
        return True, "{}", "", {"account": variables.get("account")}

    monkeypatch.setattr(main, "run_shopping_cart_script", fake_shopping_cart)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        _, env = create_project_env(client, headers, "customer-login")
        response = client.post(
            "/api/data-scripts/shopping-cart",
            headers=headers,
            json={
                "env_id": env["id"],
                "variables": {
                    "customer_id": "50",
                    "account": "old-account",
                    "password": "old-password",
                    "backend_password": "raku@123456``",
                    "client_tool": "1",
                },
            },
        )

    assert response.status_code == 200
    assert calls[0]["customer_id"] == "50"
    assert calls[0]["customer_ids"] == ["50"]
    assert calls[0]["account"] == "userID/50In"
    assert calls[0]["password"] == "xiaolin666@@"
    assert calls[0]["backend_password"] == "xiaolin666@@"


def test_data_script_customer_ids_parse_multiple_and_keep_backend_password():
    variables = main.apply_frontend_customer_login_variables(
        {
            "customer_ids": "50, 300001\n88",
            "account": "old-account",
            "password": "old-password",
            "backend_password": "keep-backend-password",
        }
    )

    assert variables["customer_ids"] == ["50", "300001", "88"]
    assert variables["customer_id"] == "50"
    assert variables["account"] == "userID/50In"
    assert variables["password"] == "xiaolin666@@"
    assert variables["backend_password"] == "keep-backend-password"


def test_data_script_customer_id_rejects_non_numeric(monkeypatch):
    def fake_shopping_cart(env, variables):
        raise AssertionError("script should not execute for invalid customer id")

    monkeypatch.setattr(main, "run_shopping_cart_script", fake_shopping_cart)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        _, env = create_project_env(client, headers, "invalid-customer-login")
        response = client.post(
            "/api/data-scripts/shopping-cart",
            headers=headers,
            json={"env_id": env["id"], "variables": {"customer_ids": "50,abc"}},
        )

    assert response.status_code == 400
    assert "ID" in response.json()["detail"]


def test_shopping_cart_fails_when_add_api_success_but_cart_verify_missing(monkeypatch):
    calls = []
    item = SimpleNamespace(
        to_dict=lambda: {
            "goods_id": "goods-1",
            "goods_title": "item",
            "price": "10",
            "num": 1,
            "pic": "",
            "detail": "[]",
            "sku_id": "sku-1",
            "spec_id": "spec-1",
            "shop_id": "shop-1",
            "shop_name": "shop",
            "from_platform": "1688",
            "price_ranges": "[]",
            "trace": "trace-1",
        }
    )

    class FakeRakumartClient:
        def __init__(self, base_url, timeout):
            self.session = SimpleNamespace(headers={})

        def login(self, account, password, client_tool):
            return "token"

        def post_form(self, path, fields):
            calls.append((path, dict(fields)))
            if "userLogin" in path:
                return {"success": True, "code": 0, "data": {"userToken": "token"}}
            if "goodsToCart" in path:
                return {"success": True, "code": 0}
            if "goodsCartList" in path:
                return {"success": True, "code": 0, "data": {"goods": []}}
            raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(data_scripts.bulk_cart, "RakumartClient", FakeRakumartClient)
    monkeypatch.setattr(data_scripts.bulk_cart, "collect_items", lambda **kwargs: {"shop-1": [item]})
    monkeypatch.setattr(data_scripts.bulk_cart, "flatten_ready_shops", lambda shops, target_shops, per_shop: [item])
    monkeypatch.setattr(data_scripts.bulk_cart, "chunks", lambda items, batch_size: [items])

    passed, log_text, _report_path, summary = data_scripts.run_shopping_cart_script(
        SimpleNamespace(base_url="https://example.test", timeout=30),
        {"account": "alice", "password": "secret", "target_shops": 1, "per_shop": 1, "sleep": 0},
    )

    log = json.loads(log_text)
    assert passed is False
    assert summary["api_added_total"] == 1
    assert summary["added_total"] == 0
    assert summary["verification_failed_batches"] == [1]
    assert log["batches"][0]["verification"]["matched_count"] == 0
    assert any("goodsCartList" in path for path, _fields in calls)


def test_shopping_cart_passes_when_cart_verify_finds_item(monkeypatch):
    item_data = {
        "goods_id": "goods-1",
        "goods_title": "item",
        "price": "10",
        "num": 1,
        "pic": "",
        "detail": "[]",
        "sku_id": "sku-1",
        "spec_id": "spec-1",
        "shop_id": "shop-1",
        "shop_name": "shop",
        "from_platform": "1688",
        "price_ranges": "[]",
        "trace": "trace-1",
    }
    item = SimpleNamespace(to_dict=lambda: dict(item_data))

    class FakeRakumartClient:
        def __init__(self, base_url, timeout):
            self.session = SimpleNamespace(headers={})

        def post_form(self, path, fields):
            if "userLogin" in path:
                return {"success": True, "code": 0, "data": {"userToken": "token"}}
            if "goodsToCart" in path:
                return {"success": True, "code": 0}
            if "goodsCartList" in path:
                return {"success": True, "code": 0, "data": {"goods": [{**item_data, "id": "cart-1"}]}}
            raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(data_scripts.bulk_cart, "RakumartClient", FakeRakumartClient)
    monkeypatch.setattr(data_scripts.bulk_cart, "collect_items", lambda **kwargs: {"shop-1": [item]})
    monkeypatch.setattr(data_scripts.bulk_cart, "flatten_ready_shops", lambda shops, target_shops, per_shop: [item])
    monkeypatch.setattr(data_scripts.bulk_cart, "chunks", lambda items, batch_size: [items])

    passed, _log_text, _report_path, summary = data_scripts.run_shopping_cart_script(
        SimpleNamespace(base_url="https://example.test", timeout=30),
        {"account": "alice", "password": "secret", "target_shops": 1, "per_shop": 1, "sleep": 0},
    )

    assert passed is True
    assert summary["api_added_total"] == 1
    assert summary["added_total"] == 1
    assert summary["verification_failed_batches"] == []


def test_shopping_cart_final_verify_checks_cart_once(monkeypatch):
    item_data = {
        "goods_id": "goods-1",
        "goods_title": "item",
        "price": "10",
        "num": 1,
        "pic": "",
        "detail": "[]",
        "sku_id": "sku-1",
        "spec_id": "spec-1",
        "shop_id": "shop-1",
        "shop_name": "shop",
        "from_platform": "1688",
        "price_ranges": "[]",
        "trace": "trace-1",
    }
    items = [
        SimpleNamespace(to_dict=lambda data={**item_data, "id": "cart-1", "sku_id": "sku-1", "spec_id": "spec-1"}: dict(data)),
        SimpleNamespace(to_dict=lambda data={**item_data, "id": "cart-2", "goods_id": "goods-2", "sku_id": "sku-2", "spec_id": "spec-2"}: dict(data)),
    ]
    calls = []

    class FakeRakumartClient:
        def __init__(self, base_url, timeout):
            self.session = SimpleNamespace(headers={})

        def post_form(self, path, fields):
            calls.append((path, dict(fields)))
            if "userLogin" in path:
                return {"success": True, "code": 0, "data": {"userToken": "token"}}
            if "goodsToCart" in path:
                return {"success": True, "code": 0}
            if "goodsCartList" in path:
                return {"success": True, "code": 0, "data": {"goods": [item.to_dict() for item in items]}}
            raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(data_scripts.bulk_cart, "RakumartClient", FakeRakumartClient)
    monkeypatch.setattr(data_scripts.bulk_cart, "collect_items", lambda **kwargs: {"shop-1": items})
    monkeypatch.setattr(data_scripts.bulk_cart, "flatten_ready_shops", lambda shops, target_shops, per_shop: items)
    monkeypatch.setattr(data_scripts.bulk_cart, "chunks", lambda items_arg, batch_size: [[items_arg[0]], [items_arg[1]]])

    passed, log_text, _report_path, summary = data_scripts.run_shopping_cart_script(
        SimpleNamespace(base_url="https://example.test", timeout=30),
        {
            "account": "alice",
            "password": "secret",
            "target_shops": 1,
            "per_shop": 2,
            "sleep": 0,
            "cart_verify_mode": "final",
        },
    )

    log = json.loads(log_text)
    assert passed is True
    assert summary["cart_verify_mode"] == "final"
    assert summary["added_total"] == 2
    assert log["final_verification"]["matched_count"] == 2
    assert len([path for path, _fields in calls if "goodsCartList" in path]) == 1


def test_cart_edit_parallel_falls_back_to_serial(monkeypatch):
    selected_items = [
        {"id": "cart-1", "goods_id": "goods-1", "num": 1, "price": "10", "detail": "[]"},
        {"id": "cart-2", "goods_id": "goods-2", "num": 2, "price": "10", "detail": "[]"},
        {"id": "cart-3", "goods_id": "goods-3", "num": 10, "price": "10", "detail": "[]"},
    ]
    worker_calls = []
    serial_calls = []

    class SerialClient:
        def post_form(self, path, fields):
            serial_calls.append((path, dict(fields)))
            return {"success": True, "code": 0}

    class WorkerClient:
        def post_form(self, path, fields):
            worker_calls.append((path, dict(fields)))
            return {"success": False, "code": 500, "msg": "busy"}

    monkeypatch.setattr(data_scripts, "_authed_client_with_token", lambda *args, **kwargs: WorkerClient())

    edit_logs, failed = data_scripts._edit_cart_items_for_order(
        SerialClient(),
        "https://example.test",
        30,
        {"cart_edit_workers": 2},
        selected_items,
        10,
        "token",
    )

    assert failed == []
    assert selected_items[0]["num"] == 10
    assert selected_items[1]["num"] == 10
    assert selected_items[2]["num"] == 10
    assert len(worker_calls) == 2
    assert len(serial_calls) == 2
    assert edit_logs[0]["retried_serial"] is True
    assert edit_logs[1]["retried_serial"] is True
    assert edit_logs[2]["skipped"] is True


def test_order_option_counts_ignore_empty_values():
    counts = data_scripts._normalize_order_option_counts(
        {
            "1": "2",
            "empty": "",
            "zero": 0,
            "negative": -1,
            "bad": "abc",
            "float_text": "3.5",
            None: 4,
        }
    )

    assert counts == {"1": 2}


def test_inspect_order_options_returns_public_catalog(monkeypatch):
    from collections import OrderedDict

    class FakeRuntime:
        def client(self, env, variables, log=None):
            return object(), "https://example.test", 25, "token", True

    catalog = OrderedDict({
        "79": {
            "key": "79",
            "id": 79,
            "name": "詳細検品",
            "label": "詳細検品",
            "name_translate": "详细检查",
            "price": "2",
            "price_type": "0",
            "unit": "件",
            "template": {"name": "詳細検品"},
        }
    })
    monkeypatch.setattr(data_scripts, "_runtime_from_variables", lambda variables: FakeRuntime())
    monkeypatch.setattr(
        data_scripts,
        "_fetch_order_option_catalog",
        lambda client, variables: (catalog, {"success": True, "code": 0}, "/client/order.optionList"),
    )

    result = data_scripts.inspect_order_options(full_flow_env(), {})

    assert result["count"] == 1
    assert result["path"] == "/client/order.optionList"
    assert result["options"] == [{
        "key": "79",
        "id": 79,
        "name": "詳細検品",
        "label": "詳細検品",
        "name_translate": "详细检查",
        "price": "2",
        "price_type": "0",
        "unit": "件",
    }]


def test_order_options_apply_to_order_detail_fields():
    items = [
        {
            "id": "cart-1",
            "goods_id": "goods-1",
            "goods_title": "测试商品",
            "price": "10",
            "num": 1,
            "pic": "",
            "detail": [],
            "sku_id": "",
            "spec_id": "",
            "shop_id": "",
            "shop_name": "",
            "from_platform": "1688",
        }
    ]

    catalog = data_scripts._order_option_catalog_from_options(ORDER_OPTION_LIST)
    summary = data_scripts._apply_order_options_to_items(items, {"order_option_counts": {"79": 3}}, catalog)
    fields = data_scripts._order_fields(items, "send", "", 10, "1", "")
    options = json.loads(fields["order_detail[0][option]"])

    assert summary["applied_detail_count"] == 1
    assert summary["selected_options"][0]["label"] == "针检"
    assert options[0]["name"] == "针检"
    assert options[0]["price"] == "0.80"
    assert options[0]["unit"] == "元"
    assert options[0]["checked"] is True
    assert options[0]["num"] == "3"


def test_order_fields_omit_options_when_no_count_selected():
    items = [
        {
            "id": "cart-1",
            "goods_id": "goods-1",
            "goods_title": "测试商品",
            "price": "10",
            "detail": [],
            "option": [{"id": 1, "name": "FBA贴标", "checked": False}],
        }
    ]

    summary = data_scripts._apply_order_options_to_items(items, {"order_option_counts": {}})
    fields = data_scripts._order_fields(items, "send", "", 10, "1", "")

    assert summary["applied_detail_count"] == 0
    assert "order_detail[0][option]" not in fields


def test_warehouse_select_items_dedupes_by_sku():
    rows = [
        {"id": "detail-1", "sku_id": "sku-a", "send_num": 5},
        {"id": "detail-2", "sku_id": "sku-a", "send_num": 5},
        {"id": "detail-3", "sku_id": "sku-b", "send_num": 5},
    ]

    selected = data_scripts._select_warehouse_items(rows, {}, 2)

    assert [data_scripts._warehouse_item_id(item) for item in selected] == ["detail-1", "detail-3"]
    assert [data_scripts._warehouse_sku_id(item) for item in selected] == ["sku-a", "sku-b"]


def test_porder_create_fields_support_multiple_details():
    fields = data_scripts._porder_create_fields_for_items(
        [
            {"order_detail_id": "detail-1", "send_num": 2},
            {"order_detail_id": "detail-2", "send_num": 3},
        ],
        "PORDER-1",
        {"porder_logistics_id": "14"},
    )

    assert fields["porder_detail[0][order_detail_id]"] == "detail-1"
    assert fields["porder_detail[0][send_num]"] == 2
    assert fields["porder_detail[1][order_detail_id]"] == "detail-2"
    assert fields["porder_detail[1][send_num]"] == 3
    assert "porder_detail[2][order_detail_id]" not in fields


def test_warehouse_delivery_uses_available_distinct_skus_when_short(monkeypatch):
    calls = []

    rows = [
        {"id": "detail-1", "sku_id": "sku-a", "goods_id": "goods-a", "send_num": 5},
        {"id": "detail-2", "sku_id": "sku-a", "goods_id": "goods-a", "send_num": 5},
        {"id": "detail-3", "sku_id": "sku-b", "goods_id": "goods-b", "send_num": 1},
    ]

    class FakeRakumartClient:
        def __init__(self, base_url, timeout):
            self.session = SimpleNamespace(headers={})

        def post_form(self, path, fields):
            calls.append((path, dict(fields)))
            if "userLogin" in path:
                return {"success": True, "code": 0, "data": {"userToken": "token"}}
            if "stockAutoList" in path:
                return {"success": True, "code": 0, "data": {"list": rows}}
            if "porderCreate" in path:
                return {"success": True, "code": 0, "data": {"porder_sn": "PORDER-1"}}
            raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(data_scripts.bulk_cart, "RakumartClient", FakeRakumartClient)

    passed, _log_text, _report_path, summary = data_scripts.run_warehouse_delivery_script(
        SimpleNamespace(base_url="https://example.test", timeout=30),
        {"account": "alice", "password": "secret", "warehouse_sku_count": 5, "send_num": 2, "run_backend_delivery_flow": False},
    )

    create_fields = next(fields for path, fields in calls if "porderCreate" in path)
    assert passed is True
    assert create_fields["porder_detail[0][order_detail_id]"] == "detail-1"
    assert create_fields["porder_detail[0][send_num]"] == 2
    assert create_fields["porder_detail[1][order_detail_id]"] == "detail-3"
    assert create_fields["porder_detail[1][send_num]"] == 1
    assert "porder_detail[2][order_detail_id]" not in create_fields
    assert summary["warehouse_sku_count"] == 5
    assert summary["actual_warehouse_sku_count"] == 2
    assert summary["total_send_num"] == 3
    assert summary["selected_sku_ids"] == ["sku-a", "sku-b"]
    assert "warning" in summary


def test_warehouse_select_items_prefers_current_order_then_history():
    rows = [
        {"id": "history-1", "sku_id": "sku-history-1", "send_num": 5},
        {"id": "current-1", "order_sn": "ORDER-1", "sku_id": "sku-current-1", "send_num": 5},
        {"id": "current-2", "order_sn": "ORDER-1", "sku_id": "sku-current-2", "send_num": 5},
        {"id": "history-2", "sku_id": "sku-current-2", "send_num": 5},
        {"id": "history-3", "sku_id": "sku-history-3", "send_num": 5},
    ]

    selected = data_scripts._select_warehouse_items(
        rows,
        {"warehouse_fill_scope": "current_order_then_history", "order_sn": "ORDER-1", "order_detail_ids": ["current-1", "current-2"]},
        3,
    )

    assert [data_scripts._warehouse_item_id(item) for item in selected] == ["current-1", "current-2", "history-1"]
    assert [item["_warehouse_source"] for item in selected] == ["current_order", "current_order", "history"]


def test_warehouse_delivery_current_order_then_history_fill(monkeypatch):
    calls = []
    rows = [
        {"id": "history-1", "sku_id": "sku-history-1", "send_num": 5},
        {"id": "current-1", "order_sn": "ORDER-1", "sku_id": "sku-current-1", "send_num": 5},
        {"id": "history-2", "sku_id": "sku-history-2", "send_num": 1},
    ]

    class FakeRakumartClient:
        def __init__(self, base_url, timeout):
            self.session = SimpleNamespace(headers={})

        def login(self, account, password, client_tool):
            return "token"

        def post_form(self, path, fields):
            calls.append((path, dict(fields)))
            if "userLogin" in path:
                return {"success": True, "code": 0, "data": {"userToken": "token"}}
            if "stockAutoList" in path:
                return {"success": True, "code": 0, "data": {"list": rows}}
            if "porderCreate" in path:
                return {"success": True, "code": 0, "data": {"porder_sn": "PORDER-1"}}
            raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(data_scripts.bulk_cart, "RakumartClient", FakeRakumartClient)

    passed, _log_text, _report_path, summary = data_scripts.run_warehouse_delivery_script(
        SimpleNamespace(base_url="https://example.test", timeout=30),
        {
            "account": "alice",
            "password": "secret",
            "warehouse_sku_count": 3,
            "send_num": 2,
            "run_backend_delivery_flow": False,
            "warehouse_fill_scope": "current_order_then_history",
            "require_warehouse_sku_count": True,
            "order_sn": "ORDER-1",
            "order_detail_ids": ["current-1"],
        },
    )

    create_fields = next(fields for path, fields in calls if "porderCreate" in path)
    assert passed is True
    assert create_fields["porder_detail[0][order_detail_id]"] == "current-1"
    assert create_fields["porder_detail[1][order_detail_id]"] == "history-1"
    assert create_fields["porder_detail[2][order_detail_id]"] == "history-2"
    assert summary["actual_warehouse_sku_count"] == 3
    assert summary["current_order_count"] == 1
    assert summary["history_fill_count"] == 2


def test_warehouse_delivery_uses_requested_ids_when_list_empty(monkeypatch):
    calls = []

    class FakeRakumartClient:
        def __init__(self, base_url, timeout):
            self.session = SimpleNamespace(headers={})

        def login(self, account, password, client_tool):
            return "token"

        def post_form(self, path, fields):
            calls.append((path, dict(fields)))
            if "userLogin" in path:
                return {"success": True, "code": 0, "data": {"userToken": "token"}}
            if "stockAutoList" in path:
                return {"success": True, "code": 0, "data": {"list": []}}
            if "porderCreate" in path:
                return {"success": True, "code": 0, "data": {"porder_sn": "PORDER-DIRECT"}}
            return {"success": False, "code": 0, "msg": "route error"}

    monkeypatch.setattr(data_scripts.bulk_cart, "RakumartClient", FakeRakumartClient)

    passed, log_text, _report_path, summary = data_scripts.run_warehouse_delivery_script(
        SimpleNamespace(base_url="https://example.test", timeout=30),
        {
            "account": "alice",
            "password": "secret",
            "warehouse_sku_count": 1,
            "send_num": 1,
            "run_backend_delivery_flow": False,
            "warehouse_fill_scope": "current_order_then_history",
            "require_warehouse_sku_count": True,
            "order_detail_ids": ["DETAIL-1", "DETAIL-2"],
        },
    )

    create_fields = next(fields for path, fields in calls if "porderCreate" in path)
    log = json.loads(log_text)
    assert passed is True
    assert create_fields["porder_detail[0][order_detail_id]"] == "DETAIL-1"
    assert summary["porder_sn"] == "PORDER-DIRECT"
    assert summary["actual_warehouse_sku_count"] == 1
    assert summary["current_order_count"] == 1
    assert log["warehouse_direct_requested_ids"]["used_order_detail_ids"] == ["DETAIL-1"]


def test_warehouse_delivery_fails_without_creating_when_required_stock_short(monkeypatch):
    calls = []
    rows = [
        {"id": "current-1", "order_sn": "ORDER-1", "sku_id": "sku-current-1", "send_num": 5},
        {"id": "history-1", "sku_id": "sku-history-1", "send_num": 5},
    ]

    class FakeRakumartClient:
        def __init__(self, base_url, timeout):
            self.session = SimpleNamespace(headers={})

        def login(self, account, password, client_tool):
            return "token"

        def post_form(self, path, fields):
            calls.append((path, dict(fields)))
            if "userLogin" in path:
                return {"success": True, "code": 0, "data": {"userToken": "token"}}
            if "stockAutoList" in path:
                return {"success": True, "code": 0, "data": {"list": rows}}
            if "porderCreate" in path:
                raise AssertionError("porderCreate should not be called when stock is short")
            raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(data_scripts.bulk_cart, "RakumartClient", FakeRakumartClient)

    passed, _log_text, _report_path, summary = data_scripts.run_warehouse_delivery_script(
        SimpleNamespace(base_url="https://example.test", timeout=30),
        {
            "account": "alice",
            "password": "secret",
            "warehouse_sku_count": 3,
            "run_backend_delivery_flow": False,
            "warehouse_fill_scope": "current_order_then_history",
            "require_warehouse_sku_count": True,
            "order_sn": "ORDER-1",
        },
    )

    assert passed is False
    assert summary["reason"] == "可用库存不足"
    assert summary["warehouse_sku_count"] == 3
    assert summary["actual_warehouse_sku_count"] == 2
    assert not any("porderCreate" in path for path, _fields in calls)


def test_order_quote_options_preview_reads_option_list_without_cart_or_order(monkeypatch):
    calls = []

    class FakeRakumartClient:
        def __init__(self, base_url, timeout):
            self.base_url = base_url
            self.timeout = timeout
            self.session = SimpleNamespace(headers={})

        def login(self, account, password, client_tool):
            calls.append(("login", account, password, client_tool))
            return "token"

        def post_form(self, path, fields):
            calls.append(("post_form", path, dict(fields)))
            assert "goodsCartList" not in path
            assert "order.orderCreate" not in path
            if "userLogin" in path:
                return {"success": True, "code": 0, "data": {"userToken": "token"}}
            assert path == "/client/order.optionList"
            return {"success": True, "code": 0, "data": ORDER_OPTION_LIST}

    monkeypatch.setattr(data_scripts.bulk_cart, "RakumartClient", FakeRakumartClient)

    result = data_scripts.preview_order_quote_options(
        SimpleNamespace(base_url="https://example.test", timeout=30),
        {"account": "alice", "password": "secret", "client_tool": "1", "order_item_count": 1},
    )

    assert result["option_count"] == 16
    assert result["selected_count"] == 0
    assert result["source_path"] == "/client/order.optionList"
    assert [item["label"] for item in result["options"][:3]] == ["详细检品", "针检", "X线针检"]
    assert [item[0] for item in calls] == ["post_form", "post_form"]


def test_order_quote_unknown_option_stops_before_create(monkeypatch):
    calls = []

    class FakeRakumartClient:
        def __init__(self, base_url, timeout):
            self.base_url = base_url
            self.timeout = timeout
            self.session = SimpleNamespace(headers={})

        def post_form(self, path, fields):
            calls.append((path, dict(fields)))
            if "userLogin" in path:
                return {"success": True, "code": 0, "data": {"userToken": "token"}}
            if "goodsCartList" in path:
                return {
                    "success": True,
                    "code": 0,
                    "data": {
                        "goods": [
                            {
                                "id": "cart-1",
                                "goods_id": "goods-1",
                                "goods_title": "测试商品",
                                "price": "10",
                                "detail": [],
                                "from_platform": "1688",
                            }
                        ]
                    },
                }
            if "goodsCartEdit" in path:
                return {"success": True, "code": 0}
            if "order.optionList" in path:
                return {"success": True, "code": 0, "data": ORDER_OPTION_LIST}
            if "order.orderCreate" in path:
                raise AssertionError("order.orderCreate should not be called for unknown option")
            raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(data_scripts.bulk_cart, "RakumartClient", FakeRakumartClient)

    passed, log_text, _report_path, summary = data_scripts.run_order_quote_script(
        SimpleNamespace(base_url="https://example.test", timeout=30),
        {
            "account": "alice",
            "password": "secret",
            "client_tool": "1",
            "order_item_count": 1,
            "order_item_num": 2,
            "order_option_counts": {"999": 1},
        },
    )

    log = json.loads(log_text)
    paths = [path for path, _fields in calls]
    assert passed is False
    assert "不存在" in summary["reason"]
    assert summary["missing_order_options"] == [{"key": "999", "num": 1, "reason": "option_not_found"}]
    assert log["order_options"]["missing"] == summary["missing_order_options"]
    assert any("order.optionList" in path for path in paths)
    assert not any("order.orderCreate" in path for path in paths)


def test_order_quote_options_preview_endpoint_uses_preview_function(monkeypatch):
    calls = []

    def fake_preview(env, variables):
        calls.append({"env_id": env.id, "variables": dict(variables)})
        return {
            "options": [{"key": "1", "label": "FBA贴标", "price": "1.00", "unit": "元"}],
            "selected_count": 1,
            "item_count": 1,
            "selection": {"selected_count": 1, "expected_total": 1, "shortage_count": 0},
        }

    monkeypatch.setattr(main, "preview_order_quote_options", fake_preview)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        project = client.post("/api/projects", headers=headers, json={"name": "option-preview-project", "desc": ""}).json()
        env = client.post(
            "/api/envs",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_name": "option-preview-env",
                "base_url": "https://example.test",
                "global_headers": {},
                "global_vars": {},
                "timeout": 30,
            },
        ).json()
        response = client.post(
            "/api/data-scripts/order-quote/options-preview",
            headers=headers,
            json={"env_id": env["id"], "variables": {"order_shop_count": 1, "order_per_shop": 1}},
        )

    assert response.status_code == 200
    assert response.json()["options"][0]["label"] == "FBA贴标"
    assert calls[0]["variables"]["order_shop_count"] == 1


def test_order_quote_options_preview_endpoint_returns_bad_request_on_runtime_error(monkeypatch):
    def fake_preview(_env, _variables):
        raise RuntimeError("client login failed")

    monkeypatch.setattr(main, "preview_order_quote_options", fake_preview)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        project = client.post("/api/projects", headers=headers, json={"name": "option-preview-error-project", "desc": ""}).json()
        env = client.post(
            "/api/envs",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_name": "option-preview-error-env",
                "base_url": "https://example.test",
                "global_headers": {},
                "global_vars": {},
                "timeout": 30,
            },
        ).json()
        response = client.post(
            "/api/data-scripts/order-quote/options-preview",
            headers=headers,
            json={"env_id": env["id"], "variables": {}},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "读取订单选项失败：client login failed"


def create_case_generation_fixture(client: TestClient, headers: dict):
    project = client.post("/api/projects", headers=headers, json={"name": "case generation project", "desc": ""}).json()
    workspace = client.get(
        "/api/case-generation/workspace",
        headers=headers,
        params={"project_id": project["id"]},
    )
    assert workspace.status_code == 200
    upload = client.post(
        "/api/case-generation/workspace/upload-screenshots",
        headers=headers,
        params={"project_id": project["id"]},
        files=[("files", ("login.png", PNG_1X1, "image/png"))],
    )
    assert upload.status_code == 200
    screenshot_id = upload.json()["uploaded"][0]["id"]
    corrected = client.put(
        f"/api/case-generation/screenshots/{screenshot_id}/ocr-text",
        headers=headers,
        json={"corrected_text": "Login page\nUsername\nPassword\nSubmit\nForgot password"},
    )
    assert corrected.status_code == 200
    note = client.post(
        "/api/case-generation/workspace/requirement-notes",
        headers=headers,
        params={"project_id": project["id"]},
        json={"note_text": "Generate manual functional execution cases for login success, wrong password, and required fields."},
    )
    assert note.status_code == 200
    generated = client.post(
        "/api/case-generation/workspace/generate-cases",
        headers=headers,
        params={"project_id": project["id"]},
    )
    assert generated.status_code == 200
    detail = generated.json()["workspace"]
    assert len(detail["cases"]) >= 2
    return project, detail, screenshot_id


def test_case_generation_is_pure_functional_and_normal_can_mark_status():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        _, detail, _ = create_case_generation_fixture(client, headers)

        response = client.post(
            "/api/users",
            headers=headers,
            json={"username": "normal_case_generation", "password": "123456", "role": "normal"},
        )
        assert response.status_code in (200, 400)
        normal_token = login(client, "normal_case_generation", "123456")
        case_id = detail["cases"][0]["id"]
        marked = client.put(
            f"/api/case-generation/cases/{case_id}/status",
            headers={"Authorization": f"Bearer {normal_token}"},
            json={"test_result": "passed"},
        )

    assert marked.status_code == 200
    assert marked.json()["test_result"] == "passed"
    assert "case_name" not in detail["cases"][0]


def test_case_generation_workspace_keeps_corrected_ocr_text():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        project, detail, screenshot_id = create_case_generation_fixture(client, headers)
        workspace = client.get(
            "/api/case-generation/workspace",
            headers=headers,
            params={"project_id": project["id"]},
        )
        screenshot = workspace.json()["screenshots"][0]

    assert workspace.status_code == 200
    assert detail["task_name"] == "用例生成草稿"
    assert screenshot["id"] == screenshot_id
    assert "Username" in screenshot["corrected_text"]


def test_case_generation_delete_screenshot_can_keep_cases_with_missing_source():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        _, detail, screenshot_id = create_case_generation_fixture(client, headers)
        task_id = detail["id"]
        before_ids = {item["id"] for item in detail["cases"]}
        deleted = client.delete(
            f"/api/case-generation/screenshots/{screenshot_id}",
            headers=headers,
            params={"delete_cases": "false"},
        )
        after = client.get(f"/api/case-generation/tasks/{task_id}", headers=headers).json()

    assert deleted.status_code == 200
    assert {item["id"] for item in after["cases"]} == before_ids
    assert all(item["source_missing"] == 1 for item in after["cases"])


def test_case_generation_delete_screenshot_can_delete_unprotected_cases_only():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        _, detail, screenshot_id = create_case_generation_fixture(client, headers)
        task_id = detail["id"]
        protected_id = detail["cases"][0]["id"]
        removable_id = detail["cases"][1]["id"]
        protected = client.put(
            f"/api/case-generation/cases/{protected_id}/status",
            headers=headers,
            json={"test_result": "passed"},
        )
        deleted = client.delete(
            f"/api/case-generation/screenshots/{screenshot_id}",
            headers=headers,
            params={"delete_cases": "true"},
        )
        after = client.get(f"/api/case-generation/tasks/{task_id}", headers=headers).json()
        after_by_id = {item["id"]: item for item in after["cases"]}

    assert protected.status_code == 200
    assert deleted.status_code == 200
    assert protected_id in after_by_id
    assert after_by_id[protected_id]["source_missing"] == 1
    assert removable_id not in after_by_id


def full_flow_env():
    return SimpleNamespace(base_url="https://example.test", timeout=30)


def patch_full_flow_report(monkeypatch):
    monkeypatch.setattr(data_scripts, "write_allure_result", lambda *args, **kwargs: "mock-report.json")
    monkeypatch.setattr(
        data_scripts,
        "run_porder_shipment_script",
        lambda env, variables: (
            True,
            "shipment-log",
            "shipment-report",
            {"porder_sn": variables.get("porder_sn"), "current_node": "porder_shipped"},
        ),
    )


class BankMinimumDepositFakeClient:
    def __init__(self, pay_amount_jpy="10600", bank_pay_amount_min="12000"):
        self.calls = []
        self.pay_amount_jpy = pay_amount_jpy
        self.bank_pay_amount_min = bank_pay_amount_min

    def post_form(self, path, fields):
        self.calls.append((path, dict(fields)))
        if path.endswith("/client/order.orderList"):
            return {
                "success": True,
                "code": 0,
                "data": [{"order_sn": "ORDER-MIN", "status_name": "等待付款", "order_amount": "10600"}],
            }
        if path.endswith("/client/order.payData"):
            return {
                "success": True,
                "code": 0,
                "data": {
                    "part_pay_amount": {
                        "JPY": {
                            "bank_pay_amount_min": self.bank_pay_amount_min,
                            "pay_amount_jpy": self.pay_amount_jpy,
                        }
                    }
                },
            }
        if path.endswith("/client/order.bankPayOrder"):
            return {
                "success": True,
                "code": 0,
                "data": {"order_sn": "ORDER-MIN", "serial_number": "BANK-MIN-1"},
            }
        raise AssertionError(path)


def test_part_pay_bank_uses_minimum_deposit_amount(monkeypatch):
    patch_full_flow_report(monkeypatch)
    client = BankMinimumDepositFakeClient()
    monkeypatch.setattr(
        data_scripts,
        "_login_client_for_payment",
        lambda *args, **kwargs: (client, "https://example.test", 30, "TOKEN"),
    )

    passed, log_text, _, summary = data_scripts.run_bank_payment_script(
        full_flow_env(),
        {
            "order_sn": "ORDER-MIN",
            "_full_flow_part_pay_script": True,
            "order_part_pay": True,
            "finance_confirm": False,
        },
    )

    assert passed is True
    assert [path for path, _ in client.calls] == [
        "/client/order.orderList",
        "/client/order.payData",
        "/client/order.bankPayOrder",
    ]
    assert client.calls[-1][1]["pay_amount"] == "12000"
    assert summary["pay_amount"] == "12000"
    assert summary["minimum_deposit_amount"] == "12000"
    assert summary["amount_source"] == "bank_pay_amount_min"
    assert json.loads(log_text)["order_pay_data"]["selected_amount"] == "12000"


def test_part_pay_bank_keeps_current_amount_above_minimum(monkeypatch):
    patch_full_flow_report(monkeypatch)
    client = BankMinimumDepositFakeClient(pay_amount_jpy="13000")
    monkeypatch.setattr(
        data_scripts,
        "_login_client_for_payment",
        lambda *args, **kwargs: (client, "https://example.test", 30, "TOKEN"),
    )

    passed, _, _, summary = data_scripts.run_bank_payment_script(
        full_flow_env(),
        {
            "order_sn": "ORDER-MIN",
            "_full_flow_part_pay_script": True,
            "order_part_pay": True,
            "finance_confirm": False,
        },
    )

    assert passed is True
    assert client.calls[-1][1]["pay_amount"] == "13000"
    assert summary["pay_amount"] == "13000"
    assert summary["minimum_deposit_amount"] == "12000"
    assert summary["amount_source"] == "order_pay_data"


def test_regular_bank_payment_keeps_order_list_amount(monkeypatch):
    patch_full_flow_report(monkeypatch)
    client = BankMinimumDepositFakeClient()
    monkeypatch.setattr(
        data_scripts,
        "_login_client_for_payment",
        lambda *args, **kwargs: (client, "https://example.test", 30, "TOKEN"),
    )

    passed, _, _, summary = data_scripts.run_bank_payment_script(
        full_flow_env(),
        {"order_sn": "ORDER-MIN", "finance_confirm": False},
    )

    assert passed is True
    assert [path for path, _ in client.calls] == [
        "/client/order.orderList",
        "/client/order.bankPayOrder",
    ]
    assert client.calls[-1][1]["pay_amount"] == "10600"
    assert summary["amount_source"] == "order_list"


def test_full_flow_part_pay_entry_is_exact_and_hides_detail_id():
    source = Path("static/full-flow.js").read_text(encoding="utf-8")

    assert 'const FULL_FLOW_PART_PAY_SCRIPT_NAME = "全流程加入分批付款";' in source
    assert "function ensureFullFlowPartPayScript" in source
    assert 'String(flow?.name || "").trim() === FULL_FLOW_PART_PAY_SCRIPT_NAME' in source
    assert "includes(FULL_FLOW_PART_PAY_SCRIPT" not in source
    assert "尾款支付番序号" in source
    assert "name=\"order_part_pay_tail_select_by\"" not in source
    assert "name=\"order_part_pay_tail_detail_ids\"" not in source
    assert "按番选择方式" not in source
    assert "<label>明细 ID</label>" not in source
    assert "next._full_flow_part_pay_script = true;" in source
    assert "next._full_flow_part_pay_script = false;" in source
    assert "function validateFullFlowPartPayVariables" in source
    assert 'throw new Error("按番尾款已启用，但未填写番序号");' in source
    assert "validateFullFlowPartPayVariables(next, flow);" in source


def test_order_part_pay_ignored_without_full_flow_part_pay_flag(monkeypatch):
    order_data = {
        "order_sn": "ORDER-PART",
        "order_detail": [{"id": "DETAIL-1", "num": 1}],
    }
    prepared = data_scripts._prepare_offer_data(order_data, {"order_part_pay": True}, 1)
    assert "order_part_pay" not in prepared

    prepared = data_scripts._prepare_offer_data(order_data, {"_full_flow_part_pay_script": True, "order_part_pay": True}, 1)
    assert prepared["order_part_pay"] == 1

    monkeypatch.setattr(data_scripts, "_post_admin_urlencoded", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("part pay API should not run")))
    passed, summary = data_scripts._save_order_part_pay_plan_if_needed(
        None,
        "https://example.test",
        {"order_part_pay": True},
        "ORDER-PART",
        prepared,
        30,
    )
    assert passed is True
    assert summary["skipped"] is True
    assert "全流程加入分批付款" in summary["reason"]


def test_order_part_pay_plan_runs_only_with_full_flow_part_pay_flag(monkeypatch):
    calls = []
    offer_data = {
        "order_sn": "ORDER-PART",
        "order_detail": [{"id": "DETAIL-1", "offer_num": 2, "offer_price": "10"}],
    }

    def post_admin_urlencoded(_session, _base_url, path, fields, _timeout):
        calls.append({"path": path, "fields": dict(fields)})
        return {"success": True, "code": 0}

    monkeypatch.setattr(data_scripts, "_post_admin_urlencoded", post_admin_urlencoded)
    passed, summary = data_scripts._save_order_part_pay_plan_if_needed(
        None,
        "https://example.test",
        {
            "_full_flow_part_pay_script": True,
            "order_part_pay": True,
            "order_part_pay_percent": 10,
            "order_part_pay_tail_node": "before_shelf",
        },
        "ORDER-PART",
        offer_data,
        30,
    )

    assert passed is True
    assert calls[0]["path"].endswith("/order.updateOrderPartPayPlan")
    assert calls[0]["fields"]["order_sn"] == "ORDER-PART"
    assert calls[0]["fields"]["first_payment_ratio"] == 10
    assert summary["request"]["goods_amount"] == "2.00"


def test_order_part_pay_goods_amount_ignores_legacy_override_and_fee_flags():
    offer_data = {
        "order_sn": "ORDER-PART",
        "order_detail": [{"id": "DETAIL-1", "offer_num": 30, "offer_price": "10"}],
    }

    fields = data_scripts._order_part_pay_plan_fields(
        "ORDER-PART",
        offer_data,
        {
            "order_part_pay_percent": 10,
            "order_part_pay_goods_amount": "300",
            "first_goods_amount": "300",
            "order_part_pay_fee_timing": {
                "domestic_freight": "first",
                "service_fee": "tail",
                "additional_service_fee": "first",
                "other_fee": "tail",
            },
        },
    )

    assert fields["goods_amount"] == "30.00"
    assert fields["is_pay_freight_amount"] == 1
    assert fields["is_pay_service_amount"] == 0
    assert fields["is_pay_option_amount"] == 1
    assert fields["is_pay_other_amount"] == 0


def test_order_part_pay_goods_amount_uses_order_quantity_not_offer_stock():
    offer_data = {
        "order_sn": "ORDER-PART",
        "order_detail": [
            {"id": "DETAIL-1", "num": 10, "confirm_num": 10, "offer_num": 100, "offer_price": "10"},
            {"id": "DETAIL-2", "num": 10, "confirm_num": 10, "offer_num": 100, "offer_price": "10"},
            {"id": "DETAIL-3", "num": 10, "confirm_num": 10, "offer_num": 100, "offer_price": "10"},
        ],
    }

    fields = data_scripts._order_part_pay_plan_fields(
        "ORDER-PART",
        offer_data,
        {"order_part_pay_percent": 50},
    )

    assert fields["goods_amount"] == "150.00"


def test_full_flow_part_pay_preview_includes_selected_option_fee():
    source = Path("static/full-flow.js").read_text(encoding="utf-8")

    assert "function fullFlowPartPaySelectedOptionAmount" in source
    assert "data.order_option_counts = readOrderOptionCounts(form);" in source
    assert "fullFlowPartPaySelectedOptionAmount(orderOptions, data.order_option_counts, productAmount)" in source
    assert "data.order_part_pay_fee_timing_additional_service_fee" in source
    assert "bindFullFlowPartPayPanel(form, () => currentOrderOptions)" in source
    assert "data.offer_num || data.order_item_num" not in source


def test_order_part_pay_plan_runs_before_submit_offer(monkeypatch):
    calls = []
    order_detail = {"id": "DETAIL-1", "goods_id": "GOODS-1", "num": 2}
    detail_payload = {
        "success": True,
        "code": 0,
        "data": {"order_sn": "ORDER-PART", "status": 22, "order_detail": [dict(order_detail)]},
    }

    monkeypatch.setattr(data_scripts, "_admin_login", lambda *args, **kwargs: ({"success": True, "code": 0}, "token"))

    def order_detail_data(*args, **kwargs):
        calls.append("detail")
        return detail_payload, dict(detail_payload["data"])

    def post_admin_form(_session, _base_url, path, _fields, _timeout):
        if path.endswith("/order.submitOffer"):
            calls.append("submit_offer")
        else:
            calls.append(path)
        return {"success": True, "code": 0}

    def post_admin_urlencoded(_session, _base_url, path, fields, _timeout):
        calls.append("part_pay_plan")
        assert path.endswith("/order.updateOrderPartPayPlan")
        assert fields["order_sn"] == "ORDER-PART"
        return {"success": True, "code": 0}

    monkeypatch.setattr(data_scripts, "_order_detail_data", order_detail_data)
    monkeypatch.setattr(data_scripts, "_post_admin_form", post_admin_form)
    monkeypatch.setattr(data_scripts, "_post_admin_urlencoded", post_admin_urlencoded)

    passed, summary = data_scripts._run_backend_order_flow(
        "https://example.test",
        30,
        {
            "_full_flow_part_pay_script": True,
            "order_part_pay": True,
            "order_part_pay_percent": 10,
        },
        "ORDER-PART",
        2,
        {},
    )

    assert passed is True
    assert summary["backend_steps"] == ["login", "detail", "translate", "confirm", "part_pay_plan", "offer"]
    assert calls.index("part_pay_plan") < calls.index("submit_offer")


def test_order_tail_payment_skips_without_full_flow_part_pay_flag(monkeypatch):
    monkeypatch.setattr(data_scripts, "_login_client_for_payment", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("tail payment should not login")))

    log = {}
    passed, summary = data_scripts._run_order_tail_payment_if_needed(
        full_flow_env(),
        {"order_part_pay": True, "order_part_pay_tail_node": "before_shelf", "order_sn": "ORDER-PART"},
        log,
        "before_shelf",
    )

    assert passed is True
    assert summary["skipped"] is True
    assert "全流程加入分批付款" in summary["reason"]
    assert "order_tail_payments" not in log


class TailPartialFakeClient:
    def __init__(self):
        self.calls = []

    def post_form(self, path, fields):
        self.calls.append((path, dict(fields)))
        if path.endswith("/client/order.orderDetail"):
            return {
                "success": True,
                "data": {
                    "order_detail": [
                        {
                            "goods": [
                                {"id": "DETAIL-1", "sorting": "1", "tail_pay_status": 0, "tail_pay_status_name": "待支付"},
                                {"id": "DETAIL-2", "sorting": "2", "tail_pay_status": 0, "tail_pay_status_name": "待支付"},
                            ]
                        }
                    ],
                    "part_pay_tail_summary": {"unpaid_tail_detail_ids": ["DETAIL-1", "DETAIL-2"]},
                },
            }
        if path.endswith("/client/order.payData"):
            detail_ids = [value for key, value in fields.items() if str(key).startswith("order_detail_ids[")]
            return {
                "success": True,
                "data": {
                    "part_pay_amount": {"JPY": {"tail_detail_ids": detail_ids, "pay_amount_jpy": "100"}},
                    "tail_detail_list": [{"id": detail_id, "can_pay_tail": True} for detail_id in detail_ids],
                },
            }
        raise AssertionError(f"unexpected path {path}")


def test_order_tail_partial_resolves_sorting_and_keeps_legacy_detail_id():
    passed, context = data_scripts._resolve_order_tail_partial_context(
        TailPartialFakeClient(),
        {"order_part_pay_tail_partial_enabled": 1, "order_part_pay_tail_sortings": "1,2"},
        "ORDER-TAIL",
        {},
    )
    assert passed is True
    assert context["select_by"] == "sorting"
    assert context["selected_order_detail_ids"] == ["DETAIL-1", "DETAIL-2"]

    passed, context = data_scripts._resolve_order_tail_partial_context(
        TailPartialFakeClient(),
        {"order_part_pay_tail_partial_enabled": 1},
        "ORDER-TAIL",
        {},
    )
    assert passed is False
    assert context["reason"] == "按番尾款已启用，但未填写番序号"

    passed, context = data_scripts._resolve_order_tail_partial_context(
        TailPartialFakeClient(),
        {"order_part_pay_tail_partial_enabled": 1, "order_part_pay_tail_sortings": "9"},
        "ORDER-TAIL",
        {},
    )
    assert passed is False
    assert context["reason"] == "所选番序号不存在或未匹配到订单明细"

    passed, context = data_scripts._resolve_order_tail_partial_context(
        TailPartialFakeClient(),
        {
            "order_part_pay_tail_partial_enabled": 1,
            "order_part_pay_tail_select_by": "detail_id",
            "order_part_pay_tail_detail_ids": "DETAIL-2",
        },
        "ORDER-TAIL",
        {},
    )
    assert passed is True
    assert context["select_by"] == "detail_id"
    assert context["selected_order_detail_ids"] == ["DETAIL-2"]


class TailBalanceFallbackFakeClient(TailPartialFakeClient):
    def post_form(self, path, fields):
        if path.endswith("/client/order.orderList"):
            self.calls.append((path, dict(fields)))
            return {"success": True, "code": 0, "data": [{"order_sn": "ORDER-TAIL", "amount": "100"}]}
        if path.endswith("/client/order.balancePayOrder"):
            self.calls.append((path, dict(fields)))
            return {"success": False, "code": 10000, "msg": "\u6b8b\u9ad8\u304c\u4e0d\u8db3\u3057\u3066\u3044\u307e\u3059"}
        if path.endswith("/client/order.bankPayOrder"):
            self.calls.append((path, dict(fields)))
            return {"success": True, "code": 0, "data": {"serial_number": "TAIL-BANK-1"}}
        return super().post_form(path, fields)


def test_order_tail_balance_insufficient_falls_back_to_bank(monkeypatch):
    client = TailBalanceFallbackFakeClient()
    finance_calls = []
    monkeypatch.setattr(
        data_scripts,
        "_login_client_for_payment",
        lambda *args, **kwargs: (client, "https://example.test", 30, "TOKEN"),
    )

    def finance_only(_env, variables):
        finance_calls.append(dict(variables))
        return True, "", "finance-report.json", {
            "payment_type": "bank",
            "order_sn": variables["order_sn"],
            "serial_number": variables["serial_number"],
            "finance_confirm": True,
            "finance_passed": True,
        }

    monkeypatch.setattr(data_scripts, "run_bank_payment_script", finance_only)

    passed, summary = data_scripts._run_order_tail_payment_if_needed(
        full_flow_env(),
        {
            "_full_flow_part_pay_script": True,
            "order_part_pay": True,
            "order_part_pay_tail_node": "before_shelf",
            "order_payment_mode": "balance_first",
            "order_sn": "ORDER-TAIL",
        },
        {},
        "before_shelf",
    )

    assert passed is True
    assert summary["fallback_from_balance"] is True
    assert summary["attempted_payment_types"] == ["balance", "bank"]
    assert summary["payment_mode"] == "bank"
    assert summary["serial_number"] == "TAIL-BANK-1"
    assert summary["finance_confirm"] is True
    assert summary["finance_passed"] is True
    assert summary["finance_confirmation"]["report_path"] == "finance-report.json"
    assert finance_calls == [
        {
            "_full_flow_part_pay_script": True,
            "order_part_pay": True,
            "order_part_pay_tail_node": "before_shelf",
            "order_payment_mode": "balance_first",
            "order_sn": "ORDER-TAIL",
            "serial_number": "TAIL-BANK-1",
            "finance_confirm": True,
        }
    ]
    assert [path for path, _fields in client.calls] == [
        "/client/order.balancePayOrder",
        "/client/order.orderList",
        "/client/order.bankPayOrder",
    ]
    assert client.calls[-1][1]["pay_amount"] == "100"


def test_order_tail_bank_finance_failure_stops_flow(monkeypatch):
    client = TailBalanceFallbackFakeClient()
    monkeypatch.setattr(
        data_scripts,
        "_login_client_for_payment",
        lambda *args, **kwargs: (client, "https://example.test", 30, "TOKEN"),
    )
    monkeypatch.setattr(
        data_scripts,
        "run_bank_payment_script",
        lambda _env, variables: (
            False,
            "",
            "",
            {
                "payment_type": "bank",
                "order_sn": variables["order_sn"],
                "serial_number": variables["serial_number"],
                "finance_confirm": True,
                "finance_passed": False,
                "reason": "待确认列表未找到流水号",
            },
        ),
    )

    passed, summary = data_scripts._run_order_tail_payment_if_needed(
        full_flow_env(),
        {
            "_full_flow_part_pay_script": True,
            "order_part_pay": True,
            "order_part_pay_tail_node": "before_shelf",
            "order_payment_mode": "balance_first",
            "order_sn": "ORDER-TAIL",
        },
        {},
        "before_shelf",
    )

    assert passed is False
    assert summary["payment_passed"] is True
    assert summary["finance_passed"] is False
    assert summary["reason"] == "待确认列表未找到流水号"


def test_order_tail_direct_bank_payment_also_confirms_finance(monkeypatch):
    client = TailBalanceFallbackFakeClient()
    finance_calls = []
    monkeypatch.setattr(
        data_scripts,
        "_login_client_for_payment",
        lambda *args, **kwargs: (client, "https://example.test", 30, "TOKEN"),
    )

    def finance_only(_env, variables):
        finance_calls.append(dict(variables))
        return True, "", "", {"finance_confirm": True, "finance_passed": True}

    monkeypatch.setattr(data_scripts, "run_bank_payment_script", finance_only)

    passed, summary = data_scripts._run_order_tail_payment_if_needed(
        full_flow_env(),
        {
            "_full_flow_part_pay_script": True,
            "order_part_pay": True,
            "order_part_pay_tail_node": "before_shelf",
            "order_payment_mode": "bank",
            "order_sn": "ORDER-TAIL",
        },
        {},
        "before_shelf",
    )

    assert passed is True
    assert summary["payment_mode"] == "bank"
    assert summary["finance_passed"] is True
    assert finance_calls[0]["serial_number"] == "TAIL-BANK-1"
    assert [path for path, _fields in client.calls] == [
        "/client/order.orderList",
        "/client/order.bankPayOrder",
    ]


def test_full_flow_rejects_empty_tail_sorting_before_order_creation(monkeypatch):
    patch_full_flow_report(monkeypatch)
    monkeypatch.setattr(
        data_scripts,
        "run_order_quote_script",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("order should not be created")),
    )

    passed, log_text, _, summary = data_scripts.run_full_flow_script(
        full_flow_env(),
        {
            "_full_flow_part_pay_script": True,
            "order_part_pay": True,
            "order_part_pay_tail_partial_enabled": 1,
            "order_part_pay_tail_sortings": "",
        },
    )

    log = json.loads(log_text)
    assert passed is False
    assert summary["current_node"] == "input_validation"
    assert summary["total_steps"] == 0
    assert summary["reason"] == "按番尾款已启用，但未填写番序号"
    assert log["input_validation"] == {
        "passed": False,
        "reason": "按番尾款已启用，但未填写番序号",
    }


def test_full_flow_runs_nodes_in_order_and_passes_shared_numbers(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    def quote(env, variables):
        calls.append("order_quote")
        assert isinstance(variables["_runtime"], data_scripts.DataScriptRuntime)
        assert variables["sleep"] == 0
        assert variables["cart_verify_mode"] == "final"
        assert variables["cart_edit_workers"] == 4
        assert variables["submit_order"] is True
        assert variables["run_backend_flow"] is True
        assert variables["order_shop_count"] == 1
        assert variables["order_per_shop"] == 3
        return True, "quote-log", "quote-report", {"order_sn": "ORDER-1", "backend_passed": True}

    def balance(env, variables):
        calls.append("order_balance")
        assert variables["order_sn"] == "ORDER-1"
        return True, "pay-log", "pay-report", {"payment_type": "balance", "order_sn": "ORDER-1", "payment_passed": True}

    def shelf(env, variables):
        calls.append("purchase_to_shelf")
        assert variables["order_sn"] == "ORDER-1"
        assert variables["link_quote_balance_before_shelf"] is False
        assert variables["auto_quote_and_pay"] is False
        return (
            True,
            "shelf-log",
            "shelf-report",
            {
                "order_sn": "ORDER-1",
                "purchase_no": "PNO-1",
                "purchase_ids": ["PUR-1"],
                "grid_id": "GRID-1",
                "grid_number": "A-01",
                "order_detail_id": "DETAIL-1",
            },
        )

    def delivery(env, variables):
        calls.append("warehouse_delivery")
        assert variables["order_detail_id"] == "DETAIL-1"
        assert variables["warehouse_sku_count"] == 3
        assert variables["warehouse_fill_scope"] == "current_order_then_history"
        assert variables["require_warehouse_sku_count"] is True
        return True, "delivery-log", "delivery-report", {"porder_sn": "PORDER-1", "order_detail_id": "DETAIL-1"}

    def porder_balance(env, variables):
        calls.append("porder_balance")
        assert variables["porder_sn"] == "PORDER-1"
        assert variables["run_backend_porder_flow"] is False
        return True, "porder-pay-log", "porder-pay-report", {"payment_type": "balance", "porder_sn": "PORDER-1"}

    def porder_shipment(env, variables):
        calls.append("porder_shipment")
        assert variables["porder_sn"] == "PORDER-1"
        return True, "shipment-log", "shipment-report", {"porder_sn": "PORDER-1", "current_node": "porder_shipped"}

    monkeypatch.setattr(data_scripts, "run_shopping_cart_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("shopping cart should be skipped when cart has enough items")))
    monkeypatch.setattr(data_scripts, "run_order_quote_script", quote)
    monkeypatch.setattr(data_scripts, "run_balance_payment_script", balance)
    monkeypatch.setattr(data_scripts, "run_bank_payment_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bank fallback not expected")))
    monkeypatch.setattr(data_scripts, "run_purchase_to_shelf_script", shelf)
    monkeypatch.setattr(data_scripts, "run_warehouse_delivery_script", delivery)
    monkeypatch.setattr(data_scripts, "run_porder_balance_payment_script", porder_balance)
    monkeypatch.setattr(data_scripts, "run_porder_bank_payment_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("porder bank fallback not expected")))
    monkeypatch.setattr(data_scripts, "run_porder_shipment_script", porder_shipment)

    passed, _, _, summary = data_scripts.run_full_flow_script(full_flow_env(), {"stop_after_node": "full_complete", "warehouse_sku_count": 3})

    assert passed is True
    assert calls == ["order_quote", "order_balance", "purchase_to_shelf", "warehouse_delivery", "porder_balance", "porder_shipment"]
    assert summary["current_node"] == "full_complete"
    assert summary["order_sn"] == "ORDER-1"
    assert summary["purchase_no"] == "PNO-1"
    assert summary["porder_sn"] == "PORDER-1"
    assert "duration_ms" in summary
    assert "step_timings" in summary
    assert summary["node_results"][0]["node"] == "shopping_cart"
    assert summary["node_results"][-1]["node"] == "full_complete"
    assert all(item["status"] == "completed" for item in summary["node_results"])


def test_full_flow_autofills_cart_once_on_shortage(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []
    quote_calls = {"count": 0}

    def quote(env, variables):
        calls.append("order_quote")
        quote_calls["count"] += 1
        if quote_calls["count"] == 1:
            return False, "shortage-log", "shortage-report", {
                "reason_code": "cart_items_shortage",
                "selected_count": 0,
                "expected_count": 2,
                "shortage_count": 2,
                "reason": "购物车可提单商品不足",
            }
        assert variables["auto_fill_cart_on_shortage"] is False
        return True, "quote-log", "quote-report", {"order_sn": "ORDER-FILL", "backend_passed": True}

    def cart(env, variables):
        calls.append("shopping_cart")
        assert variables["target_shops"] == 1
        assert variables["per_shop"] == 2
        return True, "cart-log", "cart-report", {"target_shops": 1, "per_shop": 2, "added_total": 2}

    monkeypatch.setattr(data_scripts, "run_order_quote_script", quote)
    monkeypatch.setattr(data_scripts, "run_shopping_cart_script", cart)
    monkeypatch.setattr(data_scripts, "run_balance_payment_script", lambda env, variables: (calls.append("order_balance") or (True, "", "", {"payment_type": "balance", "order_sn": "ORDER-FILL"})))
    monkeypatch.setattr(data_scripts, "run_bank_payment_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bank fallback not expected")))
    monkeypatch.setattr(data_scripts, "run_purchase_to_shelf_script", lambda env, variables: (calls.append("purchase_to_shelf") or (True, "", "", {"order_detail_id": "DETAIL-FILL"})))
    monkeypatch.setattr(data_scripts, "run_warehouse_delivery_script", lambda env, variables: (calls.append("warehouse_delivery") or (True, "", "", {"porder_sn": "PORDER-FILL"})))
    monkeypatch.setattr(data_scripts, "run_porder_balance_payment_script", lambda env, variables: (calls.append("porder_balance") or (True, "", "", {"payment_type": "balance", "porder_sn": "PORDER-FILL"})))
    monkeypatch.setattr(data_scripts, "run_porder_bank_payment_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("porder bank fallback not expected")))

    passed, log_text, _, summary = data_scripts.run_full_flow_script(full_flow_env(), {})

    log = json.loads(log_text)
    assert passed is True
    assert calls == ["order_quote", "shopping_cart", "order_quote", "order_balance", "purchase_to_shelf", "warehouse_delivery", "porder_balance"]
    assert log["cart_autofill"]["triggered"] is True
    assert log["cart_autofill"]["shortage_before"]["shortage_count"] == 2
    assert summary["order_sn"] == "ORDER-FILL"


def test_full_flow_fails_at_shopping_cart_when_autofill_fails(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    monkeypatch.setattr(
        data_scripts,
        "run_order_quote_script",
        lambda env, variables: (calls.append("order_quote") or (False, "", "shortage-report", {"reason_code": "cart_items_shortage", "reason": "购物车可提单商品不足"})),
    )
    monkeypatch.setattr(
        data_scripts,
        "run_shopping_cart_script",
        lambda env, variables: (calls.append("shopping_cart") or (False, "cart-log", "cart-report", {"reason": "未收集到可加购商品"})),
    )

    passed, log_text, _, summary = data_scripts.run_full_flow_script(full_flow_env(), {})

    log = json.loads(log_text)
    assert passed is False
    assert calls == ["order_quote", "shopping_cart"]
    assert summary["current_node"] == "shopping_cart"
    assert summary["reason"] == "未收集到可加购商品"
    assert log["cart_autofill"]["triggered"] is True


def test_full_flow_stop_at_shopping_cart_keeps_legacy_cart_step(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    monkeypatch.setattr(
        data_scripts,
        "run_shopping_cart_script",
        lambda env, variables: (calls.append("shopping_cart") or (True, "cart-log", "cart-report", {"added_total": 2})),
    )
    monkeypatch.setattr(data_scripts, "run_order_quote_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("order quote should not run when paused at shopping_cart")))

    passed, _, _, summary = data_scripts.run_full_flow_script(full_flow_env(), {"stop_after_node": "shopping_cart"})

    assert passed is True
    assert calls == ["shopping_cart"]
    assert summary["paused"] is True
    assert summary["current_node"] == "shopping_cart"


def test_full_flow_pauses_at_pending_purchase(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    monkeypatch.setattr(data_scripts, "run_shopping_cart_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("shopping cart should be skipped when cart has enough items")))
    monkeypatch.setattr(data_scripts, "run_order_quote_script", lambda env, variables: (calls.append("order_quote") or (True, "", "", {"order_sn": "ORDER-2"})))
    monkeypatch.setattr(
        data_scripts,
        "run_balance_payment_script",
        lambda env, variables: (calls.append("order_balance") or (True, "", "", {"payment_type": "balance", "order_sn": "ORDER-2"})),
    )

    def shelf(env, variables):
        calls.append("purchase_to_shelf")
        assert variables["stop_after_node"] == "pending_purchase"
        return True, "", "", data_scripts._paused_summary("pending_purchase", {"order_sn": "ORDER-2", "purchase_no": "PNO-2"})

    monkeypatch.setattr(data_scripts, "run_purchase_to_shelf_script", shelf)
    monkeypatch.setattr(data_scripts, "run_warehouse_delivery_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("delivery should not run")))
    monkeypatch.setattr(data_scripts, "run_porder_balance_payment_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("porder payment should not run")))

    passed, _, _, summary = data_scripts.run_full_flow_script(full_flow_env(), {"stop_after_node": "pending_purchase"})

    assert passed is True
    assert calls == ["order_quote", "order_balance", "purchase_to_shelf"]
    assert summary["paused"] is True
    assert summary["current_node"] == "pending_purchase"
    node_status = {item["node"]: item["status"] for item in summary["node_results"]}
    assert node_status["order_paid"] == "completed"
    assert node_status["pending_purchase"] == "paused"
    assert node_status["purchase_no_saved"] == "pending"


def test_full_flow_emits_progress_before_and_after_each_coarse_node(monkeypatch):
    patch_full_flow_report(monkeypatch)
    events = []
    monkeypatch.setattr(data_scripts, "run_shopping_cart_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应补购物车")))
    monkeypatch.setattr(data_scripts, "run_order_quote_script", lambda env, variables: (True, "", "", {"order_sn": "ORDER-PROGRESS"}))
    monkeypatch.setattr(
        data_scripts,
        "run_balance_payment_script",
        lambda env, variables: (True, "", "", {"payment_type": "balance", "order_sn": "ORDER-PROGRESS"}),
    )
    monkeypatch.setattr(
        data_scripts,
        "run_purchase_to_shelf_script",
        lambda env, variables: (True, "", "", data_scripts._paused_summary("pending_purchase", {"order_sn": "ORDER-PROGRESS"})),
    )
    monkeypatch.setattr(data_scripts, "run_warehouse_delivery_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应创建配送单")))

    passed, _, _, _ = data_scripts.run_full_flow_script(
        full_flow_env(),
        {"stop_after_node": "pending_purchase"},
        progress_callback=events.append,
    )

    assert passed is True
    assert [(item["node"], item["status"]) for item in events] == [
        ("order_offered", "running"),
        ("order_offered", "completed"),
        ("order_paid", "running"),
        ("order_paid", "completed"),
        ("pending_purchase", "running"),
        ("pending_purchase", "completed"),
    ]


def test_full_flow_balance_insufficient_uses_bank_payment(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    monkeypatch.setattr(data_scripts, "run_shopping_cart_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("shopping cart should be skipped when cart has enough items")))
    monkeypatch.setattr(data_scripts, "run_order_quote_script", lambda env, variables: (calls.append("order_quote") or (True, "", "", {"order_sn": "ORDER-3"})))
    monkeypatch.setattr(
        data_scripts,
        "run_balance_payment_script",
        lambda env, variables: (calls.append("order_balance") or (False, "余额不足", "", {"payment_type": "balance", "order_sn": "ORDER-3", "reason": "余额不足"})),
    )

    def bank(env, variables):
        calls.append("order_bank")
        assert variables["finance_confirm"] is True
        return True, "", "", {"payment_type": "bank", "order_sn": "ORDER-3", "serial_number": "SER-3"}

    monkeypatch.setattr(data_scripts, "run_bank_payment_script", bank)
    monkeypatch.setattr(data_scripts, "run_purchase_to_shelf_script", lambda env, variables: (calls.append("purchase_to_shelf") or (True, "", "", {"order_detail_id": "DETAIL-3"})))
    monkeypatch.setattr(data_scripts, "run_warehouse_delivery_script", lambda env, variables: (calls.append("warehouse_delivery") or (True, "", "", {"porder_sn": "PORDER-3"})))
    monkeypatch.setattr(data_scripts, "run_porder_balance_payment_script", lambda env, variables: (calls.append("porder_balance") or (True, "", "", {"payment_type": "balance", "porder_sn": "PORDER-3"})))

    passed, _, _, summary = data_scripts.run_full_flow_script(full_flow_env(), {})

    assert passed is True
    assert calls == [
        "order_quote",
        "order_balance",
        "order_bank",
        "purchase_to_shelf",
        "warehouse_delivery",
        "porder_balance",
    ]
    assert summary["current_node"] == "full_complete"


def test_full_flow_non_balance_failure_does_not_use_bank_payment(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    monkeypatch.setattr(data_scripts, "run_shopping_cart_script", lambda env, variables: (calls.append("shopping_cart") or (True, "", "", {})))
    monkeypatch.setattr(data_scripts, "run_order_quote_script", lambda env, variables: (calls.append("order_quote") or (True, "", "", {"order_sn": "ORDER-4"})))
    monkeypatch.setattr(
        data_scripts,
        "run_balance_payment_script",
        lambda env, variables: (calls.append("order_balance") or (False, "接口超时", "", {"payment_type": "balance", "order_sn": "ORDER-4", "reason": "接口超时"})),
    )
    monkeypatch.setattr(data_scripts, "run_bank_payment_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bank fallback should not run")))

    passed, _, _, summary = data_scripts.run_full_flow_script(full_flow_env(), {})

    assert passed is False
    assert calls == ["order_quote", "order_balance"]
    assert summary["current_node"] == "order_paid"
    assert summary["reason"] == "接口超时"


def test_full_flow_porder_balance_insufficient_uses_porder_bank_payment(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    monkeypatch.setattr(data_scripts, "run_shopping_cart_script", lambda env, variables: (calls.append("shopping_cart") or (True, "", "", {})))
    monkeypatch.setattr(data_scripts, "run_order_quote_script", lambda env, variables: (calls.append("order_quote") or (True, "", "", {"order_sn": "ORDER-5"})))
    monkeypatch.setattr(data_scripts, "run_balance_payment_script", lambda env, variables: (calls.append("order_balance") or (True, "", "", {"payment_type": "balance", "order_sn": "ORDER-5"})))
    monkeypatch.setattr(data_scripts, "run_purchase_to_shelf_script", lambda env, variables: (calls.append("purchase_to_shelf") or (True, "", "", {"order_detail_id": "DETAIL-5"})))
    monkeypatch.setattr(data_scripts, "run_warehouse_delivery_script", lambda env, variables: (calls.append("warehouse_delivery") or (True, "", "", {"porder_sn": "PORDER-5"})))
    monkeypatch.setattr(
        data_scripts,
        "run_porder_balance_payment_script",
        lambda env, variables: (calls.append("porder_balance") or (False, "余额不足", "", {"payment_type": "balance", "porder_sn": "PORDER-5", "reason": "余额不足"})),
    )

    def porder_bank(env, variables):
        calls.append("porder_bank")
        assert variables["finance_confirm"] is True
        return True, "", "", {"payment_type": "bank", "porder_sn": "PORDER-5", "serial_number": "PSER-5"}

    monkeypatch.setattr(data_scripts, "run_porder_bank_payment_script", porder_bank)

    passed, _, _, summary = data_scripts.run_full_flow_script(full_flow_env(), {})

    assert passed is True
    assert calls[-2:] == ["porder_balance", "porder_bank"]
    assert summary["current_node"] == "full_complete"


def test_resume_order_flow_resumes_by_order_status(monkeypatch):
    patch_full_flow_report(monkeypatch)
    state = {"status": 20}
    calls = []

    def detect(env, variables, order_sn, log):
        status = state["status"]
        detected = {
            20: "order_translated",
            21: "order_confirmed",
            22: "order_offered",
            30: "order_offered",
        }[status]
        return True, {
            "order_sn": order_sn,
            "order_status": status,
            "detected_start_node": detected,
            "order_data": {"status": status, "order_sn": order_sn, "order_detail": [{"id": "DETAIL-1", "num": 1}]},
        }

    def backend(base_url, timeout, variables, order_sn, item_quantity, log, order_data):
        calls.append(f"backend:{state['status']}")
        assert state["status"] in (20, 21, 22)
        assert order_data["status"] == state["status"]
        return True, {"order_sn": order_sn, "current_node": detect(None, variables, order_sn, log)[1]["detected_start_node"], "backend_passed": True}

    def pay(env, variables, porder=False):
        calls.append("pay")
        assert porder is False
        assert variables["order_sn"] == "ORDER-RESUME"
        return True, "", "pay-report", {"payment_type": "balance", "order_sn": "ORDER-RESUME"}

    def shelf(env, variables):
        calls.append("shelf")
        assert variables["order_sn"] == "ORDER-RESUME"
        assert variables["link_quote_balance_before_shelf"] is False
        assert variables["auto_quote_and_pay"] is False
        return True, "", "shelf-report", {"order_sn": "ORDER-RESUME", "purchase_no": "PNO-RESUME", "order_detail_id": "DETAIL-1"}

    def delivery(env, variables):
        calls.append("delivery")
        assert variables["order_detail_id"] == "DETAIL-1"
        return True, "", "delivery-report", {"order_sn": "ORDER-RESUME", "porder_sn": "PORDER-RESUME", "current_node": "porder_offered"}

    monkeypatch.setattr(data_scripts, "_detect_resume_order_state", detect)
    monkeypatch.setattr(data_scripts, "_run_backend_order_flow_resume", backend)
    monkeypatch.setattr(data_scripts, "_payment_with_bank_fallback", pay)
    monkeypatch.setattr(data_scripts, "run_purchase_to_shelf_script", shelf)
    monkeypatch.setattr(data_scripts, "run_warehouse_delivery_script", delivery)

    for status in (20, 21, 22, 30):
        state["status"] = status
        calls.clear()
        passed, _, _, summary = data_scripts.run_resume_order_flow_script(
            full_flow_env(),
            {"order_sn": "ORDER-RESUME", "stop_after_node": "porder_offered"},
        )

        assert passed is True
        assert summary["current_node"] == "porder_offered"
        assert summary["detected_start_node"] == ("order_offered" if status in (22, 30) else {20: "order_translated", 21: "order_confirmed"}[status])
        assert summary["order_sn"] == "ORDER-RESUME"
        assert summary["porder_sn"] == "PORDER-RESUME"
        if status == 30:
            assert calls == ["pay", "shelf", "delivery"]
            assert any(item["node"] == "order_offered" for item in summary["skipped_nodes"])
        else:
            assert calls == [f"backend:{status}", "pay", "shelf", "delivery"]


def test_resume_order_flow_pending_purchase_skips_order_quote_and_payment(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    def detect(env, variables, order_sn, log):
        return True, {
            "order_sn": order_sn,
            "order_status": 40,
            "detected_start_node": "pending_purchase",
            "purchase_items": [{"id": "PUR-1", "statusName": "待拍下"}],
            "purchase_selected_count": 1,
        }

    def shelf(env, variables):
        calls.append("shelf")
        assert variables["order_sn"] == "ORDER-PENDING"
        return True, "", "shelf-report", {"order_sn": "ORDER-PENDING", "purchase_no": "PNO-PENDING", "order_detail_id": "DETAIL-PENDING"}

    def delivery(env, variables):
        calls.append("delivery")
        assert variables["order_detail_id"] == "DETAIL-PENDING"
        return True, "", "delivery-report", data_scripts._paused_summary("porder_offered", {"porder_sn": "PORDER-PENDING", "order_sn": "ORDER-PENDING"})

    monkeypatch.setattr(data_scripts, "_detect_resume_order_state", detect)
    monkeypatch.setattr(data_scripts, "_run_backend_order_flow_resume", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("backend quote should be skipped")))
    monkeypatch.setattr(data_scripts, "_payment_with_bank_fallback", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("order payment should be skipped")))
    monkeypatch.setattr(data_scripts, "run_purchase_to_shelf_script", shelf)
    monkeypatch.setattr(data_scripts, "run_warehouse_delivery_script", delivery)

    passed, _, _, summary = data_scripts.run_resume_order_flow_script(
        full_flow_env(),
        {"order_sn": "ORDER-PENDING", "stop_after_node": "porder_offered"},
    )

    assert passed is True
    assert calls == ["shelf", "delivery"]
    assert summary["paused"] is True
    assert summary["current_node"] == "porder_offered"
    assert summary["detected_start_node"] == "pending_purchase"
    assert summary["order_sn"] == "ORDER-PENDING"
    assert summary["porder_sn"] == "PORDER-PENDING"
    assert any(item["node"] == "order_paid" for item in summary["skipped_nodes"])


def test_detect_resume_order_flow_shelf_stored_from_order_status(monkeypatch):
    monkeypatch.setattr(data_scripts, "_admin_session_from", lambda variables: SimpleNamespace(headers={}))
    monkeypatch.setattr(data_scripts, "_admin_login", lambda session, base_url, variables, timeout: ({"success": True, "code": 0}, "TOKEN"))
    monkeypatch.setattr(
        data_scripts,
        "_order_detail_data",
        lambda session, base_url, variables, order_sn, timeout: (
            {"success": True, "code": 0},
            {"order_sn": order_sn, "status": 60, "order_detail": [{"id": "DETAIL-STORED", "statusName": "待发货"}]},
        ),
    )
    monkeypatch.setattr(data_scripts, "_post_admin_form", lambda *args, **kwargs: {"success": True, "code": 0, "data": []})

    passed, summary = data_scripts._detect_resume_order_state(full_flow_env(), {}, "ORDER-STORED", {})

    assert passed is True
    assert summary["detected_start_node"] == "shelf_stored"
    assert summary["order_detail_id"] == "DETAIL-STORED"
    assert summary["order_detail_ids"] == ["DETAIL-STORED"]


def test_detect_resume_order_flow_completed_from_order_status_80(monkeypatch):
    monkeypatch.setattr(data_scripts, "_admin_session_from", lambda variables: SimpleNamespace(headers={}))
    monkeypatch.setattr(data_scripts, "_admin_login", lambda session, base_url, variables, timeout: ({"success": True, "code": 0}, "TOKEN"))
    monkeypatch.setattr(
        data_scripts,
        "_order_detail_data",
        lambda session, base_url, variables, order_sn, timeout: (
            {"success": True, "code": 0},
            {"order_sn": order_sn, "status": 80, "order_detail": [{"id": "DETAIL-SHIPPED", "status": 80, "statusName": "\u53d1\u8d27\u5b8c\u4e86"}]},
        ),
    )
    monkeypatch.setattr(data_scripts, "_post_admin_form", lambda *args, **kwargs: {"success": True, "code": 0, "data": []})

    passed, summary = data_scripts._detect_resume_order_state(full_flow_env(), {}, "ORDER-SHIPPED", {})

    assert passed is True
    assert summary["detected_start_node"] == "porder_shipped"
    assert summary["order_detail_id"] == "DETAIL-SHIPPED"


def test_resume_order_flow_completed_order_does_not_repeat_mutations(monkeypatch):
    patch_full_flow_report(monkeypatch)
    monkeypatch.setattr(
        data_scripts,
        "_detect_resume_order_state",
        lambda env, variables, order_sn, log: (
            True,
            {
                "order_sn": order_sn,
                "order_status": 80,
                "detected_start_node": "porder_shipped",
                "order_detail_id": "DETAIL-SHIPPED",
                "order_detail_ids": ["DETAIL-SHIPPED"],
            },
        ),
    )

    def unexpected_mutation(*args, **kwargs):
        raise AssertionError("completed order must not repeat mutations")

    monkeypatch.setattr(data_scripts, "_run_backend_order_flow_resume", unexpected_mutation)
    monkeypatch.setattr(data_scripts, "_payment_with_bank_fallback", unexpected_mutation)
    monkeypatch.setattr(data_scripts, "run_purchase_to_shelf_script", unexpected_mutation)
    monkeypatch.setattr(data_scripts, "run_warehouse_delivery_script", unexpected_mutation)
    monkeypatch.setattr(data_scripts, "run_porder_shipment_script", unexpected_mutation)

    passed, _, _, summary = data_scripts.run_resume_order_flow_script(
        full_flow_env(),
        {"order_sn": "ORDER-SHIPPED", "stop_after_node": "porder_shipped"},
    )

    assert passed is True
    assert summary["current_node"] == "porder_shipped"
    assert summary["detected_start_node"] == "porder_shipped"
    assert summary["order_sn"] == "ORDER-SHIPPED"


def test_shelf_type_set_is_normalized_to_array_for_wms_interface():
    from app.data_scripts.purchase import _normalize_shelf_type_set

    assert _normalize_shelf_type_set("1,3") == [1, 3]
    assert _normalize_shelf_type_set("1，3") == [1, 3]
    assert _normalize_shelf_type_set("[1,3]") == [1, 3]
    assert _normalize_shelf_type_set([1, "3"]) == [1, 3]


def test_order_status_60_with_checking_details_is_not_shelf_stored():
    assert data_scripts._order_ready_for_warehouse_delivery(
        60,
        {"order_detail": [{"id": "DETAIL-CHECKING", "status": 4, "statusName": "核查中"}]},
    ) is False


def test_order_status_60_requires_all_details_to_be_shelf_stored():
    assert data_scripts._order_ready_for_warehouse_delivery(
        60,
        {
            "order_detail": [
                {"id": "DETAIL-STORED", "statusName": "待发货"},
                {"id": "DETAIL-CHECKING", "statusName": "核查中"},
            ]
        },
    ) is False


def test_resume_order_flow_shelf_stored_skips_shelf_and_runs_delivery(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    def detect(env, variables, order_sn, log):
        return True, {
            "order_sn": order_sn,
            "order_status": 60,
            "detected_start_node": "shelf_stored",
            "order_detail_id": "DETAIL-STORED",
            "order_detail_ids": ["DETAIL-STORED"],
        }

    def delivery(env, variables):
        calls.append("delivery")
        assert variables["order_sn"] == "ORDER-STORED"
        assert variables["order_detail_id"] == "DETAIL-STORED"
        assert variables["order_detail_ids"] == ["DETAIL-STORED"]
        return True, "", "delivery-report", {"order_sn": "ORDER-STORED", "porder_sn": "PORDER-STORED", "current_node": "porder_offered"}

    monkeypatch.setattr(data_scripts, "_detect_resume_order_state", detect)
    monkeypatch.setattr(data_scripts, "_run_backend_order_flow_resume", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("backend quote should be skipped")))
    monkeypatch.setattr(data_scripts, "_payment_with_bank_fallback", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("order payment should be skipped")))
    monkeypatch.setattr(data_scripts, "run_purchase_to_shelf_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("shelf should be skipped")))
    monkeypatch.setattr(data_scripts, "run_warehouse_delivery_script", delivery)

    passed, _, _, summary = data_scripts.run_resume_order_flow_script(
        full_flow_env(),
        {"order_sn": "ORDER-STORED", "stop_after_node": "porder_offered"},
    )

    assert passed is True
    assert calls == ["delivery"]
    assert summary["current_node"] == "porder_offered"
    assert summary["detected_start_node"] == "shelf_stored"
    assert summary["order_sn"] == "ORDER-STORED"
    assert summary["porder_sn"] == "PORDER-STORED"
    assert any(item["node"] == "shelf_stored" for item in summary["skipped_nodes"])


def test_resume_order_flow_endpoint_returns_summary(monkeypatch):
    def fake_resume(env, variables):
        assert variables["order_sn"] == "ORDER-ENDPOINT"
        return True, "resume-log", "resume-report", {
            "current_node": "porder_offered",
            "detected_start_node": "order_offered",
            "order_sn": "ORDER-ENDPOINT",
            "porder_sn": "PORDER-ENDPOINT",
        }

    monkeypatch.setattr(data_script_router, "run_resume_order_flow_script", fake_resume)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        _, env = create_project_env(client, headers, name="resume-order-flow-endpoint-project")
        response = client.post(
            "/api/data-scripts/resume-order-flow",
            headers=headers,
            json={
                "env_id": env["id"],
                "variables": {
                    "order_sn": "ORDER-ENDPOINT",
                    "backend_account": "order-reader",
                    "backend_password": "test-secret",
                },
            },
        )

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["current_node"] == "porder_offered"
    assert summary["detected_start_node"] == "order_offered"
    assert summary["order_sn"] == "ORDER-ENDPOINT"
    assert summary["porder_sn"] == "PORDER-ENDPOINT"


def test_resume_order_flow_can_continue_through_porder_shipment(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    monkeypatch.setattr(
        data_scripts,
        "_detect_resume_order_state",
        lambda env, variables, order_sn, log: (
            True,
            {
                "order_sn": order_sn,
                "order_status": 60,
                "detected_start_node": "shelf_stored",
                "order_detail_id": "DETAIL-SHIP",
                "order_detail_ids": ["DETAIL-SHIP"],
            },
        ),
    )
    monkeypatch.setattr(
        data_scripts,
        "run_warehouse_delivery_script",
        lambda env, variables: (
            calls.append("delivery")
            or (True, "delivery-log", "delivery-report", {"order_sn": "ORDER-SHIP", "porder_sn": "PORDER-SHIP"})
        ),
    )

    def pay(env, variables, porder=False):
        calls.append("porder_pay")
        assert porder is True
        return True, "pay-log", "pay-report", {"payment_type": "balance", "porder_sn": "PORDER-SHIP"}

    def shipment(env, variables):
        calls.append("shipment")
        return True, "shipment-log", "shipment-report", {"porder_sn": "PORDER-SHIP", "current_node": "porder_shipped"}

    monkeypatch.setattr(data_scripts, "_payment_with_bank_fallback", pay)
    monkeypatch.setattr(data_scripts, "run_porder_shipment_script", shipment)

    passed, _, _, summary = data_scripts.run_resume_order_flow_script(
        full_flow_env(),
        {"order_sn": "ORDER-SHIP", "stop_after_node": "porder_shipped"},
    )

    assert passed is True
    assert calls == ["delivery", "porder_pay", "shipment"]
    assert summary["current_node"] == "porder_shipped"
    assert summary["porder_sn"] == "PORDER-SHIP"


def test_resume_porder_flow_porder_paid_runs_payment(monkeypatch):
    captured = {}
    calls = []

    def fake_report(name, *args, **kwargs):
        captured["report_name"] = name
        return "mock-report.json"

    def detect(env, variables, porder_sn, log):
        return True, {"porder_sn": porder_sn, "detected_start_node": "porder_wait_offer"}

    def backend(base_url, timeout, variables, porder_sn, log, detected_start_node):
        calls.append("backend")
        assert detected_start_node == "porder_wait_offer"
        return True, {"backend_passed": True, "current_node": "porder_offered", "porder_sn": porder_sn}

    def pay(env, variables, porder=False):
        calls.append("pay")
        assert porder is True
        assert variables["porder_sn"] == "PORDER-PAID"
        assert variables["run_backend_porder_flow"] is False
        return True, "", "pay-report", {"payment_type": "balance", "porder_sn": "PORDER-PAID", "pay_amount": "1"}

    monkeypatch.setattr(data_scripts, "write_allure_result", fake_report)
    monkeypatch.setattr(data_scripts, "_detect_resume_porder_state", detect)
    monkeypatch.setattr(data_scripts, "_run_backend_porder_flow_resume", backend)
    monkeypatch.setattr(data_scripts, "_payment_with_bank_fallback", pay)

    passed, _, _, summary = data_scripts.run_resume_porder_flow_script(
        full_flow_env(),
        {"porder_sn": "PORDER-PAID", "stop_after_node": "porder_paid"},
    )

    assert passed is True
    assert calls == ["backend", "pay"]
    assert captured["report_name"] == data_scripts.RESUME_PORDER_FLOW_SCRIPT_NAME
    assert summary["paused"] is False
    assert summary["current_node"] == "porder_paid"
    assert summary["porder_sn"] == "PORDER-PAID"
    assert [item["node"] for item in summary["steps"]] == ["porder_offered", "porder_paid"]


def test_resume_porder_flow_paid_state_runs_shipment_without_repaying(monkeypatch):
    calls = []

    monkeypatch.setattr(data_scripts, "write_allure_result", lambda *args, **kwargs: "mock-report.json")
    monkeypatch.setattr(
        data_scripts,
        "_detect_resume_porder_state",
        lambda env, variables, porder_sn, log: (
            True,
            {"porder_sn": porder_sn, "detected_start_node": "porder_paid"},
        ),
    )
    monkeypatch.setattr(
        data_scripts,
        "_run_backend_porder_flow_resume",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("backend flow should be skipped")),
    )
    monkeypatch.setattr(
        data_scripts,
        "_payment_with_bank_fallback",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("payment should not run twice")),
    )

    def shipment(env, variables):
        calls.append("shipment")
        assert variables["porder_sn"] == "PORDER-SHIP"
        return True, "shipment-log", "shipment-report", {"porder_sn": "PORDER-SHIP", "current_node": "porder_shipped"}

    monkeypatch.setattr(data_scripts, "run_porder_shipment_script", shipment)

    passed, _, _, summary = data_scripts.run_resume_porder_flow_script(
        full_flow_env(),
        {"porder_sn": "PORDER-SHIP", "stop_after_node": "porder_shipped"},
    )

    assert passed is True
    assert calls == ["shipment"]
    assert summary["current_node"] == "porder_shipped"
    assert summary["porder_sn"] == "PORDER-SHIP"
    assert summary["steps"][-1]["node"] == "porder_shipped"


def test_porder_status_text_detects_paid_and_shipped_nodes():
    assert data_scripts._porder_node_from_status_texts(["待出货"]) == "porder_paid"
    assert data_scripts._porder_node_from_status_texts(["已发出"]) == "porder_shipped"
    assert data_scripts._porder_node_from_status_texts(["已出货"]) == "porder_shipped"


def test_detect_resume_porder_state_uses_detail_status_text(monkeypatch):
    monkeypatch.setattr(data_scripts, "_admin_session_from", lambda variables: SimpleNamespace(headers={}))
    monkeypatch.setattr(data_scripts, "_admin_login", lambda session, base_url, variables, timeout: ({"success": True, "code": 0}, "TOKEN"))
    monkeypatch.setattr(
        data_scripts,
        "_porder_detail_payload",
        lambda session, base_url, variables, porder_sn, timeout, retries=4: (
            {"success": True, "code": 0},
            [{"id": "DETAIL-1", "statusName": "待报价"}],
        ),
    )
    monkeypatch.setattr(
        data_scripts,
        "_post_admin_urlencoded",
        lambda session, base_url, path, fields, timeout: {"success": True, "code": 0, "data": []},
    )

    detected, summary = data_scripts._detect_resume_porder_state(
        full_flow_env(),
        {},
        "PORDER-STATUS",
        {},
    )

    assert detected is True
    assert summary["status_detected_node"] == "porder_wait_offer"
    assert summary["detected_start_node"] == "porder_wait_offer"


def test_full_flow_endpoint_returns_summary(monkeypatch):
    def fake_full_flow(env, variables):
        assert variables["stop_after_node"] == "pending_purchase"
        return True, "full-log", "full-report", {"current_node": "pending_purchase", "paused": True, "order_sn": "ORDER-ENDPOINT"}

    monkeypatch.setattr(data_script_router, "run_full_flow_script", fake_full_flow)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        _, env = create_project_env(client, headers, name="full-flow-endpoint-project")
        response = client.post(
            "/api/data-scripts/full-flow",
            headers=headers,
            json={
                "env_id": env["id"],
                "variables": {
                    "stop_after_node": "pending_purchase",
                    "backend_account": "order-reader",
                    "backend_password": "test-secret",
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["summary"]["current_node"] == "pending_purchase"
    assert response.json()["summary"]["order_sn"] == "ORDER-ENDPOINT"


def test_requirement_pack_impact_data_check_and_conclusion(monkeypatch):
    def fake_proxy(method, url, headers, body, timeout):
        assert method == "GET"
        assert "order/detail" in url
        return FakeResponse(200, {"data": {"amount": "12.3"}})

    monkeypatch.setattr(main, "guarded_proxy_request", fake_proxy)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        project = client.post("/api/projects", headers=headers, json={"name": "requirement-pack-project", "desc": ""}).json()
        old_task = client.post(
            "/api/functional-tasks",
            headers=headers,
            json={
                "project_id": project["id"],
                "iteration_name": "订单金额历史需求",
                "target_url": "https://example.test/orders",
                "requirement_text": "订单金额状态",
            },
        ).json()
        new_task = client.post(
            "/api/functional-tasks",
            headers=headers,
            json={
                "project_id": project["id"],
                "iteration_name": "订单金额状态改造",
                "target_url": "https://example.test/orders/detail",
                "requirement_text": "验证订单金额和状态流转正确",
            },
        ).json()

        db = SessionLocal()
        try:
            db.add(
                main.FunctionalCase(
                    task_id=old_task["id"],
                    title="订单金额状态历史回归",
                    precondition="",
                    steps="查看订单金额状态",
                    expected="金额状态正确",
                    category="数据结果",
                    priority="P1",
                    automation_status="draft",
                    test_result="failed",
                    ui_case_id=None,
                    create_time=main.datetime.now(),
                )
            )
            db.add(
                main.FunctionalCase(
                    task_id=new_task["id"],
                    title="订单金额状态主流程",
                    precondition="",
                    steps="提交订单并查看金额",
                    expected="金额状态正确",
                    category="数据结果",
                    priority="P0",
                    automation_status="draft",
                    test_result="passed",
                    ui_case_id=None,
                    create_time=main.datetime.now(),
                )
            )
            db.commit()
        finally:
            db.close()

        impact_resp = client.post(f"/api/functional-tasks/{new_task['id']}/impact-items/analyze", headers=headers)
        assert impact_resp.status_code == 200
        assert impact_resp.json()["created"] >= 1
        impact_id = impact_resp.json()["items"][0]["id"]

        rule_resp = client.post(
            f"/api/functional-tasks/{new_task['id']}/data-check-rules",
            headers=headers,
            json={
                "rule_name": "订单金额页面/API一致",
                "check_type": "amount_quantity",
                "page_value": "12.30",
                "api_method": "GET",
                "api_url": "/order/detail",
                "api_value_path": "json.data.amount",
            },
        )
        assert rule_resp.status_code == 200
        rule_id = rule_resp.json()["rule"]["id"]

        run_resp = client.post(f"/api/functional-data-check-rules/{rule_id}/execute", headers=headers)
        assert run_resp.status_code == 200
        assert run_resp.json()["result"]["result"] == "passed"

        conclusion_resp = client.get(f"/api/functional-tasks/{new_task['id']}/conclusion", headers=headers)
        assert conclusion_resp.status_code == 200
        assert conclusion_resp.json()["conclusion"]["decision"] == "ready"

        failed_impact = client.put(
            f"/api/functional-impact-items/{impact_id}",
            headers=headers,
            json={"test_result": "failed"},
        )
        assert failed_impact.status_code == 200
        risky_resp = client.get(f"/api/functional-tasks/{new_task['id']}/conclusion", headers=headers)
        assert risky_resp.json()["conclusion"]["decision"] == "risky"

        update_rule = client.put(
            f"/api/functional-data-check-rules/{rule_id}",
            headers=headers,
            json={"page_value": "15.00"},
        )
        assert update_rule.status_code == 200
        failed_check = client.post(f"/api/functional-data-check-rules/{rule_id}/execute", headers=headers)
        assert failed_check.json()["result"]["result"] == "failed"
        blocked_resp = client.get(f"/api/functional-tasks/{new_task['id']}/conclusion", headers=headers)
        assert blocked_resp.json()["conclusion"]["decision"] == "not_recommended"
