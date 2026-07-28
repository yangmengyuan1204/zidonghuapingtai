from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DataAgentSessionCreate(BaseModel):
    project_id: int
    env_id: int
    instruction: str = Field(min_length=1, max_length=4000)
    topbar_customer_ids: list[str] = Field(default_factory=list, max_length=100)


class DataAgentSessionMessage(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class DataAgentSessionConfirm(BaseModel):
    plan_version: int


class DataAgentContractFeedback(BaseModel):
    plan_version: int
    verdict: Literal["correct", "invalid"]


class DataAgentRiskConfirm(BaseModel):
    plan_version: int
    contract_hash: str = Field(min_length=16, max_length=64)
    acknowledged: bool


class DataAgentPermissionResume(BaseModel):
    plan_version: int
    backend_account_profile_id: int | None = None
    backend_account: str = ""
    backend_password: str = ""



class DataAgentGoalUpdate(BaseModel):
    """Partial goal update from user direct edit."""
    plan_version: int
    fields: dict[str, object] | None = None
    order_shop_count: int | None = None
    order_per_shop: int | None = None
    order_item_num: int | None = None
    offer_price: str | None = None
    offer_unit_prices: list[str] | None = None
    target_node: str | None = None


class DataAgentContractPreview(BaseModel):
    plan_version: int
    message: str = Field(min_length=1, max_length=4000)


class DataAgentContractPreviewApply(BaseModel):
    plan_version: int
    base_contract_hash: str = Field(min_length=16, max_length=64)
    preview_hash: str = Field(min_length=16, max_length=64)


class DataAgentRuleReviewRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class DataAgentRuleRollbackRequest(BaseModel):
    target_version_id: int
    reason: str = Field(min_length=1, max_length=1000)
