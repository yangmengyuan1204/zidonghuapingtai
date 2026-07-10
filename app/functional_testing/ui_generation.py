from __future__ import annotations

import sys

from ..executors import parse_json_value


_COMPAT_NAMES = (
    'ALLOWED_UI_ACTIONS',
    'AiConfig',
    'Any',
    'Dict',
    'FunctionalCase',
    'FunctionalTask',
    'GeneratedResult',
    'PageSnapshot',
    '_json_from_text',
    '_load_action_templates',
    '_match_template_for_case',
    'call_local_model_json',
    'rule_generate_ui_steps',
    'validate_ui_steps',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.functional_testing"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl_validate_ui_steps(steps: Any) -> list[Dict[str, Any]]:
    if isinstance(steps, str):
        steps = _json_from_text(steps)
    if isinstance(steps, dict):
        steps = steps.get("steps")
    if not isinstance(steps, list):
        raise ValueError("UI步骤必须是数组")
    normalized: list[Dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"第{index}步不是对象")
        current_step = dict(step)
        action = str(current_step.get("action") or "").strip()
        if action not in ALLOWED_UI_ACTIONS:
            raise ValueError(f"第{index}步 action 不支持：{action}")
        locator_hint = current_step.get("value") or current_step.get("text")
        if not current_step.get("locator"):
            if action in {"click", "assert_visible"} and locator_hint:
                current_step["locator"] = f"text={locator_hint}"
            elif action == "text_assert":
                current_step["locator"] = "body"
        locator_required = action in {"input", "click", "wait_for_selector", "text_assert", "select", "check", "uncheck", "assert_visible", "assert_value"}
        value_required = action in {"goto", "input", "wait", "text_assert", "select", "assert_url", "assert_value"}
        if locator_required and not current_step.get("locator"):
            raise ValueError(f"第{index}步缺少 locator")
        if value_required and current_step.get("value") in (None, ""):
            raise ValueError(f"第{index}步缺少 value")
        normalized.append({key: value for key, value in current_step.items() if value not in (None, "")})
    return normalized


def _impl_rule_generate_ui_steps(case: FunctionalCase, task: FunctionalTask, snapshot: PageSnapshot | None) -> list[Dict[str, Any]]:
    steps: list[Dict[str, Any]] = [{"name": "打开目标页面", "action": "goto", "value": task.target_url}]
    steps.append({"name": "等待页面加载", "action": "wait_for_selector", "locator": "body"})
    if "注册" in (case.title or "") and "login" in (task.target_url or "").lower():
        steps.extend(
            [
                {"name": "点击立即注册", "action": "click", "locator": "text=立即注册", "fallback_locators": ['button:has-text("立即注册")', 'a:has-text("立即注册")']},
                {"name": "等待注册入口响应", "action": "wait", "value": 1000},
            ]
        )
    steps.append({"name": "保存页面截图", "action": "screenshot"})
    return steps


def _impl__basic_generate_ui_steps(case: FunctionalCase, task: FunctionalTask, snapshot: PageSnapshot | None, config: AiConfig | None) -> GeneratedResult:
    dom_summary = snapshot.dom_summary if snapshot else ""
    prompt = f"""
请把以下功能测试点转换成 Playwright 可执行的 UI steps JSON。
只输出 JSON，格式：{{"steps":[{{"name":"打开登录页","action":"goto","value":"..."}}]}}
允许 action：{", ".join(sorted(ALLOWED_UI_ACTIONS))}
locator 优先级：data-testid、id、name、placeholder、aria-label、text，不要使用不稳定的深层 CSS。
placeholder 请使用 CSS 写法，例如 input[placeholder="邮箱/手机号"]，不要写 placeholder=邮箱/手机号。
除 goto/wait/screenshot/assert_url 外，所有操作必须带 locator；点击可使用 text=按钮文案。
每个有 locator 的步骤尽量输出 fallback_locators 数组，至少给 1-3 个备用定位器。
每一步必须有 name，用测试人员能理解的中文描述动作目标。
允许可选字段 timeout、optional；非关键弱断言可以标 optional=true。
运行时变量可用：{{{{username}}}}、{{{{password}}}}、{{{{code}}}}。

目标页面：{task.target_url}
测试点标题：{case.title}
前置条件：{case.precondition or ""}
测试步骤：{case.steps or ""}
预期结果：{case.expected or ""}
页面DOM摘要：
{dom_summary[:14000]}
"""
    warning = ""
    try:
        payload = call_local_model_json(config, prompt)
        steps = validate_ui_steps(payload)
    except Exception as exc:
        steps = []
        warning = f"本地模型未生成可执行步骤，已使用规则兜底：{exc}"
    if steps:
        if steps[0].get("action") != "goto":
            steps.insert(0, {"action": "goto", "value": task.target_url})
        return GeneratedResult(source="ai", warning=warning, items=steps)
    fallback = rule_generate_ui_steps(case, task, snapshot)
    return GeneratedResult(source="rule", warning=warning or "未配置本地模型或模型输出无效，已生成最小可执行步骤。", items=fallback)


def _impl__load_action_templates(project_id: int) -> list[Any]:
    """加载项目下的操作模板"""
    try:
        from .models import ActionTemplate
        from .database import SessionLocal
        db = SessionLocal()
        try:
            return db.query(ActionTemplate).filter(ActionTemplate.project_id == project_id).all()
        finally:
            db.close()
    except Exception:
        return []


def _impl__match_template_for_case(case: FunctionalCase, templates: list[Any]) -> Any | None:
    """匹配用例到操作模板"""
    try:
        from .executors import match_action_template
        return match_action_template(case.title or "", case.steps or "", templates)
    except Exception:
        return None


def _impl_generate_ui_steps(case: FunctionalCase, task: FunctionalTask, snapshot: PageSnapshot | None, config: AiConfig | None) -> GeneratedResult:
    dom_summary = snapshot.dom_summary if snapshot else ""
    # 尝试匹配操作模板
    templates = _load_action_templates(task.project_id) if hasattr(task, "project_id") else []
    matched_template = _match_template_for_case(case, templates)

    if matched_template:
        steps = parse_json_value(matched_template.steps, [])
        if isinstance(steps, list) and steps:
            return GeneratedResult(
                source="template",
                warning=f"已匹配操作模板：{matched_template.name}",
                items=steps,
            )

    prompt = f"""
你是一名资深测试工程师，请根据功能测试点生成 Playwright 可执行的 UI steps JSON。

## 严格定位器优先级（必须遵守）
1. data-testid / data-test / data-cy（最高优先级）
2. id / name 属性
3. placeholder / aria-label（CSS 写法，如 input[placeholder="邮箱"]）
4. text=按钮文案（最后手段）

## 禁止使用的定位器
- nth-child / :nth-of-type / :eq()（结构易变）
- 深层 CSS 路径如 div > div > div > button
- 纯 class 选择器（多页面共用类名，不唯一）

## 输出要求
- 只输出 JSON，格式：{{"steps":[{{"name":"打开页面","action":"goto","value":"..."}}]}}
- 允许 action：{", ".join(sorted(ALLOWED_UI_ACTIONS))}
- 除 goto/wait/screenshot/assert_url 外，所有操作必须带 locator
- 每个有 locator 的步骤输出 fallback_locators 数组，至少 1-3 个备用定位器
- 每一步必须有 name，用测试人员能理解的中文描述动作目标
- 允许可选字段 timeout、optional；非关键弱断言可以标 optional=true
- 运行时变量可用：{{{{username}}}}、{{{{password}}}}、{{{{code}}}}
- 如果页面同时存在"登录"和"立即注册/注册"，登录流程只能点击"登录"

目标页面：{task.target_url}
测试点标题：{case.title}
前置条件：{case.precondition or ""}
测试步骤：{case.steps or ""}
预期结果：{case.expected or ""}
页面 DOM 摘要：{dom_summary[:14000]}
"""
    warning = ""
    try:
        payload = call_local_model_json(config, prompt)
        steps = validate_ui_steps(payload)
    except Exception as exc:
        steps = []
        warning = f"本地模型未生成可执行步骤，已使用规则兜底：{exc}"
    if steps:
        if steps[0].get("action") != "goto":
            steps.insert(0, {"action": "goto", "value": task.target_url})
        return GeneratedResult(source="ai", warning=warning, items=steps)
    fallback = rule_generate_ui_steps(case, task, snapshot)
    return GeneratedResult(source="rule", warning=warning or "未配置本地模型或模型输出无效，已生成最小可执行步骤。", items=fallback)


def validate_ui_steps(steps: Any) -> list[Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_validate_ui_steps(steps)

def rule_generate_ui_steps(case: FunctionalCase, task: FunctionalTask, snapshot: PageSnapshot | None) -> list[Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_rule_generate_ui_steps(case, task, snapshot)

def _basic_generate_ui_steps(case: FunctionalCase, task: FunctionalTask, snapshot: PageSnapshot | None, config: AiConfig | None) -> GeneratedResult:
    _sync_compat_globals()
    return _impl__basic_generate_ui_steps(case, task, snapshot, config)

def _load_action_templates(project_id: int) -> list[Any]:
    _sync_compat_globals()
    return _impl__load_action_templates(project_id)

def _match_template_for_case(case: FunctionalCase, templates: list[Any]) -> Any | None:
    _sync_compat_globals()
    return _impl__match_template_for_case(case, templates)

def generate_ui_steps(case: FunctionalCase, task: FunctionalTask, snapshot: PageSnapshot | None, config: AiConfig | None) -> GeneratedResult:
    _sync_compat_globals()
    return _impl_generate_ui_steps(case, task, snapshot, config)
