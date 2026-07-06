from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(80), nullable=False, unique=True)
    password = Column(String(128), nullable=False)
    role = Column(String(16), nullable=False)
    create_time = Column(DateTime, nullable=False)


class Project(Base):
    __tablename__ = "project"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    desc = Column("desc", Text, nullable=True)
    create_time = Column(DateTime, nullable=False)


class Env(Base):
    __tablename__ = "env"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False, index=True)
    env_name = Column(String(120), nullable=False)
    base_url = Column(String(500), nullable=False)
    global_headers = Column(Text, nullable=True)
    global_vars = Column(Text, nullable=True)
    timeout = Column(Integer, nullable=True)


class ApiCase(Base):
    __tablename__ = "api_case"
    __table_args__ = (
        Index("ix_api_case_project_env", "project_id", "env_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False, index=True)
    env_id = Column(Integer, nullable=False, index=True)
    case_name = Column(String(160), nullable=False)
    method = Column(String(16), nullable=False)
    url = Column(String(500), nullable=False)
    headers = Column(Text, nullable=True)
    params = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    assert_rule = Column(Text, nullable=True)
    status = Column(String(32), nullable=True)
    create_time = Column(DateTime, nullable=False)


class UiCase(Base):
    __tablename__ = "ui_case"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False, index=True)
    case_name = Column(String(160), nullable=False)
    page_url = Column(String(500), nullable=False)
    steps = Column(Text, nullable=True)
    timeout = Column(Integer, nullable=True)
    status = Column(String(32), nullable=True)
    create_time = Column(DateTime, nullable=False)


class TestRecord(Base):
    __tablename__ = "test_record"
    __table_args__ = (
        Index("ix_test_record_type_case", "case_type", "case_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_type = Column(String(16), nullable=False, index=True)
    case_id = Column(Integer, nullable=False, index=True)
    project_id = Column(Integer, nullable=True, index=True)
    result = Column(String(32), nullable=False)
    log = Column(Text, nullable=True)
    screenshot = Column(String(500), nullable=True)
    report_path = Column(String(500), nullable=True)
    execute_time = Column(DateTime, nullable=False)


class FunctionalTask(Base):
    __tablename__ = "functional_task"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False, index=True)
    iteration_name = Column(String(160), nullable=False)
    requirement_text = Column(Text, nullable=True)
    axure_path = Column(String(500), nullable=True)
    target_url = Column(String(500), nullable=False)
    context = Column(Text, nullable=True)
    status = Column(String(32), nullable=False)
    create_time = Column(DateTime, nullable=False)


class FunctionalCase(Base):
    __tablename__ = "functional_case"
    __table_args__ = (
        Index("ix_func_case_task_status", "task_id", "automation_status"),
        Index("ix_func_case_task_result", "task_id", "test_result"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    precondition = Column(Text, nullable=True)
    steps = Column(Text, nullable=True)
    expected = Column(Text, nullable=True)
    category = Column(String(40), nullable=True)
    priority = Column(String(20), nullable=True)
    automation_status = Column(String(32), nullable=False)
    test_result = Column(String(20), nullable=True, default="untested")
    ui_case_id = Column(Integer, nullable=True)
    quality_status = Column(String(32), nullable=True, default="unchecked")
    quality_report = Column(Text, nullable=True)
    failure_count = Column(Integer, nullable=True, default=0)
    create_time = Column(DateTime, nullable=False)


class PageSnapshot(Base):
    __tablename__ = "page_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    page_url = Column(String(500), nullable=False)
    dom_summary = Column(Text, nullable=True)
    screenshot_path = Column(String(500), nullable=True)
    scan_time = Column(DateTime, nullable=False)


class FunctionalScreenshot(Base):
    __tablename__ = "functional_screenshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    image_path = Column(String(500), nullable=False)
    analysis_result = Column(Text, nullable=True)
    create_time = Column(DateTime, nullable=False)


class FunctionalRequirementNote(Base):
    __tablename__ = "functional_requirement_note"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    note_text = Column(Text, nullable=False)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=True)


class FunctionalRun(Base):
    __tablename__ = "functional_run"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    result = Column(String(32), nullable=False)
    log = Column(Text, nullable=True)
    passed_count = Column(Integer, nullable=False)
    failed_count = Column(Integer, nullable=False)
    execute_time = Column(DateTime, nullable=False)


class FunctionalImpactItem(Base):
    __tablename__ = "functional_impact_item"
    __table_args__ = (
        Index("ix_func_impact_task_result", "task_id", "test_result"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    item_type = Column(String(40), nullable=False)
    ref_id = Column(Integer, nullable=True, index=True)
    title = Column(String(200), nullable=False)
    target = Column(String(500), nullable=True)
    risk_level = Column(String(20), nullable=True)
    test_result = Column(String(20), nullable=True, default="untested")
    source = Column(String(40), nullable=True)
    reason = Column(Text, nullable=True)
    remark = Column(Text, nullable=True)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=True)


class FunctionalDataCheckRule(Base):
    __tablename__ = "functional_data_check_rule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    rule_name = Column(String(160), nullable=False)
    check_type = Column(String(40), nullable=False)
    page_value = Column(Text, nullable=True)
    api_method = Column(String(16), nullable=True)
    api_url = Column(String(500), nullable=True)
    api_headers = Column(Text, nullable=True)
    api_body = Column(Text, nullable=True)
    api_value_path = Column(String(200), nullable=True)
    compare_rule = Column(Text, nullable=True)
    expected_value = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="active")
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=True)


class FunctionalDataCheckResult(Base):
    __tablename__ = "functional_data_check_result"
    __table_args__ = (
        Index("ix_func_data_check_task_result", "task_id", "result"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    rule_id = Column(Integer, nullable=False, index=True)
    result = Column(String(32), nullable=False)
    page_value = Column(Text, nullable=True)
    api_value = Column(Text, nullable=True)
    message = Column(Text, nullable=True)
    detail = Column(Text, nullable=True)
    execute_time = Column(DateTime, nullable=False)


class CaseGenerationTask(Base):
    __tablename__ = "case_generation_task"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False, index=True)
    task_name = Column(String(160), nullable=False)
    target_name = Column(String(240), nullable=False)
    target_url = Column(String(500), nullable=True)
    requirement_text = Column(Text, nullable=True)
    context = Column(Text, nullable=True)
    status = Column(String(32), nullable=False)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=True)


class CaseGenerationScreenshot(Base):
    __tablename__ = "case_generation_screenshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    image_path = Column(String(500), nullable=False)
    analysis_result = Column(Text, nullable=True)
    ocr_text = Column(Text, nullable=True)
    corrected_text = Column(Text, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    low_confidence_items = Column(Text, nullable=True)
    regions = Column(Text, nullable=True)
    needs_manual_confirm = Column(Integer, nullable=False, default=1)
    ocr_error = Column(Text, nullable=True)
    create_time = Column(DateTime, nullable=False)


class CaseGenerationRequirementNote(Base):
    __tablename__ = "case_generation_requirement_note"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    note_text = Column(Text, nullable=False)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=True)


class CaseGenerationCase(Base):
    __tablename__ = "case_generation_case"
    __table_args__ = (
        Index("ix_case_generation_case_task_result", "task_id", "test_result"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    precondition = Column(Text, nullable=True)
    steps = Column(Text, nullable=True)
    expected = Column(Text, nullable=True)
    priority = Column(String(20), nullable=True)
    source_refs = Column(Text, nullable=True)
    generation_batch = Column(String(80), nullable=True)
    manual_edited = Column(Integer, nullable=False, default=0)
    test_result = Column(String(20), nullable=True, default="untested")
    source_missing = Column(Integer, nullable=False, default=0)
    remark = Column(Text, nullable=True)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=True)


class AiConfig(Base):
    __tablename__ = "ai_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(40), nullable=False)
    base_url = Column(String(500), nullable=True)
    model = Column(String(160), nullable=True)
    api_key = Column(String(500), nullable=True)
    create_time = Column(DateTime, nullable=False)
    heal_enabled = Column(Integer, nullable=False, default=1)
    heal_confidence_threshold = Column(Float, nullable=False, default=0.7)

class TestAccountProfile(Base):
    __tablename__ = "test_account_profile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=True, index=True)
    profile_name = Column(String(160), nullable=False)
    variables = Column(Text, nullable=True)
    sensitive_variables = Column(Text, nullable=True)
    login_url = Column(String(500), nullable=True)
    username_locator = Column(Text, nullable=True)
    password_locator = Column(Text, nullable=True)
    submit_locator = Column(Text, nullable=True)
    success_url_contains = Column(String(500), nullable=True)
    success_selector = Column(String(500), nullable=True)
    status = Column(String(32), nullable=False)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=True)


class TestAccountBinding(Base):
    __tablename__ = "test_account_binding"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target_type = Column(String(40), nullable=False, index=True)
    target_id = Column(Integer, nullable=False, index=True)
    account_profile_id = Column(Integer, nullable=True, index=True)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=True)


class ActionTemplate(Base):
    __tablename__ = "action_template"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    trigger_keywords = Column(Text, nullable=True)
    steps = Column(Text, nullable=False)
    variables = Column(Text, nullable=True)
    locator_fallbacks = Column(Text, nullable=True)
    create_time = Column(DateTime, nullable=False)


class LocatorHealLog(Base):
    __tablename__ = "locator_heal_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, nullable=False, index=True)
    old_locator = Column(String(500), nullable=False)
    new_locator = Column(String(500), nullable=False)
    page_url = Column(String(500), nullable=True)
    screenshot_path = Column(String(500), nullable=True)
    confirmed = Column(Integer, nullable=False, default=0)
    create_time = Column(DateTime, nullable=False)
    # 自动自愈扩展字段
    step_action = Column(String(32), nullable=True)
    ai_prompt = Column(Text, nullable=True)
    ai_response = Column(Text, nullable=True)
    auto_applied = Column(Integer, nullable=False, default=0)


class LocatorHealHistory(Base):
    """Locator 自愈历史学习表：记录同一 locator 的历史映射，加速二次自愈。"""
    __tablename__ = "locator_heal_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=True, index=True)
    old_locator = Column(String(500), nullable=False)
    new_locator = Column(String(500), nullable=False)
    apply_count = Column(Integer, nullable=False, default=1)
    success_count = Column(Integer, nullable=False, default=0)
    last_used = Column(DateTime, nullable=True)
    create_time = Column(DateTime, nullable=False)


class RecordedFlow(Base):
    """录制流程：浏览器操作录制的接口序列（如样品单支付→后台处理）。"""
    __tablename__ = "recorded_flow"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    steps = relationship("RecordedFlowStep", back_populates="flow", cascade="all, delete-orphan")


class RecordedFlowStep(Base):
    """录制流程步骤：单条接口请求信息，body 中动态值以 {{var}} 占位。"""
    __tablename__ = "recorded_flow_step"

    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_id = Column(Integer, ForeignKey("recorded_flow.id", ondelete="CASCADE"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    method = Column(String(10), nullable=False)
    path = Column(String(500), nullable=False)
    headers_json = Column(Text, nullable=True)
    body_template = Column(Text, nullable=True)
    field_schema_json = Column(Text, nullable=True)
    response_extraction_json = Column(Text, nullable=True)

    flow = relationship("RecordedFlow", back_populates="steps")

