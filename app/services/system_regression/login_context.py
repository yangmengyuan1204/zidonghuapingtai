from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from sqlalchemy.orm import Session

from app.core.account_utils import account_profile_variables
from app.core.utils import data_script_variables
from app.models import Env, TestAccountProfile
from app.system_regression.models import SystemRegressionSuite


ADMIN_IDENTITY = "admin"
CLIENT_IDENTITY = "client"
IDENTITY_TYPES = (ADMIN_IDENTITY, CLIENT_IDENTITY)
ADMIN_LOGIN_PATH = "/admin.login"
CLIENT_LOGIN_PATH = "/client/userLogin"

SYSTEM_REGRESSION_ADMIN_PROFILE_NAME = "沈文妮账号"
# Kept as a compatibility export for callers that used the old constant name.
SYSTEM_REGRESSION_CUSTOMER_PROFILE_NAME = SYSTEM_REGRESSION_ADMIN_PROFILE_NAME
SYSTEM_REGRESSION_LOGIN_KIND_CUSTOMER = "customer_frontend"
SYSTEM_REGRESSION_LOGIN_KIND_BACKEND = "backend"


def _mask_account(account: Any) -> str:
    text = str(account or "").strip()
    if not text:
        return ""
    return f"{text[:1]}***{text[-1:]}" if len(text) > 1 else f"{text}***"


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _clean(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


@dataclass(frozen=True)
class AdminIdentity:
    username: str = ""
    password: str = ""
    system: str = "1"
    compute_token: str = ""
    code: str = "wnm666"
    token: str = ""
    source: str = ""

    @property
    def present(self) -> bool:
        return bool(self.username and self.password)

    def safe_payload(self, profile_id: int | None = None) -> dict[str, Any]:
        return {
            "identity_type": ADMIN_IDENTITY,
            "present": self.present,
            "source": self.source,
            "profile_id": profile_id,
            "username_masked": _mask_account(self.username),
            "route": ADMIN_LOGIN_PATH,
        }


@dataclass(frozen=True)
class ClientIdentity:
    account: str = ""
    password: str = ""
    client_tool: str = "1"
    customer_id: str = ""
    token: str = ""
    source: str = ""

    @property
    def present(self) -> bool:
        return bool(self.account and self.password and self.client_tool in {"1", "2"})

    def safe_payload(self, profile_id: int | None = None) -> dict[str, Any]:
        return {
            "identity_type": CLIENT_IDENTITY,
            "present": self.present,
            "source": self.source,
            "profile_id": profile_id,
            "account_masked": _mask_account(self.account),
            "customer_id_present": bool(self.customer_id),
            "client_tool": self.client_tool,
            "route": CLIENT_LOGIN_PATH,
        }


@dataclass(frozen=True)
class SystemRegressionIdentityContext:
    admin: AdminIdentity = field(default_factory=AdminIdentity)
    client: ClientIdentity = field(default_factory=ClientIdentity)
    environment: dict[str, Any] = field(default_factory=dict)

    @property
    def available_identities(self) -> tuple[str, ...]:
        return tuple(
            identity
            for identity, present in (
                (ADMIN_IDENTITY, self.admin.present),
                (CLIENT_IDENTITY, self.client.present),
            )
            if present
        )

    def safe_payload(self, *, admin_profile_id: int | None, client_profile_id: int | None) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "admin": self.admin.safe_payload(admin_profile_id),
            "client": self.client.safe_payload(client_profile_id),
            "environment": dict(self.environment),
            "admin_identity_present": self.admin.present,
            "client_identity_present": self.client.present,
            "available_identities": list(self.available_identities),
        }


@dataclass(frozen=True)
class IdentityPreflightResult:
    status: str
    reason_code: str
    required_identities: tuple[str, ...] = ()
    available_identities: tuple[str, ...] = ()
    missing_identities: tuple[str, ...] = ()
    failure_reason: str = ""


@dataclass(frozen=True)
class SystemRegressionLoginResolution:
    variables: dict[str, Any]
    precondition_evidence: dict[str, Any]
    login_context: dict[str, Any]
    identity_context: SystemRegressionIdentityContext = field(default_factory=SystemRegressionIdentityContext)


class SystemRegressionLoginContextError(ValueError):
    def __init__(self, reason_code: str, precondition_evidence: dict[str, Any], failure_reason: str) -> None:
        super().__init__(failure_reason)
        self.reason_code = reason_code
        self.precondition_evidence = precondition_evidence
        self.failure_reason = failure_reason

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "status": "blocked",
            "reason_code": self.reason_code,
            "guard_kind": "system_regression_login",
            "expected_stage": "batch_create",
            "actual_stage": "batch_create",
            "actor": "system",
            "precondition_evidence": self.precondition_evidence,
            "required_identities": self.precondition_evidence.get("required_identities", []),
            "available_identities": self.precondition_evidence.get("available_identities", []),
            "missing_identities": self.precondition_evidence.get("missing_identities", []),
            "failure_reason": self.failure_reason,
            "message": self.failure_reason,
        }


def _profile(
    db: Session,
    profile_id: Any,
    *,
    project_id: int | None,
) -> TestAccountProfile | None:
    if profile_id in (None, ""):
        return None
    try:
        profile = db.get(TestAccountProfile, int(profile_id))
    except (TypeError, ValueError):
        return None
    if profile is None or profile.status != "active":
        return None
    if project_id is not None and profile.project_id not in (None, project_id):
        return None
    return profile


def _profile_values(db: Session, profile: TestAccountProfile | None, project_id: int | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if profile is None:
        return {}, {}
    values, metadata = account_profile_variables(db, profile.id, project_id)
    return dict(values or {}), dict(metadata or {})


def _profile_id(login_context: Mapping[str, Any], key: str) -> Any:
    value = login_context.get(key)
    if value not in (None, ""):
        return value
    return None


def _selected_profile_ids(
    db: Session,
    *,
    project_id: int | None,
    suite_key: str,
    login_context: Mapping[str, Any],
    login_kind: str,
) -> tuple[Any, Any]:
    admin_profile_id = _profile_id(login_context, "admin_profile_id")
    client_profile_id = _profile_id(login_context, "client_profile_id")
    customer_profile_id = _profile_id(login_context, "customer_profile_id")
    legacy_profile_id = _profile_id(login_context, "profile_id")
    if client_profile_id is None and customer_profile_id is not None:
        client_profile_id = customer_profile_id
    if legacy_profile_id is not None:
        if login_kind == SYSTEM_REGRESSION_LOGIN_KIND_CUSTOMER and client_profile_id is None:
            client_profile_id = legacy_profile_id
        elif admin_profile_id is None:
            # The old profile_id was used by the system-regression admin entry. Treating
            # it as admin is the safe compatibility direction; it can never become client.account.
            admin_profile_id = legacy_profile_id

    suite = db.query(SystemRegressionSuite).filter(SystemRegressionSuite.suite_key == suite_key).first()
    config = suite.config if suite is not None else {}
    if admin_profile_id is None:
        admin_profile_id = config.get("admin_profile_id") if isinstance(config, Mapping) else None
    if admin_profile_id is None:
        profile = (
            db.query(TestAccountProfile)
            .filter(
                TestAccountProfile.profile_name == SYSTEM_REGRESSION_ADMIN_PROFILE_NAME,
                TestAccountProfile.status == "active",
            )
            .order_by(TestAccountProfile.id.asc())
            .first()
        )
        admin_profile_id = profile.id if profile is not None else None
    return admin_profile_id, client_profile_id


def _normalize_required(required_identities: Iterable[str] | None, login_kind: str) -> tuple[str, ...]:
    if required_identities is None:
        inferred = {
            SYSTEM_REGRESSION_LOGIN_KIND_BACKEND: (ADMIN_IDENTITY,),
            SYSTEM_REGRESSION_LOGIN_KIND_CUSTOMER: (CLIENT_IDENTITY,),
        }.get(login_kind, ())
    else:
        inferred = tuple(str(value).strip().lower() for value in required_identities if str(value).strip())
    return tuple(identity for identity in IDENTITY_TYPES if identity in inferred)


def _identity_requirement_from_case(case: Mapping[str, Any]) -> tuple[str, ...] | None:
    expectation = case.get("expectation") if isinstance(case.get("expectation"), Mapping) else {}
    if "required_identities" not in expectation:
        return None
    values = expectation.get("required_identities")
    if not isinstance(values, (list, tuple)):
        return None
    normalized = tuple(str(value).strip().lower() for value in values if str(value).strip())
    if any(value not in IDENTITY_TYPES for value in normalized):
        return None
    return tuple(identity for identity in IDENTITY_TYPES if identity in normalized)


def validate_identity_requirements(
    cases: Iterable[Mapping[str, Any]],
    *,
    available_identities: Iterable[str],
) -> IdentityPreflightResult:
    required: set[str] = set()
    for case in cases:
        values = _identity_requirement_from_case(case)
        if values is None:
            return IdentityPreflightResult(
                status="blocked",
                reason_code="identity_requirement_unknown",
                failure_reason=f"用例 {case.get('case_key') or case.get('id') or ''} 未声明 required_identities",
            )
        required.update(values)
    ordered_required = tuple(identity for identity in IDENTITY_TYPES if identity in required)
    available = tuple(identity for identity in IDENTITY_TYPES if identity in set(available_identities))
    missing = tuple(identity for identity in ordered_required if identity not in available)
    if not missing:
        return IdentityPreflightResult(
            status="passed",
            reason_code="",
            required_identities=ordered_required,
            available_identities=available,
        )
    if missing == (ADMIN_IDENTITY,):
        reason_code = "admin_credentials_missing"
    elif missing == (CLIENT_IDENTITY,):
        reason_code = "client_credentials_missing"
    else:
        reason_code = "admin_and_client_credentials_missing"
    return IdentityPreflightResult(
        status="blocked",
        reason_code=reason_code,
        required_identities=ordered_required,
        available_identities=available,
        missing_identities=missing,
        failure_reason=f"所选用例需要 {', '.join(ordered_required)} 身份，但缺少 {', '.join(missing)} 凭据",
    )


def resolve_system_regression_login_context(
    db: Session,
    *,
    project_id: int | None,
    env_id: int | None,
    context: Mapping[str, Any] | None,
    suite_key: str = "japan",
    required_identities: Iterable[str] | None = None,
) -> SystemRegressionLoginResolution:
    stored_context = dict(context or {})
    raw_variables = dict(stored_context.get("variables") or {})
    login_context = dict(stored_context.get("system_regression_login") or {})
    login_kind = _clean(login_context.get("kind")) or "dual"
    required = _normalize_required(required_identities, login_kind)

    env = db.get(Env, int(env_id)) if env_id not in (None, "") else None
    environment_present = bool(env and _clean(env.base_url))
    if not environment_present:
        evidence = {
            "account_present": False,
            "password_present": False,
            "client_tool": _clean(raw_variables.get("client_tool") or "1"),
            "credential_source": "",
            "profile_id": login_context.get("profile_id"),
            "customer_id_present": bool(raw_variables.get("customer_id") or raw_variables.get("customer_ids")),
            "environment_present": False,
            "admin_identity_present": False,
            "client_identity_present": False,
            "required_identities": list(required),
            "available_identities": [],
            "missing_identities": list(required),
        }
        raise SystemRegressionLoginContextError("environment_missing", evidence, "system regression environment is missing base_url")

    admin_profile_id, client_profile_id = _selected_profile_ids(
        db,
        project_id=project_id,
        suite_key=suite_key,
        login_context=login_context,
        login_kind=login_kind,
    )
    admin_profile = _profile(db, admin_profile_id, project_id=project_id)
    client_profile = _profile(db, client_profile_id, project_id=project_id)
    admin_profile_values, _ = _profile_values(db, admin_profile, project_id)
    client_profile_values, _ = _profile_values(db, client_profile, project_id)

    typed_backend = login_kind == SYSTEM_REGRESSION_LOGIN_KIND_BACKEND
    admin_username = _clean(
        _first_non_empty(
            raw_variables.get("backend_account"),
            raw_variables.get("backend_username"),
            raw_variables.get("username") if typed_backend else None,
            admin_profile_values.get("admin_username"),
            admin_profile_values.get("backend_username"),
            admin_profile_values.get("username"),
        )
    )
    admin_password = _clean(
        _first_non_empty(
            raw_variables.get("backend_password"),
            raw_variables.get("admin_password"),
            raw_variables.get("password") if typed_backend else None,
            admin_profile_values.get("admin_password"),
            admin_profile_values.get("backend_password"),
            admin_profile_values.get("password"),
        )
    )
    admin_source = ""
    if raw_variables.get("backend_account") or raw_variables.get("backend_password") or (typed_backend and raw_variables.get("username")):
        admin_source = "explicit_admin"
    elif admin_profile is not None:
        admin_source = "admin_profile.username"
    admin = AdminIdentity(
        username=admin_username,
        password=admin_password,
        system=_clean(_first_non_empty(raw_variables.get("backend_system"), admin_profile_values.get("system"), "1")) or "1",
        compute_token=_clean(_first_non_empty(raw_variables.get("backend_compute_token"), admin_profile_values.get("compute_token"), "")),
        code=_clean(_first_non_empty(raw_variables.get("backend_code"), admin_profile_values.get("code"), "wnm666")) or "wnm666",
        source=admin_source,
    )

    # data_script_variables is used only for API-path resolution and the explicit
    # customer_id compatibility path. Its seeded account/password defaults are
    # never treated as a client identity without a typed source.
    script_values = data_script_variables(db, raw_variables, project_id)
    customer_id = _clean(_first_non_empty(raw_variables.get("customer_id"), raw_variables.get("customer_ids")))
    explicit_client_account = _clean(raw_variables.get("account"))
    explicit_client_password = _clean(raw_variables.get("password")) if not typed_backend else ""
    client_account = explicit_client_account
    client_password = explicit_client_password
    client_source = "explicit_account" if client_account and client_password else ""
    if not (client_account and client_password) and customer_id:
        client_account = _clean(script_values.get("account"))
        client_password = _clean(script_values.get("password"))
        client_source = "customer_id" if client_account and client_password else ""
    if not (client_account and client_password):
        client_account = _clean(_first_non_empty(client_profile_values.get("client_account"), client_profile_values.get("account")))
        client_password = _clean(_first_non_empty(client_profile_values.get("client_password"), client_profile_values.get("password")))
        client_source = "client_profile.account" if client_account and client_password else client_source
    client_tool = _clean(_first_non_empty(raw_variables.get("client_tool"), client_profile_values.get("client_tool"), "1")) or "1"
    client = ClientIdentity(
        account=client_account,
        password=client_password,
        client_tool=client_tool,
        customer_id=customer_id,
        source=client_source,
    )

    identity_context = SystemRegressionIdentityContext(
        admin=admin,
        client=client,
        environment={
            "base_url": _clean(env.base_url),
            "env_id": env.id,
            "profile_id": login_context.get("profile_id") or admin_profile_id or client_profile_id,
            "present": True,
        },
    )
    available = identity_context.available_identities
    missing = tuple(identity for identity in required if identity not in available)
    precondition_evidence = {
        # Existing client-oriented fields remain additive and retain their meaning.
        "account_present": bool(client.account),
        "password_present": bool(client.password),
        "client_tool": client.client_tool,
        "credential_source": client.source or admin.source,
        "profile_id": login_context.get("profile_id") or admin_profile_id or client_profile_id,
        "customer_id_present": bool(client.customer_id),
        "environment_present": True,
        "account_masked": _mask_account(client.account),
        "admin_identity_present": admin.present,
        "client_identity_present": client.present,
        "admin_profile_id": admin_profile.id if admin_profile else None,
        "client_profile_id": client_profile.id if client_profile else None,
        "admin_username_present": bool(admin.username),
        "admin_password_present": bool(admin.password),
        "admin_username_masked": _mask_account(admin.username),
        "admin_credential_source": admin.source,
        "client_credential_source": client.source,
        "required_identities": list(required),
        "available_identities": list(available),
        "missing_identities": list(missing),
    }
    if client_tool not in {"1", "2"} and CLIENT_IDENTITY in required:
        raise SystemRegressionLoginContextError("client_credentials_missing", precondition_evidence, "system regression client_tool is invalid")
    if missing:
        validation = validate_identity_requirements(
            [{"case_key": "required", "expectation": {"required_identities": list(required)}}],
            available_identities=available,
        )
        raise SystemRegressionLoginContextError(validation.reason_code, precondition_evidence, validation.failure_reason)

    resolved_variables = {
        key: value
        for key, value in raw_variables.items()
        if key not in {
            "username", "password", "account", "client_tool",
            "backend_account", "backend_username", "backend_password", "admin_password",
            "backend_system", "backend_compute_token", "backend_code",
            "token", "admin_token", "client_token",
        }
    }
    resolved_variables["api_paths"] = script_values.get("api_paths") or raw_variables.get("api_paths") or {}
    if admin.present:
        resolved_variables.update(
            {
                "backend_account": admin.username,
                "backend_password": admin.password,
                "backend_system": admin.system,
                "backend_compute_token": admin.compute_token,
                "backend_code": admin.code,
            }
        )
    if client.present:
        resolved_variables.update(
            {
                "account": client.account,
                "password": client.password,
                "client_tool": client.client_tool,
            }
        )
        if client.customer_id:
            resolved_variables["customer_id"] = client.customer_id

    safe_identity = identity_context.safe_payload(
        admin_profile_id=admin_profile.id if admin_profile else None,
        client_profile_id=client_profile.id if client_profile else None,
    )
    login_context = {
        **login_context,
        "schema_version": 2,
        "kind": login_kind,
        "credential_source": client.source or admin.source,
        "profile_id": login_context.get("profile_id") or admin_profile_id or client_profile_id,
        "admin_profile_id": admin_profile.id if admin_profile else admin_profile_id,
        "client_profile_id": client_profile.id if client_profile else client_profile_id,
        "client_tool": client.client_tool,
        "customer_id_present": bool(client.customer_id),
        "environment_present": True,
        "account_masked": _mask_account(client.account),
        "required_identities": list(required),
        **safe_identity,
    }
    return SystemRegressionLoginResolution(
        variables=resolved_variables,
        precondition_evidence=precondition_evidence,
        login_context=login_context,
        identity_context=identity_context,
    )


__all__ = [
    "ADMIN_IDENTITY",
    "CLIENT_IDENTITY",
    "IDENTITY_TYPES",
    "ADMIN_LOGIN_PATH",
    "CLIENT_LOGIN_PATH",
    "SYSTEM_REGRESSION_ADMIN_PROFILE_NAME",
    "SYSTEM_REGRESSION_CUSTOMER_PROFILE_NAME",
    "SYSTEM_REGRESSION_LOGIN_KIND_BACKEND",
    "SYSTEM_REGRESSION_LOGIN_KIND_CUSTOMER",
    "AdminIdentity",
    "ClientIdentity",
    "IdentityPreflightResult",
    "SystemRegressionIdentityContext",
    "SystemRegressionLoginContextError",
    "SystemRegressionLoginResolution",
    "resolve_system_regression_login_context",
    "validate_identity_requirements",
]
