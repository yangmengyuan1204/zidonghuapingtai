from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text

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
    priority = Column(String(20), nullable=True)
    automation_status = Column(String(32), nullable=False)
    test_result = Column(String(20), nullable=True, default="untested")
    ui_case_id = Column(Integer, nullable=True)
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

