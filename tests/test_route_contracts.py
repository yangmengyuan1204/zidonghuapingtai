"""
路由契约测试 - 阶段二拆分安全网

验证所有路由端点的：
1. 路径存在（不返回 404）
2. 方法匹配
3. 鉴权行为不变（未鉴权返回 401，普通用户访问管理员接口返回 403）

搬迁 main.py 路由到 routers/ 时，这些测试必须全部保持绿色。
"""
import atexit
import base64
import json
import os
from pathlib import Path

TEST_DB = Path(__file__).resolve().parent / "test_route_contracts.db"


def _cleanup():
    try:
        TEST_DB.unlink(missing_ok=True)
    except Exception:
        pass


atexit.register(_cleanup)
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "admin123"
os.environ["SECRET_KEY"] = "test-secret-key-route-contracts"

from fastapi.testclient import TestClient

import app.main as main  # noqa: F401  触发 app 初始化
from app.core.utils import init_app
from app.main import app

# 初始化数据库表结构（lifespan 在 TestClient 上下文管理器中才会触发，这里手动初始化）
init_app()

client = TestClient(app)


def test_runtime_route_contract_matches_baseline():
    """重构前后公开路由契约必须完全一致。"""
    expected = json.loads((Path(__file__).with_name("route_contract_expected.json")).read_text(encoding="utf-8-sig"))
    expected_keys = {(item["method"], item["path"]) for item in expected}
    current_keys = set()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        for method in sorted(methods - {"HEAD", "OPTIONS"}):
            current_keys.add((method, path))
    assert current_keys == expected_keys


def _login(username: str, password: str) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


ADMIN_HEADERS = None
USER_HEADERS = None


def _admin_headers() -> dict:
    global ADMIN_HEADERS
    if ADMIN_HEADERS is None:
        ADMIN_HEADERS = _login("admin", "admin123")
    return ADMIN_HEADERS


def _user_headers() -> dict:
    global USER_HEADERS
    if USER_HEADERS is None:
        # 创建普通用户
        client.post(
            "/api/users",
            headers=_admin_headers(),
            json={"username": "user_route_test", "password": "user123", "is_admin": False},
        )
        USER_HEADERS = _login("user_route_test", "user123")
    return USER_HEADERS


# 公开端点（无需鉴权）
PUBLIC_ENDPOINTS = [
    ("get", "/"),
    ("get", "/health"),
    ("post", "/api/auth/login"),
]


# 需鉴权端点（未带 token 应返回 401）
PROTECTED_ENDPOINTS = [
    ("get", "/api/auth/me"),
    ("get", "/api/dashboard"),
    ("get", "/api/users"),
    ("post", "/api/users"),
    ("get", "/api/projects"),
    ("post", "/api/projects"),
    ("get", "/api/envs"),
    ("post", "/api/envs"),
    ("get", "/api/api-cases"),
    ("post", "/api/api-cases"),
    ("get", "/api/ui-cases"),
    ("post", "/api/ui-cases"),
    ("post", "/api/ui-record/sessions"),
    ("get", "/api/ui-record/sessions/missing/events"),
    ("post", "/api/ui-record/sessions/missing/save"),
    ("delete", "/api/ui-record/sessions/missing"),
    ("get", "/api/test-accounts"),
    ("post", "/api/test-accounts"),
    ("get", "/api/action-templates"),
    ("post", "/api/action-templates"),
    ("get", "/api/locator-heal-logs"),
    ("get", "/api/ai-config"),
    ("get", "/api/test-records"),
    ("get", "/api/test-records/1/re-execute"),
    ("post", "/api/test-records/1/re-execute"),
    ("post", "/api/proxy/request"),
]


# 仅管理员可访问的端点（普通用户应返回 403）
ADMIN_ONLY_ENDPOINTS = [
    ("post", "/api/users"),
    ("post", "/api/envs"),
    ("post", "/api/projects"),
    ("post", "/api/ui-record/sessions"),
    ("post", "/api/ui-record/sessions/missing/save"),
    ("delete", "/api/ui-record/sessions/missing"),
    ("get", "/api/users"),
]


def test_public_endpoints_accessible():
    """公开端点无需鉴权即可访问"""
    for method, path in PUBLIC_ENDPOINTS:
        if method == "get":
            r = client.get(path)
        elif method == "post":
            r = client.post(path, json={})
        elif method == "delete":
            r = client.delete(path)
        # 不应返回 404（路径必须存在）
        assert r.status_code != 404, f"{method.upper()} {path} 返回 404，路由不存在"


def test_protected_endpoints_require_auth():
    """受保护端点未鉴权应返回 401，不能是 404"""
    for method, path in PROTECTED_ENDPOINTS:
        if method == "get":
            r = client.get(path)
        elif method == "post":
            r = client.post(path, json={})
        assert r.status_code != 404, f"{method.upper()} {path} 未鉴权返回 404，路由丢失"
        assert r.status_code in (401, 403, 422), f"{method.upper()} {path} 鉴权响应异常: {r.status_code}"


def test_admin_only_endpoints_block_normal_user():
    """管理员接口对普通用户返回 403"""
    for method, path in ADMIN_ONLY_ENDPOINTS:
        if method == "get":
            r = client.get(path, headers=_user_headers())
        elif method == "post":
            r = client.post(path, headers=_user_headers(), json={})
        elif method == "delete":
            r = client.delete(path, headers=_user_headers())
        assert r.status_code == 403, f"{method.upper()} {path} 普通用户应被拒绝，实际: {r.status_code}"


def test_login_and_me():
    """登录 + me 完整流程"""
    headers = _admin_headers()
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


def test_projects_crud_path():
    """projects CRUD 路径完整"""
    headers = _admin_headers()
    # list
    r = client.get("/api/projects", headers=headers)
    assert r.status_code == 200
    # create
    r = client.post("/api/projects", headers=headers, json={"name": "route-contract-test", "desc": ""})
    assert r.status_code in (200, 201)
    pid = r.json()["id"]
    # update
    r = client.put(f"/api/projects/{pid}", headers=headers, json={"name": "renamed", "desc": ""})
    assert r.status_code == 200
    # delete
    r = client.delete(f"/api/projects/{pid}", headers=headers)
    assert r.status_code == 200


def test_envs_crud_path():
    """envs CRUD 路径完整"""
    headers = _admin_headers()
    project = client.post("/api/projects", headers=headers, json={"name": "env-contract-proj", "desc": ""}).json()
    # create
    r = client.post(
        "/api/envs",
        headers=headers,
        json={"project_id": project["id"], "env_name": "test-env", "base_url": "http://x", "global_headers": "{}"},
    )
    assert r.status_code in (200, 201), f"创建 env 失败: {r.text}"
    # list
    r = client.get("/api/envs", headers=headers, params={"project_id": project["id"]})
    assert r.status_code == 200
    client.delete(f"/api/projects/{project['id']}", headers=headers)


def test_ai_config_get():
    """ai-config 读取路径"""
    r = client.get("/api/ai-config", headers=_admin_headers())
    assert r.status_code == 200


def test_locator_heal_logs_list():
    """locator-heal-logs 列表路径"""
    r = client.get("/api/locator-heal-logs", headers=_admin_headers())
    assert r.status_code == 200


def test_test_records_list():
    """test-records 列表路径"""
    r = client.get("/api/test-records", headers=_admin_headers())
    assert r.status_code == 200


def test_action_templates_list():
    """action-templates 列表路径"""
    r = client.get("/api/action-templates", headers=_admin_headers())
    assert r.status_code == 200


def test_test_accounts_list():
    """test-accounts 列表路径"""
    r = client.get("/api/test-accounts", headers=_admin_headers())
    assert r.status_code == 200


def test_dashboard_endpoint():
    """dashboard 路径"""
    r = client.get("/api/dashboard", headers=_admin_headers())
    assert r.status_code == 200
