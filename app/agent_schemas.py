from __future__ import annotations

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


class DataAgentPermissionResume(BaseModel):
    plan_version: int
    backend_account_profile_id: int | None = None
    backend_account: str = ""
    backend_password: str = ""



class DataAgentGoalUpdate(BaseModel):
    """Partial goal update from user direct edit."""
    order_shop_count: int | None = None
    order_per_shop: int | None = None
    order_item_num: int | None = None
    offer_price: str | None = None
    offer_unit_prices: list[str] | None = None
    target_node: str | None = None
