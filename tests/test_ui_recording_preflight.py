import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, inspect

from app.database import Base
from app.models import UiCaseRevision, UiLocatorMemory, UiRecordPreflight
from app.services.ui_recording_preflight import (
    determine_recorded_case_status,
    steps_snapshot_hash,
    summarize_preflight_log,
)
from app.services import ui_recording_preflight
from app.executors.runtime import _browser_context_options


def test_preflight_learning_and_revision_tables_are_registered():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    tables = set(inspect(engine).get_table_names())
    assert {"ui_record_preflight", "ui_locator_memory", "ui_case_revision"} <= tables


def test_passed_preflight_with_stable_locators_activates_recorded_case():
    steps = [
        {"action": "goto", "value": "https://example.test"},
        {"action": "click", "locator": "#save", "locator_profile": {"quality": "stable"}},
    ]
    report = {
        "verification_mode": "verified",
        "verified_rounds": 2,
        "rounds": [{"round_no": 1, "status": "passed", "frozen": False}, {"round_no": 2, "status": "passed", "frozen": True}],
        "steps_snapshot_hash": steps_snapshot_hash(steps),
    }

    assert determine_recorded_case_status("passed", steps, report) == "active"
    assert determine_recorded_case_status("passed", steps) == "draft"


def test_failed_or_risky_preflight_stays_draft():
    risky_steps = [
        {"action": "click", "locator": "text=保存", "locator_profile": {"quality": "risk"}},
    ]

    assert determine_recorded_case_status("passed", risky_steps) == "draft"
    assert determine_recorded_case_status("failed", []) == "draft"
    assert determine_recorded_case_status("", []) == "draft"


def test_preflight_summary_exposes_step_failure_and_screenshot():
    log_text = json.dumps(
        {
            "step_logs": [{"index": 1, "status": "passed", "used_locator": "#ok"}],
            "failed_step_index": 2,
            "failed_step_detail": {
                "status": "failed",
                "error": "未找到可用定位器",
                "failure_screenshot": "reports/screenshots/fail.png",
                "current_url": "https://example.test/order",
            },
            "error_category": "元素定位失败",
        },
        ensure_ascii=False,
    )

    summary = summarize_preflight_log(False, log_text, "fallback.png")

    assert summary["status"] == "failed"
    assert summary["failed_step_index"] == 2
    assert summary["steps"][-1]["error"] == "未找到可用定位器"
    assert summary["screenshot"] == "reports/screenshots/fail.png"


def test_preflight_browser_context_reuses_recorded_storage_state():
    storage_state = {"cookies": [{"name": "session", "value": "secret"}], "origins": []}

    options = _browser_context_options({"storage_state": storage_state})

    assert options["storage_state"] is storage_state


def test_preflight_snapshot_must_match_steps_being_saved():
    matcher = getattr(ui_recording_preflight, "preflight_matches_steps", None)
    assert matcher is not None
    row = SimpleNamespace(
        steps_json=json.dumps([{"action": "click", "locator": "#checked"}], ensure_ascii=False)
    )

    assert matcher(row, [{"action": "click", "locator": "#checked"}]) is True
    assert matcher(row, [{"action": "click", "locator": "#changed"}]) is False


def test_preflight_progress_accumulates_step_status_and_locator_evidence():
    merge = getattr(ui_recording_preflight, "merge_preflight_progress", None)
    assert merge is not None
    report = merge({}, {"event": "started", "status": "running", "total_steps": 1})
    report = merge(
        report,
        {
            "event": "prepared",
            "status": "running",
            "steps": [
                {
                    "name": "保存",
                    "action": "click",
                    "locator": "#save",
                    "locator_profile": {
                        "quality": "stable",
                        "candidates": [{"value": "#save", "score": 85, "count": 1, "visible": True}],
                    },
                }
            ],
        },
    )
    report = merge(report, {"event": "step_start", "status": "running", "index": 1})
    report = merge(
        report,
        {
            "event": "step_finish",
            "status": "passed",
            "index": 1,
            "detail": {"used_locator": "#save", "matched_count": 1},
        },
    )

    assert report["total_steps"] == 1
    assert report["completed_steps"] == 1
    assert report["steps"][0]["status"] == "passed"
    assert report["steps"][0]["used_locator"] == "#save"
    assert report["steps"][0]["locator_candidates"][0]["score"] == 85


def test_executor_imports_locator_heal_from_app_services_package():
    actions = Path("app/executors/actions.py").read_text(encoding="utf-8")
    runtime = Path("app/executors/runtime.py").read_text(encoding="utf-8")

    assert "from ..services.locator_heal import auto_heal" in actions
    assert "from ..services.locator_heal import update_heal_history_on_success" in runtime
    assert "confirm_locator_updates" in runtime


def test_launch_preflight_delegates_to_verification(monkeypatch):
    calls = []
    monkeypatch.setattr(ui_recording_preflight, "launch_verification", lambda row, *, case_data, storage_state: calls.append((row, case_data, storage_state)), raising=False)
    row = SimpleNamespace(run_id="run-9", session_id="session-9", project_id=1)
    case_data = {"case_name": "测试", "page_url": "https://example.test", "steps": [], "timeout": 30}

    ui_recording_preflight.launch_preflight(row, case_data=case_data, storage_state=None)

    assert calls == [(row, case_data, None)]


def test_serialize_preflight_keeps_legacy_fields_and_adds_round_repair():
    row = SimpleNamespace(
        run_id="run-10",
        session_id="session-10",
        project_id=1,
        case_id=0,
        status="repair_ready",
        screenshot="shots/fail.png",
        error_category="",
        update_time=None,
        report_json=json.dumps({
            "status": "repair_ready",
            "round_no": 1,
            "rounds": 2,
            "reset": {"passed": True, "outputs": {}},
            "repair": {"failed_step_index": 3, "attempts": 1},
            "steps": [],
        }, ensure_ascii=False),
    )

    payload = ui_recording_preflight.serialize_preflight(row)

    assert payload["run_id"] == "run-10"
    assert payload["session_id"] == "session-10"
    assert payload["project_id"] == 1
    assert payload["case_id"] == 0
    assert payload["status"] == "repair_ready"
    assert payload["screenshot"] == "shots/fail.png"
    assert payload["round_no"] == 1
    assert payload["rounds"] == 2
    assert payload["repair"] == {"failed_step_index": 3, "attempts": 1}
    assert payload["reset"] == {"passed": True, "outputs": {}}


def test_preflight_progress_merges_reset_and_repair_and_round():
    merge = ui_recording_preflight.merge_preflight_progress
    report = merge({}, {"event": "reset", "status": "resetting", "round_no": 1, "reset": {"passed": True, "outputs": {}}})
    assert report["round_no"] == 1
    assert report["reset"] == {"passed": True, "outputs": {}}
    report = merge(report, {"event": "repair", "status": "repair_required", "round_no": 1, "repair": {"failed_step_index": 3}})
    assert report["status"] == "repair_required"
    assert report["repair"] == {"failed_step_index": 3}
