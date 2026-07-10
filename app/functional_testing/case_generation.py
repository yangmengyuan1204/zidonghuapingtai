from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'AiConfig',
    'Any',
    'Dict',
    'FunctionalRequirementNote',
    'FunctionalScreenshot',
    'FunctionalTask',
    'GeneratedResult',
    'Iterable',
    'PageSnapshot',
    '_extract_json_list_field',
    '_normalize_generated_cases',
    'call_local_model_json',
    'compact_requirement',
    'json',
    'normalize_case_category',
    're',
    'rule_generate_cases',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.functional_testing"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl__normalize_generated_cases(
    payload: Any,
) -> tuple[list[Dict[str, Any]], list[str]]:
    """从 AI 响应 payload 中提取 cases 和 questions_for_product。

    Returns:
        (cases, questions_for_product)
    """
    questions: list[str] = []
    if isinstance(payload, dict):
        cases = payload.get("cases")
        q_raw = payload.get("questions_for_product") or payload.get("questions") or []
        if isinstance(q_raw, list):
            questions = [str(q).strip() for q in q_raw if q and str(q).strip()]
    else:
        cases = payload
    if not isinstance(cases, list):
        return [], questions
    result = []
    for index, item in enumerate(cases, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or f"功能测试点{index}").strip()
        if not title:
            continue
        result.append(
            {
                "title": title[:200],
                "precondition": str(item.get("precondition") or item.get("前置条件") or "").strip(),
                "steps": str(item.get("steps") or item.get("步骤") or "").strip(),
                "expected": str(item.get("expected") or item.get("预期结果") or "").strip(),
                "priority": str(item.get("priority") or item.get("优先级") or ("P0" if index == 1 else "P1")).strip()[:20],
                "category": normalize_case_category(item.get("category") or item.get("分类") or item.get("type") or "", title),
                "automation_status": "draft",
            }
        )
    return result[:30], questions


def _impl_normalize_case_category(value: Any, fallback_text: str = "") -> str:
    text = str(value or "").strip()
    category_aliases = {
        "主流程": "主流程",
        "查询筛选": "查询筛选",
        "表单交互": "表单交互",
        "等价类": "等价类",
        "边界值": "边界值",
        "异常流程": "异常流程",
        "异常提示": "异常提示",
        "权限状态": "权限状态",
        "权限/状态": "权限状态",
        "数据结果": "数据结果",
        "页面展示": "页面展示",
    }
    if text in category_aliases:
        return category_aliases[text]
    allowed = ["页面展示", "输入校验", "主流程", "异常流程", "权限/状态", "数据结果"]
    if text in allowed:
        return text
    source = f"{text} {fallback_text}".lower()
    if "boundary" in source or "边界" in source or "临界" in source:
        return "边界值"
    if "equivalence" in source or "等价" in source:
        return "等价类"
    keyword_map = [
        ("查询筛选", ("查询", "搜索", "筛选", "检索", "keyword", "search", "filter")),
        ("表单交互", ("表单", "弹窗", "登记", "新增", "编辑", "保存", "取消", "dialog", "modal", "form")),
        ("数据结果", ("金额", "数量", "库存", "数据", "接口", "计算", "合计", "price", "amount", "total")),
        ("权限/状态", ("权限", "状态", "审核", "启用", "禁用", "登录", "角色", "status", "auth")),
        ("异常流程", ("异常", "失败", "错误", "为空", "重复", "非法", "超限", "error", "fail")),
        ("输入校验", ("输入", "必填", "格式", "校验", "长度", "手机号", "邮箱", "validate")),
        ("页面展示", ("展示", "显示", "列表", "弹窗", "按钮", "文案", "页面", "display")),
    ]
    for category, keywords in keyword_map:
        if any(keyword in source for keyword in keywords):
            return category
    return "主流程"


def _impl__extract_json_list_field(text: str, field_name: str) -> list[str]:
    pattern = rf'"{re.escape(field_name)}"\s*:\s*(\[[\s\S]*?\])'
    items: list[str] = []
    for match in re.finditer(pattern, text or ""):
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            items.extend(str(item).strip() for item in value if str(item).strip())
    return items


def _impl_rule_generate_cases(task: FunctionalTask, axure_text: str, extra_context: str = "") -> list[Dict[str, Any]]:
    source_text = "\n".join([task.requirement_text or "", axure_text or "", extra_context or ""])
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    keywords = ("新增", "编辑", "删除", "查询", "搜索", "提交", "审核", "支付", "保存", "登录", "上传", "导出", "状态", "列表", "详情")
    picked = _extract_json_list_field(source_text, "suggested_test_points")
    if not picked:
        picked = [line for line in lines if any(word in line for word in keywords)]
    if not picked:
        picked = lines[:8]
    if not picked:
        picked = [f"验证页面 {task.target_url} 的核心功能流程"]

    result = []
    default_categories = ["主流程", "查询筛选", "等价类", "边界值", "异常提示", "权限状态", "数据结果"]
    while len(picked) < 20:
        picked.append(f"验证{task.iteration_name or '目标页面'}核心场景 {len(picked) + 1}")
    for index, line in enumerate(picked[:30], start=1):
        title = line[:80]
        result.append(
            {
                "title": title,
                "precondition": "测试账号可登录，测试环境数据可用。",
                "steps": f"1. 打开目标页面\n2. 按需求执行：{line}\n3. 观察页面反馈和数据变化",
                "expected": "页面提示正确，数据状态符合需求，核心流程无报错。",
                "category": normalize_case_category(default_categories[(index - 1) % len(default_categories)], title),
                "priority": "P0" if index <= 2 else "P1",
                "automation_status": "draft",
            }
        )
    return result


def _impl_generate_functional_cases(
    task: FunctionalTask,
    axure_text: str,
    snapshot: PageSnapshot | None,
    config: AiConfig | None,
    screenshots: Iterable[FunctionalScreenshot] | None = None,
    notes: Iterable[FunctionalRequirementNote] | None = None,
) -> GeneratedResult:
    requirement_context = compact_requirement(task, axure_text, snapshot, screenshots, notes)
    prompt = f"""
你是一名资深软件测试工程师，请根据以下需求和原型信息，设计功能测试用例。
要求：
1. 覆盖核心业务流程（登录→操作→提交→结果反馈的完整路径）
2. 覆盖正常流程、关键异常场景、权限/必填/状态变化
3. 如果有多张截图或多个页面信息，请设计跨页面的完整业务流程用例
4. 对需求不明确的地方，在 questions_for_product 数组中列出需要向产品确认的问题
5. 只输出合法 JSON，不要输出说明文字
6. 请生成 20-30 条结构化测试设计用例，覆盖核心页面和主要功能模块；不要堆重复用例

输出格式：
{{"cases":[{{"title":"","precondition":"","steps":"","expected":"","category":"页面展示/输入校验/主流程/异常流程/权限/状态/数据结果","priority":"P0/P1/P2"}}],"questions_for_product":["问题1","问题2"]}}

新增硬性约束：
- category 只能使用：主流程、查询筛选、等价类、边界值、异常提示、权限状态、数据结果。
- 自动化友好的主流程、查询筛选、表单交互用例优先 P0/P1；网络中断、权限绕过、已删除数据、复杂业务状态只作为人工/高级用例。
- 生成的是测试设计全集，不代表全部都要自动执行。

{requirement_context}
"""
    warning = ""
    questions: list[str] = []
    try:
        raw_payload = call_local_model_json(config, prompt)
        generated, questions = _normalize_generated_cases(raw_payload)
        if len(generated) < 20:
            warning = f"AI 仅生成了 {len(generated)} 条测试点，期望 20-30 条结构化测试设计用例，建议补充需求描述后重试"
    except Exception as exc:
        generated = []
        warning = f"本地模型调用失败，已使用规则生成：{exc}"
    if generated:
        return GeneratedResult(
            source="ai",
            warning=warning,
            items=generated,
            questions_for_product=questions or None,
        )
    fallback = rule_generate_cases(task, axure_text, requirement_context)
    if not warning:
        warning = "未配置本地模型或模型未返回合法 JSON，已使用规则生成草稿。"
    return GeneratedResult(source="rule", warning=warning, items=fallback)


def _normalize_generated_cases(payload: Any) -> tuple[list[Dict[str, Any]], list[str]]:
    _sync_compat_globals()
    return _impl__normalize_generated_cases(payload)

def normalize_case_category(value: Any, fallback_text: str='') -> str:
    _sync_compat_globals()
    return _impl_normalize_case_category(value, fallback_text)

def _extract_json_list_field(text: str, field_name: str) -> list[str]:
    _sync_compat_globals()
    return _impl__extract_json_list_field(text, field_name)

def rule_generate_cases(task: FunctionalTask, axure_text: str, extra_context: str='') -> list[Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_rule_generate_cases(task, axure_text, extra_context)

def generate_functional_cases(task: FunctionalTask, axure_text: str, snapshot: PageSnapshot | None, config: AiConfig | None, screenshots: Iterable[FunctionalScreenshot] | None=None, notes: Iterable[FunctionalRequirementNote] | None=None) -> GeneratedResult:
    _sync_compat_globals()
    return _impl_generate_functional_cases(task, axure_text, snapshot, config, screenshots, notes)
