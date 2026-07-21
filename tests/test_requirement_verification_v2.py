from datetime import datetime

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.models import (
    Project,
    RequirementVerification,
    VerificationItem,
    VerificationRun,
    VerificationRunItem,
)
from app.services.verification_learning import boundary_combinations, defect_draft, sanitize_learning_payload
from app.services.verification_runtime_v2 import (
    VerificationAwaitingUser,
    cancel_run,
    classify_failure,
    conditions_compatible,
    consume_manual_decision,
    evaluate_conditions,
    group_items_by_conditions,
    recover_unfinished_runs,
    request_manual_action,
    resolve_manual_action,
    should_reuse_data,
)


def _item(item_id, conditions):
    return VerificationItem(
        id=item_id,
        task_id=1,
        analysis_version=1,
        item_type="data",
        title=f"验证项{item_id}",
        priority="P1",
        config_json=__import__("json").dumps({"conditions": conditions}, ensure_ascii=False),
        automation_level="auto",
        risk_level="low",
        status="confirmed",
        confirmed=1,
        create_time=datetime.now(),
    )


def test_condition_grouping_and_data_validation_are_business_safe():
    low = [{"field": "order_amount", "operator": "lte", "value": "1000"}, {"field": "customer_level", "operator": "in", "value": ["V0", "V1", "V2", "V3", "V4"]}]
    high = [{"field": "order_amount", "operator": "gt", "value": "1000"}]
    assert conditions_compatible(low, high) is False
    groups = group_items_by_conditions([_item(1, low), _item(2, low), _item(3, high)])
    assert sorted(len(group["item_ids"]) for group in groups) == [1, 2]
    valid = evaluate_conditions(low, {"order_amount": "999", "customer_level": "V2"})
    assert valid["passed"] is True
    assert evaluate_conditions([{"field": "quantity", "operator": "eq", "value": 3}], {"item_quantity": 3})["passed"] is True
    assert evaluate_conditions([{"field": "item_count", "operator": "eq", "value": 2}], {"selected_count": 2})["passed"] is True
    invalid = evaluate_conditions(low, {"order_amount": "1100", "customer_level": "V2"})
    assert invalid["passed"] is False
    missing = evaluate_conditions(low, {"order_amount": "999"})
    assert missing["passed"] is False
    assert missing["missing_fields"] == ["customer_level"]


def test_failure_kinds_never_turn_technical_errors_into_business_failures():
    assert classify_failure("当前登录已失效") == "auth_error"
    assert classify_failure("页面业务区域加载超时") == "page_not_ready"
    assert classify_failure("无法可靠定位その他字段") == "locator_error"
    assert classify_failure("数据不符合前置条件") == "data_invalid"
    assert should_reuse_data("auth_error") is True
    assert should_reuse_data("locator_error") is True
    assert should_reuse_data("data_invalid") is False
    assert should_reuse_data("business_mismatch") is False


def test_manual_takeover_is_persisted_without_timeout_and_can_resume_after_new_session():
    db = SessionLocal()
    try:
        project = Project(name="V2人工接管", desc="", create_time=datetime.now())
        db.add(project)
        db.flush()
        task = RequirementVerification(project_id=project.id, name="登录恢复", status="ready", analysis_version=1, create_time=datetime.now())
        db.add(task)
        db.flush()
        item = _item(1001, [])
        item.task_id = task.id
        db.add(item)
        db.flush()
        run = VerificationRun(task_id=task.id, status="running", phase="running", variables_json="{}", summary_json="{}", visible_browser=1, create_time=datetime.now())
        db.add(run)
        db.flush()
        run_item = VerificationRunItem(run_id=run.id, item_id=item.id, result="running", evidence_json="{}", resume_json="{}")
        db.add(run_item)
        db.commit()
        with pytest.raises(VerificationAwaitingUser):
            request_manual_action(db, run, run_item, {"type": "login", "message": "请完成验证码"})
        run_item_id = run_item.id
    finally:
        db.close()

    resumed_db = SessionLocal()
    try:
        persisted = resumed_db.get(VerificationRunItem, run_item_id)
        assert persisted.result == "waiting_user"
        run = resolve_manual_action(resumed_db, persisted, "continue", note="登录完成")
        assert run.status == "queued"
        persisted = resumed_db.get(VerificationRunItem, run_item_id)
        decision = consume_manual_decision(persisted, "login")
        assert decision["decision"] == "continue"
        assert decision["note"] == "登录完成"
    finally:
        resumed_db.close()


def test_cancel_waiting_run_finishes_immediately_and_cancels_unfinished_items():
    db = SessionLocal()
    try:
        project = Project(name="V2取消执行", desc="", create_time=datetime.now())
        db.add(project)
        db.flush()
        task = RequirementVerification(project_id=project.id, name="取消人工等待", status="waiting_user", analysis_version=1, create_time=datetime.now())
        db.add(task)
        db.flush()
        item = _item(1101, [])
        item.task_id = task.id
        db.add(item)
        db.flush()
        run = VerificationRun(task_id=task.id, status="waiting_user", phase="waiting_user", variables_json="{}", summary_json="{}", visible_browser=1, create_time=datetime.now())
        db.add(run)
        db.flush()
        run_item = VerificationRunItem(run_id=run.id, item_id=item.id, result="waiting_user", evidence_json="{}", resume_json="{}")
        db.add(run_item)
        db.commit()

        cancel_run(db, run)

        db.refresh(run)
        db.refresh(run_item)
        assert run.status == "cancelled"
        assert run.finish_time is not None
        assert run_item.result == "cancelled"
        assert run_item.failure_kind == "cancelled"
    finally:
        db.close()


def test_restart_recovery_keeps_manual_waiting_and_pauses_uncertain_data_setup():
    db = SessionLocal()
    try:
        project = Project(name="V2重启恢复", desc="", create_time=datetime.now())
        db.add(project)
        db.flush()
        task = RequirementVerification(project_id=project.id, name="恢复检查点", status="running", analysis_version=1, create_time=datetime.now())
        db.add(task)
        db.flush()
        waiting = VerificationRun(task_id=task.id, status="waiting_user", phase="waiting_user", variables_json="{}", summary_json="{}", visible_browser=1, create_time=datetime.now())
        preparing = VerificationRun(task_id=task.id, status="running", phase="data_preparing", variables_json="{}", summary_json="{}", visible_browser=1, create_time=datetime.now())
        cancelling = VerificationRun(task_id=task.id, status="cancelling", phase="cancelling", variables_json="{}", summary_json="{}", visible_browser=1, create_time=datetime.now())
        db.add_all([waiting, preparing, cancelling])
        db.flush()
        item = _item(1201, [])
        item.task_id = task.id
        db.add(item)
        db.flush()
        cancelled_item = VerificationRunItem(run_id=cancelling.id, item_id=item.id, result="pending", evidence_json="{}", resume_json="{}")
        db.add(cancelled_item)
        db.commit()

        result = recover_unfinished_runs()

        db.expire_all()
        assert result["paused"] >= 1
        assert db.get(VerificationRun, waiting.id).status == "waiting_user"
        assert db.get(VerificationRun, preparing.id).status == "paused"
        assert "防止重复造数" in db.get(VerificationRun, preparing.id).pause_reason
        assert db.get(VerificationRun, cancelling.id).status == "cancelled"
        assert db.get(VerificationRunItem, cancelled_item.id).failure_kind == "cancelled"
    finally:
        db.close()


def test_learning_redaction_and_boundary_generation():
    safe = sanitize_learning_payload(
        {
            "password": "123456",
            "token": "secret-token",
            "note": "手机号 13800138000",
            "nested": {"cookie": "session=abc"},
        }
    )
    assert safe["password"] == "***"
    assert safe["token"] == "***"
    assert "13800138000" not in safe["note"]
    assert safe["nested"]["cookie"] == "***"

    db = SessionLocal()
    try:
        project = Project(name="边界组合", desc="", create_time=datetime.now())
        db.add(project)
        db.flush()
        task = RequirementVerification(project_id=project.id, name="手续费边界", status="ready", analysis_version=1, create_time=datetime.now())
        db.add(task)
        db.flush()
        item = _item(2001, [{"field": "order_amount", "operator": "lte", "value": "1000", "unit": "CNY"}, {"field": "customer_level", "operator": "in", "value": ["V0", "V2", "V4"]}])
        item.task_id = task.id
        db.add(item)
        db.commit()
        result = boundary_combinations(db, task.id)
        amounts = {row["conditions"].get("order_amount") for row in result["items"]}
        assert {"999", "1000", "1001"}.issubset(amounts)
        assert "笛卡尔积" in result["strategy"]
    finally:
        db.close()


def test_defect_draft_only_accepts_real_business_mismatch():
    db = SessionLocal()
    try:
        project = Project(name="缺陷草稿", desc="", create_time=datetime.now())
        db.add(project)
        db.flush()
        task = RequirementVerification(project_id=project.id, name="金额核对", status="failed", analysis_version=1, create_time=datetime.now())
        db.add(task)
        db.flush()
        item = _item(3001, [])
        item.task_id = task.id
        item.expected = "应为1060"
        db.add(item)
        db.flush()
        run = VerificationRun(task_id=task.id, status="failed", phase="failed", variables_json='{"order_sn":"ORDER-1"}', summary_json="{}", visible_browser=1, create_time=datetime.now())
        db.add(run)
        db.flush()
        technical = VerificationRunItem(run_id=run.id, item_id=item.id, result="needs_review", failure_kind="locator_error", message="无法定位", actual_json="{}", evidence_json="{}")
        business = VerificationRunItem(run_id=run.id, item_id=item.id, result="failed", failure_kind="business_mismatch", message="实际999", actual_json='{"actual":"999"}', evidence_json='{"actions":[],"screenshots":[]}')
        db.add_all([technical, business])
        db.commit()
        with pytest.raises(HTTPException):
            defect_draft(db, technical.id)
        draft = defect_draft(db, business.id)
        assert draft["business_keys"]["order_sn"] == "ORDER-1"
        assert "应为1060" in draft["copy_text"]
    finally:
        db.close()
