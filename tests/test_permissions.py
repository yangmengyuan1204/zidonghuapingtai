import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace

TEST_DB = Path(__file__).resolve().parent / "test_platform.db"
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "admin123"
os.environ["SECRET_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient

import app.executors as executors
import app.data_scripts as data_scripts
import app.main as main
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
                    "backend_password": "keep-backend-password",
                    "client_tool": "1",
                },
            },
        )

    assert response.status_code == 200
    assert calls[0]["customer_id"] == "50"
    assert calls[0]["customer_ids"] == ["50"]
    assert calls[0]["account"] == "userID/50In"
    assert calls[0]["password"] == "raku@123456``"
    assert calls[0]["backend_password"] == "keep-backend-password"


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
    assert variables["password"] == "raku@123456``"
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


def test_full_flow_runs_nodes_in_order_and_passes_shared_numbers(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    def cart(env, variables):
        calls.append("shopping_cart")
        assert variables["stop_after_node"] == "full_complete"
        assert isinstance(variables["_runtime"], data_scripts.DataScriptRuntime)
        assert variables["sleep"] == 0
        assert variables["cart_verify_mode"] == "final"
        assert variables["cart_edit_workers"] == 4
        assert variables["order_shop_count"] == 1
        assert variables["order_per_shop"] == 3
        assert variables["order_item_count"] == 3
        assert variables["per_shop"] >= 3
        return True, "cart-log", "cart-report", {"added_total": 2}

    def quote(env, variables):
        calls.append("order_quote")
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

    monkeypatch.setattr(data_scripts, "run_shopping_cart_script", cart)
    monkeypatch.setattr(data_scripts, "run_order_quote_script", quote)
    monkeypatch.setattr(data_scripts, "run_balance_payment_script", balance)
    monkeypatch.setattr(data_scripts, "run_bank_payment_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bank fallback not expected")))
    monkeypatch.setattr(data_scripts, "run_purchase_to_shelf_script", shelf)
    monkeypatch.setattr(data_scripts, "run_warehouse_delivery_script", delivery)
    monkeypatch.setattr(data_scripts, "run_porder_balance_payment_script", porder_balance)
    monkeypatch.setattr(data_scripts, "run_porder_bank_payment_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("porder bank fallback not expected")))

    passed, _, _, summary = data_scripts.run_full_flow_script(full_flow_env(), {"stop_after_node": "full_complete", "warehouse_sku_count": 3})

    assert passed is True
    assert calls == ["shopping_cart", "order_quote", "order_balance", "purchase_to_shelf", "warehouse_delivery", "porder_balance"]
    assert summary["current_node"] == "full_complete"
    assert summary["order_sn"] == "ORDER-1"
    assert summary["purchase_no"] == "PNO-1"
    assert summary["porder_sn"] == "PORDER-1"
    assert "duration_ms" in summary
    assert "step_timings" in summary
    assert summary["node_results"][0]["node"] == "shopping_cart"
    assert summary["node_results"][-1]["node"] == "full_complete"
    assert all(item["status"] == "completed" for item in summary["node_results"])


def test_full_flow_pauses_at_pending_purchase(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    monkeypatch.setattr(data_scripts, "run_shopping_cart_script", lambda env, variables: (calls.append("shopping_cart") or (True, "", "", {})))
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
    assert calls == ["shopping_cart", "order_quote", "order_balance", "purchase_to_shelf"]
    assert summary["paused"] is True
    assert summary["current_node"] == "pending_purchase"
    node_status = {item["node"]: item["status"] for item in summary["node_results"]}
    assert node_status["order_paid"] == "completed"
    assert node_status["pending_purchase"] == "paused"
    assert node_status["purchase_no_saved"] == "pending"


def test_full_flow_balance_insufficient_uses_bank_payment(monkeypatch):
    patch_full_flow_report(monkeypatch)
    calls = []

    monkeypatch.setattr(data_scripts, "run_shopping_cart_script", lambda env, variables: (calls.append("shopping_cart") or (True, "", "", {})))
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
    assert "order_bank" in calls
    assert calls.index("order_bank") < calls.index("purchase_to_shelf")
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
    assert calls == ["shopping_cart", "order_quote", "order_balance"]
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


def test_full_flow_endpoint_returns_summary(monkeypatch):
    def fake_full_flow(env, variables):
        assert variables["stop_after_node"] == "pending_purchase"
        return True, "full-log", "full-report", {"current_node": "pending_purchase", "paused": True, "order_sn": "ORDER-ENDPOINT"}

    monkeypatch.setattr(main, "run_full_flow_script", fake_full_flow)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        _, env = create_project_env(client, headers, name="full-flow-endpoint-project")
        response = client.post(
            "/api/data-scripts/full-flow",
            headers=headers,
            json={"env_id": env["id"], "variables": {"stop_after_node": "pending_purchase"}},
        )

    assert response.status_code == 200
    assert response.json()["summary"]["current_node"] == "pending_purchase"
    assert response.json()["summary"]["order_sn"] == "ORDER-ENDPOINT"
