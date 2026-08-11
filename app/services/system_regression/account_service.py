from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping

from sqlalchemy.orm import Session

from app.core.account_utils import account_profile_variables
from app.models import TestAccountProfile
from app.system_regression.common.execution import sanitize_secrets


MINISTER_PROFILE_NAME = "沈文妮"
MINISTER_REFUND_THRESHOLD_CNY = Decimal("500")


class AccountLoginRequired(RuntimeError):
    def __init__(self, message: str, *, profile_name: str = MINISTER_PROFILE_NAME) -> None:
        super().__init__(message)
        self.profile_name = profile_name


def requires_minister_account(refund_cny: Any) -> bool:
    try:
        amount = Decimal(str(refund_cny or 0))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("退款金额不是有效数字") from exc
    return amount >= MINISTER_REFUND_THRESHOLD_CNY


def minister_account_context(
    db: Session,
    *,
    project_id: int,
    refund_cny: Any,
    login_probe: Callable[[Mapping[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    if not requires_minister_account(refund_cny):
        return {}
    profile = (
        db.query(TestAccountProfile)
        .filter(
            TestAccountProfile.project_id == project_id,
            TestAccountProfile.profile_name == MINISTER_PROFILE_NAME,
            TestAccountProfile.status == "active",
        )
        .order_by(TestAccountProfile.id.asc())
        .first()
    )
    if profile is None:
        profile = (
            db.query(TestAccountProfile)
            .filter(
                TestAccountProfile.project_id.is_(None),
                TestAccountProfile.profile_name == MINISTER_PROFILE_NAME,
                TestAccountProfile.status == "active",
            )
            .order_by(TestAccountProfile.id.asc())
            .first()
        )
    if profile is None:
        raise AccountLoginRequired("项目内未找到沈文妮部长账号，请手动输入账号密码")
    variables, metadata = account_profile_variables(db, profile.id, project_id)
    if login_probe is not None and not login_probe(variables):
        raise AccountLoginRequired("沈文妮账号自动登录失败，请手动输入账号密码")
    admin_variables = dict(variables)
    if not admin_variables.get("backend_account") and admin_variables.get("username"):
        admin_variables["backend_account"] = admin_variables["username"]
    if not admin_variables.get("backend_password") and admin_variables.get("password"):
        admin_variables["backend_password"] = admin_variables["password"]
    admin_variables.pop("username", None)
    admin_variables.pop("password", None)
    return {
        **admin_variables,
        "backend_account_profile_id": profile.id,
        "backend_account_profile_name": metadata.get("profile_name") or MINISTER_PROFILE_NAME,
    }


def use_temporary_credentials(
    *,
    username: str,
    password: str,
    continuation: Callable[[dict[str, str]], Mapping[str, Any]],
) -> dict[str, Any]:
    if not username.strip() or not password:
        raise ValueError("账号和密码不能为空")
    temporary = {"backend_account": username.strip(), "backend_password": password}
    result = continuation(temporary)
    return dict(sanitize_secrets(dict(result or {})))


__all__ = [
    "AccountLoginRequired",
    "MINISTER_PROFILE_NAME",
    "minister_account_context",
    "requires_minister_account",
    "use_temporary_credentials",
]
