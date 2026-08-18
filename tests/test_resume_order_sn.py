from types import SimpleNamespace

import app.data_scripts as data_scripts


def _env():
    return SimpleNamespace(base_url="https://example.test", timeout=30)


def test_resume_order_flow_strips_order_sn_label_prefix(monkeypatch):
    captured = {}

    def detect(env, variables, order_sn, log):
        captured["order_sn"] = order_sn
        captured["variables_order_sn"] = variables.get("order_sn")
        return False, {"reason": "stop-after-detect", "detected_start_node": "order_created"}

    monkeypatch.setattr(data_scripts, "_detect_resume_order_state", detect)
    monkeypatch.setattr(data_scripts, "write_allure_result", lambda *args, **kwargs: "mock-report.json")
    monkeypatch.setattr(data_scripts, "ensure_report_dirs", lambda: None)

    passed, _, _, summary = data_scripts.run_resume_order_flow_script(
        _env(),
        {
            "order_sn": "订单号:2026081714340484-300001",
            "stop_after_node": "checking_started",
            "sleep": 0,
        },
    )

    assert captured["order_sn"] == "2026081714340484-300001"
    assert captured["variables_order_sn"] == "2026081714340484-300001"
    assert summary["order_sn"] == "2026081714340484-300001"
    assert passed is False


def test_resume_order_flow_keeps_plain_order_sn(monkeypatch):
    captured = {}

    def detect(env, variables, order_sn, log):
        captured["order_sn"] = order_sn
        return False, {"reason": "stop-after-detect", "detected_start_node": "order_created"}

    monkeypatch.setattr(data_scripts, "_detect_resume_order_state", detect)
    monkeypatch.setattr(data_scripts, "write_allure_result", lambda *args, **kwargs: "mock-report.json")
    monkeypatch.setattr(data_scripts, "ensure_report_dirs", lambda: None)

    data_scripts.run_resume_order_flow_script(_env(), {"order_sn": "ORDER-RESUME", "sleep": 0})

    assert captured["order_sn"] == "ORDER-RESUME"
