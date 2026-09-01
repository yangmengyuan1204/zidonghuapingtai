from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from ..database import SessionLocal
from ..models import UiRecordPreflight
from .ui_recording_capture import recording_init_script, repick_script
from .ui_recording_config import get_recording_config
from .ui_recording_reset import ResetExecutionResult, execute_recording_reset, resolve_reset_templates
from .ui_recording_session import get_session_state, override_session_step_target
from .ui_target_profile import build_target_profile
from .ui_target_resolver import select_profile_page

# 第一轮修复等待上限：超过后按环境失败收尾，避免后台线程无限等待
REPAIR_WAIT_SECONDS = 600.0
DEFAULT_MAX_REPAIR_ATTEMPTS = 3

# 可进入重新选点修复的失败分类（定位/交互/效果）；其余按最终失败处理
_REPAIR_CATEGORIES = frozenset({
    "定位器写法错误", "定位器不唯一", "定位器找不到",
    "元素不可见/不可点击", "操作超时",
    "locator_error", "effect_error", "interaction_error",
})


@dataclass
class VerificationControl:
    run_id: str
    repick_requested: threading.Event = field(default_factory=threading.Event)
    stop_requested: threading.Event = field(default_factory=threading.Event)
    requested_step_index: int = 0
    repair_attempts: int = 0
    max_repair_attempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS


_CONTROLS: dict[str, VerificationControl] = {}
_CONTROLS_LOCK = threading.Lock()


def _register_control(control: VerificationControl) -> VerificationControl:
    with _CONTROLS_LOCK:
        _CONTROLS[control.run_id] = control
    return control


def _get_control(run_id: str) -> VerificationControl | None:
    with _CONTROLS_LOCK:
        return _CONTROLS.get(run_id)


def cleanup_verification(run_id: str) -> None:
    with _CONTROLS_LOCK:
        control = _CONTROLS.pop(run_id, None)
    if control:
        control.stop_requested.set()


@dataclass
class RoundResult:
    round_no: int
    passed: bool
    log_text: str = ""
    screenshot: str = ""
    category: str = ""
    failed_step_index: Any = None
    failed_step_detail: dict[str, Any] | None = None


def _failure_category(log_text: str) -> str:
    try:
        data = json.loads(log_text or "{}")
    except (TypeError, ValueError):
        data = {}
    detail = data.get("failed_step_detail")
    if isinstance(detail, dict):
        return str(detail.get("category") or detail.get("error_category") or "未知异常")
    return str(data.get("error_category") or "未知异常")


def _failed_step_index(log_text: str) -> Any:
    try:
        data = json.loads(log_text or "{}")
    except (TypeError, ValueError):
        return None
    value = data.get("failed_step_index")
    if value is None:
        detail = data.get("failed_step_detail")
        if isinstance(detail, dict):
            return detail.get("index")
    return value

def _commit(db: Any, row: UiRecordPreflight, **extra: Any) -> None:
    for key, value in extra.items():
        setattr(row, key, value)
    row.update_time = datetime.now()
    if db is not None:
        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass


def _build_case(row: UiRecordPreflight, steps: list[dict[str, Any]], timeout: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=0,
        project_id=row.project_id,
        case_name=str(getattr(row, "session_id", "") or "录制用例验证"),
        page_url="",
        steps=steps,
        timeout=timeout,
        status="draft",
    )


class _VerificationRunner:
    """双轮验证：每轮先重置数据，再开浏览器执行；第一轮修复类失败暂停等待重新选点。"""

    def __init__(
        self,
        row: UiRecordPreflight,
        case_data: dict[str, Any],
        storage_state: dict[str, Any] | None,
        db: Any,
        progress_callback: Any = None,
    ) -> None:
        self.row = row
        self.case_data = case_data
        self.storage_state = storage_state
        self.db = db
        self.progress_callback = progress_callback
        self.config = get_recording_config(db, row.project_id) if db is not None else None
        self.browser_is_open = False
        self.playwright = None
        self.browser = None
        self.page = None

    def execute_recording_reset(self) -> ResetExecutionResult:
        if self.config is None:
            return ResetExecutionResult(
                passed=False,
                raw_outputs={},
                runtime_variables={},
                public_report={},
                error="项目未配置数据重置脚本",
            )
        return execute_recording_reset(self.db, self.config)

    def _round_execution(self, round_no: int) -> dict[str, Any]:
        execution: dict[str, Any] = {"retry_count": 0, "preflight": True}
        if round_no == 2:
            execution.update({"freeze_resolution": True, "disable_ai_heal": True})
        else:
            execution.update({"freeze_resolution": False, "disable_ai_heal": False})
        return execution

    def _emit(self, callback: Any, payload: dict[str, Any], round_no: int) -> None:
        if not callback:
            return
        try:
            callback(dict(payload, round_no=round_no))
        except Exception:
            pass

    def execute_round(self, round_no: int, context: dict[str, Any]) -> RoundResult:
        from playwright.sync_api import sync_playwright

        from ..executors import execute_ui_case_in_page, launch_chromium_browser

        steps = context.get("steps") or []
        case = _build_case(self.row, steps, int(self.case_data.get("timeout") or 30))
        case_name = str(self.case_data.get("case_name") or "录制用例验证")
        case.case_name = case_name
        case.page_url = str(self.case_data.get("page_url") or "")
        playwright = sync_playwright().start()
        browser = None
        try:
            browser = launch_chromium_browser(playwright, headless=round_no != 1)
            options: dict[str, Any] = {}
            if isinstance(self.storage_state, dict) and isinstance(self.storage_state.get("cookies"), list):
                options["storage_state"] = self.storage_state
            context_obj = browser.new_context(**options)
            context_obj.add_init_script(recording_init_script())
            page = context_obj.new_page()
            passed, log_text, screenshot, _report = execute_ui_case_in_page(
                case,
                page,
                runtime_vars={},
                execution_context=context.get("execution") or {},
                db_session=self.db,
                progress_callback=context.get("progress_callback"),
            )
            if not passed and round_no == 1 and _failure_category(log_text) in _REPAIR_CATEGORIES:
                self.playwright = playwright
                self.browser = browser
                self.page = page
                self.browser_is_open = True
                return RoundResult(
                    round_no=round_no,
                    passed=False,
                    log_text=log_text,
                    screenshot=screenshot,
                    category=_failure_category(log_text),
                )
            return RoundResult(
                round_no=round_no,
                passed=passed,
                log_text=log_text,
                screenshot=screenshot,
                category="" if passed else _failure_category(log_text),
            )
        except Exception as exc:
            return RoundResult(
                round_no=round_no,
                passed=False,
                log_text="",
                screenshot="",
                category="environment_error",
                failed_step_detail={"error": str(exc)[:500]},
            )
        finally:
            if browser and not self.browser_is_open:
                try:
                    browser.close()
                except Exception:
                    pass
                try:
                    playwright.stop()
                except Exception:
                    pass

    def close_browser(self) -> None:
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
        self.playwright = None
        self.browser = None
        self.page = None
        self.browser_is_open = False

    def run(self) -> RoundResult:
        for round_no in (1, 2):
            _commit(self.db, self.row, status="resetting")
            self._emit(self.progress_callback, {"event": "state", "status": "resetting"}, round_no)
            reset_result = self.execute_recording_reset()
            if not reset_result.passed:
                _commit(self.db, self.row, status="failed", error_category="environment_error")
                self._emit(self.progress_callback, {"event": "state", "status": "failed"}, round_no)
                return RoundResult(round_no=round_no, passed=False, category="environment_error", failed_step_detail={"error": reset_result.error})
            self._emit(self.progress_callback, {"event": "reset", "status": "resetting", "reset": dict(reset_result.public_report)}, round_no)
            steps = resolve_reset_templates(list(self.case_data.get("steps") or []), reset_result.runtime_variables)
            context = {
                "round_no": round_no,
                "steps": steps,
                "reset_outputs": dict(reset_result.runtime_variables),
                "execution": self._round_execution(round_no),
                "progress_callback": self.progress_callback,
            }
            _commit(self.db, self.row, status=f"round_{round_no}_running")
            self._emit(self.progress_callback, {"event": "state", "status": f"round_{round_no}_running"}, round_no)
            result = self.execute_round(round_no, context)
            if result.passed:
                round_status = "passed" if round_no == 2 else "round_1_passed"
                self._emit(self.progress_callback, {"event": "state", "status": round_status}, round_no)
                if round_no == 1:
                    self.close_browser()
                    continue
                _commit(self.db, self.row, status="passed")
                return result
            if round_no == 1 and result.category in _REPAIR_CATEGORIES:
                self.browser_is_open = True
                _commit(self.db, self.row, status="repair_required")
                self._emit(
                    self.progress_callback,
                    {
                        "event": "repair",
                        "status": "repair_required",
                        "repair": {"failed_step_index": _failed_step_index(result.log_text), "attempts": 0},
                    },
                    round_no,
                )
                return result
            self.close_browser()
            _commit(self.db, self.row, status="failed", error_category=result.category or "environment_error")
            self._emit(self.progress_callback, {"event": "state", "status": "failed"}, round_no)
            return result
        return RoundResult(round_no=2, passed=False, category="environment_error")


def _evaluate_repick(page: Any, step_index: int) -> dict[str, Any]:
    try:
        page.evaluate(recording_init_script())
    except Exception:
        pass
    result = page.evaluate(repick_script(step_index))
    return result if isinstance(result, dict) else {}


def _repick_frame_selector(frame: dict[str, Any]) -> str:
    selector = str(frame.get("selector") or "").strip()
    if selector:
        return selector
    attrs = frame.get("stable_attrs") if isinstance(frame.get("stable_attrs"), dict) else {}
    for key in ("data-testid", "data-test", "id", "name", "title"):
        value = str(attrs.get(key) or frame.get(key) or "").strip().replace('"', '\\"')
        if value:
            return f'iframe[{key}="{value}"]'
    return "iframe"


def _repick_execution_context(page: Any, session_id: str, step_index: int) -> Any:
    try:
        state = get_session_state(session_id)
        steps = state.get("preview_steps") if isinstance(state, dict) else []
        step = steps[step_index - 1] if isinstance(steps, list) and 0 < step_index <= len(steps) else {}
    except Exception:
        step = {}
    if not isinstance(step, dict):
        return page
    selected: Any = select_profile_page(page, step, timeout_ms=5000)
    profile = step.get("target_profile") if isinstance(step.get("target_profile"), dict) else {}
    frames = profile.get("frame_chain") if isinstance(profile.get("frame_chain"), list) else []
    for index, raw in enumerate(frames, start=1):
        if not isinstance(raw, dict):
            continue
        locator = selected.locator(_repick_frame_selector(raw))
        count = int(locator.count())
        if count != 1:
            raise RuntimeError(f"重新选点 iframe 第{index}层匹配数量为 {count}")
        handle = locator.element_handle()
        selected = handle.content_frame() if handle is not None else None
        if selected is None:
            raise RuntimeError(f"重新选点 iframe 第{index}层无法进入")
    return selected


def _apply_repick(control: VerificationControl, page: Any, row: UiRecordPreflight) -> None:
    try:
        if page is None:
            raise RuntimeError("验证浏览器已关闭，无法重新选点")
        repick_context = _repick_execution_context(page, row.session_id, control.requested_step_index)
        result = _evaluate_repick(repick_context, control.requested_step_index)
        candidates = [str(item).strip() for item in (result.get("locator_candidates") or []) if str(item).strip()][:12]
        source = result.get("target_profile_source")
        profile = build_target_profile(source) if isinstance(source, dict) else {}
        if not candidates and not profile:
            raise RuntimeError("重新选点未返回可用的定位器")
        override_session_step_target(row.session_id, control.requested_step_index, candidates, profile)
        row.status = "repair_ready"
        row.error_category = ""
    except Exception as exc:
        row.status = "failed"
        row.error_category = "repick_failed"
        try:
            report = json.loads(row.report_json or "{}")
        except (TypeError, ValueError):
            report = {}
        if isinstance(report, dict):
            report["repick_error"] = str(exc)[:500]
            row.report_json = json.dumps(report, ensure_ascii=False, default=str)


def _wait_for_repick(control: VerificationControl, runner: _VerificationRunner) -> None:
    deadline = time.monotonic() + REPAIR_WAIT_SECONDS
    while time.monotonic() < deadline:
        if control.stop_requested.wait(timeout=0.25):
            _commit(runner.db, runner.row, status="failed", error_category="repick_cancelled")
            return
        if control.repick_requested.is_set():
            _commit(runner.db, runner.row, status="repick_waiting")
            _apply_repick(control, runner.page, runner.row)
            _commit(runner.db, runner.row)
            return
    _commit(runner.db, runner.row, status="failed", error_category="repick_timeout")


def _run_verification_worker(
    run_id: str,
    case_data: dict[str, Any],
    storage_state: dict[str, Any] | None,
) -> None:
    db = SessionLocal()
    try:
        row = db.get(UiRecordPreflight, run_id)
        if not row:
            return
        attempts = 0
        try:
            report = json.loads(row.report_json or "{}")
            if isinstance(report, dict):
                attempts = max(0, int(report.get("repair_attempts") or 0))
        except (TypeError, ValueError):
            pass
        config = get_recording_config(db, row.project_id)
        max_attempts = int(config.max_repair_attempts) if config and config.max_repair_attempts else DEFAULT_MAX_REPAIR_ATTEMPTS
        control = _register_control(VerificationControl(run_id=run_id, repair_attempts=attempts, max_repair_attempts=max_attempts))
        progress_report: dict[str, Any] = {"status": "queued", "steps": [], "rounds": 2}
        round_status: dict[int, str] = {}

        def progress(payload: dict[str, Any]) -> None:
            nonlocal progress_report, round_status
            from .ui_recording_preflight import merge_preflight_progress

            progress_report = merge_preflight_progress(progress_report, payload)
            round_no = payload.get("round_no")
            if isinstance(round_no, int) and round_no > 0:
                status_text = str(payload.get("status") or "")
                if payload.get("event") == "state" and status_text in {"passed", "round_1_passed", "failed"}:
                    round_status[int(round_no)] = "passed" if status_text == "round_1_passed" else status_text
                elif payload.get("event") == "repair" and status_text == "repair_required":
                    round_status[1] = "failed"
            row.report_json = json.dumps(progress_report, ensure_ascii=False, default=str)
            row.update_time = datetime.now()
            db.commit()

        runner = _VerificationRunner(row, case_data, storage_state, db, progress_callback=progress)
        runner.run()
        if row.status == "repair_required":
            _wait_for_repick(control, runner)
        if row.status == "repair_ready":
            try:
                report = json.loads(row.report_json or "{}")
            except (TypeError, ValueError):
                report = {}
            if isinstance(report, dict):
                report["repair"] = {"failed_step_index": control.requested_step_index, "attempts": control.repair_attempts}
                row.report_json = json.dumps(report, ensure_ascii=False, default=str)
        if row.status == "passed":
            try:
                report = json.loads(row.report_json or "{}")
            except (TypeError, ValueError):
                report = {}
            from .ui_recording_preflight import steps_snapshot_hash

            if isinstance(report, dict):
                report["verification_mode"] = "verified"
                report["required_rounds"] = 2
                report["verified_rounds"] = 2
                report["rounds"] = [
                    {"round_no": 1, "status": round_status.get(1, "unknown"), "frozen": False},
                    {"round_no": 2, "status": round_status.get(2, "unknown"), "frozen": True},
                ]
                report["steps_snapshot_hash"] = steps_snapshot_hash(case_data.get("steps") or [])
                row.report_json = json.dumps(report, ensure_ascii=False, default=str)
        runner.close_browser()
        row.update_time = datetime.now()
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
            row = db.get(UiRecordPreflight, run_id)
            if row:
                row.status = "failed"
                row.error_category = "environment_error"
                row.report_json = json.dumps(
                    {"status": "failed", "error": str(exc)[:500], "error_category": "environment_error", "steps": []},
                    ensure_ascii=False,
                )
                row.update_time = datetime.now()
                db.commit()
        except Exception:
            pass
    finally:
        cleanup_verification(run_id)
        try:
            db.close()
        except Exception:
            pass


def launch_verification(
    row: UiRecordPreflight,
    *,
    case_data: dict[str, Any],
    storage_state: dict[str, Any] | None,
) -> None:
    thread = threading.Thread(
        target=_run_verification_worker,
        args=(row.run_id, case_data, storage_state),
        daemon=True,
    )
    thread.start()


def request_repick(run_id: str, step_index: int) -> dict[str, Any]:
    control = _get_control(run_id)
    if not control:
        raise ValueError("验证不在运行中或已结束")
    index = int(step_index)
    if index <= 0:
        raise ValueError("步骤序号不能为空")
    if control.repair_attempts >= control.max_repair_attempts:
        raise ValueError("已达到最大重新选点次数")
    control.repair_attempts += 1
    control.requested_step_index = index
    control.repick_requested.set()
    return {"run_id": run_id, "status": "repick_waiting", "step_index": index}


def restart_verification(
    db: Any,
    row: UiRecordPreflight,
    case_data: dict[str, Any],
    storage_state: dict[str, Any] | None,
) -> None:
    from .ui_recording_preflight import create_preflight

    new_row = create_preflight(
        db,
        session_id=row.session_id,
        project_id=row.project_id,
        steps=list(case_data.get("steps") or []),
        assertion_text=str(getattr(row, "assertion_text", None) or ""),
    )
    try:
        report = json.loads(row.report_json or "{}")
    except (TypeError, ValueError):
        report = {}
    if isinstance(report, dict):
        report["restarted_run_id"] = new_row.run_id
        row.report_json = json.dumps(report, ensure_ascii=False, default=str)
    row.update_time = datetime.now()
    db.commit()
    launch_verification(new_row, case_data=case_data, storage_state=storage_state)
