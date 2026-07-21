import time
from datetime import datetime

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import AiConfig
from app.services import requirement_verification as verification_service
from app.services import ui_recording_session


def _headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _project(client: TestClient, headers: dict[str, str], name: str = "需求验证测试项目") -> dict:
    response = client.post("/api/projects", headers=headers, json={"name": name, "desc": ""})
    assert response.status_code == 200
    return response.json()


def _task(client: TestClient, headers: dict[str, str], project_id: int, name: str = "跨境订单金额与状态需求") -> dict:
    response = client.post(
        "/api/requirement-verifications",
        headers=headers,
        json={
            "project_id": project_id,
            "name": name,
            "target_url": "https://example.test/orders",
            "requirement_text": "\n".join(
                [
                    "页面显示订单编号",
                    "前台和后台订单数量保持一致",
                    "提交审核后状态从待审核→已审核",
                    "订单总金额=商品单价*数量+运费-优惠",
                ]
            ),
            "context": "PC网页功能测试",
        },
    )
    assert response.status_code == 200
    return response.json()


def _wait_for_run(client: TestClient, headers: dict[str, str], run_id: int) -> dict:
    run = {}
    for _ in range(80):
        response = client.get(f"/api/requirement-verifications/runs/{run_id}", headers=headers)
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] not in {"queued", "running"}:
            return run
        time.sleep(0.05)
    return run


def _enable_fake_ai() -> None:
    db = SessionLocal()
    try:
        db.add(AiConfig(provider="openai_compatible", base_url="https://ai.example.test", model="fake-model", api_key="", create_time=datetime.now()))
        db.commit()
    finally:
        db.close()


def test_requirement_analysis_generates_traceable_matrix_without_fixed_count():
    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers)
        task = _task(client, headers, project["id"])

        response = client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers)
        assert response.status_code == 200, response.text
        detail = response.json()

        assert detail["analysis_version"] == 1
        assert detail["analysis"]["source"] == "rule"
        assert 4 <= len(detail["items"]) < 20
        assert {item["item_type"] for item in detail["items"]} >= {"page", "data", "state", "amount"}
        assert all(item["source_refs"] for item in detail["items"])
        assert all(item["automation_level"] in {"auto", "supervised", "manual"} for item in detail["items"])


def test_feature_category_supports_multiple_target_pages_and_legacy_primary_url():
    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "多页面功能项目")
        created = client.post(
            "/api/requirement-verifications",
            headers=headers,
            json={
                "project_id": project["id"],
                "name": "订单支付新增多页面功能",
                "target_pages": [
                    {"name": "订单列表", "role": "客服", "url": "https://example.test/orders"},
                    {"name": "订单详情", "role": "买家", "url": "https://example.test/orders/{{order_id}}"},
                    {"name": "支付结果页", "role": "买家", "url": ""},
                ],
                "requirement_text": "订单列表进入详情后发起支付，并在支付结果页显示成功状态。",
                "context": "PC网页功能测试",
            },
        )
        assert created.status_code == 200, created.text
        task = created.json()
        assert task["target_url"] == "https://example.test/orders"
        assert [page["name"] for page in task["target_pages"]] == ["订单列表", "订单详情", "支付结果页"]
        assert task["target_pages"][1]["role"] == "买家"

        analyzed = client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers)
        assert analyzed.status_code == 200, analyzed.text
        assert analyzed.json()["analysis"]["impacted_pages"] == ["订单列表", "订单详情", "支付结果页"]

        listing = client.get(
            f"/api/requirement-verifications?project_id={project['id']}&archived=false",
            headers=headers,
        )
        assert listing.status_code == 200, listing.text
        assert listing.json()[0]["target_pages"][2]["url"] == ""

        updated = client.put(
            f"/api/requirement-verifications/{task['id']}",
            headers=headers,
            json={
                "target_pages": [
                    {"name": "支付确认页", "role": "买家", "url": "https://example.test/payment/confirm"},
                    {"name": "支付结果页", "role": "买家", "url": "https://example.test/payment/result"},
                ]
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["target_url"] == "https://example.test/payment/confirm"
        assert len(updated.json()["target_pages"]) == 2

        legacy = client.post(
            "/api/requirement-verifications",
            headers=headers,
            json={
                "project_id": project["id"],
                "name": "旧版单页面需求",
                "target_url": "https://example.test/legacy",
                "requirement_text": "验证旧页面展示。",
            },
        )
        assert legacy.status_code == 200, legacy.text
        assert legacy.json()["target_pages"] == [{"name": "主要页面", "url": "https://example.test/legacy", "role": ""}]


def test_formula_engine_is_decimal_versioned_and_rejects_code_execution():
    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "金额公式隔离项目")

        created = client.post(
            f"/api/requirement-verifications/projects/{project['id']}/formulas",
            headers=headers,
            json={
                "name": "订单应付日元",
                "expression": "unit_price * quantity + shipping - discount",
                "variables": {"unit_price": "商品单价", "quantity": "数量", "shipping": "运费", "discount": "优惠"},
                "currency": "JPY",
                "scale": 0,
                "rounding_mode": "HALF_UP",
                "rounding_stage": "final",
                "source_refs": ["requirement:amount-rule"],
            },
        )
        assert created.status_code == 200, created.text
        formula = created.json()

        preview = client.post(
            f"/api/requirement-verifications/formulas/{formula['id']}/preview",
            headers=headers,
            json={"unit_price": "12.34", "quantity": 2, "shipping": 5, "discount": 1},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["raw_result"] == "28.68"
        assert preview.json()["expected_amount"] == "29"

        malicious = client.post(
            f"/api/requirement-verifications/projects/{project['id']}/formulas",
            headers=headers,
            json={
                "name": "危险公式",
                "expression": "__import__('os').system('whoami')",
                "variables": {},
                "scale": 2,
                "rounding_mode": "HALF_UP",
                "rounding_stage": "final",
            },
        )
        assert malicious.status_code == 400


def test_confirmed_matrix_executes_page_data_state_and_amount_checks():
    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "完整验证链路项目")
        task = _task(client, headers, project["id"])
        detail = client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers).json()

        formula_response = client.post(
            f"/api/requirement-verifications/projects/{project['id']}/formulas",
            headers=headers,
            json={
                "task_id": task["id"],
                "name": "订单总金额",
                "expression": "unit_price * quantity + shipping - discount",
                "variables": {"unit_price": "单价", "quantity": "数量", "shipping": "运费", "discount": "优惠"},
                "currency": "JPY",
                "scale": 0,
                "rounding_mode": "HALF_UP",
                "rounding_stage": "final",
                "source_refs": ["requirement:line:4"],
            },
        )
        assert formula_response.status_code == 200, formula_response.text
        formula = formula_response.json()
        assert client.post(f"/api/requirement-verifications/formulas/{formula['id']}/confirm", headers=headers).status_code == 200

        configs = {
            "page": {
                "observations": [{"name": "page_title", "source": "literal", "value": "订单详情"}],
                "assertions": [{"left": "page_title", "operator": "eq", "right_value": "订单详情"}],
            },
            "data": {
                "observations": [
                    {"name": "frontend_quantity", "source": "literal", "value": 2},
                    {"name": "backend_quantity", "source": "literal", "value": 2},
                ],
                "assertions": [{"left": "frontend_quantity", "operator": "eq", "right": "backend_quantity"}],
            },
            "state": {
                "observations": [{"name": "actual_status", "source": "literal", "value": "已审核"}],
                "assertions": [{"left": "actual_status", "operator": "eq", "right_value": "已审核"}],
            },
            "amount": {
                "formula_id": formula["id"],
                "observations": [
                    {"name": "unit_price_value", "source": "literal", "value": "12.34"},
                    {"name": "quantity_value", "source": "literal", "value": 2},
                    {"name": "shipping_value", "source": "literal", "value": 5},
                    {"name": "discount_value", "source": "literal", "value": 1},
                    {"name": "actual_amount", "source": "literal", "value": 29},
                ],
                "formula_inputs": {
                    "unit_price": "unit_price_value",
                    "quantity": "quantity_value",
                    "shipping": "shipping_value",
                    "discount": "discount_value",
                },
                "actual_key": "actual_amount",
                "assertions": [],
            },
        }
        selected = []
        for item_type in ("page", "data", "state", "amount"):
            item = next(item for item in detail["items"] if item["item_type"] == item_type)
            response = client.put(
                f"/api/requirement-verifications/items/{item['id']}",
                headers=headers,
                json={"automation_level": "auto", "status": "draft", "config": configs[item_type]},
            )
            assert response.status_code == 200, response.text
            selected.append(item["id"])

        confirmed = client.post(
            f"/api/requirement-verifications/{task['id']}/items/batch-confirm",
            headers=headers,
            json={"item_ids": selected, "confirmed": True},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["confirmed"] == 4

        started = client.post(
            f"/api/requirement-verifications/{task['id']}/runs",
            headers=headers,
            json={"item_ids": selected, "variables": {}, "visible_browser": False},
        )
        assert started.status_code == 200, started.text
        run_id = started.json()["id"]

        run = None
        for _ in range(50):
            response = client.get(f"/api/requirement-verifications/runs/{run_id}", headers=headers)
            assert response.status_code == 200, response.text
            run = response.json()
            if run["status"] not in {"queued", "running"}:
                break
            time.sleep(0.05)

        assert run is not None
        assert run["status"] == "passed"
        assert run["summary"]["counts"] == {"passed": 4}
        amount_result = next(item for item in run["items"] if item["item_id"] == selected[-1])
        assert amount_result["actual"]["calculation"]["expected_amount"] == "29"
        assert amount_result["actual"]["calculation"]["difference"] == "0"


def test_blocked_matrix_item_can_be_confirmed_but_cannot_execute():
    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "阻塞验证项确认项目")
        task = _task(client, headers, project["id"])
        detail = client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers).json()
        item = detail["items"][0]

        blocked = client.put(
            f"/api/requirement-verifications/items/{item['id']}",
            headers=headers,
            json={"status": "blocked"},
        )
        assert blocked.status_code == 200, blocked.text

        confirmed = client.post(
            f"/api/requirement-verifications/{task['id']}/items/batch-confirm",
            headers=headers,
            json={"item_ids": [item["id"]], "confirmed": True},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json() == {"confirmed": 1, "blocked": [item["title"]]}

        saved_item = next(
            row
            for row in client.get(f"/api/requirement-verifications/{task['id']}", headers=headers).json()["items"]
            if row["id"] == item["id"]
        )
        assert saved_item["confirmed"] is True
        assert saved_item["status"] == "blocked"

        started = client.post(
            f"/api/requirement-verifications/{task['id']}/runs",
            headers=headers,
            json={"item_ids": [item["id"]], "variables": {}, "visible_browser": False},
        )
        assert started.status_code == 400
        assert started.json()["detail"] == "没有已确认的可执行验证项"


def test_read_only_data_source_is_project_isolated_and_path_limited():
    with TestClient(app) as client:
        headers = _headers(client)
        first = _project(client, headers, "数据源项目A")
        second = _project(client, headers, "数据源项目B")
        env = client.post(
            "/api/envs",
            headers=headers,
            json={"project_id": first["id"], "env_name": "测试环境", "base_url": "https://example.test", "global_headers": {}, "global_vars": {}, "timeout": 20},
        )
        assert env.status_code == 200, env.text

        wrong_project = client.post(
            f"/api/requirement-verifications/projects/{second['id']}/data-sources",
            headers=headers,
            json={"env_id": env.json()["id"], "name": "错误归属", "allowed_paths": ["/api/orders"]},
        )
        assert wrong_project.status_code == 400

        unsafe_path = client.post(
            f"/api/requirement-verifications/projects/{first['id']}/data-sources",
            headers=headers,
            json={"env_id": env.json()["id"], "name": "危险路径", "allowed_paths": ["https://evil.test/api"]},
        )
        assert unsafe_path.status_code == 400

        created = client.post(
            f"/api/requirement-verifications/projects/{first['id']}/data-sources",
            headers=headers,
            json={"env_id": env.json()["id"], "name": "订单查询", "allowed_paths": ["/api/orders", "/api/order-detail"]},
        )
        assert created.status_code == 200, created.text
        assert created.json()["allowed_methods"] == ["GET", "HEAD"]


def test_verification_mutations_require_admin_role():
    with TestClient(app) as client:
        admin_headers = _headers(client)
        project = _project(client, admin_headers, "验证权限项目")
        created_user = client.post(
            "/api/users",
            headers=admin_headers,
            json={"username": "verification_reader", "password": "reader123", "role": "normal"},
        )
        assert created_user.status_code == 200, created_user.text
        login = client.post("/api/auth/login", json={"username": "verification_reader", "password": "reader123"})
        normal_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        denied = client.post(
            "/api/requirement-verifications",
            headers=normal_headers,
            json={"project_id": project["id"], "name": "不允许创建", "requirement_text": "测试"},
        )
        assert denied.status_code == 403

        listing = client.get(f"/api/requirement-verifications?project_id={project['id']}", headers=normal_headers)
        assert listing.status_code == 200


def test_data_factory_outputs_are_reused_as_verification_variables(monkeypatch):
    calls = []

    def fake_runner(env, variables):
        calls.append({"env_id": env.id, "variables": variables})
        return True, "prepared", "", {"order_no": "ORDER-1001"}

    monkeypatch.setitem(verification_service.SCRIPT_REGISTRY["shopping_cart"], "func", fake_runner)

    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "data factory linkage")
        env_response = client.post(
            "/api/envs",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_name": "verification env",
                "base_url": "https://example.test",
                "global_headers": {},
                "global_vars": {},
                "timeout": 20,
            },
        )
        assert env_response.status_code == 200, env_response.text
        env = env_response.json()
        task = _task(client, headers, project["id"])
        detail = client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers).json()
        item = next(entry for entry in detail["items"] if entry["item_type"] == "page")

        config = {
            "data_setup": {
                "script_type": "shopping_cart",
                "env_id": env["id"],
                "variables": {"sku": "SKU-1"},
            },
            "observations": [{"name": "actual_order_no", "source": "variable", "key": "order_no"}],
            "assertions": [{"left": "actual_order_no", "operator": "eq", "right_value": "ORDER-1001"}],
        }
        updated = client.put(
            f"/api/requirement-verifications/items/{item['id']}",
            headers=headers,
            json={"automation_level": "auto", "status": "draft", "config": config},
        )
        assert updated.status_code == 200, updated.text
        confirmed = client.post(
            f"/api/requirement-verifications/{task['id']}/items/batch-confirm",
            headers=headers,
            json={"item_ids": [item["id"]], "confirmed": True},
        )
        assert confirmed.status_code == 200, confirmed.text

        started = client.post(
            f"/api/requirement-verifications/{task['id']}/runs",
            headers=headers,
            json={"item_ids": [item["id"]], "variables": {}, "visible_browser": False},
        )
        assert started.status_code == 200, started.text
        run_id = started.json()["id"]

        run = None
        for _ in range(50):
            run_response = client.get(f"/api/requirement-verifications/runs/{run_id}", headers=headers)
            assert run_response.status_code == 200, run_response.text
            run = run_response.json()
            if run["status"] not in {"queued", "running"}:
                break
            time.sleep(0.05)

        assert run is not None
        assert run["status"] == "passed"
        assert len(calls) == 1
        assert run["items"][0]["actual"]["observations"]["actual_order_no"] == "ORDER-1001"
        assert run["items"][0]["evidence"]["data_setup"]["outputs"] == {"order_no": "ORDER-1001"}


def test_feature_categories_are_searchable_archivable_and_project_isolated():
    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "日本站")
        other_project = _project(client, headers, "美国站")
        payment = _task(client, headers, project["id"], "订单支付新增XX功能")
        delivery = _task(client, headers, project["id"], "配送单XX改动")
        _task(client, headers, other_project["id"], "订单支付新增XX功能")

        payment_detail = client.post(f"/api/requirement-verifications/{payment['id']}/analyze", headers=headers).json()
        delivery_detail = client.post(f"/api/requirement-verifications/{delivery['id']}/analyze", headers=headers).json()
        assert {item["id"] for item in payment_detail["items"]}.isdisjoint({item["id"] for item in delivery_detail["items"]})
        assert delivery_detail["runs"] == []

        item = next(entry for entry in payment_detail["items"] if entry["item_type"] == "page")
        updated = client.put(
            f"/api/requirement-verifications/items/{item['id']}",
            headers=headers,
            json={
                "automation_level": "auto",
                "status": "draft",
                "config": {
                    "observations": [{"name": "title", "source": "literal", "value": "订单支付"}],
                    "assertions": [{"left": "title", "operator": "eq", "right_value": "订单支付"}],
                },
            },
        )
        assert updated.status_code == 200, updated.text
        assert client.post(
            f"/api/requirement-verifications/{payment['id']}/items/batch-confirm",
            headers=headers,
            json={"item_ids": [item["id"]], "confirmed": True},
        ).status_code == 200
        started = client.post(
            f"/api/requirement-verifications/{payment['id']}/runs",
            headers=headers,
            json={"item_ids": [item["id"]], "variables": {}, "visible_browser": False},
        )
        assert started.status_code == 200, started.text
        run_id = started.json()["id"]
        for _ in range(50):
            run = client.get(f"/api/requirement-verifications/runs/{run_id}", headers=headers).json()
            if run["status"] not in {"queued", "running"}:
                break
            time.sleep(0.05)
        assert run["status"] == "passed"

        project_rows = client.get(
            f"/api/requirement-verifications?project_id={project['id']}",
            headers=headers,
        ).json()
        assert {row["id"] for row in project_rows} == {payment["id"], delivery["id"]}
        payment_row = next(row for row in project_rows if row["id"] == payment["id"])
        assert payment_row["item_count"] == len(payment_detail["items"])
        assert payment_row["result_counts"]["passed"] == 1
        assert payment_row["run_count"] == 1
        assert payment_row["latest_result"] == "passed"

        archived = client.put(
            f"/api/requirement-verifications/{payment['id']}",
            headers=headers,
            json={"is_archived": True},
        )
        assert archived.status_code == 200, archived.text
        assert archived.json()["is_archived"] is True
        assert len(archived.json()["runs"]) == 1

        active_rows = client.get(
            f"/api/requirement-verifications?project_id={project['id']}&archived=false",
            headers=headers,
        ).json()
        assert [row["id"] for row in active_rows] == [delivery["id"]]
        archived_rows = client.get(
            f"/api/requirement-verifications?project_id={project['id']}&keyword=订单支付&status=passed&archived=true",
            headers=headers,
        ).json()
        assert [row["id"] for row in archived_rows] == [payment["id"]]
        delivery_rows = client.get(
            f"/api/requirement-verifications?project_id={project['id']}&keyword=配送单&archived=false",
            headers=headers,
        ).json()
        assert [row["id"] for row in delivery_rows] == [delivery["id"]]

        restored = client.put(
            f"/api/requirement-verifications/{payment['id']}",
            headers=headers,
            json={"is_archived": False},
        )
        assert restored.status_code == 200
        assert restored.json()["is_archived"] is False


def test_category_data_setup_runs_steps_once_shares_outputs_and_keeps_defaults(monkeypatch):
    calls = []
    progress_snapshots = []
    order_counter = {"value": 0}

    def cart_runner(env, variables):
        progress_db = verification_service.SessionLocal()
        try:
            progress_run = progress_db.query(verification_service.VerificationRun).order_by(verification_service.VerificationRun.id.desc()).first()
            progress_snapshots.append(verification_service.json_load(progress_run.setup_result_json, {}))
        finally:
            progress_db.close()
        order_counter["value"] += 1
        order_sn = f"ORDER-{order_counter['value']}"
        calls.append(("shopping_cart", variables.get("seed"), order_sn))
        return True, "cart prepared", "", {"order_sn": order_sn, "currency": "JPY"}

    def quote_runner(env, variables):
        calls.append(("order_quote", variables.get("linked_order"), variables.get("order_sn")))
        return True, "quote prepared", "", {"quote_amount": "88.50"}

    monkeypatch.setitem(verification_service.SCRIPT_REGISTRY["shopping_cart"], "func", cart_runner)
    monkeypatch.setitem(verification_service.SCRIPT_REGISTRY["order_quote"], "func", quote_runner)

    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "分类统一造数项目")
        env = client.post(
            "/api/envs",
            headers=headers,
            json={"project_id": project["id"], "env_name": "造数环境", "base_url": "https://example.test", "global_headers": {}, "global_vars": {}, "timeout": 20},
        ).json()
        task = _task(client, headers, project["id"], "订单报价联动验证")
        detail = client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers).json()
        selected = [item for item in detail["items"] if item["item_type"] in {"page", "data"}][:2]
        assert len(selected) == 2
        for item in selected:
            response = client.put(
                f"/api/requirement-verifications/items/{item['id']}",
                headers=headers,
                json={
                    "automation_level": "auto",
                    "status": "draft",
                    "config": {
                        "observations": [
                            {"name": "actual_order_sn", "source": "variable", "key": "order_sn"},
                            {"name": "actual_quote_amount", "source": "variable", "key": "quote_amount"},
                        ],
                        "assertions": [
                            {"left": "actual_order_sn", "operator": "exists"},
                            {"left": "actual_quote_amount", "operator": "exists"},
                        ],
                    },
                },
            )
            assert response.status_code == 200, response.text
        item_ids = [item["id"] for item in selected]
        assert client.post(
            f"/api/requirement-verifications/{task['id']}/items/batch-confirm",
            headers=headers,
            json={"item_ids": item_ids, "confirmed": True},
        ).status_code == 200

        default_setup = {
            "steps": [
                {"script_type": "shopping_cart", "env_id": env["id"], "variables": {"seed": "default"}, "enabled": True},
                {"script_type": "order_quote", "env_id": env["id"], "variables": {"linked_order": "{{order_sn}}"}, "enabled": True},
            ]
        }
        saved = client.put(
            f"/api/requirement-verifications/{task['id']}",
            headers=headers,
            json={"data_setup": default_setup},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["data_setup"] == default_setup

        run_setup = {
            "steps": [
                {"script_type": "shopping_cart", "env_id": env["id"], "variables": {"seed": "override"}, "enabled": True},
                default_setup["steps"][1],
            ]
        }
        started = client.post(
            f"/api/requirement-verifications/{task['id']}/runs",
            headers=headers,
            json={"item_ids": item_ids, "variables": {}, "data_setup": run_setup, "risk_confirmed": False, "visible_browser": False},
        )
        assert started.status_code == 200, started.text
        run = _wait_for_run(client, headers, started.json()["id"])
        assert run["status"] == "passed"
        assert calls == [("shopping_cart", "default", "ORDER-1"), ("order_quote", "ORDER-1", "ORDER-1")]
        assert run["data_setup"] == default_setup
        assert run["setup_result"]["status"] == "passed"
        assert run["setup_result"]["total_steps"] == 2
        assert run["setup_result"]["completed_steps"] == 2
        assert run["setup_result"]["outputs"] == {"order_sn": "ORDER-1", "currency": "JPY", "quote_amount": "88.50"}
        assert progress_snapshots[0]["status"] == "running"
        assert progress_snapshots[0]["current_step"] == 1
        assert progress_snapshots[0]["steps"][0]["status"] == "running"
        assert all(item["actual"]["observations"]["actual_order_sn"] == "ORDER-1" for item in run["items"])
        assert client.get(f"/api/requirement-verifications/{task['id']}", headers=headers).json()["data_setup"] == default_setup

        rerun = client.post(
            f"/api/requirement-verifications/{task['id']}/runs",
            headers=headers,
            json={"item_ids": item_ids, "variables": {}, "visible_browser": False},
        )
        assert rerun.status_code == 200, rerun.text
        rerun_result = _wait_for_run(client, headers, rerun.json()["id"])
        assert rerun_result["status"] == "passed"
        assert rerun_result["setup_result"]["outputs"]["order_sn"] == "ORDER-2"
        assert calls[2:] == [("shopping_cart", "default", "ORDER-2"), ("order_quote", "ORDER-2", "ORDER-2")]


def test_category_data_setup_validates_project_and_high_risk_confirmation(monkeypatch):
    calls = []

    def payment_runner(env, variables):
        calls.append(env.id)
        return True, "paid", "", {"payment_status": "paid"}

    monkeypatch.setitem(verification_service.SCRIPT_REGISTRY["balance_payment"], "func", payment_runner)

    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "高风险造数项目")
        other_project = _project(client, headers, "其它造数项目")
        env = client.post(
            "/api/envs",
            headers=headers,
            json={"project_id": project["id"], "env_name": "本项目环境", "base_url": "https://example.test", "global_headers": {}, "global_vars": {}, "timeout": 20},
        ).json()
        other_env = client.post(
            "/api/envs",
            headers=headers,
            json={"project_id": other_project["id"], "env_name": "其它环境", "base_url": "https://other.test", "global_headers": {}, "global_vars": {}, "timeout": 20},
        ).json()
        task = _task(client, headers, project["id"], "余额支付验证")
        detail = client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers).json()
        item = detail["items"][0]
        assert client.put(
            f"/api/requirement-verifications/items/{item['id']}",
            headers=headers,
            json={"automation_level": "auto", "status": "draft", "config": {"observations": [{"name": "ok", "source": "literal", "value": True}], "assertions": [{"left": "ok", "operator": "eq", "right_value": True}]}},
        ).status_code == 200
        assert client.post(
            f"/api/requirement-verifications/{task['id']}/items/batch-confirm",
            headers=headers,
            json={"item_ids": [item["id"]], "confirmed": True},
        ).status_code == 200

        invalid = client.put(
            f"/api/requirement-verifications/{task['id']}",
            headers=headers,
            json={"data_setup": {"steps": [{"script_type": "balance_payment", "env_id": other_env["id"], "variables": {}, "enabled": True}]}},
        )
        assert invalid.status_code == 400
        missing_script = client.put(
            f"/api/requirement-verifications/{task['id']}",
            headers=headers,
            json={"data_setup": {"steps": [{"script_type": "missing_script", "env_id": env["id"], "variables": {}, "enabled": True}]}},
        )
        assert missing_script.status_code == 400
        sensitive = client.put(
            f"/api/requirement-verifications/{task['id']}",
            headers=headers,
            json={"data_setup": {"steps": [{"script_type": "balance_payment", "env_id": env["id"], "variables": {"password": "secret"}, "enabled": True}]}},
        )
        assert sensitive.status_code == 400

        setup = {"steps": [{"script_type": "balance_payment", "env_id": env["id"], "variables": {}, "enabled": True}]}
        assert client.put(f"/api/requirement-verifications/{task['id']}", headers=headers, json={"data_setup": setup}).status_code == 200
        denied = client.post(
            f"/api/requirement-verifications/{task['id']}/runs",
            headers=headers,
            json={"item_ids": [item["id"]], "variables": {}, "visible_browser": False},
        )
        assert denied.status_code == 400
        assert calls == []
        accepted = client.post(
            f"/api/requirement-verifications/{task['id']}/runs",
            headers=headers,
            json={"item_ids": [item["id"]], "variables": {}, "risk_confirmed": True, "visible_browser": False},
        )
        assert accepted.status_code == 200, accepted.text
        assert _wait_for_run(client, headers, accepted.json()["id"])["status"] == "passed"
        assert calls == [env["id"]]
        catalog = client.get("/api/requirement-verifications/data-script-catalog", headers=headers)
        assert catalog.status_code == 200
        payment_meta = next(row for row in catalog.json() if row["script_type"] == "balance_payment")
        assert payment_meta["risk_level"] == "high"


def test_category_data_setup_failure_blocks_items_and_redacts_evidence(monkeypatch):
    def failed_runner(env, variables):
        return False, "token=super-secret phone=13800138000", "", {"token": "not-stored"}

    monkeypatch.setitem(verification_service.SCRIPT_REGISTRY["shopping_cart"], "func", failed_runner)

    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "造数失败项目")
        env = client.post(
            "/api/envs",
            headers=headers,
            json={"project_id": project["id"], "env_name": "失败环境", "base_url": "https://example.test", "global_headers": {}, "global_vars": {}, "timeout": 20},
        ).json()
        task = _task(client, headers, project["id"], "造数失败阻塞验证")
        detail = client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers).json()
        item = detail["items"][0]
        assert client.put(
            f"/api/requirement-verifications/items/{item['id']}",
            headers=headers,
            json={"automation_level": "auto", "status": "draft", "config": {"observations": [{"name": "ok", "source": "literal", "value": True}], "assertions": [{"left": "ok", "operator": "eq", "right_value": True}]}},
        ).status_code == 200
        assert client.post(
            f"/api/requirement-verifications/{task['id']}/items/batch-confirm",
            headers=headers,
            json={"item_ids": [item["id"]], "confirmed": True},
        ).status_code == 200
        setup = {"steps": [{"script_type": "shopping_cart", "env_id": env["id"], "variables": {}, "enabled": True}]}
        started = client.post(
            f"/api/requirement-verifications/{task['id']}/runs",
            headers=headers,
            json={"item_ids": [item["id"]], "variables": {}, "data_setup": setup, "visible_browser": False},
        )
        assert started.status_code == 200, started.text
        run = _wait_for_run(client, headers, started.json()["id"])
        assert run["status"] == "blocked"
        assert run["items"][0]["result"] == "blocked"
        assert run["setup_result"]["status"] == "failed"
        log = run["setup_result"]["steps"][0]["log"]
        assert "super-secret" not in log
        assert "13800138000" not in log
        assert "***手机号***" in log


def test_clarification_uses_three_question_cap_restatement_and_batch_matrix_update(monkeypatch):
    _enable_fake_ai()
    analysis_prompts: list[str] = []

    def fake_ai(config, prompt, timeout=0):
        if "用户刚用自然语言回答了一个澄清问题" in prompt:
            return {
                "summary": "用户确认后的规则",
                "understood_rules": ["只按用户明确回答的内容执行"],
                "conditions": ["当前功能分类"],
                "exceptions": [],
                "affected_item_titles": [],
                "ambiguities": [],
                "conflicts": [],
                "confidence": 0.95,
            }
        analysis_prompts.append(prompt)
        questions = [
            {"topic_key": "payment.rounding", "question": "支付金额采用哪种舍入方式？", "why_needed": "影响应付金额", "suggested_answers": ["四舍五入", "直接截断"], "affected_item_titles": ["支付金额校验"], "source_ref": "需求金额"},
            {"topic_key": "order.state", "question": "支付成功后的订单状态是什么？", "why_needed": "影响状态判断", "suggested_answers": ["已支付", "待审核"], "affected_item_titles": ["订单状态校验"], "source_ref": "需求状态"},
            {"topic_key": "order.permission", "question": "哪些角色可以执行支付？", "why_needed": "影响权限判断", "suggested_answers": ["仅买家", "客服和买家"], "affected_item_titles": ["支付权限校验"], "source_ref": "需求权限"},
            {"topic_key": "payment.path", "question": "支付入口位于哪个页面？", "why_needed": "影响操作路径", "suggested_answers": ["订单详情", "订单列表"], "affected_item_titles": ["支付入口校验"], "source_ref": "需求路径"},
        ]
        items = [
            {"item_type": "amount", "title": "支付金额校验", "source_refs": ["需求金额"], "automation_level": "auto", "config": {"blocking_topic_keys": ["payment.rounding"]}},
            {"item_type": "state", "title": "订单状态校验", "source_refs": ["需求状态"], "automation_level": "auto", "config": {"blocking_topic_keys": ["order.state"]}},
            {"item_type": "permission", "title": "支付权限校验", "source_refs": ["需求权限"], "automation_level": "auto", "config": {"blocking_topic_keys": ["order.permission"]}},
            {"item_type": "page", "title": "订单编号展示", "source_refs": ["需求页面"], "automation_level": "auto", "config": {}},
        ]
        return {"summary": "支付功能变更", "flows": ["进入订单并支付"], "clarifications": questions, "verification_items": items, "formulas": []}

    monkeypatch.setattr(verification_service, "call_local_model_json", fake_ai)
    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "澄清复述项目")
        task = _task(client, headers, project["id"], "订单支付澄清验证")

        detail = client.post(
            f"/api/requirement-verifications/{task['id']}/analyze",
            headers=headers,
            json={"mode": "standard"},
        ).json()
        active = [row for row in detail["clarifications"] if row["status"] in {"open", "pending_confirmation"}]
        assert len(active) == 3
        assert active[0]["review"]["suggested_answers"] == ["四舍五入", "直接截断"]

        first = active[0]
        drafted = client.put(
            f"/api/requirement-verifications/clarifications/{first['id']}",
            headers=headers,
            json={"answer": "本需求金额按日元四舍五入"},
        )
        assert drafted.status_code == 200, drafted.text
        assert drafted.json()["status"] == "pending_confirmation"
        assert drafted.json()["review"]["interpretation"]["summary"] == "用户确认后的规则"

        client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers, json={"mode": "standard"})
        assert "本需求金额按日元四舍五入" not in analysis_prompts[-1]
        confirmed = client.post(
            f"/api/requirement-verifications/clarifications/{first['id']}/confirm",
            headers=headers,
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "answered"

        updated = client.post(
            f"/api/requirement-verifications/{task['id']}/analyze",
            headers=headers,
            json={"mode": "standard"},
        ).json()
        assert "只按用户明确回答的内容执行" in analysis_prompts[-1]
        assert "本需求金额按日元四舍五入" not in analysis_prompts[-1]
        remaining = [row for row in updated["clarifications"] if row["status"] in {"open", "pending_confirmation"}]
        assert len(remaining) == 2

        second, third = remaining
        second_draft = client.put(
            f"/api/requirement-verifications/clarifications/{second['id']}",
            headers=headers,
            json={"answer": "状态显示已支付"},
        ).json()
        supplemented = client.put(
            f"/api/requirement-verifications/clarifications/{second['id']}",
            headers=headers,
            json={"supplement": "后台也显示已支付"},
        ).json()
        assert second_draft["answer"] in supplemented["answer"]
        assert "补充说明：后台也显示已支付" in supplemented["answer"]
        assert client.post(f"/api/requirement-verifications/clarifications/{second['id']}/confirm", headers=headers).status_code == 200
        assert client.post(f"/api/requirement-verifications/clarifications/{third['id']}/defer", headers=headers).status_code == 200

        continued = client.post(
            f"/api/requirement-verifications/{task['id']}/analyze",
            headers=headers,
            json={"mode": "continue_without_questions"},
        ).json()
        assert not [row for row in continued["clarifications"] if row["status"] in {"open", "pending_confirmation"}]
        blocked_titles = {item["title"] for item in continued["items"] if item["status"] == "blocked"}
        assert blocked_titles == {"支付权限校验"}
        assert len(continued["confirmed_clarifications"]) == 2


def test_clarification_ai_failure_keeps_answer_unconfirmed():
    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "澄清失败保护项目")
        task = client.post(
            "/api/requirement-verifications",
            headers=headers,
            json={"project_id": project["id"], "name": "AI不可用澄清验证", "requirement_text": "订单支付金额规则有调整"},
        ).json()
        detail = client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers).json()
        question = next(row for row in detail["clarifications"] if row["status"] == "open")

        drafted = client.put(
            f"/api/requirement-verifications/clarifications/{question['id']}",
            headers=headers,
            json={"answer": "我认为是四舍五入"},
        )
        assert drafted.status_code == 200, drafted.text
        assert drafted.json()["status"] == "pending_confirmation"
        assert drafted.json()["review"]["interpretation"]["can_confirm"] is False
        denied = client.post(
            f"/api/requirement-verifications/clarifications/{question['id']}/confirm",
            headers=headers,
        )
        assert denied.status_code == 400


def test_preflight_ignores_legacy_item_setup_when_category_setup_exists(monkeypatch):
    calls = []

    def full_flow_runner(env, variables):
        calls.append((env.id, variables.get("seed")))
        return True, "prepared", "", {"order_sn": "NEW-ORDER-1"}

    monkeypatch.setitem(verification_service.SCRIPT_REGISTRY["full_flow"], "func", full_flow_runner)
    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "快速预检项目")
        env = client.post(
            "/api/envs",
            headers=headers,
            json={"project_id": project["id"], "env_name": "日本站测试环境", "base_url": "https://example.test", "global_headers": {}, "global_vars": {}, "timeout": 20},
        ).json()
        task = _task(client, headers, project["id"], "日本站手续费对比")
        detail = client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers).json()
        item = next(row for row in detail["items"] if row["item_type"] == "page")
        updated = client.put(
            f"/api/requirement-verifications/items/{item['id']}",
            headers=headers,
            json={
                "automation_level": "auto",
                "status": "draft",
                "config": {
                    "data_setup": {"script_type": "全流程完全体", "env_id": "{需澄清}", "variables": {}},
                    "observations": [{"name": "其它费用", "source": "literal", "value": "1060"}],
                    "assertions": [{"left": "${其它费用}", "operator": "eq", "right_value": "1060"}],
                },
            },
        )
        assert updated.status_code == 200, updated.text
        assert client.post(
            f"/api/requirement-verifications/{task['id']}/items/batch-confirm",
            headers=headers,
            json={"item_ids": [item["id"]], "confirmed": True},
        ).status_code == 200
        category_setup = {"steps": [{"script_type": "full_flow", "env_id": env["id"], "variables": {"seed": "category"}, "enabled": True}]}
        assert client.put(f"/api/requirement-verifications/{task['id']}", headers=headers, json={"data_setup": category_setup}).status_code == 200

        preflight = client.post(
            f"/api/requirement-verifications/{task['id']}/preflight",
            headers=headers,
            json={"item_ids": [item["id"]], "variables": {}},
        )
        assert preflight.status_code == 200, preflight.text
        result = preflight.json()
        assert result["summary"] == {"auto": 1, "assisted": 0, "blocked": 0}
        assert result["data_setup"]["steps"][0]["environment"] == "日本站测试环境"
        assert "order_sn" in result["data_setup"]["steps"][0]["output_keys"]
        assert any(issue["code"] == "legacy_setup_ignored" for issue in result["items"][0]["issues"])
        catalog = client.get(f"/api/requirement-verifications/data-script-catalog?project_id={project['id']}", headers=headers).json()
        assert catalog
        assert all(not row["script_type"].startswith("oem_") for row in catalog)

        started = client.post(
            f"/api/requirement-verifications/{task['id']}/runs",
            headers=headers,
            json={"item_ids": [item["id"]], "variables": {}, "risk_confirmed": True, "visible_browser": False},
        )
        assert started.status_code == 200, started.text
        run = _wait_for_run(client, headers, started.json()["id"])
        assert run["status"] == "passed"
        assert calls == [(env["id"], "category")]
        assert run["items"][0]["evidence"]["preflight"]["execution_mode"] == "auto"


def test_preflight_blocks_unresolved_placeholder_before_data_creation(monkeypatch):
    calls = []

    def runner(env, variables):
        calls.append(env.id)
        return True, "prepared", "", {"order_sn": "SHOULD-NOT-EXIST"}

    monkeypatch.setitem(verification_service.SCRIPT_REGISTRY["shopping_cart"], "func", runner)
    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "预检拦截项目")
        task = _task(client, headers, project["id"], "未完成配置验证")
        detail = client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers).json()
        item = next(row for row in detail["items"] if row["item_type"] == "page")
        assert client.put(
            f"/api/requirement-verifications/items/{item['id']}",
            headers=headers,
            json={
                "automation_level": "auto",
                "status": "draft",
                "config": {
                    "data_setup": {"script_type": "shopping_cart", "env_id": "{需澄清}", "variables": {}},
                    "observations": [{"name": "ok", "source": "literal", "value": True}],
                    "assertions": [{"left": "ok", "operator": "eq", "right_value": True}],
                },
            },
        ).status_code == 200
        assert client.post(
            f"/api/requirement-verifications/{task['id']}/items/batch-confirm",
            headers=headers,
            json={"item_ids": [item["id"]], "confirmed": True},
        ).status_code == 200

        preflight = client.post(f"/api/requirement-verifications/{task['id']}/preflight", headers=headers, json={"item_ids": [item["id"]]}).json()
        assert preflight["summary"]["blocked"] == 1
        assert {issue["code"] for issue in preflight["items"][0]["issues"]} >= {"legacy_env_invalid", "unresolved_placeholder"}
        denied = client.post(
            f"/api/requirement-verifications/{task['id']}/runs",
            headers=headers,
            json={"item_ids": [item["id"]], "variables": {}, "visible_browser": False},
        )
        assert denied.status_code == 400
        assert calls == []


def test_runtime_url_replaces_historical_business_number():
    url = "https://jp.example.test/OrderDetails?order_sn=OLD-ORDER&tab=detail"
    assert verification_service._runtime_url(url, {"order_sn": "NEW-ORDER"}) == "https://jp.example.test/OrderDetails?order_sn=NEW-ORDER&tab=detail"


def test_page_observation_allows_manual_value_and_only_business_mismatch_fails(monkeypatch):
    opened_manual_browsers = []

    async def fake_start_manual_browser(*args, **kwargs):
        opened_manual_browsers.append({"args": args, "kwargs": kwargs})
        return str(kwargs.get("preferred_session_id") or "manual-browser")

    monkeypatch.setattr(ui_recording_session, "start_session", fake_start_manual_browser)
    class FakePage:
        def __init__(self):
            self.url = "about:blank"

        def goto(self, url, **kwargs):
            self.url = url

    class FakeSessions:
        def __init__(self, db, project_id, visible):
            self.page = FakePage()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def page_for(self, task, item, variables):
            return self.page

    monkeypatch.setattr(verification_service, "BrowserSessions", FakeSessions)
    monkeypatch.setattr(verification_service, "_capture", lambda *args, **kwargs: "evidence.png")
    monkeypatch.setattr(verification_service, "_semantic_snapshot", lambda page: [])
    monkeypatch.setattr(verification_service, "_wait_page_business_ready", lambda *args, **kwargs: {"ready": True, "data_warnings": []})
    monkeypatch.setattr(verification_service, "_runtime_preflight_probe", lambda *args, **kwargs: {"status": "passed", "login": "valid", "page": "ready", "message": "测试桩预检通过"})

    def wait_until_confirmation(client, headers, run_id):
        for _ in range(80):
            run = client.get(f"/api/requirement-verifications/runs/{run_id}", headers=headers).json()
            waiting = next((row for row in run["items"] if row["result"] in {"waiting_confirmation", "waiting_user"}), None)
            if waiting:
                return waiting
            time.sleep(0.03)
        raise AssertionError("未进入人工接管")

    with TestClient(app) as client:
        headers = _headers(client)
        project = _project(client, headers, "页面人工接管项目")
        account = client.post(
            "/api/test-accounts",
            headers=headers,
            json={
                "project_id": project["id"],
                "profile_name": "页面验证账号",
                "variables": {"username": "tester"},
                "sensitive_variables": {"password": "secret"},
                "login_url": "https://example.test/login",
                "status": "active",
            },
        ).json()
        assert client.put(
            "/api/test-account-bindings",
            headers=headers,
            json={"target_type": "project", "target_id": project["id"], "account_profile_id": account["id"]},
        ).status_code == 200
        task = _task(client, headers, project["id"], "其它费用页面验证")
        detail = client.post(f"/api/requirement-verifications/{task['id']}/analyze", headers=headers).json()
        item = next(row for row in detail["items"] if row["item_type"] == "page")
        assert client.put(
            f"/api/requirement-verifications/items/{item['id']}",
            headers=headers,
            json={
                "automation_level": "supervised",
                "status": "draft",
                "config": {
                    "start_page": "主要页面",
                    "actions": [{"action": "observe", "goal": "查看其它费用"}],
                    "observations": [{"name": "其它费用", "source": "page", "goal": "その他字段金额"}],
                    "assertions": [{"left": "${其它费用}", "operator": "eq", "right_value": "1060"}],
                },
            },
        ).status_code == 200
        assert client.post(
            f"/api/requirement-verifications/{task['id']}/items/batch-confirm",
            headers=headers,
            json={"item_ids": [item["id"]], "confirmed": True},
        ).status_code == 200

        for actual_value, expected_status in (("1060", "passed"), ("999", "failed")):
            started = client.post(
                f"/api/requirement-verifications/{task['id']}/runs",
                headers=headers,
                json={"item_ids": [item["id"]], "variables": {}, "visible_browser": True},
            )
            assert started.status_code == 200, started.text
            waiting = wait_until_confirmation(client, headers, started.json()["id"])
            assert waiting["evidence"]["type"] == "observation_value"
            opened = client.post(
                f"/api/requirement-verifications/runs/{started.json()['id']}/open-browser",
                headers=headers,
            )
            assert opened.status_code == 200, opened.text
            assert opened.json()["status"] == "opened"
            assert opened_manual_browsers[-1]["kwargs"]["persistent"] is True
            assert opened_manual_browsers[-1]["kwargs"]["persist_learning_events"] is False
            submitted = client.post(
                f"/api/requirement-verifications/run-items/{waiting['id']}/confirm",
                headers=headers,
                json={"decision": "provide_value", "observed_value": actual_value},
            )
            assert submitted.status_code == 200, submitted.text
            assert _wait_for_run(client, headers, started.json()["id"])["status"] == expected_status
