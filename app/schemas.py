from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel


RoleName = Literal["admin", "normal"]
AccountBindingTarget = Literal["project", "functional_task", "functional_case", "ui_case"]


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: RoleName = "normal"


class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[RoleName] = None


class ProjectCreate(BaseModel):
    name: str
    desc: Optional[str] = ""


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    desc: Optional[str] = None


class EnvCreate(BaseModel):
    project_id: int
    env_name: str
    base_url: str
    global_headers: Any = None
    global_vars: Any = None
    timeout: Optional[int] = 30


class EnvUpdate(BaseModel):
    project_id: Optional[int] = None
    env_name: Optional[str] = None
    base_url: Optional[str] = None
    global_headers: Any = None
    global_vars: Any = None
    timeout: Optional[int] = None


class ApiCaseCreate(BaseModel):
    project_id: int
    env_id: int
    case_name: str
    method: str
    url: str
    headers: Any = None
    params: Any = None
    body: Any = None
    assert_rule: Any = None
    status: Optional[str] = "active"


class ApiCaseUpdate(BaseModel):
    project_id: Optional[int] = None
    env_id: Optional[int] = None
    case_name: Optional[str] = None
    method: Optional[str] = None
    url: Optional[str] = None
    headers: Any = None
    params: Any = None
    body: Any = None
    assert_rule: Any = None
    status: Optional[str] = None


class ApiExecuteRequest(BaseModel):
    env_id: Optional[int] = None
    variables: Dict[str, Any] = {}


class ApiBatchExecuteRequest(BaseModel):
    case_ids: list[int]
    env_id: Optional[int] = None
    variables: Dict[str, Any] = {}


class DataScriptExecuteRequest(BaseModel):
    project_id: Optional[int] = None
    env_id: Optional[int] = None
    variables: Dict[str, Any] = {}


class UiCaseCreate(BaseModel):
    project_id: int
    case_name: str
    page_url: str
    steps: Any = None
    timeout: Optional[int] = 30
    status: Optional[str] = "active"


class UiCaseUpdate(BaseModel):
    project_id: Optional[int] = None
    case_name: Optional[str] = None
    page_url: Optional[str] = None
    steps: Any = None
    timeout: Optional[int] = None
    status: Optional[str] = None


class TestAccountProfileCreate(BaseModel):
    project_id: Optional[int] = None
    profile_name: str
    variables: Dict[str, Any] = {}
    sensitive_variables: Dict[str, Any] = {}
    login_url: Optional[str] = ""
    username_locator: Optional[str] = ""
    password_locator: Optional[str] = ""
    submit_locator: Optional[str] = ""
    success_url_contains: Optional[str] = ""
    success_selector: Optional[str] = ""
    status: Optional[str] = "active"


class TestAccountProfileUpdate(BaseModel):
    project_id: Optional[int] = None
    profile_name: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    sensitive_variables: Optional[Dict[str, Any]] = None
    login_url: Optional[str] = None
    username_locator: Optional[str] = None
    password_locator: Optional[str] = None
    submit_locator: Optional[str] = None
    success_url_contains: Optional[str] = None
    success_selector: Optional[str] = None
    status: Optional[str] = None


class TestAccountBindingUpdate(BaseModel):
    target_type: AccountBindingTarget
    target_id: int
    account_profile_id: Optional[int] = None


class FunctionalTaskCreate(BaseModel):
    project_id: int
    iteration_name: str
    requirement_text: Optional[str] = ""
    target_url: str
    context: Optional[str] = ""
    status: Optional[str] = "draft"


class FunctionalTaskContextUpdate(BaseModel):
    context: str


class FunctionalTaskAxureBindingUpdate(BaseModel):
    page_ids: list[str] = []


class FunctionalCaseUpdate(BaseModel):
    title: Optional[str] = None
    precondition: Optional[str] = None
    steps: Optional[str] = None
    expected: Optional[str] = None
    priority: Optional[str] = None
    automation_status: Optional[str] = None


class FunctionalRequirementNoteCreate(BaseModel):
    note_text: str


class FunctionalRequirementNoteUpdate(BaseModel):
    note_text: str


class FunctionalScanAuth(BaseModel):
    enabled: bool = False
    login_url: Optional[str] = ""
    username: Optional[str] = ""
    password: Optional[str] = ""
    username_locator: Optional[str] = ""
    password_locator: Optional[str] = ""
    submit_locator: Optional[str] = ""
    success_url_contains: Optional[str] = ""
    success_selector: Optional[str] = ""


class FunctionalScanRequest(BaseModel):
    auth: Optional[FunctionalScanAuth] = None


class FunctionalScreenshotOrderUpdate(BaseModel):
    screenshot_ids: list[int]


class FunctionalCaseStatusUpdate(BaseModel):
    test_result: str = "untested"


class FunctionalCaseBatchStatusUpdate(BaseModel):
    case_ids: list[int]
    test_result: str = "untested"


class FunctionalCaseStats(BaseModel):
    total: int = 0
    untested: int = 0
    passed: int = 0
    failed: int = 0
    blocked: int = 0
    skipped: int = 0


class FunctionalExecuteRequest(BaseModel):
    variables: Dict[str, Any] = {}
    account_profile_id: Optional[int] = None
    account_mode: Optional[str] = "default"
    case_id: Optional[int] = None


class CaseGenerationTaskCreate(BaseModel):
    project_id: int
    task_name: str
    target_name: str
    target_url: Optional[str] = ""
    requirement_text: Optional[str] = ""
    context: Optional[str] = ""
    status: Optional[str] = "draft"


class CaseGenerationTaskUpdate(BaseModel):
    project_id: Optional[int] = None
    task_name: Optional[str] = None
    target_name: Optional[str] = None
    target_url: Optional[str] = None
    requirement_text: Optional[str] = None
    context: Optional[str] = None
    status: Optional[str] = None


class CaseGenerationRequirementNoteCreate(BaseModel):
    note_text: str


class CaseGenerationRequirementNoteUpdate(BaseModel):
    note_text: str


class CaseGenerationScreenshotOcrUpdate(BaseModel):
    corrected_text: str = ""


class CaseGenerationCaseUpdate(BaseModel):
    title: Optional[str] = None
    precondition: Optional[str] = None
    steps: Optional[str] = None
    expected: Optional[str] = None
    priority: Optional[str] = None
    remark: Optional[str] = None


class CaseGenerationCaseStatusUpdate(BaseModel):
    test_result: str = "untested"


class CaseGenerationCaseBatchStatusUpdate(BaseModel):
    case_ids: list[int]
    test_result: str = "untested"


class AiConfigUpdate(BaseModel):
    provider: str = "openai_compatible"
    base_url: Optional[str] = ""
    model: Optional[str] = ""
    api_key: Optional[str] = ""


class QuickRunRequest(BaseModel):
    method: str = "GET"
    url: str
    headers: Dict[str, str] = {}
    body: str = ""


class ActionTemplateCreate(BaseModel):
    project_id: int
    name: str
    description: Optional[str] = ""
    trigger_keywords: Any = None
    steps: Any = None
    variables: Any = None
    locator_fallbacks: Any = None


class ActionTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_keywords: Any = None
    steps: Any = None
    variables: Any = None
    locator_fallbacks: Any = None


class LocatorHealLogConfirm(BaseModel):
    confirmed: int = 1


class PreflightResult(BaseModel):
    passed: bool
    warnings: list[str] = []
    errors: list[str] = []

