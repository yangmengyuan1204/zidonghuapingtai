from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel


RoleName = Literal["admin", "normal"]


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


class FunctionalTaskCreate(BaseModel):
    project_id: int
    iteration_name: str
    requirement_text: Optional[str] = ""
    target_url: str
    status: Optional[str] = "draft"


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


class FunctionalExecuteRequest(BaseModel):
    variables: Dict[str, Any] = {}


class AiConfigUpdate(BaseModel):
    provider: str = "openai_compatible"
    base_url: Optional[str] = ""
    model: Optional[str] = ""
    api_key: Optional[str] = ""
