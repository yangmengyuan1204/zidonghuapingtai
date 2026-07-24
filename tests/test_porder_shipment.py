"""porder_shipment 数据脚本测试 — 仅测试导入、签名、参数校验和注册完整性。"""
import pytest
import app.data_scripts as ds
import app.data_scripts.porder_shipment as shipment

def test_script_importable():
    assert callable(ds.run_porder_shipment_script), "run_porder_shipment_script 应可调用"

def test_script_name_constant():
    assert getattr(ds, "POORDER_SHIPMENT_SCRIPT_NAME", "") == "配送单出货"

def test_script_registered():
    assert ds.SCRIPT_REGISTRY.get("porder_shipment", {}).get("func") is ds.run_porder_shipment_script

@pytest.mark.parametrize("status_text", ["已发出", "已發出"])
def test_shipped_status_recognizes_sent_label(status_text):
    assert shipment._status_texts_contain(status_text, shipment._SHIPPED_KEYWORDS)

def test_legacy_export_counts():
    entries = [name for name, value in vars(ds).items() if name.startswith("run_") and name.endswith("_script") and callable(value)]
    assert len(entries) >= 23, f"预期至少 23 个可调用脚本入口，实际 {len(entries)}"

def test_missing_porder_sn_returns_failure():
    class FakeEnv:
        timeout = 25
        base_url = ""
    passed, log_text, report_path, summary = ds.run_porder_shipment_script(FakeEnv(), {})
    assert passed is False
    assert "reason" in summary
    assert "porder_sn" in summary["reason"].lower()

def test_shipment_verifies_top_level_porder_status(monkeypatch):
    class FakeEnv:
        timeout = 25
        base_url = "https://example.test"

    class FakeSession:
        headers = {}

    detail_payloads = iter([
        ({"success": True, "code": 0, "data": {"statusName": "待出货"}}, [{"id": 1, "porder_sn": "P1-123"}]),
        ({"success": True, "code": 0, "data": {"statusName": "已出货"}}, [{"id": 1, "porder_sn": "P1-123"}]),
    ])
    submitted = []
    express_updates = []
    freight_refreshes = iter([
        {"success": True, "code": 0, "data": [{"group": [
            {"logistics_id": 15, "list": [{"id": 10, "logistics_id": 15, "express_no": ""}]},
            {"logistics_id": 25, "list": [{"id": 20, "logistics_id": 25, "express_no": ""}]},
        ]}]},
        {"success": True, "code": 0, "data": [{"group": [
            {"logistics_id": 15, "list": [{"id": 10, "logistics_id": 15, "express_no": "EXP015"}]},
            {"logistics_id": 25, "list": [{"id": 20, "logistics_id": 25, "express_no": "EXP025"}]},
        ]}]},
    ])

    monkeypatch.setattr(ds, "_admin_session_from", lambda variables: FakeSession())
    monkeypatch.setattr(ds, "_admin_login", lambda *args: ({"success": True, "code": 0}, "token"))
    monkeypatch.setattr(ds, "_porder_detail_payload", lambda *args, **kwargs: next(detail_payloads))
    monkeypatch.setattr(ds, "_finish_named", lambda name, log, passed, summary: (passed, "", "", summary))
    monkeypatch.setattr(shipment._time, "sleep", lambda seconds: None)

    def fake_post(session, base_url, path, fields, timeout):
        if path.endswith("freightList"):
            return next(freight_refreshes)
        if path.endswith("getExpressNo"):
            freight_ids = list(fields["freight_id_set"])
            assert fields["porder_sn"] == "P1-123"
            if freight_ids == [10]:
                return {"success": True, "code": 0, "data": {"express_no": "EXP015"}}
            return {"success": True, "code": 0, "data": "EXP025"}
        if path.endswith("updateExpressNo"):
            freight_ids = list(fields["freight_id_set"])
            if len(freight_ids) > 1:
                return {"success": False, "code": 10000, "msg": "不同物流方式不可以使用同一个物流号"}
            express_updates.append((freight_ids, fields["express_no"]))
        if path.endswith("submitDelivery"):
            submitted.append(fields["porder_sn"])
        return {"success": True, "code": 0}

    monkeypatch.setattr(ds, "_post_admin_urlencoded", fake_post)

    passed, _, _, summary = ds.run_porder_shipment_script(
        FakeEnv(), {"porder_sn": "P1-123"}
    )

    assert passed is True
    assert express_updates == [([10], "EXP015"), ([20], "EXP025")]
    assert submitted == ["P1-123"]
    assert summary["shipped"] is True
    assert summary["express_nos"] == ["EXP015", "EXP025"]


def test_shipment_timeout_returns_last_verified_status(monkeypatch):
    class FakeEnv:
        timeout = 25
        base_url = "https://example.test"

    class FakeSession:
        headers = {}

    waiting = {"success": True, "code": 0, "data": {"statusName": "已支付已确认"}}
    monkeypatch.setattr(ds, "_admin_session_from", lambda variables: FakeSession())
    monkeypatch.setattr(ds, "_admin_login", lambda *args: ({"success": True, "code": 0}, "token"))
    monkeypatch.setattr(ds, "_porder_detail_payload", lambda *args, **kwargs: (waiting, [{"id": 1}]))
    monkeypatch.setattr(ds, "_finish_named", lambda name, log, passed, summary: (passed, "", "", summary))
    monkeypatch.setattr(shipment._time, "sleep", lambda seconds: None)

    freight_calls = iter([
        {"success": True, "code": 0, "data": [{"group": [
            {"logistics_id": 25, "list": [{"id": 20, "logistics_id": 25, "express_no": "EXP025"}]},
        ]}]},
        {"success": True, "code": 0, "data": [{"group": [
            {"logistics_id": 25, "list": [{"id": 20, "logistics_id": 25, "express_no": "EXP025"}]},
        ]}]},
    ])

    def fake_post(session, base_url, path, fields, timeout):
        if path.endswith("freightList"):
            return next(freight_calls)
        return {"success": True, "code": 0}

    monkeypatch.setattr(ds, "_post_admin_urlencoded", fake_post)
    passed, _, _, summary = ds.run_porder_shipment_script(
        FakeEnv(), {"porder_sn": "P1-123", "shipment_verify_attempts": 2}
    )

    assert passed is False
    assert summary["last_verify"]["attempt"] == 2
    assert summary["last_verify"]["status_texts"] == ["已支付已确认"]


def test_co_shipment_child_redirects_all_operations_to_main_porder(monkeypatch):
    class FakeEnv:
        timeout = 25
        base_url = "https://example.test"

    class FakeSession:
        headers = {}

    child_sn = "P-CHILD-1868"
    main_sn = "P-MAIN-300001"
    detail_calls = []
    submitted = []
    freight_calls = []
    express_requests = []
    express_updates = []
    finished_logs = []

    def fake_detail(session, base_url, variables, porder_sn, timeout, retries=4):
        detail_calls.append(porder_sn)
        if porder_sn == child_sn:
            return (
                {
                    "success": True,
                    "code": 0,
                    "data": {
                        "porder_sn": child_sn,
                        "statusName": "已支付已确认",
                        "merge_type": "集运出货·副",
                        "co_porder_sn": main_sn,
                    },
                },
                [{"id": 1, "porder_sn": child_sn}],
            )
        status_name = "已出货" if detail_calls.count(main_sn) > 1 else "已支付已确认"
        return (
            {
                "success": True,
                "code": 0,
                "data": {
                    "porder_sn": main_sn,
                    "statusName": status_name,
                    "merge_type": "集运出货·总",
                },
            },
            [{"id": 2, "porder_sn": main_sn}],
        )

    freight_payloads = iter([
        {"success": True, "code": 0, "data": [{"group": [
            {"logistics_id": 20, "list": [{"id": 10, "logistics_id": 20, "express_no": ""}]},
        ]}]},
        {"success": True, "code": 0, "data": [{"group": [
            {"logistics_id": 20, "list": [{"id": 10, "logistics_id": 20, "express_no": "EXP-MAIN"}]},
        ]}]},
    ])

    def fake_post(session, base_url, path, fields, timeout):
        if path.endswith("freightList"):
            freight_calls.append(fields["porder_sn"])
            return next(freight_payloads)
        if path.endswith("getExpressNo"):
            express_requests.append((fields["porder_sn"], list(fields["freight_id_set"])))
            return {"success": True, "code": 0, "data": "EXP-MAIN"}
        if path.endswith("updateExpressNo"):
            express_updates.append((list(fields["freight_id_set"]), fields["express_no"]))
        if path.endswith("submitDelivery"):
            submitted.append(fields["porder_sn"])
        return {"success": True, "code": 0}

    def fake_finish(name, log, passed, summary):
        finished_logs.append(log)
        return passed, "", "", summary

    monkeypatch.setattr(ds, "_admin_session_from", lambda variables: FakeSession())
    monkeypatch.setattr(ds, "_admin_login", lambda *args: ({"success": True, "code": 0}, "token"))
    monkeypatch.setattr(ds, "_porder_detail_payload", fake_detail)
    monkeypatch.setattr(ds, "_post_admin_urlencoded", fake_post)
    monkeypatch.setattr(ds, "_finish_named", fake_finish)
    monkeypatch.setattr(shipment._time, "sleep", lambda seconds: None)

    passed, _, _, summary = ds.run_porder_shipment_script(FakeEnv(), {"porder_sn": child_sn})

    assert passed is True
    assert detail_calls == [child_sn, main_sn, main_sn]
    assert freight_calls == [main_sn, main_sn]
    assert express_requests == [(main_sn, [10])]
    assert express_updates == [([10], "EXP-MAIN")]
    assert submitted == [main_sn]
    assert summary["requested_porder_sn"] == child_sn
    assert summary["porder_sn"] == main_sn
    assert finished_logs[-1]["requested_porder_sn"] == child_sn
    assert finished_logs[-1]["porder_sn"] == main_sn


def test_co_shipment_child_without_main_porder_fails_before_mutation(monkeypatch):
    class FakeEnv:
        timeout = 25
        base_url = "https://example.test"

    class FakeSession:
        headers = {}

    child_payload = {
        "success": True,
        "code": 0,
        "data": {
            "porder_sn": "P-CHILD-1868",
            "statusName": "已支付已确认",
            "merge_type": "集运出货·副",
            "co_porder_sn": "",
        },
    }
    post_calls = []
    monkeypatch.setattr(ds, "_admin_session_from", lambda variables: FakeSession())
    monkeypatch.setattr(ds, "_admin_login", lambda *args: ({"success": True, "code": 0}, "token"))
    monkeypatch.setattr(ds, "_porder_detail_payload", lambda *args, **kwargs: (child_payload, [{"id": 1}]))
    monkeypatch.setattr(ds, "_post_admin_urlencoded", lambda *args, **kwargs: post_calls.append(args) or {"success": True, "code": 0})
    monkeypatch.setattr(ds, "_finish_named", lambda name, log, passed, summary: (passed, "", "", summary))

    passed, _, _, summary = ds.run_porder_shipment_script(
        FakeEnv(), {"porder_sn": "P-CHILD-1868"}
    )

    assert passed is False
    assert summary["reason"] == "集运副单缺少主配送单号"
    assert post_calls == []


def test_freight_refresh_failure_blocks_submit_delivery(monkeypatch):
    class FakeEnv:
        timeout = 25
        base_url = "https://example.test"

    class FakeSession:
        headers = {}

    detail_calls = 0
    submitted = []

    def fake_detail(*args, **kwargs):
        nonlocal detail_calls
        detail_calls += 1
        status_name = "已出货" if detail_calls > 1 else "已支付已确认"
        return {"success": True, "code": 0, "data": {"statusName": status_name}}, [{"id": 1}]

    freight_payloads = iter([
        {"success": True, "code": 0, "data": [{"group": [
            {"logistics_id": 20, "list": [{"id": 10, "logistics_id": 20, "express_no": "EXP001"}]},
        ]}]},
        {"success": False, "code": 10001, "msg": "箱子查询失败"},
    ])

    def fake_post(session, base_url, path, fields, timeout):
        if path.endswith("freightList"):
            return next(freight_payloads)
        if path.endswith("submitDelivery"):
            submitted.append(fields["porder_sn"])
        return {"success": True, "code": 0}

    monkeypatch.setattr(ds, "_admin_session_from", lambda variables: FakeSession())
    monkeypatch.setattr(ds, "_admin_login", lambda *args: ({"success": True, "code": 0}, "token"))
    monkeypatch.setattr(ds, "_porder_detail_payload", fake_detail)
    monkeypatch.setattr(ds, "_post_admin_urlencoded", fake_post)
    monkeypatch.setattr(ds, "_finish_named", lambda name, log, passed, summary: (passed, "", "", summary))

    passed, _, _, summary = ds.run_porder_shipment_script(FakeEnv(), {"porder_sn": "P1-123"})

    assert passed is False
    assert summary["reason"] == "出货前未获取到配送单箱子"
    assert submitted == []
