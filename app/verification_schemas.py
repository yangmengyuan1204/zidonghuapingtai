from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class RequirementVerificationCreate(BaseModel):
    project_id: int
    name: str
    target_url: Optional[str] = ""
    target_pages: list[Dict[str, Any]] = Field(default_factory=list)
    data_setup: Dict[str, Any] = Field(default_factory=dict)
    requirement_text: Optional[str] = ""
    context: Optional[str] = ""


class RequirementVerificationUpdate(BaseModel):
    name: Optional[str] = None
    target_url: Optional[str] = None
    target_pages: Optional[list[Dict[str, Any]]] = None
    data_setup: Optional[Dict[str, Any]] = None
    requirement_text: Optional[str] = None
    context: Optional[str] = None
    status: Optional[str] = None
    is_archived: Optional[bool] = None


class VerificationMaterialCreate(BaseModel):
    material_type: str = "note"
    name: Optional[str] = ""
    content_text: str


class VerificationAnalysisRequest(BaseModel):
    mode: str = "standard"


class VerificationClarificationAnswer(BaseModel):
    answer: Optional[str] = ""
    supplement: Optional[str] = ""


class VerificationItemUpdate(BaseModel):
    title: Optional[str] = None
    priority: Optional[str] = None
    role_name: Optional[str] = None
    precondition: Optional[str] = None
    action_goal: Optional[str] = None
    expected: Optional[str] = None
    source_refs: Any = None
    automation_level: Optional[str] = None
    risk_level: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class VerificationItemBatchConfirm(BaseModel):
    item_ids: list[int] = Field(default_factory=list)
    confirmed: bool = True


class VerificationFormulaCreate(BaseModel):
    task_id: Optional[int] = None
    name: str
    expression: str
    variables: Dict[str, Any] = Field(default_factory=dict)
    conditions: Dict[str, Any] = Field(default_factory=dict)
    currency: Optional[str] = ""
    scale: int = 2
    rounding_mode: str = "HALF_UP"
    rounding_stage: str = "final"
    source_refs: Any = None
    status: str = "draft"


class VerificationFormulaUpdate(BaseModel):
    name: Optional[str] = None
    expression: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    conditions: Optional[Dict[str, Any]] = None
    currency: Optional[str] = None
    scale: Optional[int] = None
    rounding_mode: Optional[str] = None
    rounding_stage: Optional[str] = None
    source_refs: Any = None
    status: Optional[str] = None


class VerificationDataSourceCreate(BaseModel):
    env_id: int
    name: str
    allowed_paths: list[str] = Field(default_factory=list)
    status: str = "active"


class VerificationDataSourceUpdate(BaseModel):
    name: Optional[str] = None
    allowed_paths: Optional[list[str]] = None
    status: Optional[str] = None


class VerificationRunCreate(BaseModel):
    item_ids: list[int] = Field(default_factory=list)
    variables: Dict[str, Any] = Field(default_factory=dict)
    data_setup: Optional[Dict[str, Any]] = None
    risk_confirmed: bool = False
    visible_browser: bool = True
    mode: str = "quick"
    reuse_data_from_run_id: Optional[int] = None
    dataset_overrides: Dict[str, Any] = Field(default_factory=dict)


class VerificationPreflightRequest(BaseModel):
    item_ids: list[int] = Field(default_factory=list)
    variables: Dict[str, Any] = Field(default_factory=dict)
    data_setup: Optional[Dict[str, Any]] = None
    runtime_check: bool = True
    visible_browser: bool = True


class VerificationConfirmation(BaseModel):
    decision: str
    candidate_index: Optional[int] = None
    note: Optional[str] = ""
    observed_value: Any = None


class VerificationRunRetry(BaseModel):
    strategy: str = "current_step"
    item_ids: list[int] = Field(default_factory=list)
    risk_confirmed: bool = False


class VerificationLearningSessionCreate(BaseModel):
    role_name: Optional[str] = ""
    page_name: Optional[str] = ""
    start_url: Optional[str] = ""
    account_profile_id: Optional[int] = None


class VerificationLearningEventBatch(BaseModel):
    events: list[Dict[str, Any]] = Field(default_factory=list)


class VerificationCheckpointCreate(BaseModel):
    page_name: Optional[str] = ""
    role_name: Optional[str] = ""
    field_name: str
    actual_value: Any = None
    value_type: str = "text"
    currency: Optional[str] = ""
    verification_type: str = "equals"
    expected: Any = None
    relation: Optional[str] = ""
    locator_candidates: list[Any] = Field(default_factory=list)
    screenshot_path: Optional[str] = ""
    extraction: Dict[str, Any] = Field(default_factory=dict)


class VerificationLearningSave(BaseModel):
    name: Optional[str] = ""
    promote_to_project: bool = False
    replay_verified: bool = False


class VerificationInheritRequest(BaseModel):
    source_task_id: int
    memory_ids: list[int] = Field(default_factory=list)
    item_ids: list[int] = Field(default_factory=list)


class VerificationTemplateCopyRequest(BaseModel):
    target_project_id: int
    memory_ids: list[int] = Field(default_factory=list)


class VerificationMemoryCreate(BaseModel):
    memory_type: str
    name: str
    content: Dict[str, Any] = Field(default_factory=dict)
    source_task_id: Optional[int] = None
    status: str = "draft"


class VerificationMemoryUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
