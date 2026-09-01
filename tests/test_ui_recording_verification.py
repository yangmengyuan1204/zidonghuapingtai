import json
from types import SimpleNamespace

import pytest

from app.services import ui_recording_verification as verification
from app.services.ui_recording_reset import ResetExecutionResult
from app.services.ui_recording_verification import (
    RoundResult,
    VerificationControl,
    _VerificationRunner,
    cleanup_verification,
    request_repick,
    _register_control,
)


def _passed_reset():
    return ResetExecutionResult(passed=True, raw_outputs={}, runtime_variables={}, public_report={})


def _passed_round():
    return RoundResult(round_no=0, passed=True, log_text="{}", screenshot="")


def _failed_round(category, step_index):
    return RoundResult(
        round_no=0,
        passed=False,
        log_text=json.dumps({"failed_step_index": step_index}, ensure_ascii=False),
        screenshot="",
        category=category,
        failed_step_index=step_index,
    )


@pytest.fixture
def runner():
    row = SimpleNamespace(
        run_id="run-1",
        session_id="session-1",
        project_id=1,
        status="queued",
        report_json="{}",
        error_category="",
        update_time=None,
    )
    instance = _VerificationRunner(
        row=row,
        case_data={"case_name": "测试", "page_url": "https://example.test", "steps": [], "timeout": 30},
        storage_state=None,
        db=None,
    )
    _register_control(VerificationControl(run_id=row.run_id))
    yield instance
    cleanup_verification(row.run_id)


def test_each_round_resets_data_before_browser(monkeypatch, runner):
    calls = []
    monkeypatch.setattr(runner, "execute_recording_reset", lambda *_: calls.append("reset") or _passed_reset())
    monkeypatch.setattr(runner, "execute_round", lambda round_no, *_args: calls.append(f"round-{round_no}") or _passed_round())

    runner.run()

    assert calls == ["reset", "round-1", "reset", "round-2"]
    assert runner.row.status == "passed"


def test_second_round_is_frozen(monkeypatch, runner):
    contexts = []
    monkeypatch.setattr(runner, "execute_recording_reset", lambda *_args: _passed_reset())

    def run_round(_round, context):
        contexts.append(context)
        return _passed_round()

    monkeypatch.setattr(runner, "execute_round", run_round)
    runner.run()

    assert contexts[0]["execution"]["freeze_resolution"] is False
    assert contexts[0]["execution"]["disable_ai_heal"] is False
    assert contexts[1]["execution"]["freeze_resolution"] is True
    assert contexts[1]["execution"]["disable_ai_heal"] is True
    assert contexts[1]["execution"]["retry_count"] == 0


def test_locator_failure_pauses_first_round_for_repick(monkeypatch, runner):
    monkeypatch.setattr(runner, "execute_recording_reset", lambda *_args: _passed_reset())
    monkeypatch.setattr(runner, "execute_round", lambda *_args: _failed_round("定位器找不到", step_index=3))

    runner.run()

    assert runner.row.status == "repair_required"
    assert runner.browser_is_open is True


def test_second_round_failure_is_final(monkeypatch, runner):
    monkeypatch.setattr(runner, "execute_recording_reset", lambda *_args: _passed_reset())

    def run_round(round_no, _context):
        if round_no == 1:
            return _passed_round()
        return _failed_round("定位器找不到", step_index=2)

    monkeypatch.setattr(runner, "execute_round", run_round)
    runner.run()

    assert runner.row.status == "failed"
    assert runner.browser_is_open is False


def test_reset_failure_stops_before_browser(monkeypatch, runner):
    calls = []
    failed = ResetExecutionResult(passed=False, raw_outputs={}, runtime_variables={}, public_report={}, error="重置失败")
    monkeypatch.setattr(runner, "execute_recording_reset", lambda *_args: calls.append("reset") or failed)
    monkeypatch.setattr(runner, "execute_round", lambda *_args: calls.append("round") or _passed_round())

    runner.run()

    assert calls == ["reset"]
    assert runner.row.status == "failed"
    assert runner.browser_is_open is False


def test_repair_limit_prevents_infinite_loop(monkeypatch, runner):
    _register_control(VerificationControl(run_id=runner.row.run_id, repair_attempts=3, max_repair_attempts=3))

    with pytest.raises(ValueError, match="已达到最大重新选点次数"):
        request_repick(runner.row.run_id, 3)


def test_request_repick_signals_control(monkeypatch, runner):
    control = _register_control(VerificationControl(run_id=runner.row.run_id))
    result = request_repick(runner.row.run_id, 2)

    assert result["status"] == "repick_waiting"
    assert control.requested_step_index == 2
    assert control.repick_requested.is_set()
    assert control.repair_attempts == 1


def test_request_repick_requires_live_control(monkeypatch):
    cleanup_verification("missing-run")
    with pytest.raises(ValueError, match="验证不在运行中或已结束"):
        request_repick("missing-run", 1)


def test_apply_repick_persists_target_override(monkeypatch):
    overrides = {}
    monkeypatch.setattr(verification, "override_session_step_target", lambda session_id, index, candidates, profile: overrides.update(
        {"session_id": session_id, "index": index, "candidates": candidates, "profile": profile}) or {"ok": True}, raising=False)

    def fake_build(source):
        return {"element": {"stable_attrs": source.get("stable_attrs") or {}}}

    monkeypatch.setattr(verification, "build_target_profile", fake_build, raising=False)
    monkeypatch.setattr(
        verification,
        "_evaluate_repick",
        lambda _page, _step_index: {"locator_candidates": ["#save"], "target_profile_source": {"stable_attrs": {"id": "save"}}},
        raising=False,
    )
    row = SimpleNamespace(session_id="session-1", status="repair_required", update_time=None, report_json="{}")
    control = VerificationControl(run_id="run-1", requested_step_index=3)
    verification._apply_repick(control, object(), row)

    assert row.status == "repair_ready"
    assert overrides["session_id"] == "session-1"
    assert overrides["index"] == 3
    assert overrides["candidates"] == ["#save"]
    assert overrides["profile"]["element"]["stable_attrs"] == {"id": "save"}


def test_runner_emits_state_and_reset_progress(monkeypatch):
    payloads = []
    row = SimpleNamespace(run_id="run-2", session_id="s", project_id=1, status="queued", report_json="{}", error_category="", update_time=None)
    instance = _VerificationRunner(
        row=row,
        case_data={"case_name": "测试", "page_url": "https://example.test", "steps": [], "timeout": 30},
        storage_state=None,
        db=None,
        progress_callback=lambda payload: payloads.append(dict(payload)),
    )
    monkeypatch.setattr(instance, "execute_recording_reset", lambda *_args: _passed_reset())
    monkeypatch.setattr(instance, "execute_round", lambda _round, _context: _passed_round())

    instance.run()

    events = [item for item in payloads if item.get("event") == "state"]
    assert [item["status"] for item in events] == ["resetting", "round_1_running", "round_1_passed", "resetting", "round_2_running", "passed"]
    assert [item["round_no"] for item in events] == [1, 1, 1, 2, 2, 2]
    reset_events = [item for item in payloads if item.get("event") == "reset"]
    assert len(reset_events) == 2
    assert reset_events[0]["reset"] == {}
    assert reset_events[0]["round_no"] == 1


def test_worker_records_both_successful_rounds_as_passed(monkeypatch):
    row = SimpleNamespace(
        run_id="run-worker",
        session_id="session-worker",
        project_id=1,
        status="queued",
        report_json="{}",
        error_category="",
        update_time=None,
    )

    class _Db:
        def get(self, _model, run_id):
            return row if run_id == row.run_id else None

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    class _Runner:
        def __init__(self, target, _case_data, _storage, _db, progress_callback=None):
            self.row = target
            self.progress_callback = progress_callback

        def run(self):
            self.progress_callback({"event": "state", "status": "round_1_passed", "round_no": 1})
            self.progress_callback({"event": "state", "status": "passed", "round_no": 2})
            self.row.status = "passed"

        def close_browser(self):
            return None

    monkeypatch.setattr(verification, "SessionLocal", lambda: _Db())
    monkeypatch.setattr(verification, "get_recording_config", lambda *_args: SimpleNamespace(max_repair_attempts=3))
    monkeypatch.setattr(verification, "_VerificationRunner", _Runner)

    verification._run_verification_worker(
        row.run_id,
        {"steps": [{"action": "goto", "value": "https://example.test"}]},
        None,
    )

    report = json.loads(row.report_json)
    assert [item["status"] for item in report["rounds"]] == ["passed", "passed"]


def test_repair_required_emits_repair_progress(monkeypatch):
    payloads = []
    row = SimpleNamespace(run_id="run-3", session_id="s", project_id=1, status="queued", report_json="{}", error_category="", update_time=None)
    instance = _VerificationRunner(
        row=row,
        case_data={"case_name": "测试", "page_url": "https://example.test", "steps": [], "timeout": 30},
        storage_state=None,
        db=None,
        progress_callback=lambda payload: payloads.append(dict(payload)),
    )
    monkeypatch.setattr(instance, "execute_recording_reset", lambda *_args: _passed_reset())
    monkeypatch.setattr(instance, "execute_round", lambda _round, _context: _failed_round("定位器找不到", step_index=3))

    instance.run()

    repair_events = [item for item in payloads if item.get("event") == "repair"]
    assert repair_events and repair_events[-1]["status"] == "repair_required"
    assert repair_events[-1]["repair"]["failed_step_index"] == 3


def test_wait_for_repick_marks_repick_waiting_before_apply(monkeypatch):
    seen = {}
    monkeypatch.setattr(verification, "_apply_repick", lambda control, page, row: seen.update({"before": row.status}) or setattr(row, "status", "repair_ready"), raising=False)
    row = SimpleNamespace(run_id="run-4", status="repair_required", update_time=None, error_category="")
    control = VerificationControl(run_id="run-4")
    control.repick_requested.set()
    fake_runner = SimpleNamespace(db=None, row=row, page=object())

    verification._wait_for_repick(control, fake_runner)

    assert seen["before"] == "repick_waiting"
    assert row.status == "repair_ready"


def test_repick_uses_failed_step_page_and_iframe_context(monkeypatch):
    frame = object()

    class _Handle:
        def content_frame(self):
            return frame

    class _FrameLocator:
        def count(self):
            return 1

        def element_handle(self):
            return _Handle()

    first = SimpleNamespace(url="https://example.test/home", title=lambda: "主页")
    second = SimpleNamespace(
        url="https://example.test/pay",
        title=lambda: "支付页",
        locator=lambda selector: _FrameLocator() if selector == "iframe[name=pay]" else None,
    )
    context = SimpleNamespace(pages=[first, second])
    first.context = second.context = context
    monkeypatch.setattr(verification, "get_session_state", lambda _sid: {
        "preview_steps": [
            {"action": "goto", "value": "https://example.test/home"},
            {
                "action": "input",
                "target_profile": {
                    "page": {"title": "支付页"},
                    "frame_chain": [{"selector": "iframe[name=pay]"}],
                },
            },
        ],
    }, raising=False)
    used = {}
    monkeypatch.setattr(verification, "_evaluate_repick", lambda target, _index: used.update({"target": target}) or {
        "locator_candidates": ["#card"],
        "target_profile_source": {"stable_attrs": {"id": "card"}},
    })
    monkeypatch.setattr(verification, "override_session_step_target", lambda *_args: None)
    monkeypatch.setattr(verification, "build_target_profile", lambda source: source)
    row = SimpleNamespace(session_id="session-frame", status="repair_required", error_category="", report_json="{}")

    verification._apply_repick(VerificationControl(run_id="run", requested_step_index=2), first, row)

    assert row.status == "repair_ready"
    assert used["target"] is frame


def test_repick_script_contains_bounded_timeout_and_cleanup():
    script = verification.repick_script(3, timeout_ms=1500)

    assert "setTimeout" in script
    assert "1500" in script
    assert "removeEventListener" in script
