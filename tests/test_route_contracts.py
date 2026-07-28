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
import subprocess
import textwrap
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


def test_migration_bridge_consumes_initial_legacy_hash():
    """Vue fallback hash must activate legacy views and redirect migrated ones."""
    bridge_path = Path(__file__).resolve().parents[1] / "static" / "migration-bridge.js"
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const source = fs.readFileSync({json.dumps(str(bridge_path))}, 'utf8');

        async function run(hash, migrated, buttonAfterQueries = 0) {{
          let clicked = 0;
          let queryCalls = 0;
          const button = {{ click() {{ clicked += 1; }} }};
          const context = {{
            fetch() {{ return Promise.resolve({{ json() {{ return Promise.resolve({{ migrated }}); }} }}); }},
            document: {{
              addEventListener() {{}},
              querySelector(selector) {{
                queryCalls += 1;
                return selector === '[data-view="dataScripts"]' && queryCalls > buttonAfterQueries ? button : null;
              }},
            }},
            window: {{ location: {{ hash, href: 'UNCHANGED' }} }},
            setTimeout(fn) {{ fn(); return 1; }},
            Set,
          }};
          vm.runInNewContext(source, context);
          await new Promise((resolve) => setImmediate(resolve));
          await new Promise((resolve) => setImmediate(resolve));
          return {{ clicked, href: context.window.location.href, queryCalls }};
        }}

        (async () => {{
          const legacy = await run('#/dataScripts', ['dashboard']);
          const delayed = await run('#/dataScripts', ['dashboard'], 3);
          const migrated = await run('#/dashboard', ['dashboard']);
          const invalid = await run('#/../../dataScripts', ['dashboard']);
          process.stdout.write(JSON.stringify({{ legacy, delayed, migrated, invalid }}));
        }})().catch((error) => {{ console.error(error); process.exit(1); }});
        """
    )
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    behavior = json.loads(result.stdout)
    assert behavior["legacy"] == {"clicked": 1, "href": "UNCHANGED", "queryCalls": 1}
    assert behavior["delayed"] == {"clicked": 1, "href": "UNCHANGED", "queryCalls": 4}
    assert behavior["migrated"] == {"clicked": 0, "href": "/v3/dashboard", "queryCalls": 0}
    assert behavior["invalid"] == {"clicked": 0, "href": "UNCHANGED", "queryCalls": 0}


def test_vue_legacy_agent_integration_assets_are_pinned():
    root = Path(__file__).resolve().parents[1]
    index_source = (root / "static" / "index.html").read_text(encoding="utf-8")
    ordered_assets = [
        "/static/data-agent-contract-editor.js",
        "/static/data-agent-learning-center.js",
        "/static/data-factory-agent.js",
    ]
    positions = [index_source.index(asset) for asset in ordered_assets]
    assert positions == sorted(positions)
    assert "/static/api-harvester.js" in index_source
    assert "/static/migration-bridge.js" in index_source

    record_log_source = (root / "frontend" / "src" / "utils" / "recordLog.js").read_text(encoding="utf-8")
    assert "agent.renderRecordSummary(parsed, escapeHtml)" in record_log_source


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


def test_contract_editor_module_is_loaded_before_agent_module():
    html = Path("static/index.html").read_text(encoding="utf-8")
    editor = html.index("/static/data-agent-contract-editor.js")
    agent = html.index("/static/data-factory-agent.js")
    assert editor < agent


def test_learning_center_module_has_all_four_views():
    source = Path("static/data-agent-learning-center.js").read_text(encoding="utf-8")
    for key in ("samples", "candidates", "rules", "metrics"):
        assert f'data-learning-view="{key}"' in source
    for text in ("学习样本", "规则候选", "生效规则", "命中率"):
        assert text in source


def test_learning_center_displays_rate_with_denominator():
    source = Path("static/data-agent-learning-center.js").read_text(encoding="utf-8")
    assert "verified_count" in source
    assert "pending_count" in source
    assert "first_hit_rate" in source


def test_learning_center_samples_preserve_contract_and_session_provenance():
    source = Path("static/data-agent-learning-center.js").read_text(encoding="utf-8")
    for key in ("instruction", "initial_contract", "final_contract", "source", "session_id", "data_quality"):
        assert key in source


def test_learning_center_module_is_loaded_before_agent_and_opening_is_delegated():
    html = Path("static/index.html").read_text(encoding="utf-8")
    learning_center = html.index("/static/data-agent-learning-center.js")
    agent = html.index("/static/data-factory-agent.js")
    assert learning_center < agent

    source = Path("static/data-factory-agent.js").read_text(encoding="utf-8")
    assert "DataAgentLearningCenter.open" in source
    assert "function renderLearningCenter" not in source


def test_learning_center_and_agent_use_the_same_fresh_cache_version():
    html = Path("static/index.html").read_text(encoding="utf-8")
    learning_src = next(line for line in html.splitlines() if "/static/data-agent-learning-center.js" in line)
    agent_src = next(line for line in html.splitlines() if "/static/data-factory-agent.js" in line)
    expected_version = "v=20260727-learning-center-v2"
    assert expected_version in learning_src
    assert expected_version in agent_src


def test_agent_learning_center_open_errors_are_caught_and_reported():
    source = Path("static/data-factory-agent.js").read_text(encoding="utf-8")
    assert "openLearningCenter().catch" in source
    assert "学习中心打开失败" in source


def test_contract_editor_has_required_actions_and_no_fixed_field_whitelist():
    source = Path("static/data-agent-contract-editor.js").read_text(encoding="utf-8")
    for text in ("重新生成合同", "合同正确", "保存修改", "确认并执行", "恢复推断值"):
        assert text in source
    assert "session.contract_editor.fields" in source
    assert "order_shop_count,order_per_shop" not in source


def _run_node(source: str) -> dict:
    completed = subprocess.run(
        ["node", "-e", source],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(completed.stdout.strip())


def _contract_editor_node_prelude() -> str:
    source = Path("static/data-agent-contract-editor.js").read_text(encoding="utf-8")
    return f"global.window = {{}}; eval({json.dumps(source)});"


def _learning_center_node_prelude() -> str:
    source = Path("static/data-agent-learning-center.js").read_text(encoding="utf-8")
    return f"global.window = {{prompt: () => 'reason'}}; eval({json.dumps(source)});"


def test_learning_center_latest_open_wins_when_overview_responses_are_reordered():
    script = _learning_center_node_prelude() + r"""
function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}
function overview(instruction) {
  return {
    samples: [{id: 1, instruction, initial_contract: {}, final_contract: {}, corrections: [], status: "verified", session_id: instruction}],
    candidates: [], active_rules: [], recent_versions: [], metrics: {days_7: {}, days_30: {}},
  };
}
const dialog = {
  style: {}, _html: "", renderCount: 0, open: false,
  get innerHTML() { return this._html; },
  set innerHTML(value) { this._html = value; this.renderCount += 1; },
  querySelector: () => null, querySelectorAll: () => [],
  showModal() { this.open = true; }, close() {},
};
const requests = [];
const api = (url) => new Promise((resolve) => requests.push({url, resolve}));
(async () => {
  const first = window.DataAgentLearningCenter.open({dialog, api, escapeHtml, showToast() {}, projectId: 1, isAdmin: true});
  const second = window.DataAgentLearningCenter.open({dialog, api, escapeHtml, showToast() {}, projectId: 2, isAdmin: true});
  requests[1].resolve(overview("LATEST_PROJECT"));
  await second;
  const rendersAfterLatest = dialog.renderCount;
  requests[0].resolve(overview("STALE_PROJECT"));
  await first;
  console.log(JSON.stringify({
    latestVisible: dialog.innerHTML.includes("LATEST_PROJECT"),
    staleVisible: dialog.innerHTML.includes("STALE_PROJECT"),
    staleRerendered: dialog.renderCount !== rendersAfterLatest,
    urls: requests.map((item) => item.url),
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""

    assert _run_node(script) == {
        "latestVisible": True,
        "staleVisible": False,
        "staleRerendered": False,
        "urls": [
            "/api/data-scripts/agent/learning/overview?project_id=1",
            "/api/data-scripts/agent/learning/overview?project_id=2",
        ],
    }


def test_learning_center_refresh_clears_detail_and_drops_stale_detail_response():
    script = _learning_center_node_prelude() + r"""
function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}
function overview() {
  return {
    samples: [],
    candidates: [{id: 7, module_key: "order", rule_key: "rule", occurrence_count: 3, status: "pending_review"}],
    active_rules: [], recent_versions: [], metrics: {days_7: {}, days_30: {}},
  };
}
function candidateDetail(marker) {
  return {
    candidate: {status: "pending_review", regression: {}, proposal: {}},
    source_samples: [{id: 1, instruction: marker, corrections: []}], reviews: [],
  };
}
const dialog = {
  style: {}, innerHTML: "", open: false, controls: {},
  querySelector: () => null,
  querySelectorAll(selector) {
    let dataset = {};
    if (selector === "[data-learning-view]") dataset = {learningView: "candidates"};
    else if (selector === "[data-learning-candidate]" && this.innerHTML.includes('data-learning-candidate="7"')) dataset = {learningCandidate: "7"};
    else if (selector !== "#refreshLearningCenter") return [];
    const button = {dataset, addEventListener: (name, handler) => { button.handler = handler; }};
    this.controls[selector] = button;
    return [button];
  },
  showModal() { this.open = true; }, close() {},
};
const detailResolvers = [];
const api = (url) => {
  if (url.includes("/candidates/7")) return new Promise((resolve) => detailResolvers.push(resolve));
  return Promise.resolve(overview());
};
const tick = () => new Promise((resolve) => setImmediate(resolve));
(async () => {
  await window.DataAgentLearningCenter.open({dialog, api, escapeHtml, showToast() {}, projectId: 1, isAdmin: true});
  dialog.controls["[data-learning-view]"].handler();
  dialog.controls["[data-learning-candidate]"].handler();
  detailResolvers[0](candidateDetail("OLD_DETAIL"));
  await tick();
  const hadDetail = dialog.innerHTML.includes("OLD_DETAIL");

  dialog.controls["#refreshLearningCenter"].handler();
  await tick();
  const clearedDetail = !dialog.innerHTML.includes("OLD_DETAIL");

  dialog.controls["[data-learning-candidate]"].handler();
  dialog.controls["#refreshLearningCenter"].handler();
  await tick();
  detailResolvers[1](candidateDetail("STALE_DETAIL"));
  await tick();
  const droppedStale = !dialog.innerHTML.includes("STALE_DETAIL");
  console.log(JSON.stringify({hadDetail, clearedDetail, droppedStale}));
})().catch((error) => { console.error(error); process.exit(1); });
"""

    assert _run_node(script) == {"hadDetail": True, "clearedDetail": True, "droppedStale": True}


def test_learning_center_uses_independent_overview_detail_and_action_tokens():
    source = Path("static/data-agent-learning-center.js").read_text(encoding="utf-8")
    for token in ("overviewToken", "detailToken", "actionToken"):
        assert token in source


def test_approve_refresh_survives_view_and_detail_activity():
    script = _learning_center_node_prelude() + r"""
function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}
function overview(ruleKey, status = "pending_review") {
  return {
    samples: [],
    candidates: [{id: 7, module_key: "order", rule_key: ruleKey, occurrence_count: 3, status}],
    active_rules: [], recent_versions: [], metrics: {days_7: {}, days_30: {}},
  };
}
function candidateDetail(marker) {
  return {
    candidate: {status: "pending_review", regression: {}, proposal: {}},
    source_samples: [{id: 1, instruction: marker, corrections: []}], reviews: [],
  };
}
const dialog = {
  style: {}, innerHTML: "", open: false, controls: {}, nextView: "candidates",
  querySelector: () => null,
  querySelectorAll(selector) {
    let dataset = {};
    if (selector === "[data-learning-view]") dataset = {learningView: this.nextView};
    else if (selector === "[data-learning-candidate]" && this.innerHTML.includes('data-learning-candidate="7"')) dataset = {learningCandidate: "7"};
    else if (selector === "[data-learning-approve]" && this.innerHTML.includes('data-learning-approve="7"')) dataset = {learningApprove: "7"};
    else if (selector !== "#refreshLearningCenter") return [];
    const button = {dataset, addEventListener: (name, handler) => { button.handler = handler; }};
    this.controls[selector] = button;
    return [button];
  },
  showModal() { this.open = true; }, close() {},
};
let overviewCalls = 0;
let resolveRefresh;
let resolveDetail;
const urls = [];
const api = (url) => {
  urls.push(url);
  if (url.includes("/approve")) return Promise.resolve({candidate: {status: "approved"}});
  if (url.includes("/candidates/7")) return new Promise((resolve) => { resolveDetail = resolve; });
  overviewCalls += 1;
  if (overviewCalls === 1) return Promise.resolve(overview("INITIAL_RULE"));
  return new Promise((resolve) => { resolveRefresh = resolve; });
};
const tick = () => new Promise((resolve) => setImmediate(resolve));
(async () => {
  await window.DataAgentLearningCenter.open({dialog, api, escapeHtml, showToast() {}, projectId: 1, isAdmin: true});
  dialog.controls["[data-learning-view]"].handler();
  dialog.controls["[data-learning-approve]"].handler();
  await tick();

  dialog.nextView = "metrics";
  dialog.controls["[data-learning-view]"].dataset.learningView = "metrics";
  dialog.controls["[data-learning-view]"].handler();
  dialog.nextView = "candidates";
  dialog.controls["[data-learning-view]"].dataset.learningView = "candidates";
  dialog.controls["[data-learning-view]"].handler();
  dialog.controls["[data-learning-candidate]"].handler();

  resolveRefresh(overview("APPROVED_RULE", "approved"));
  await tick();
  const refreshedOverviewVisible = dialog.innerHTML.includes("APPROVED_RULE");
  resolveDetail(candidateDetail("STALE_DETAIL"));
  await tick();
  console.log(JSON.stringify({
    refreshedOverviewVisible,
    staleDetailVisible: dialog.innerHTML.includes("STALE_DETAIL"),
    approveCalls: urls.filter((url) => url.includes("/approve")).length,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""

    assert _run_node(script) == {
        "refreshedOverviewVisible": True,
        "staleDetailVisible": False,
        "approveCalls": 1,
    }


def test_contract_editor_submits_only_changes_and_clears_drafts_after_success():
    script = _contract_editor_node_prelude() + r"""
const fields = [
  {name: "offer_price", label: "统一单价", group: "goods_price", value_type: "decimal", editor: "decimal", value: null},
  {name: "offer_unit_prices", label: "逐商品单价", group: "goods_price", value_type: "list[str]", editor: "text", value: ["1", "2"]},
  {name: "order_item_num", label: "购买数量", group: "goods_price", value_type: "int", editor: "number", value: 2},
  {name: "order_sn", label: "订单号", group: "task_scope", value_type: "str", editor: "text", value: "ORDER-1"},
  {name: "customer_ids", label: "客户", group: "task_scope", value_type: "list[str]", editor: "text", value: ["300001", "300002"]},
];
const session = {id: "success", plan_version: 1, status: "awaiting_confirmation", can_confirm: true, contract_editor: {groups: [{key: "task_scope", label: "范围"}, {key: "goods_price", label: "价格"}], fields}};
const controls = [
  {type: "number", value: "", dataset: {contractField: "offer_price"}},
  {type: "text", value: "1, 2", dataset: {contractField: "offer_unit_prices"}},
  {type: "number", value: "2", dataset: {contractField: "order_item_num"}},
  {type: "text", value: "", dataset: {contractField: "order_sn"}},
  {type: "text", value: "300001,300002", dataset: {contractField: "customer_ids"}},
];
const errors = fields.map((field) => ({dataset: {fieldError: field.name}, textContent: ""}));
const listeners = {};
const button = {disabled: false};
const form = {addEventListener: (name, handler) => { listeners[name] = handler; }, querySelector: () => button};
const editor = {dataset: {}};
const container = {
  querySelector(selector) {
    if (selector === "[data-contract-editor]") return editor;
    if (selector === "[data-contract-save-form]") return form;
    return null;
  },
  querySelectorAll(selector) {
    if (selector === "[data-contract-field]") return controls;
    if (selector === "[data-field-error]") return errors;
    return [];
  },
};
let saved = null;
window.DataAgentContractEditor.bind(container, session, {
  escapeHtml: String,
  save: async (changes) => { saved = changes; },
});
(async () => {
  await listeners.submit({preventDefault() {}});
  const html = window.DataAgentContractEditor.render(session, {escapeHtml: String});
  console.log(JSON.stringify({saved, restored: html.includes('value="ORDER-1"')}));
})().catch((error) => { console.error(error); process.exit(1); });
"""

    assert _run_node(script) == {"saved": {"order_sn": ""}, "restored": True}


def test_contract_editor_restores_original_inferred_value_after_manual_edit():
    script = _contract_editor_node_prelude() + r"""
const field = {
  name: "keyword", label: "商品关键词", group: "business", value_type: "str",
  editor: "text", value: "鞋", inferred: false, source: "direct_edit",
  restore_value: "衣服", restore_source: "default", restore_inferred: true,
};
const session = {
  id: "restore", plan_version: 2, status: "awaiting_confirmation", can_confirm: true,
  contract_editor: {groups: [{key: "business", label: "业务参数"}], fields: [field]},
};
const html = window.DataAgentContractEditor.render(session, {escapeHtml: String});
const control = {type: "text", value: "鞋", dataset: {contractField: "keyword"}};
const error = {dataset: {fieldError: "keyword"}, textContent: "旧错误"};
const restoreButton = {
  dataset: {restoreField: "keyword"},
  addEventListener(name, handler) { this.handler = handler; },
};
const editor = {dataset: {}};
const container = {
  querySelector(selector) {
    if (selector === "[data-contract-editor]") return editor;
    return null;
  },
  querySelectorAll(selector) {
    if (selector === "[data-restore-field]") return [restoreButton];
    if (selector === "[data-contract-field]") return [control];
    if (selector === "[data-field-error]") return [error];
    return [];
  },
};
window.DataAgentContractEditor.bind(container, session, {escapeHtml: String});
restoreButton.handler();
console.log(JSON.stringify({
  hasRestore: html.includes('data-restore-field="keyword"'),
  currentValue: html.includes('value="鞋"'),
  restoredValue: control.value,
  clearedError: error.textContent,
}));
"""

    assert _run_node(script) == {
        "hasRestore": True,
        "currentValue": True,
        "restoredValue": "衣服",
        "clearedError": "",
    }


def test_contract_editor_preserves_all_drafts_and_maps_structured_field_errors():
    script = _contract_editor_node_prelude() + r"""
const fields = [
  {name: "order_item_num", label: "购买数量", group: "goods_price", value_type: "int", editor: "number", value: 2},
  {name: "order_sn", label: "订单号", group: "task_scope", value_type: "str", editor: "text", value: "ORDER-1"},
];
const session = {id: "failure", plan_version: 1, status: "awaiting_confirmation", can_confirm: true, contract_editor: {groups: [{key: "task_scope", label: "范围"}, {key: "goods_price", label: "价格"}], fields}};
const controls = [
  {type: "number", value: "0", dataset: {contractField: "order_item_num"}},
  {type: "text", value: "draft-order", dataset: {contractField: "order_sn"}},
];
const errors = fields.map((field) => ({dataset: {fieldError: field.name}, textContent: ""}));
const listeners = {};
const button = {disabled: false};
const form = {addEventListener: (name, handler) => { listeners[name] = handler; }, querySelector: () => button};
const container = {
  querySelector: (selector) => selector === "[data-contract-editor]" ? {dataset: {}} : selector === "[data-contract-save-form]" ? form : null,
  querySelectorAll(selector) {
    if (selector === "[data-contract-field]") return controls;
    if (selector === "[data-field-error]") return errors;
    return [];
  },
};
window.DataAgentContractEditor.bind(container, session, {
  escapeHtml: String,
  save: async () => {
    const error = new Error("合同字段校验失败");
    error.detail = {message: "合同字段校验失败", fields: {order_item_num: "必须是正整数"}};
    throw error;
  },
});
(async () => {
  await listeners.submit({preventDefault() {}});
  const html = window.DataAgentContractEditor.render(session, {escapeHtml: String});
  console.log(JSON.stringify({
    fieldError: errors[0].textContent,
    quantityDraft: html.includes('value="0"'),
    orderDraft: html.includes('value="draft-order"'),
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""

    assert _run_node(script) == {
        "fieldError": "必须是正整数",
        "quantityDraft": True,
        "orderDraft": True,
    }


def test_contract_editor_compares_numeric_text_without_precision_loss():
    script = _contract_editor_node_prelude() + r"""
const fields = [
  {name: "integer_equivalent", label: "等价整数", group: "goods_price", value_type: "int", editor: "number", value: "01"},
  {name: "decimal_equivalent", label: "等价小数", group: "goods_price", value_type: "decimal", editor: "decimal", value: "01.00"},
  {name: "negative_zero", label: "负零", group: "goods_price", value_type: "decimal", editor: "decimal", value: "-0.000"},
  {name: "huge_integer", label: "超大整数", group: "goods_price", value_type: "int", editor: "number", value: "9007199254740992"},
  {name: "precise_decimal", label: "高精度小数", group: "goods_price", value_type: "decimal", editor: "decimal", value: "0.123456789012345678901"},
  {name: "invalid_equivalent", label: "无效等价", group: "goods_price", value_type: "decimal", editor: "decimal", value: " invalid "},
  {name: "invalid_changed", label: "无效变化", group: "goods_price", value_type: "decimal", editor: "decimal", value: "invalid"},
  {name: "cleared_integer", label: "清空整数", group: "goods_price", value_type: "int", editor: "number", value: "7"},
];
const session = {id: "numeric", plan_version: 1, status: "awaiting_confirmation", can_confirm: true, contract_editor: {groups: [{key: "goods_price", label: "价格"}], fields}};
const controls = [
  {type: "number", value: "+001", dataset: {contractField: "integer_equivalent"}},
  {type: "number", value: "1", dataset: {contractField: "decimal_equivalent"}},
  {type: "number", value: "0", dataset: {contractField: "negative_zero"}},
  {type: "number", value: "9007199254740993", dataset: {contractField: "huge_integer"}},
  {type: "number", value: "0.123456789012345678902", dataset: {contractField: "precise_decimal"}},
  {type: "text", value: "invalid", dataset: {contractField: "invalid_equivalent"}},
  {type: "text", value: " invalid-2 ", dataset: {contractField: "invalid_changed"}},
  {type: "number", value: "", dataset: {contractField: "cleared_integer"}},
];
const listeners = {};
const button = {disabled: false};
const form = {addEventListener: (name, handler) => { listeners[name] = handler; }, querySelector: () => button};
const container = {
  querySelector: (selector) => selector === "[data-contract-editor]" ? {dataset: {}} : selector === "[data-contract-save-form]" ? form : null,
  querySelectorAll: (selector) => selector === "[data-contract-field]" ? controls : [],
};
let saved = null;
window.DataAgentContractEditor.bind(container, session, {
  escapeHtml: String,
  save: async (changes) => { saved = changes; },
});
(async () => {
  await listeners.submit({preventDefault() {}});
  console.log(JSON.stringify(saved));
})().catch((error) => { console.error(error); process.exit(1); });
"""

    assert _run_node(script) == {
        "huge_integer": "9007199254740993",
        "precise_decimal": "0.123456789012345678902",
        "invalid_changed": " invalid-2 ",
        "cleared_integer": "",
    }


def test_contract_editor_saves_dirty_fields_before_confirming_new_version():
    script = _contract_editor_node_prelude() + r"""
const field = {name: "order_sn", label: "订单号", group: "task_scope", value_type: "str", editor: "text", value: "OLD"};
const session = {id: "dirty-confirm", plan_version: 1, status: "awaiting_confirmation", can_confirm: true, contract_editor: {groups: [{key: "task_scope", label: "范围"}], fields: [field]}};
const control = {type: "text", value: "NEW", disabled: false, dataset: {contractField: "order_sn"}};
const listeners = {};
const saveButton = {disabled: false};
const confirmButton = {disabled: false, addEventListener: (name, handler) => { listeners.confirm = handler; }};
const correctButton = {disabled: false, addEventListener: (name, handler) => { listeners.correct = handler; }};
const saveForm = {addEventListener: (name, handler) => { listeners.save = handler; }, querySelector: () => saveButton};
const editor = {dataset: {}};
const container = {
  querySelector(selector) {
    if (selector === "[data-contract-editor]") return editor;
    if (selector === "[data-contract-save-form]") return saveForm;
    if (selector === "[data-contract-confirm]") return confirmButton;
    if (selector === "[data-contract-correct]") return correctButton;
    return null;
  },
  querySelectorAll(selector) {
    if (selector === "[data-contract-field]") return [control];
    if (selector === "[data-contract-field], button") return [control, saveButton, confirmButton, correctButton];
    return [];
  },
};
const calls = [];
window.DataAgentContractEditor.bind(container, session, {
  escapeHtml: String,
  save: async (fields, version) => { calls.push(["save", fields, version]); return {plan_version: 2}; },
  confirm: async (version) => { calls.push(["confirm", version]); },
  markCorrect: async () => {},
});
(async () => {
  await listeners.confirm({currentTarget: confirmButton});
  console.log(JSON.stringify(calls));
})().catch((error) => { console.error(error); process.exit(1); });
"""

    assert _run_node(script) == [
        ["save", {"order_sn": "NEW"}, 1],
        ["confirm", 2],
    ]


def test_contract_editor_reuses_in_flight_save_before_confirm():
    script = _contract_editor_node_prelude() + r"""
const field = {name: "order_sn", label: "订单号", group: "task_scope", value_type: "str", editor: "text", value: "OLD"};
const session = {id: "save-race", plan_version: 1, status: "awaiting_confirmation", can_confirm: true, contract_editor: {groups: [{key: "task_scope", label: "范围"}], fields: [field]}};
const control = {type: "text", value: "NEW", disabled: false, dataset: {contractField: "order_sn"}};
const listeners = {};
const saveButton = {disabled: false};
const confirmButton = {disabled: false, addEventListener: (name, handler) => { listeners.confirm = handler; }};
const correctButton = {disabled: false, addEventListener: (name, handler) => { listeners.correct = handler; }};
const saveForm = {addEventListener: (name, handler) => { listeners.save = handler; }, querySelector: () => saveButton};
const editor = {dataset: {}};
const container = {
  querySelector(selector) {
    if (selector === "[data-contract-editor]") return editor;
    if (selector === "[data-contract-save-form]") return saveForm;
    if (selector === "[data-contract-confirm]") return confirmButton;
    if (selector === "[data-contract-correct]") return correctButton;
    return null;
  },
  querySelectorAll(selector) {
    if (selector === "[data-contract-field]") return [control];
    if (selector === "[data-contract-field], button") return [control, saveButton, confirmButton, correctButton];
    return [];
  },
};
let resolveSave;
let saveCalls = 0;
const confirmVersions = [];
window.DataAgentContractEditor.bind(container, session, {
  escapeHtml: String,
  save: () => { saveCalls += 1; return new Promise((resolve) => { resolveSave = resolve; }); },
  confirm: async (version) => { confirmVersions.push(version); },
  markCorrect: async () => {},
});
(async () => {
  const saving = listeners.save({preventDefault() {}});
  const confirming = listeners.confirm({currentTarget: confirmButton});
  await Promise.resolve();
  const before = {saveCalls, confirmVersions: [...confirmVersions]};
  resolveSave({plan_version: 2});
  await Promise.all([saving, confirming]);
  console.log(JSON.stringify({before, after: {saveCalls, confirmVersions}}));
})().catch((error) => { console.error(error); process.exit(1); });
"""

    assert _run_node(script) == {
        "before": {"saveCalls": 1, "confirmVersions": []},
        "after": {"saveCalls": 1, "confirmVersions": [2]},
    }


def test_shared_api_error_retains_structured_detail():
    source = Path("static/app.js").read_text(encoding="utf-8")
    start = source.index("async function api(")
    api_source = source[start:source.index("function sleep(", start)]
    script = """
const state = {token: ""};
const showToast = () => {};
const fetch = async () => ({
  status: 400,
  ok: false,
  statusText: "Bad Request",
  text: async () => JSON.stringify({detail: {message: "合同字段校验失败", fields: {order_item_num: "必须是正整数"}}}),
});
__API_SOURCE__
(async () => {
  try { await api("/contract"); }
  catch (error) { console.log(JSON.stringify({message: error.message, detail: error.detail})); }
})().catch((error) => { console.error(error); process.exit(1); });
""".replace("__API_SOURCE__", api_source)

    assert _run_node(script) == {
        "message": "合同字段校验失败",
        "detail": {
            "message": "合同字段校验失败",
            "fields": {"order_item_num": "必须是正整数"},
        },
    }
