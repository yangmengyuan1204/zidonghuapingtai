from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    "ACCOUNT_RUNTIME_VARS",
    "ApiCase",
    "BUILTIN_RUNTIME_VARS",
    "Counter",
    "FUNCTIONAL_CASE_KIND_AUTH_NEGATIVE",
    "FUNCTIONAL_CASE_KIND_BUSINESS_AUTH",
    "FUNCTIONAL_CASE_KIND_MANUAL_ONLY",
    "FunctionalCase",
    "FunctionalTask",
    "PageSnapshot",
    "QUALITY_AUTH_RISK",
    "QUALITY_EXECUTABLE",
    "QUALITY_LOCATOR_RISK",
    "QUALITY_MISSING_VARIABLES",
    "QUALITY_NEEDS_REVIEW",
    "QUALITY_NOT_RECOMMENDED",
    "QUALITY_UNCHECKED",
    "SEARCH_KEYWORDS",
    "SEARCH_SEED_KEYS",
    "TestRecord",
    "UiCase",
    "_case_group_key",
    "_strip_leading_login_steps",
    "account_preflight_status",
    "build_functional_seed_text",
    "case_has_business_assertion",
    "case_locator_issues",
    "case_required_seed_keys",
    "case_step_structure_issues",
    "clean_seed_value",
    "datetime",
    "ensure_weak_business_assertion",
    "evaluate_functional_case_quality",
    "first_pattern_value",
    "functional_case_kind",
    "functional_case_ui_payload",
    "functional_missing_variables_detail",
    "functional_package_preflight_summary",
    "functional_preflight_case_groups",
    "functional_preflight_primary_action",
    "functional_task_keywords",
    "functional_task_runtime_variables",
    "guess_functional_login_url",
    "impact_item_key",
    "is_sensitive_account_key",
    "json",
    "keyword_score",
    "normalize_functional_result",
    "normalize_variable_name",
    "parse_json_value",
    "placeholder_names",
    "quality_report_payload",
    "re",
    "resolve_execution_account",
    "seed_has_key",
    "seed_functional_package_data",
    "to_json_text",
    "urlparse",
)


def _sync_compat_globals() -> None:
    module = sys.modules["app.core.utils"]
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(module, name)


def _compat_wrapper(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        _sync_compat_globals()
        return func(*args, **kwargs)

    return wrapped


def _impl_placeholder_names(text: str) -> list[str]:
    names = re.findall(r"\{\{\s*([A-Za-z_][A-Za-z0-9_$]*)\s*\}\}", text or "")
    result: list[str] = []
    seen: set[str] = set()
    for name in names:
        clean = name.replace("$", "")
        norm = normalize_variable_name(clean)
        if not norm or norm in seen or clean in BUILTIN_RUNTIME_VARS or clean in ACCOUNT_RUNTIME_VARS:
            continue
        seen.add(norm)
        result.append(clean)
    return result


def _impl_seed_has_key(seed_variables: Dict[str, Any], name: str) -> bool:
    target = normalize_variable_name(name)
    if not target:
        return True
    for key, value in (seed_variables or {}).items():
        if value in ("", None):
            continue
        if normalize_variable_name(key) == target:
            return True
    for canonical, aliases in SEARCH_SEED_KEYS.items():
        alias_norms = {normalize_variable_name(item) for item in [canonical, *aliases]}
        if target in alias_norms:
            return any(seed_variables.get(alias) not in ("", None) for alias in [canonical, *aliases])
    return False


def _impl_case_required_seed_keys(case: FunctionalCase, steps: list[Dict[str, Any]]) -> list[str]:
    raw_text = " ".join(
        [
            case.title or "",
            case.precondition or "",
            case.steps or "",
            case.expected or "",
            json.dumps(steps, ensure_ascii=False, default=str),
        ]
    )
    lower_text = raw_text.lower()
    needed: list[str] = placeholder_names(raw_text)
    if any(keyword in raw_text for keyword in ["搜索", "查询", "筛选"]) or "search" in lower_text:
        for seed_key, keywords in SEARCH_KEYWORDS.items():
            if any(keyword.lower() in lower_text for keyword in keywords):
                needed.append(seed_key)
    if re.search(r"\b(CUST|ORDER|BOX)[-_]?\d{3,}\b", raw_text, flags=re.IGNORECASE):
        if "customer_id" not in needed and re.search(r"\bCUST[-_]?\d{3,}\b", raw_text, flags=re.IGNORECASE):
            needed.append("customer_id")
        if "orderNumber" not in needed and re.search(r"\bORDER[-_]?\d{3,}\b", raw_text, flags=re.IGNORECASE):
            needed.append("orderNumber")
        if "box_no" not in needed and re.search(r"\bBOX[-_]?\d{3,}\b", raw_text, flags=re.IGNORECASE):
            needed.append("box_no")
    unique: list[str] = []
    seen: set[str] = set()
    for item in needed:
        norm = normalize_variable_name(item)
        if norm and norm not in seen:
            seen.add(norm)
            unique.append(item)
    return unique


def _impl_first_pattern_value(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if match:
            value = match.group(1) if match.groups() else match.group(0)
            value = str(value or "").strip(" ：:，,。;；\n\r\t")
            if value:
                return value[:80]
    return ""


def _impl_clean_seed_value(value: str, value_type: str) -> str:
    text = str(value or "").strip(" ：:，,。;；\n\r\t")
    if not text:
        return ""
    lower = text.lower()
    fake_values = {
        "cust123456",
        "customer123456",
        "order123456",
        "ord123456",
        "box123456",
        "test123456",
        "boxkeyword",
        "orderstatusmap",
    }
    if lower in fake_values or lower.endswith(("keyword", "map", "placeholder")):
        return ""
    if "{{" in text or "}}" in text:
        return ""
    if value_type in {"customer_id", "order_no", "box_no", "location_code"} and not re.search(r"\d", text):
        return ""
    if value_type == "customer_name":
        generic_terms = {"搜索", "筛选", "查询", "页面", "功能", "测试", "search", "filter", "query", "page", "feature", "test"}
        if lower in generic_terms or any(text.startswith(item) for item in ["搜索", "筛选", "查询", "页面", "功能"]):
            return ""
        return text[:80]
    if value_type == "customer_name" and any(keyword in text for keyword in ["搜索", "筛选", "查询", "页面", "功能", "测试"]):
        return ""
    return text[:80]


def _impl_build_functional_seed_text(db: Session, task: FunctionalTask) -> tuple[str, list[str]]:
    chunks: list[str] = []
    sources: list[str] = []
    snapshot = (
        db.query(PageSnapshot)
        .filter(PageSnapshot.task_id == task.id)
        .order_by(PageSnapshot.id.desc())
        .first()
    )
    if snapshot and snapshot.dom_summary:
        chunks.append(snapshot.dom_summary)
        sources.append("page_snapshot")
    ui_ids = [
        row[0]
        for row in db.query(FunctionalCase.ui_case_id)
        .filter(FunctionalCase.task_id == task.id, FunctionalCase.ui_case_id.isnot(None))
        .all()
        if row[0]
    ]
    if ui_ids:
        records = (
            db.query(TestRecord)
            .filter(TestRecord.case_type == "ui", TestRecord.case_id.in_(ui_ids))
            .order_by(TestRecord.id.desc())
            .limit(20)
            .all()
        )
        for record in records:
            if record.log:
                chunks.append(record.log)
        if records:
            sources.append("recent_ui_records")
    return "\n".join(chunks), sources


def _impl_seed_functional_package_data(db: Session, task: FunctionalTask) -> Dict[str, Any]:
    text, sources = build_functional_seed_text(db, task)
    variables: Dict[str, Any] = {}
    customer_id = first_pattern_value(
        text,
        [
            r"\bID\s*[:\uFF1A]\s*([A-Za-z0-9_-]{3,32})",
            r'"customer(?:_?id|Id)"\s*:\s*"([A-Za-z0-9_-]{3,32})"',
            r"(?:客户ID|客户Id|客户id|客户编号|客户号)\s*[:：]?\s*([A-Za-z0-9_-]{3,32})",
            r"\b(CUST[-_]?[A-Za-z0-9]{3,24})\b",
        ],
    )
    if customer_id:
        customer_id = clean_seed_value(customer_id, "customer_id")
    if customer_id:
        variables.update({"customer_id": customer_id, "customerId": customer_id, "customerID": customer_id})
    customer_name = first_pattern_value(
        text,
        [
            r"\bID\s*[:\uFF1A]\s*[A-Za-z0-9_-]{3,32}\s+([^\s\d][^\r\n]{1,40}?)\s+(?:20\d{8,}|[A-Z]{2,}[-_]?\d|\u3010)",
            r'"customer(?:_?name|Name)"\s*:\s*"([^"]{2,40})"',
            r"(?:客户名称|客户名|客户姓名)\s*[:：]?\s*([\u4e00-\u9fffA-Za-z0-9_\- ]{2,40})",
        ],
    )
    if customer_name:
        customer_name = clean_seed_value(customer_name, "customer_name")
    if customer_name:
        variables.update({"customer_name": customer_name, "customerName": customer_name})
    order_no = first_pattern_value(
        text,
        [
            r"(?:订单号|订单编号|订单SN|order[_ -]?(?:no|number|sn))\s*[:：]?\s*([A-Z0-9][A-Z0-9_-]{5,40})",
            r"\b(ORDER[-_]?[A-Z0-9]{5,36})\b",
        ],
    )
    if order_no:
        order_no = clean_seed_value(order_no, "order_no")
    if order_no:
        variables.update({"orderNumber": order_no, "order_no": order_no, "orderNo": order_no, "order_sn": order_no})
    box_no = first_pattern_value(
        text,
        [
            r"\b(20\d{10,}-[A-Za-z0-9_-]{3,}-\d+)\b",
            r'"box(?:_?no|No|_?number|Number|Code|_?code)"\s*:\s*"([A-Za-z0-9_-]{5,40})"',
            r"(?:箱号|箱子编号|box[_ -]?(?:no|number))\s*[:：]?\s*([A-Z0-9][A-Z0-9_-]{4,40})",
            r"\b(BOX[-_]?[A-Z0-9]{4,36})\b",
        ],
    )
    if box_no:
        box_no = clean_seed_value(box_no, "box_no")
    if box_no:
        variables.update({"box_no": box_no, "boxNo": box_no, "boxCode": box_no, "box_number": box_no})
    location_code = first_pattern_value(
        text,
        [
            r"\u3010([^\u3011]{2,80})\u3011",
            r'"(?:location(?:_?code|Code)?|warehouse_location|storage_location)"\s*:\s*"([^"]{2,80})"',
            r"(?:库位|仓位|location(?:_code)?)\s*[:：]?\s*([A-Z0-9][A-Z0-9_-]{2,32})",
        ],
    )
    if location_code:
        location_code = clean_seed_value(location_code, "location_code")
    if location_code:
        variables.update({"location_code": location_code, "locationCode": location_code, "warehouse_location": location_code})
    if "keyword" not in variables:
        keyword = location_code or customer_id or customer_name or box_no
        if keyword:
            variables["keyword"] = keyword
    dates = re.findall(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2})", text or "")
    if dates:
        variables.update({"startDate": dates[0], "start_date": dates[0]})
        variables.update({"endDate": dates[-1], "end_date": dates[-1]})
    saved_runtime_variables = functional_task_runtime_variables(task)
    if saved_runtime_variables:
        variables.update(saved_runtime_variables)
        if "task_runtime_variables" not in sources:
            sources.append("task_runtime_variables")
    return {"variables": variables, "sources": sources, "source_text_available": bool(text)}


def _impl_functional_task_runtime_variables(task: FunctionalTask) -> Dict[str, Any]:
    payload = parse_json_value(task.context or "", {})
    if not isinstance(payload, dict):
        return {}
    raw_variables = payload.get("runtime_variables") or payload.get("__runtime_variables") or {}
    if not isinstance(raw_variables, dict):
        return {}
    return {
        str(key): value
        for key, value in raw_variables.items()
        if value not in ("", None) and not is_sensitive_account_key(key)
    }


def _impl_account_preflight_status(
    db: Session,
    task: FunctionalTask,
    payload: FunctionalExecuteRequest | None,
) -> Dict[str, Any]:
    account_mode = (payload.account_mode if payload else "default") or "default"
    if account_mode == "none":
        return {"status": "skipped", "message": "本次选择不使用测试账号"}
    try:
        variables, execution_context = resolve_execution_account(
            db,
            payload,
            "functional_task",
            task.id,
            task.project_id,
            task.target_url,
        )
    except Exception as exc:
        return {"status": "blocked", "message": f"账号解析失败：{exc}"}
    if not execution_context.get("login_required"):
        return {"status": "warning", "message": "未绑定测试账号，预检按公开页面处理"}
    login_config = execution_context.get("login_config") or {}
    login_url = str(login_config.get("login_url") or "").strip() or guess_functional_login_url(task.target_url)
    has_username = any(str(variables.get(key) or "").strip() for key in ["username", "account", "email", "mobile", "phone"])
    has_password = any(str(variables.get(key) or "").strip() for key in ["password", "pwd"])
    missing = []
    if not login_url:
        missing.append("登录页URL")
    if not has_username:
        missing.append("登录账号")
    if not has_password:
        missing.append("登录密码")
    if missing:
        return {
            "status": "blocked",
            "message": "登录前置缺失：" + "、".join(missing),
            "account_profile_id": execution_context.get("account_profile_id"),
            "login_url": login_url,
        }
    return {
        "status": "ready",
        "message": "测试账号信息完整，正式执行时会先登录并复用登录态",
        "account_profile_id": execution_context.get("account_profile_id"),
        "login_url": login_url,
    }


def _impl_guess_functional_login_url(target_url: str | None) -> str:
    raw = str(target_url or "").strip()
    try:
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return ""
        if parsed.fragment and "/" in parsed.fragment:
            hash_prefix = "#!/" if parsed.fragment.startswith("!/") else "#/"
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}{hash_prefix}login"
        return f"{parsed.scheme}://{parsed.netloc}/login"
    except Exception:
        return ""


def _impl_evaluate_functional_case_quality(
    db: Session,
    task: FunctionalTask,
    case: FunctionalCase,
    seed_variables: Dict[str, Any],
    account_status: Dict[str, Any],
) -> Dict[str, Any]:
    if case.automation_status != "approved":
        return quality_report_payload(QUALITY_NOT_RECOMMENDED, "用例未确认，不进入自动执行")
    if not case.ui_case_id:
        return quality_report_payload(QUALITY_NOT_RECOMMENDED, "尚未生成 UI 步骤")
    ui_case, steps = functional_case_ui_payload(db, case)
    if not ui_case:
        return quality_report_payload(QUALITY_NOT_RECOMMENDED, "关联 UI 用例不存在")
    if account_status.get("status") == "blocked":
        return quality_report_payload(QUALITY_AUTH_RISK, account_status.get("message") or "登录前置未通过")
    if not steps:
        return quality_report_payload(QUALITY_NOT_RECOMMENDED, "UI 步骤为空，无法自动执行")
    case_kind = functional_case_kind(case)
    if case_kind == FUNCTIONAL_CASE_KIND_AUTH_NEGATIVE:
        return quality_report_payload(
            QUALITY_NOT_RECOMMENDED,
            "未登录/负向认证用例默认作为人工/高级用例，不进入可信自动执行",
            case_kind=case_kind,
        )
    if case_kind == FUNCTIONAL_CASE_KIND_MANUAL_ONLY:
        return quality_report_payload(
            QUALITY_NOT_RECOMMENDED,
            "该用例依赖权限、异常环境或复杂业务状态，默认不进入可信自动执行",
            case_kind=case_kind,
        )
    if case_kind == FUNCTIONAL_CASE_KIND_BUSINESS_AUTH:
        stripped_steps, removed_login_steps = _strip_leading_login_steps(steps)
        if removed_login_steps:
            steps = stripped_steps
            ui_case.steps = to_json_text(steps, [])
            db.flush()
    steps, generated_weak_assertion = ensure_weak_business_assertion(db, case, ui_case, steps)
    step_issues = case_step_structure_issues(steps)
    if step_issues:
        return quality_report_payload(
            QUALITY_NOT_RECOMMENDED,
            "UI 步骤结构不完整，需修复后才能自动执行",
            step_issues,
            case_kind=case_kind,
            result_reason="step_invalid",
        )
    locator_issues = case_locator_issues(steps)
    if locator_issues:
        return quality_report_payload(QUALITY_LOCATOR_RISK, "存在缺失 locator 的步骤", locator_issues)
    required_seed_keys = case_required_seed_keys(case, steps)
    missing_seed = [item for item in required_seed_keys if not seed_has_key(seed_variables, item)]
    if missing_seed:
        return quality_report_payload(
            QUALITY_MISSING_VARIABLES,
            "搜索/筛选类用例缺少真实业务数据样本",
            [f"缺少真实数据：{item}" for item in missing_seed],
            required_seed_keys=required_seed_keys,
        )
    if not case_has_business_assertion(case, steps):
        return quality_report_payload(
            QUALITY_NEEDS_REVIEW,
            "缺少明确业务断言，不能自动标记为可信通过",
            ["请补充 assert_url/assert_visible/assert_value/text_assert 或成功条件"],
        )
    if generated_weak_assertion:
        return quality_report_payload(
            QUALITY_NEEDS_REVIEW,
            "已根据预期结果自动补充弱断言，建议人工确认后再作为可信通过",
            ["自动追加 body 文本弱断言"],
            generated_assertion=True,
        )
    return quality_report_payload(
        QUALITY_EXECUTABLE,
        "账号、步骤、测试数据和业务断言预检通过",
        required_seed_keys=required_seed_keys,
    )


def _impl_functional_package_preflight_summary(cases: list[Dict[str, Any]]) -> Dict[str, Any]:
    counts = Counter((item.get("quality_status") or QUALITY_UNCHECKED) for item in cases)
    total = len(cases)
    manual_statuses = {QUALITY_NEEDS_REVIEW, QUALITY_MISSING_VARIABLES, QUALITY_LOCATOR_RISK, QUALITY_AUTH_RISK, QUALITY_NOT_RECOMMENDED}
    trial_statuses = {QUALITY_EXECUTABLE, QUALITY_UNCHECKED, QUALITY_NEEDS_REVIEW, QUALITY_LOCATOR_RISK}
    return {
        "total": total,
        "executable": counts.get(QUALITY_EXECUTABLE, 0),
        "trial_runnable": sum(counts.get(item, 0) for item in trial_statuses),
        "manual_check": sum(counts.get(item, 0) for item in manual_statuses),
        "unchecked": counts.get(QUALITY_UNCHECKED, 0),
        "auth_blocked": counts.get(QUALITY_AUTH_RISK, 0),
        "data_missing": counts.get(QUALITY_MISSING_VARIABLES, 0),
        "locator_risk": counts.get(QUALITY_LOCATOR_RISK, 0),
        "missing_assertion": counts.get(QUALITY_NEEDS_REVIEW, 0),
        "not_automatable": counts.get(QUALITY_NOT_RECOMMENDED, 0),
    }


def _impl__case_group_key(category: Any) -> str:
    raw = str(category or "").strip()
    aliases = {
        "页面展示": "页面展示",
        "输入校验": "等价类",
        "主流程": "主流程",
        "异常流程": "异常流程",
        "权限/状态": "权限状态",
        "权限状态": "权限状态",
        "数据结果": "数据结果",
        "边界值": "边界值",
        "等价类": "等价类",
    }
    if raw in aliases:
        return aliases[raw]
    if "边界" in raw:
        return "边界值"
    if "等价" in raw or "输入" in raw or "校验" in raw:
        return "等价类"
    if "权限" in raw or "状态" in raw:
        return "权限状态"
    if "异常" in raw:
        return "异常流程"
    if "数据" in raw:
        return "数据结果"
    return "主流程"


def _impl_functional_preflight_case_groups(cases: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    order = ["主流程", "等价类", "边界值", "异常流程", "权限状态", "数据结果", "页面展示"]
    grouped: Dict[str, Dict[str, Any]] = {}
    for item in cases:
        key = _case_group_key(item.get("category"))
        group = grouped.setdefault(
            key,
            {
                "category": key,
                "total": 0,
                "executable": 0,
                "blocked": 0,
                "needs_review": 0,
                "locator_risk": 0,
                "case_ids": [],
            },
        )
        status_value = item.get("quality_status") or QUALITY_UNCHECKED
        group["total"] += 1
        group["case_ids"].append(item.get("case_id"))
        if status_value == QUALITY_EXECUTABLE:
            group["executable"] += 1
        elif status_value in {QUALITY_AUTH_RISK, QUALITY_MISSING_VARIABLES, QUALITY_NOT_RECOMMENDED}:
            group["blocked"] += 1
        elif status_value == QUALITY_NEEDS_REVIEW:
            group["needs_review"] += 1
        elif status_value == QUALITY_LOCATOR_RISK:
            group["locator_risk"] += 1
    return sorted(grouped.values(), key=lambda item: order.index(item["category"]) if item["category"] in order else len(order))


def _impl_functional_missing_variables_detail(cases: list[Dict[str, Any]], seed_variables: Dict[str, Any]) -> list[Dict[str, Any]]:
    details: Dict[str, Dict[str, Any]] = {}
    for item in cases:
        if item.get("quality_status") != QUALITY_MISSING_VARIABLES:
            continue
        required_keys = item.get("required_seed_keys") or []
        if not required_keys:
            for issue in item.get("issues") or []:
                text = str(issue or "")
                if "：" in text:
                    required_keys.append(text.rsplit("：", 1)[-1].strip())
                elif ":" in text:
                    required_keys.append(text.rsplit(":", 1)[-1].strip())
        for name in required_keys:
            key = str(name or "").strip()
            if not key:
                continue
            row = details.setdefault(
                key,
                {
                    "name": key,
                    "affected_case_ids": [],
                    "suggested_value": seed_variables.get(key, ""),
                    "source": "seed" if seed_variables.get(key) not in ("", None) else "",
                    "required": True,
                },
            )
            row["affected_case_ids"].append(item.get("case_id"))
    return list(details.values())


def _impl_functional_preflight_primary_action(account_status: Dict[str, Any], summary: Dict[str, Any], missing_details: list[Dict[str, Any]]) -> str:
    if account_status.get("status") == "blocked" or summary.get("auth_blocked", 0):
        return "bind_account"
    if missing_details or summary.get("data_missing", 0):
        return "fill_variables"
    if summary.get("locator_risk", 0):
        return "fix_locators"
    if summary.get("missing_assertion", 0):
        return "review_assertions"
    if summary.get("executable", 0):
        return "execute"
    return "review_assertions"


def _impl_preflight_functional_package(
    db: Session,
    task: FunctionalTask,
    payload: FunctionalExecuteRequest | None = None,
    selected_case_ids: list[int] | None = None,
    persist: bool = True,
) -> Dict[str, Any]:
    requested_ids = set(selected_case_ids or [])
    seed_result = seed_functional_package_data(db, task)
    seed_variables = dict(seed_result.get("variables") or {})
    if payload and payload.variables:
        seed_variables.update({key: value for key, value in payload.variables.items() if value not in ("", None)})
    account_status = account_preflight_status(db, task, payload)
    query = db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id)
    if requested_ids:
        query = query.filter(FunctionalCase.id.in_(requested_ids))
    cases = query.order_by(FunctionalCase.id.asc()).all()
    case_items: list[Dict[str, Any]] = []
    for case in cases:
        report = evaluate_functional_case_quality(db, task, case, seed_variables, account_status)
        status_value = str(report.get("status") or QUALITY_UNCHECKED)
        if persist:
            case.quality_status = status_value
            case.quality_report = json.dumps(report, ensure_ascii=False, default=str)
        case_items.append(
            {
                "case_id": case.id,
                "title": case.title,
                "category": case.category,
                "priority": case.priority,
                "automation_status": case.automation_status,
                "quality_status": status_value,
                "case_kind": report.get("case_kind") or functional_case_kind(case),
                "reason": report.get("reason") or "",
                "issues": report.get("issues") or [],
                "required_seed_keys": report.get("required_seed_keys") or [],
            }
        )
    summary = functional_package_preflight_summary(case_items)
    case_groups = functional_preflight_case_groups(case_items)
    missing_variables_detail = functional_missing_variables_detail(case_items, seed_variables)
    primary_action = functional_preflight_primary_action(account_status, summary, missing_variables_detail)
    executable_case_ids = [item["case_id"] for item in case_items if item["quality_status"] == QUALITY_EXECUTABLE]
    trusted_case_ids = executable_case_ids[:12]
    trial_case_ids = [
        item["case_id"]
        for item in case_items
        if item["quality_status"] in {QUALITY_EXECUTABLE, QUALITY_UNCHECKED, QUALITY_NEEDS_REVIEW, QUALITY_LOCATOR_RISK}
    ]
    manual_items = [item for item in case_items if item["quality_status"] != QUALITY_EXECUTABLE]
    blocked_cases = [
        item
        for item in case_items
        if item["quality_status"] in {QUALITY_AUTH_RISK, QUALITY_MISSING_VARIABLES, QUALITY_NOT_RECOMMENDED}
    ]
    page_status = "ready" if db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).first() else "unchecked"
    result = {
        "task_id": task.id,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "login": account_status,
        "page": {
            "status": page_status,
            "target_url": task.target_url,
            "message": "已有页面快照" if page_status == "ready" else "暂无页面快照，建议先扫描目标页面",
        },
        "seed": seed_result,
        "counts": summary,
        "total": len(case_items),
        "design_case_count": len(case_items),
        "trusted_case_count": len(trusted_case_ids),
        "manual_case_count": len(manual_items),
        "executable_count": len(trusted_case_ids),
        "executable_case_ids": trusted_case_ids,
        "trusted_case_ids": trusted_case_ids,
        "trial_count": len(trial_case_ids),
        "trial_case_ids": trial_case_ids,
        "blocked_cases": blocked_cases[:80],
        "manual_check_items": manual_items[:80],
        "case_groups": case_groups,
        "missing_variables_detail": missing_variables_detail,
        "primary_action": primary_action,
        "can_execute_now": bool(executable_case_ids) and account_status.get("status") != "blocked",
    }
    if persist:
        db.commit()
    return result


def _impl_functional_task_keywords(task: FunctionalTask) -> list[str]:
    raw = " ".join([task.iteration_name or "", task.requirement_text or "", task.context or "", task.target_url or ""])
    try:
        parsed = urlparse(task.target_url or "")
        raw += " " + parsed.path.replace("/", " ")
    except Exception:
        pass
    tokens = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", raw)
    seen: set[str] = set()
    result = []
    for token in tokens:
        text = token.strip().lower()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result[:30]


def _impl_keyword_score(text: str, keywords: Iterable[str]) -> int:
    source = (text or "").lower()
    return sum(1 for keyword in keywords if keyword and keyword in source)


def _impl_impact_item_key(item_type: str, ref_id: int | None, title: str, target: str | None = "") -> str:
    return f"{item_type}:{ref_id or ''}:{(title or '').strip().lower()}:{(target or '').strip().lower()}"


def _impl_suggest_functional_impact_items(db: Session, task: FunctionalTask) -> list[Dict[str, Any]]:
    keywords = functional_task_keywords(task)
    candidates: list[Dict[str, Any]] = []
    seen: set[str] = set()

    def add_candidate(item: Dict[str, Any]) -> None:
        key = impact_item_key(item.get("item_type") or "", item.get("ref_id"), item.get("title") or "", item.get("target") or "")
        if key in seen:
            return
        seen.add(key)
        candidates.append(item)

    existing_task_ids = [
        row[0]
        for row in db.query(FunctionalTask.id)
        .filter(FunctionalTask.project_id == task.project_id, FunctionalTask.id != task.id)
        .all()
    ]
    if existing_task_ids:
        case_rows = (
            db.query(FunctionalCase, FunctionalTask)
            .join(FunctionalTask, FunctionalCase.task_id == FunctionalTask.id)
            .filter(FunctionalCase.task_id.in_(existing_task_ids))
            .all()
        )
        for case, source_task in case_rows:
            text = " ".join([case.title or "", case.precondition or "", case.steps or "", case.expected or "", source_task.iteration_name or ""])
            score = keyword_score(text, keywords)
            is_history_risk = normalize_functional_result(case.test_result) in {"failed", "blocked"}
            if score <= 0 and not is_history_risk:
                continue
            add_candidate(
                {
                    "item_type": "functional_case",
                    "ref_id": case.id,
                    "title": case.title,
                    "target": f"{source_task.iteration_name} / 用例#{case.id}",
                    "risk_level": "P0" if is_history_risk else (case.priority or "P1"),
                    "source": "history_failed" if is_history_risk else "keyword",
                    "reason": "历史失败/阻塞用例" if is_history_risk else f"命中需求关键词 {score} 个",
                }
            )

    try:
        target_path = urlparse(task.target_url or "").path.strip("/").lower()
    except Exception:
        target_path = ""
    for ui_case in db.query(UiCase).filter(UiCase.project_id == task.project_id).all():
        text = f"{ui_case.case_name or ''} {ui_case.page_url or ''}"
        score = keyword_score(text, keywords)
        same_path = bool(target_path and target_path in (ui_case.page_url or "").lower())
        if score <= 0 and not same_path:
            continue
        add_candidate(
            {
                "item_type": "ui_case",
                "ref_id": ui_case.id,
                "title": ui_case.case_name,
                "target": ui_case.page_url,
                "risk_level": "P1" if same_path else "P2",
                "source": "same_url" if same_path else "keyword",
                "reason": "同页面或同路径相关" if same_path else f"命中需求关键词 {score} 个",
            }
        )

    for api_case in db.query(ApiCase).filter(ApiCase.project_id == task.project_id).all():
        text = f"{api_case.case_name or ''} {api_case.url or ''}"
        score = keyword_score(text, keywords)
        if score <= 0:
            continue
        add_candidate(
            {
                "item_type": "api_case",
                "ref_id": api_case.id,
                "title": api_case.case_name,
                "target": f"{api_case.method} {api_case.url}",
                "risk_level": "P1",
                "source": "keyword",
                "reason": f"接口名称/路径命中需求关键词 {score} 个",
            }
        )

    return candidates[:30]


placeholder_names = _compat_wrapper(_impl_placeholder_names)
seed_has_key = _compat_wrapper(_impl_seed_has_key)
case_required_seed_keys = _compat_wrapper(_impl_case_required_seed_keys)
first_pattern_value = _compat_wrapper(_impl_first_pattern_value)
clean_seed_value = _compat_wrapper(_impl_clean_seed_value)
build_functional_seed_text = _compat_wrapper(_impl_build_functional_seed_text)
seed_functional_package_data = _compat_wrapper(_impl_seed_functional_package_data)
functional_task_runtime_variables = _compat_wrapper(_impl_functional_task_runtime_variables)
account_preflight_status = _compat_wrapper(_impl_account_preflight_status)
guess_functional_login_url = _compat_wrapper(_impl_guess_functional_login_url)
evaluate_functional_case_quality = _compat_wrapper(_impl_evaluate_functional_case_quality)
functional_package_preflight_summary = _compat_wrapper(_impl_functional_package_preflight_summary)
_case_group_key = _compat_wrapper(_impl__case_group_key)
functional_preflight_case_groups = _compat_wrapper(_impl_functional_preflight_case_groups)
functional_missing_variables_detail = _compat_wrapper(_impl_functional_missing_variables_detail)
functional_preflight_primary_action = _compat_wrapper(_impl_functional_preflight_primary_action)
preflight_functional_package = _compat_wrapper(_impl_preflight_functional_package)
functional_task_keywords = _compat_wrapper(_impl_functional_task_keywords)
keyword_score = _compat_wrapper(_impl_keyword_score)
impact_item_key = _compat_wrapper(_impl_impact_item_key)
suggest_functional_impact_items = _compat_wrapper(_impl_suggest_functional_impact_items)
