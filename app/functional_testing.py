from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from html import unescape
import json
import mimetypes
from pathlib import Path
import re
import time
from typing import Any, Dict, Iterable
from urllib.parse import urlparse
from uuid import uuid4
import zipfile

import requests

from .executors import SCREENSHOT_DIR, ensure_report_dirs, launch_chromium_browser
from .models import AiConfig, FunctionalCase, FunctionalRequirementNote, FunctionalRun, FunctionalScreenshot, FunctionalTask, PageSnapshot


BASE_DIR = Path(__file__).resolve().parent.parent
FUNCTIONAL_DIR = BASE_DIR / "reports" / "functional"
AXURE_DIR = FUNCTIONAL_DIR / "axure"
FUNCTIONAL_SCREENSHOT_DIR = FUNCTIONAL_DIR / "screenshots"

ALLOWED_UI_ACTIONS = {
    "goto",
    "input",
    "click",
    "wait",
    "wait_for_selector",
    "text_assert",
    "screenshot",
    "select",
    "check",
    "uncheck",
    "assert_visible",
    "assert_url",
    "assert_value",
}


@dataclass
class GeneratedResult:
    source: str
    warning: str
    items: list[Dict[str, Any]]


def ensure_functional_dirs() -> None:
    ensure_report_dirs()
    AXURE_DIR.mkdir(parents=True, exist_ok=True)
    FUNCTIONAL_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def store_axure_file(filename: str, content: bytes) -> str:
    ensure_functional_dirs()
    suffix = Path(filename or "prototype.rp").suffix or ".rp"
    target = AXURE_DIR / f"{uuid4()}{suffix}"
    target.write_bytes(content)
    return str(target)


def store_functional_screenshot_file(filename: str, content: bytes) -> str:
    ensure_functional_dirs()
    suffix = Path(filename or "screenshot.png").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("只支持上传 PNG/JPG/WebP 截图")
    target = FUNCTIONAL_SCREENSHOT_DIR / f"{uuid4()}{suffix}"
    target.write_bytes(content)
    return str(target)


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _plain_text(raw: str) -> str:
    text = unescape(raw)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _interesting_lines(text: str, limit: int = 220) -> str:
    chunks = re.split(r"[\r\n。；;!?！？]| {2,}", text)
    seen = set()
    lines: list[str] = []
    for chunk in chunks:
        item = chunk.strip(" \t:：,，.-")
        if len(item) < 2 or len(item) > 120:
            continue
        if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", item):
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(item)
        if len(lines) >= limit:
            break
    return "\n".join(lines)


def read_axure_text(axure_path: str | None) -> str:
    if not axure_path:
        return ""
    path = Path(axure_path)
    if not path.exists() or not path.is_file():
        return ""
    try:
        if zipfile.is_zipfile(path):
            texts: list[str] = []
            total = 0
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.is_dir() or info.file_size <= 0:
                        continue
                    if info.file_size > 1024 * 1024:
                        continue
                    name = info.filename.lower()
                    if not name.endswith((".xml", ".html", ".htm", ".js", ".txt", ".json")):
                        continue
                    raw = archive.read(info)
                    total += len(raw)
                    texts.append(_plain_text(_decode_bytes(raw)))
                    if total > 2 * 1024 * 1024:
                        break
            return _interesting_lines("\n".join(texts))
        return _interesting_lines(_plain_text(_decode_bytes(path.read_bytes())))
    except Exception as exc:
        return f"Axure解析失败：{exc}"


def compact_requirement(
    task: FunctionalTask,
    axure_text: str,
    snapshot: PageSnapshot | None = None,
    screenshots: Iterable[FunctionalScreenshot] | None = None,
    notes: Iterable[FunctionalRequirementNote] | None = None,
) -> str:
    parts = [
        f"迭代：{task.iteration_name}",
        f"目标页面：{task.target_url}",
        f"初始需求说明：{task.requirement_text or ''}",
    ]
    note_text = "\n".join(
        f"- {item.create_time}: {item.note_text}" for item in (notes or []) if getattr(item, "note_text", "")
    )
    if note_text:
        parts.append(f"产品沟通后的补充需求：\n{note_text[:12000]}")
    screenshot_text = "\n\n".join(
        f"截图#{item.id}识别结果：\n{item.analysis_result}"
        for item in (screenshots or [])
        if getattr(item, "analysis_result", "")
    )
    if screenshot_text:
        parts.append(f"产品截图识别材料：\n{screenshot_text[:16000]}")
    if axure_text:
        parts.append(f"Axure提取文本：\n{axure_text[:12000]}")
    if snapshot and snapshot.dom_summary:
        parts.append(f"页面DOM摘要：\n{snapshot.dom_summary[:12000]}")
    return "\n\n".join(parts)


def _json_from_text(text: str) -> Any:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.I)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    start_candidates = [pos for pos in [raw.find("{"), raw.find("[")] if pos >= 0]
    if not start_candidates:
        return None
    start = min(start_candidates)
    end = max(raw.rfind("}"), raw.rfind("]"))
    if end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


def _format_model_http_error(response: requests.Response) -> str:
    status_code = response.status_code
    url = response.url
    host = ""
    match = re.match(r"https?://([^/]+)", url or "")
    if match:
        host = match.group(1)

    response_text = ""
    try:
        response_text = response.text[:500]
    except Exception:
        response_text = ""

    if status_code == 400 and "image_url" in response_text:
        return "当前模型接口不支持 image_url 图片输入，不能直接识别截图；请切换到支持视觉的 OpenAI兼容模型，或先使用系统兜底分析继续生成测试点。"
    if status_code == 401:
        return "模型接口认证失败，请检查 AI 配置里的 API Key 是否正确。"
    if status_code == 402:
        vendor = "DeepSeek" if "deepseek" in host.lower() else "当前模型服务"
        return f"{vendor} 返回 402 Payment Required，表示账号余额不足、额度耗尽或未开通计费；请充值/开通额度，或在 AI配置 中切换到 Ollama/其它可用模型。"
    if status_code == 403:
        return "模型接口没有访问权限，请检查 API Key 权限、模型名称和账号是否允许调用该模型。"
    if status_code == 404:
        return "模型接口地址或模型名称不存在，请检查 Base URL 和模型名称。"
    if status_code == 429:
        return "模型接口限流，请稍后重试，或更换额度更充足的模型。"
    if 500 <= status_code < 600:
        return f"模型服务端异常 HTTP {status_code}，请稍后重试或切换模型。"
    detail = f"；响应：{response_text}" if response_text else ""
    return f"模型接口调用失败 HTTP {status_code}{detail}"


def _raise_for_model_response(response: requests.Response) -> None:
    if response.ok:
        return
    raise RuntimeError(_format_model_http_error(response))


def _is_deepseek_api_base_url(base_url: str) -> bool:
    host = ""
    match = re.match(r"https?://([^/]+)", base_url or "")
    if match:
        host = match.group(1).lower()
    return host == "api.deepseek.com" or host.endswith(".deepseek.com")


def call_local_model_json(config: AiConfig | None, prompt: str, timeout: int = 90) -> Any:
    if not config or not config.base_url or not config.model:
        return None
    provider = (config.provider or "openai_compatible").strip().lower()
    base_url = config.base_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    if provider == "ollama":
        response = requests.post(
            f"{base_url}/api/generate",
            json={"model": config.model, "prompt": prompt, "stream": False, "format": "json"},
            timeout=timeout,
        )
        _raise_for_model_response(response)
        return _json_from_text(response.json().get("response", ""))

    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/v1/chat/completions"
    response = requests.post(
        endpoint,
        headers=headers,
        json={
            "model": config.model,
            "messages": [
                {"role": "system", "content": "你是资深软件测试工程师，只输出合法 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        },
        timeout=timeout,
    )
    _raise_for_model_response(response)
    payload = response.json()
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    return _json_from_text(content)


def _image_data_url(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists() or not path.is_file():
        raise RuntimeError("截图文件不存在")
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def call_visual_model_json(config: AiConfig | None, prompt: str, image_path: str, timeout: int = 120) -> Any:
    if not config or not config.base_url or not config.model:
        raise RuntimeError("未配置 AI 模型，无法识别截图")
    provider = (config.provider or "openai_compatible").strip().lower()
    if provider != "openai_compatible":
        raise RuntimeError("截图识别需要 OpenAI兼容视觉模型；当前配置不是 OpenAI兼容模式")
    base_url = config.base_url.rstrip("/")
    if _is_deepseek_api_base_url(base_url):
        raise RuntimeError(
            "DeepSeek 官方 chat/completions 接口当前文档只定义文本消息，messages.content 不支持 image_url 图片输入；"
            "请切换到支持视觉的 OpenAI兼容模型，或先使用系统兜底分析继续生成测试点。"
        )
    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    response = requests.post(
        endpoint,
        headers=headers,
        json={
            "model": config.model,
            "messages": [
                {"role": "system", "content": "你是资深软件测试工程师，只输出合法 JSON。"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                    ],
                },
            ],
            "temperature": 0.2,
        },
        timeout=timeout,
    )
    _raise_for_model_response(response)
    payload = response.json()
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    return _json_from_text(content)


def fallback_screenshot_analysis(task: FunctionalTask, screenshot: FunctionalScreenshot, reason: str) -> str:
    page_hint = f"{task.iteration_name} 页面" if task.iteration_name else "产品截图页面"
    if "login" in (task.target_url or "").lower() or "注册" in (task.iteration_name or ""):
        page_summary = f"{page_hint}截图已保存。当前模型未能直接读取图片，系统按注册/登录类页面生成兜底需求分析。"
        visible_controls = [
            "账号/身份相关输入项",
            "手机号/邮箱/验证码/密码等注册类字段",
            "验证码发送或校验入口",
            "协议勾选入口",
            "提交/下一步按钮",
            "错误提示或确认弹窗",
        ]
        inferred_rules = [
            "必填项为空时应阻止提交并提示",
            "手机号、邮箱、验证码、密码格式需要校验",
            "验证码发送后通常存在倒计时和重复发送限制",
            "协议未勾选时应提示确认或禁止继续",
            "已注册账号应给出明确提示",
        ]
        suggested_test_points = [
            "验证注册页面字段展示和默认状态",
            "验证必填项为空、格式错误、重复账号的提示",
            "验证验证码获取、倒计时、重复发送和错误验证码",
            "验证协议勾选/未勾选对提交流程的影响",
            "验证提交成功后进入下一步或成功页",
        ]
    else:
        page_summary = f"{page_hint}截图已保存。当前模型未能直接读取图片，系统生成通用兜底需求分析。"
        visible_controls = ["页面主要输入项", "主要操作按钮", "列表/表格/提示信息", "弹窗或状态反馈"]
        inferred_rules = ["关键字段应做必填和格式校验", "主流程提交后应有明确反馈", "异常状态应展示可理解提示"]
        suggested_test_points = ["验证页面元素展示", "验证主流程操作", "验证必填/格式/异常提示", "验证权限或状态变化"]

    payload = {
        "analysis_source": "fallback",
        "model_error": reason,
        "page_summary": page_summary,
        "visible_controls": visible_controls,
        "inferred_rules": inferred_rules,
        "questions_for_product": [
            "请确认截图中的字段是否全部必填",
            "请确认每个字段的格式、长度和唯一性规则",
            "请确认验证码发送频率、有效期和错误次数限制",
            "请确认协议未勾选时是弹窗提示还是禁止提交",
            "请确认成功提交后的跳转页面和状态变化",
        ],
        "suggested_test_points": suggested_test_points,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def analyze_functional_screenshot(task: FunctionalTask, screenshot: FunctionalScreenshot, config: AiConfig | None) -> str:
    prompt = f"""
请识别这张产品需求/原型截图，并从软件测试工程师角度输出 JSON。
格式：
{{
  "page_summary": "页面功能概述",
  "visible_controls": ["可见按钮、输入框、筛选项、表格、弹窗等"],
  "inferred_rules": ["从截图能推测出的业务规则"],
  "questions_for_product": ["需要向产品确认的问题"],
  "suggested_test_points": ["建议测试点"]
}}
要求：不要编造截图里完全看不到的信息；如果截图信息不足，把需要确认的问题写清楚。
迭代：{task.iteration_name}
目标页面：{task.target_url}
初始需求说明：{task.requirement_text or ""}
"""
    try:
        payload = call_visual_model_json(config, prompt, screenshot.image_path)
    except Exception as exc:
        return fallback_screenshot_analysis(task, screenshot, str(exc))
    if not isinstance(payload, dict):
        return fallback_screenshot_analysis(task, screenshot, "视觉模型未返回合法 JSON")
    normalized = {
        "page_summary": payload.get("page_summary") or payload.get("summary") or "",
        "visible_controls": payload.get("visible_controls") or payload.get("controls") or [],
        "inferred_rules": payload.get("inferred_rules") or payload.get("rules") or [],
        "questions_for_product": payload.get("questions_for_product") or payload.get("questions") or [],
        "suggested_test_points": payload.get("suggested_test_points") or payload.get("test_points") or [],
    }
    return json.dumps(normalized, ensure_ascii=False, indent=2)


def _normalize_generated_cases(payload: Any) -> list[Dict[str, Any]]:
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        return []
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
                "automation_status": "draft",
            }
        )
    return result[:30]


def _extract_json_list_field(text: str, field_name: str) -> list[str]:
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


def rule_generate_cases(task: FunctionalTask, axure_text: str, extra_context: str = "") -> list[Dict[str, Any]]:
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
    for index, line in enumerate(picked[:10], start=1):
        title = line[:80]
        result.append(
            {
                "title": title,
                "precondition": "测试账号可登录，测试环境数据可用。",
                "steps": f"1. 打开目标页面\n2. 按需求执行：{line}\n3. 观察页面反馈和数据变化",
                "expected": "页面提示正确，数据状态符合需求，核心流程无报错。",
                "priority": "P0" if index <= 2 else "P1",
                "automation_status": "draft",
            }
        )
    return result


def generate_functional_cases(
    task: FunctionalTask,
    axure_text: str,
    snapshot: PageSnapshot | None,
    config: AiConfig | None,
    screenshots: Iterable[FunctionalScreenshot] | None = None,
    notes: Iterable[FunctionalRequirementNote] | None = None,
) -> GeneratedResult:
    requirement_context = compact_requirement(task, axure_text, snapshot, screenshots, notes)
    prompt = f"""
请根据以下需求和原型信息，生成适合功能测试的测试点草稿。
输出 JSON，格式：
{{"cases":[{{"title":"","precondition":"","steps":"","expected":"","priority":"P0/P1/P2"}}]}}
要求：
1. 以 UI 功能流程为主；
2. 覆盖正常流程、关键异常、权限/必填/状态变化；
3. 不要输出说明文字，只输出 JSON。

{requirement_context}
"""
    warning = ""
    try:
        generated = _normalize_generated_cases(call_local_model_json(config, prompt))
    except Exception as exc:
        generated = []
        warning = f"本地模型调用失败，已使用规则生成：{exc}"
    if generated:
        return GeneratedResult(source="ai", warning=warning, items=generated)
    fallback = rule_generate_cases(task, axure_text, requirement_context)
    if not warning:
        warning = "未配置本地模型或模型未返回合法 JSON，已使用规则生成草稿。"
    return GeneratedResult(source="rule", warning=warning, items=fallback)


def _locator_candidates(value: Any, defaults: list[str]) -> list[str]:
    raw_items: list[str] = []
    if isinstance(value, list):
        raw_items = [str(item) for item in value]
    elif value:
        raw_items = re.split(r"[\r\n]+", str(value))
    candidates: list[str] = []
    for item in [*raw_items, *defaults]:
        locator = str(item or "").strip()
        if locator and locator not in candidates:
            candidates.append(locator)
    return candidates


class FunctionalScanError(RuntimeError):
    def __init__(self, message: str, trace: list[str] | None = None):
        super().__init__(message)
        self.trace = trace or []


def _scan_trace(trace: list[str], message: str) -> None:
    trace.append(message)


def _scan_error(message: str, trace: list[str]) -> FunctionalScanError:
    return FunctionalScanError(message, trace)


def _fill_first_available(page: Any, locators: list[str], value: str, name: str, trace: list[str]) -> str:
    last_error = ""
    for locator in locators:
        try:
            target = page.locator(locator).first
            target.wait_for(state="visible", timeout=5000)
            target.fill(value)
            _scan_trace(trace, f"已填写{name}：{locator}")
            return locator
        except Exception as exc:
            last_error = str(exc)
    raise _scan_error(f"登录未成功，请检查{name}定位器。最后错误：{last_error[:300]}", trace)


def _clean_text_locator_value(locator: str) -> str:
    value = locator.strip()[5:].strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    return value.strip()


def _element_text(locator: Any) -> str:
    try:
        return locator.evaluate(
            """
            (el) => (el.innerText || el.textContent || el.value || el.getAttribute("aria-label") || "").trim().replace(/\\s+/g, " ")
            """
        )
    except Exception:
        return ""


def _click_text_locator(page: Any, locator: str, trace: list[str]) -> bool:
    target_text = _clean_text_locator_value(locator)
    if not target_text:
        return False
    targets = page.locator(locator)
    try:
        count = min(targets.count(), 30)
    except Exception:
        return False

    visible_indexes: list[int] = []
    exact_indexes: list[int] = []
    for index in range(count):
        item = targets.nth(index)
        try:
            if not item.is_visible(timeout=500):
                continue
            visible_indexes.append(index)
            if _element_text(item) == target_text:
                exact_indexes.append(index)
        except Exception:
            continue

    for index in exact_indexes:
        try:
            targets.nth(index).click()
            _scan_trace(trace, f"已点击登录按钮：{locator}（精确文本）")
            return True
        except Exception:
            continue

    for index in reversed(visible_indexes):
        try:
            text = _element_text(targets.nth(index))
            targets.nth(index).click()
            _scan_trace(trace, f"已点击登录按钮：{locator}（可见候选：{text or index}）")
            return True
        except Exception:
            continue
    return False


def _click_first_available(page: Any, locators: list[str], name: str, trace: list[str]) -> str:
    last_error = ""
    for locator in locators:
        try:
            if name == "登录按钮" and locator.strip().lower().startswith("text=") and _click_text_locator(page, locator, trace):
                return locator
            target = page.locator(locator).last if name == "登录按钮" else page.locator(locator).first
            target.wait_for(state="visible", timeout=5000)
            target.click()
            _scan_trace(trace, f"已点击{name}：{locator}")
            return locator
        except Exception as exc:
            last_error = str(exc)
    raise _scan_error(f"登录未成功，请检查{name}定位器。最后错误：{last_error[:300]}", trace)


def _input_meta(locator: Any, index: int) -> Dict[str, Any]:
    return locator.evaluate(
        """
        (el, index) => {
          const textOf = (node) => (node && (node.innerText || node.textContent || "") || "").trim().replace(/\\s+/g, " ").slice(0, 160);
          const wrap = el.closest(".el-form-item,.ant-form-item,.form-item,.field,.input-item,.login-item,.login-form,.form-group,label") || el.parentElement;
          const rect = el.getBoundingClientRect();
          return {
            index,
            type: (el.getAttribute("type") || "").toLowerCase(),
            id: el.id || "",
            name: el.getAttribute("name") || "",
            placeholder: el.getAttribute("placeholder") || "",
            autocomplete: el.getAttribute("autocomplete") || "",
            ariaLabel: el.getAttribute("aria-label") || "",
            labelText: textOf(wrap),
            visible: !!(rect.width && rect.height)
          };
        }
        """,
        index,
    )


def _score_input(meta: Dict[str, Any], kind: str) -> int:
    text = " ".join(
        str(meta.get(key) or "")
        for key in ["type", "id", "name", "placeholder", "autocomplete", "ariaLabel", "labelText"]
    ).lower()
    input_type = str(meta.get("type") or "").lower()
    if not meta.get("visible") or input_type in {"hidden", "checkbox", "radio", "submit", "button"}:
        return -100
    if kind == "password":
        score = 0
        if input_type == "password":
            score += 100
        for keyword in ["密码", "パスワード", "password", "pwd"]:
            if keyword.lower() in text:
                score += 30
        return score

    if input_type == "password":
        return -100
    score = 5
    for keyword in ["邮箱", "邮件", "手机号", "手机", "账号", "帐号", "用户名", "名字", "メール", "email", "mail", "phone", "mobile", "account", "user", "name"]:
        if keyword.lower() in text:
            score += 30
    if input_type in {"email", "tel", "text", ""}:
        score += 10
    return score


def _fill_auto_input(page: Any, value: str, kind: str, name: str, trace: list[str]) -> str:
    inputs = page.locator("input, textarea")
    candidates: list[tuple[int, int, Dict[str, Any]]] = []
    try:
        count = min(inputs.count(), 40)
    except Exception as exc:
        raise _scan_error(f"登录未成功，无法读取登录表单输入框：{str(exc)[:300]}", trace)
    for index in range(count):
        item = inputs.nth(index)
        try:
            meta = _input_meta(item, index)
            score = _score_input(meta, kind)
            if score > 0:
                candidates.append((score, index, meta))
        except Exception:
            continue
    if not candidates:
        raise _scan_error(f"登录未成功，自动识别不到{name}", trace)
    score, index, meta = sorted(candidates, key=lambda item: item[0], reverse=True)[0]
    inputs.nth(index).fill(value)
    label = meta.get("placeholder") or meta.get("name") or meta.get("id") or meta.get("labelText") or f"input[{index}]"
    _scan_trace(trace, f"已自动填写{name}：{label}，匹配分 {score}")
    return f"input:nth({index})"


def _click_login_submit(page: Any, locators: list[str], trace: list[str]) -> str:
    try:
        return _click_first_available(page, locators, "登录按钮", trace)
    except FunctionalScanError:
        pass

    fallback_locators = [
        'button:has-text("登录")',
        'button:has-text("登入")',
        'button:has-text("Login")',
        'button:has-text("Sign in")',
        'button:has-text("ログイン")',
        '[role="button"]:has-text("登录")',
        '[role="button"]:has-text("Login")',
        '.el-button:has-text("登录")',
        '.ant-btn:has-text("登录")',
        '[class*="btn"]:has-text("登录")',
        '[class*="button"]:has-text("登录")',
        'text=登录',
        'text=Login',
    ]
    for locator in fallback_locators:
        try:
            target = page.locator(locator).last
            target.wait_for(state="visible", timeout=2500)
            target.click()
            _scan_trace(trace, f"已通过兜底规则点击登录按钮：{locator}")
            return locator
        except Exception:
            continue

    try:
        page.keyboard.press("Enter")
        _scan_trace(trace, "未定位到登录按钮，已尝试按 Enter 提交")
        return "keyboard:Enter"
    except Exception as exc:
        raise _scan_error(f"登录未成功，登录按钮定位失败，且 Enter 提交失败：{str(exc)[:300]}", trace)


def _check_keep_login(page: Any, trace: list[str]) -> None:
    checkbox_locators = [
        'label:has-text("保持账号登录")',
        'text=保持账号登录',
        'input[type="checkbox"]',
        '.el-checkbox:has-text("保持账号登录")',
        '.ant-checkbox-wrapper:has-text("保持账号登录")',
    ]
    for locator in checkbox_locators:
        try:
            target = page.locator(locator).first
            target.wait_for(state="visible", timeout=1500)
            try:
                input_target = target if locator.startswith("input") else target.locator('input[type="checkbox"]').first
                if input_target.count() and not input_target.is_checked(timeout=500):
                    input_target.check(force=True)
                    _scan_trace(trace, f"已勾选保持账号登录：{locator}")
                    return
                if input_target.count() and input_target.is_checked(timeout=500):
                    _scan_trace(trace, "保持账号登录已是勾选状态")
                    return
            except Exception:
                pass
            target.click()
            _scan_trace(trace, f"已点击保持账号登录：{locator}")
            return
        except Exception:
            continue
    _scan_trace(trace, "未找到保持账号登录选项，继续登录")


def _safe_url_label(url: str) -> str:
    try:
        parsed = urlparse(url)
        return f"{parsed.netloc}{parsed.path}"
    except Exception:
        return str(url).split("?")[0][:120]


def _attach_login_network_trace(page: Any, trace: list[str]) -> list[str]:
    events: list[str] = []

    def is_interesting(url: str, method: str = "") -> bool:
        text = url.lower()
        return method.upper() == "POST" or any(keyword in text for keyword in ["login", "auth", "token", "user", "partner"])

    def on_request(request: Any) -> None:
        try:
            if is_interesting(request.url, request.method):
                events.append(f"请求 {request.method} {_safe_url_label(request.url)}")
        except Exception:
            return

    def on_response(response: Any) -> None:
        try:
            request = response.request
            if is_interesting(response.url, request.method):
                events.append(f"响应 {response.status} {request.method} {_safe_url_label(response.url)}")
        except Exception:
            return

    page.on("request", on_request)
    page.on("response", on_response)
    _scan_trace(trace, "已开启登录阶段网络请求监听")
    return events


def _is_login_response(response: Any) -> bool:
    try:
        url = response.url.lower()
        method = response.request.method.upper()
        return method == "POST" and any(keyword in url for keyword in ["login", "auth", "token", "partnerlogin"])
    except Exception:
        return False


def _redacted_response_summary(response: Any) -> str:
    try:
        payload = response.json()
    except Exception:
        try:
            text = response.text()
        except Exception:
            text = ""
        return f"HTTP {response.status}，响应文本：{text[:180]}"

    if isinstance(payload, dict):
        parts = [f"HTTP {response.status}"]
        for key in ["success", "code", "msg", "message", "error"]:
            if key in payload:
                parts.append(f"{key}={payload.get(key)}")
        data = payload.get("data")
        if isinstance(data, dict):
            safe_keys = [key for key in data.keys() if not re.search(r"token|password|secret|authorization", str(key), re.I)]
            sensitive_keys = [key for key in data.keys() if key not in safe_keys]
            if safe_keys:
                parts.append(f"data字段={','.join(map(str, safe_keys[:12]))}")
            if sensitive_keys:
                parts.append(f"敏感字段已隐藏={','.join(map(str, sensitive_keys[:8]))}")
        return "，".join(parts)
    return f"HTTP {response.status}，响应类型={type(payload).__name__}"


def _auth_storage_snapshot(page: Any) -> str:
    try:
        return page.evaluate(
            """
            () => JSON.stringify({
              url: location.href,
              local: Object.keys(localStorage).filter((key) => /token|auth|user|login|session/i.test(key)).map((key) => [key, localStorage.getItem(key)]),
              session: Object.keys(sessionStorage).filter((key) => /token|auth|user|login|session/i.test(key)).map((key) => [key, sessionStorage.getItem(key)]),
              cookie: document.cookie || ""
            })
            """
        )
    except Exception:
        return ""


def _wait_after_login_submit(page: Any, before_url: str, before_storage: str, trace: list[str], timeout: int) -> None:
    deadline = time.time() + min(max(timeout, 8), 20)
    last_url = before_url
    while time.time() < deadline:
        page.wait_for_timeout(500)
        current_url = page.url
        if current_url != before_url:
            _scan_trace(trace, f"检测到登录后页面跳转：{current_url}")
            return
        current_storage = _auth_storage_snapshot(page)
        if current_storage and current_storage != before_storage:
            _scan_trace(trace, "检测到登录态写入 localStorage/sessionStorage/cookie")
            return
        if last_url != current_url:
            last_url = current_url
        if not _looks_like_login_page(page):
            _scan_trace(trace, "登录表单已消失")
            return
    _scan_trace(trace, "登录后未检测到明显跳转或登录态变化，继续尝试进入目标页面")


def _has_visible_locator(page: Any, locator: str, timeout: int = 300) -> bool:
    try:
        targets = page.locator(locator)
        count = min(targets.count(), 5)
        return any(targets.nth(index).is_visible(timeout=timeout) for index in range(count))
    except Exception:
        return False


def _looks_like_login_page(page: Any, expected_url: str = "") -> bool:
    try:
        current_url = (page.url or "").lower()
        expected = (expected_url or "").lower()
        if ("login" in current_url or "signin" in current_url) and current_url != expected:
            return True
        has_password = _has_visible_locator(page, 'input[type="password"]')
        if not has_password:
            return False
        has_account = any(
            _has_visible_locator(page, locator)
            for locator in [
                'input[name="username"]',
                'input[name="account"]',
                'input[name="mobile"]',
                'input[name="email"]',
                'input[placeholder*="账号"]',
                'input[placeholder*="用户名"]',
                'input[placeholder*="手机号"]',
                'input[placeholder*="邮箱"]',
            ]
        )
        has_login_button = any(
            _has_visible_locator(page, locator)
            for locator in ["text=登录", "text=登入", "text=登陆", "text=Login", "text=Sign in", "text=ログイン"]
        )
        return has_account or has_login_button
    except Exception:
        return False


def _login_before_scan(page: Any, page_url: str, auth: Dict[str, Any], timeout: int, trace: list[str]) -> None:
    login_url = str(auth.get("login_url") or "").strip()
    username = str(auth.get("username") or "")
    password = str(auth.get("password") or "")
    if not login_url or not username or not password:
        raise _scan_error("登录未成功，请填写登录页URL、登录账号和登录密码", trace)

    username_locators = _locator_candidates(
        auth.get("username_locator"),
        [
            'input[name="username"]',
            'input[name="account"]',
            'input[name="mobile"]',
            'input[name="email"]',
            'input[placeholder*="账号"]',
            'input[placeholder*="用户名"]',
            'input[placeholder*="手机号"]',
            'input[placeholder*="邮箱"]',
            'input[placeholder*="メール"]',
            'input[placeholder*="email" i]',
            'input[type="text"]',
            'input:not([type])',
        ],
    )
    password_locators = _locator_candidates(
        auth.get("password_locator"),
        [
            'input[type="password"]',
            'input[name="password"]',
            'input[placeholder*="密码"]',
            'input[placeholder*="パスワード"]',
            'input[placeholder*="password" i]',
        ],
    )
    submit_locators = _locator_candidates(
        auth.get("submit_locator"),
        [
            'button[type="submit"]',
            'input[type="submit"]',
            "text=登录",
            "text=登入",
            "text=登陆",
            "text=Login",
            "text=Sign in",
            "text=ログイン",
        ],
    )

    _scan_trace(trace, f"打开登录页：{login_url}")
    page.goto(login_url, wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    try:
        _fill_first_available(page, username_locators, username, "账号输入框", trace)
    except FunctionalScanError:
        _fill_auto_input(page, username, "username", "账号输入框", trace)
    try:
        _fill_first_available(page, password_locators, password, "密码输入框", trace)
    except FunctionalScanError:
        _fill_auto_input(page, password, "password", "密码输入框", trace)
    _check_keep_login(page, trace)
    network_events = _attach_login_network_trace(page, trace)
    before_url = page.url
    before_storage = _auth_storage_snapshot(page)
    login_response = None
    try:
        with page.expect_response(_is_login_response, timeout=15000) as response_info:
            _click_login_submit(page, submit_locators, trace)
        login_response = response_info.value
    except FunctionalScanError:
        raise
    except Exception:
        _scan_trace(trace, "点击登录后 15 秒内未捕获登录接口响应")
    if login_response is not None:
        _scan_trace(trace, f"登录接口返回摘要：{_redacted_response_summary(login_response)}")

    success_selector = str(auth.get("success_selector") or "").strip()
    success_url_contains = str(auth.get("success_url_contains") or "").strip()
    if success_selector:
        _scan_trace(trace, f"等待登录成功元素：{success_selector}")
        page.wait_for_selector(success_selector, timeout=timeout * 1000)
    elif success_url_contains:
        _scan_trace(trace, f"等待登录成功 URL 包含：{success_url_contains}")
        page.wait_for_url(f"**{success_url_contains}**", timeout=timeout * 1000)
    else:
        _scan_trace(trace, "等待登录请求和页面跳转完成")
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            page.wait_for_timeout(2000)
        _wait_after_login_submit(page, before_url, before_storage, trace, timeout)
    if network_events:
        _scan_trace(trace, "登录阶段网络请求：")
        for item in network_events[-12:]:
            _scan_trace(trace, f"  {item}")
    else:
        _scan_trace(trace, "登录阶段没有捕获到登录/认证相关请求")

    _scan_trace(trace, f"进入目标页面：{page_url}")
    page.goto(page_url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        page.wait_for_timeout(1200)
    if _looks_like_login_page(page, expected_url=page_url):
        raise _scan_error(f"登录未成功，请检查账号密码或登录定位器。当前页面：{page.url}", trace)
    _scan_trace(trace, f"目标页面已打开：{page.url}")


def scan_page_dom(page_url: str, timeout: int = 30, auth: Dict[str, Any] | None = None) -> Dict[str, str]:
    ensure_functional_dirs()
    screenshot = SCREENSHOT_DIR / f"functional-{uuid4()}.png"
    started = time.time()
    trace: list[str] = []
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _scan_error(f"Playwright不可用：{exc}", trace) from exc

    with sync_playwright() as p:
        browser = launch_chromium_browser(p, headless=True)
        page = browser.new_page()
        page.set_default_timeout(timeout * 1000)
        auth_config = auth or {}
        if auth_config.get("enabled"):
            _login_before_scan(page, page_url, auth_config, timeout, trace)
        else:
            _scan_trace(trace, f"未启用登录，直接打开目标页面：{page_url}")
            page.goto(page_url, wait_until="domcontentloaded")
            page.wait_for_timeout(800)
        _scan_trace(trace, "开始提取页面 DOM 摘要")
        summary = page.evaluate(
            """
            () => {
              const css = (value) => {
                if (!value) return "";
                if (window.CSS && CSS.escape) return CSS.escape(value);
                return String(value).replace(/[^a-zA-Z0-9_-]/g, "\\\\$&");
              };
              const textOf = (el) => (el.innerText || el.value || el.getAttribute("aria-label") || el.getAttribute("placeholder") || "").trim().replace(/\\s+/g, " ").slice(0, 80);
              const locatorOf = (el) => {
                const quote = (value) => String(value || "").replace(/"/g, '\\"');
                const testAttr = ["data-testid", "data-test", "data-cy"].find((attr) => el.getAttribute(attr));
                if (testAttr) return `[${testAttr}="${quote(el.getAttribute(testAttr))}"]`;
                if (el.id) return `#${css(el.id)}`;
                if (el.name) return `${el.tagName.toLowerCase()}[name="${quote(el.name)}"]`;
                const aria = el.getAttribute("aria-label");
                if (aria) return `${el.tagName.toLowerCase()}[aria-label="${quote(aria)}"]`;
                const placeholder = el.getAttribute("placeholder");
                if (placeholder) return `${el.tagName.toLowerCase()}[placeholder="${quote(placeholder)}"]`;
                const text = textOf(el);
                if (text && ["BUTTON","A","SPAN","DIV"].includes(el.tagName)) return `text=${text}`;
                return el.tagName.toLowerCase();
              };
              const selectors = "a,button,input,textarea,select,[role=button],[role=link],[contenteditable=true],.el-button,.ant-btn,[class*=btn],[class*=button]";
              const elements = Array.from(document.querySelectorAll(selectors)).slice(0, 180).map((el, index) => ({
                index,
                tag: el.tagName.toLowerCase(),
                type: el.getAttribute("type") || "",
                id: el.id || "",
                name: el.getAttribute("name") || "",
                role: el.getAttribute("role") || "",
                text: textOf(el),
                placeholder: el.getAttribute("placeholder") || "",
                locator: locatorOf(el)
              }));
              const headings = Array.from(document.querySelectorAll("h1,h2,h3,h4,label")).slice(0, 80).map(textOf).filter(Boolean);
              return { title: document.title, url: location.href, headings, elements };
            }
            """
        )
        _scan_trace(trace, f"DOM 摘要提取完成：{len(summary.get('elements') or [])} 个可操作元素")
        page.screenshot(path=str(screenshot), full_page=True)
        _scan_trace(trace, "页面截图已保存")
        browser.close()

    return {
        "dom_summary": json.dumps({"scan_seconds": round(time.time() - started, 2), "scan_trace": trace, **summary}, ensure_ascii=False, indent=2),
        "screenshot_path": str(screenshot),
        "scan_trace": trace,
    }


def validate_ui_steps(steps: Any) -> list[Dict[str, Any]]:
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


def rule_generate_ui_steps(case: FunctionalCase, task: FunctionalTask, snapshot: PageSnapshot | None) -> list[Dict[str, Any]]:
    steps: list[Dict[str, Any]] = [{"action": "goto", "value": task.target_url}]
    steps.append({"action": "wait_for_selector", "locator": "body"})
    if "注册" in (case.title or "") and "login" in (task.target_url or "").lower():
        steps.extend(
            [
                {"action": "click", "locator": "text=立即注册"},
                {"action": "wait", "value": 1000},
            ]
        )
    steps.append({"action": "screenshot"})
    return steps


def generate_ui_steps(case: FunctionalCase, task: FunctionalTask, snapshot: PageSnapshot | None, config: AiConfig | None) -> GeneratedResult:
    dom_summary = snapshot.dom_summary if snapshot else ""
    prompt = f"""
请把以下功能测试点转换成 Playwright 可执行的 UI steps JSON。
只输出 JSON，格式：{{"steps":[{{"action":"goto","value":"..."}}]}}
允许 action：{", ".join(sorted(ALLOWED_UI_ACTIONS))}
locator 优先级：data-testid、id、name、placeholder、aria-label、text，不要使用不稳定的深层 CSS。
placeholder 请使用 CSS 写法，例如 input[placeholder="邮箱/手机号"]，不要写 placeholder=邮箱/手机号。
除 goto/wait/screenshot/assert_url 外，所有操作必须带 locator；点击可使用 text=按钮文案。
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


def _load_json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _step_text(step: Any) -> str:
    if not isinstance(step, dict):
        return str(step or "未知步骤")
    action = step.get("action") or "未知动作"
    locator = step.get("locator")
    value = step.get("value")
    parts = [f"动作：{action}"]
    if locator:
        parts.append(f"定位：{locator}")
    if value not in (None, ""):
        parts.append(f"值：{value}")
    return "，".join(parts)


def _locator_from_error(error: str) -> str:
    patterns = [
        r"locator\((?:'|\")(.+?)(?:'|\")\)",
        r"locator\s+['\"](.+?)['\"]",
        r"locator\s+(.+?)\s+(?:is not visible|failed)",
    ]
    for pattern in patterns:
        match = re.search(pattern, error)
        if match:
            return match.group(1)
    return ""


def _infer_failed_step(ui_log: Dict[str, Any], error: str) -> tuple[Any, int | None]:
    step = ui_log.get("failed_step")
    index = ui_log.get("failed_step_index")
    if step:
        return step, index if isinstance(index, int) else None
    steps = ui_log.get("steps") if isinstance(ui_log.get("steps"), list) else []
    locator = _locator_from_error(error)
    if locator:
        for pos, item in enumerate(steps, start=1):
            if isinstance(item, dict) and item.get("locator") == locator:
                return item, pos
    action_hints = [
        ("text_assert failed", "text_assert"),
        ("assert_visible failed", "assert_visible"),
        ("assert_url failed", "assert_url"),
        ("assert_value failed", "assert_value"),
    ]
    for error_text, action in action_hints:
        if error_text in error:
            for pos, item in enumerate(steps, start=1):
                if isinstance(item, dict) and item.get("action") == action:
                    return item, pos
    return None, None


def _failure_reason_and_actions(error: str, failed_step: Any) -> tuple[str, str, list[str]]:
    error_lower = error.lower()
    locator = _locator_from_error(error)
    if "unknown engine" in error_lower:
        return (
            "定位写法不符合 Playwright 规则",
            "用例里的 locator 写法无法被 Playwright 识别，例如 placeholder=xxx 不是当前执行器支持的选择器写法。",
            ["把 locator 改成 CSS 写法，例如 input[placeholder=\"邮箱/手机号\"]", "重新扫描页面 DOM 后重新生成 UI 步骤", "优先使用 id、name、data-testid 这类稳定定位"],
        )
    if "playwright 不可用" in error or "greenlet" in error_lower or "browser" in error_lower and "executable" in error_lower:
        return (
            "执行环境异常",
            "本机 Playwright、浏览器或 Python 依赖不可用，用例还没有真正跑到页面步骤。",
            ["先修复本地运行环境，再重跑该用例", "检查 Chromium/Chrome/Edge 是否可启动", "确认服务启动使用的是同一个稳定 Python 虚拟环境"],
        )
    if "timeout" in error_lower or "waiting for" in error_lower:
        target = f"：{locator}" if locator else ""
        return (
            f"页面元素等待超时{target}",
            "页面在规定时间内没有出现目标元素，常见原因是页面没有进入预期状态、定位不准确、加载慢或前一步点击没有生效。",
            ["打开失败截图确认当前页面停在哪一步", "确认前一步操作后页面是否应该出现该元素", "优先用稳定 locator，必要时增加等待或改成更准确的步骤"],
        )
    if "text_assert failed" in error:
        return (
            "页面文案断言失败",
            "实际页面文本和用例预期不一致，可能是预期写错、页面文案变更，或当前页面不是目标页面。",
            ["查看失败截图和实际页面文案", "确认产品需求中的文案是否已变更", "如果只是标题/说明类文案，不建议作为主流程强断言"],
        )
    if "assert_url failed" in error:
        return (
            "页面跳转结果不符合预期",
            "执行后 URL 没有跳到预期地址，可能是提交失败、权限/登录状态异常，或预期跳转地址写错。",
            ["检查当前 URL 和失败截图", "确认前置账号、验证码、测试数据是否有效", "确认需求里成功后的跳转页面"],
        )
    if "assert_value failed" in error:
        return (
            "输入值校验失败",
            "输入框中的实际值和预期值不一致，可能是输入未生效、控件格式化了内容，或定位到了错误输入框。",
            ["确认输入框 locator 是否唯一", "检查页面是否自动格式化输入内容", "必要时先 assert_visible 再 input"],
        )
    if "strict mode violation" in error_lower:
        return (
            "元素定位不唯一",
            "当前 locator 匹配到了多个元素，Playwright 无法判断应该操作哪一个。",
            ["改用更唯一的定位方式，如 id、name、placeholder 或更精确的 text", "避免使用过宽泛的 input/button 定位"],
        )
    if "not visible" in error_lower:
        return (
            "目标元素不可见",
            "元素存在但当前不可见，可能被弹窗遮挡、在折叠区域内、还未渲染完成或需要滚动。",
            ["查看截图确认元素是否被遮挡", "补充点击展开、滚动或等待步骤", "确认当前页面状态是否符合预期"],
        )
    return (
        "用例执行异常",
        "执行过程中出现异常，需要结合失败截图、当前页面和用例步骤继续判断。",
        ["先查看失败截图确认页面状态", "检查失败步骤的 locator 和测试数据", "必要时把页面 DOM 重新扫描后重新生成步骤"],
    )


def rule_diagnose_failure(run: FunctionalRun) -> Dict[str, Any]:
    run_log = _load_json_object(run.log)
    records = run_log.get("records") if isinstance(run_log.get("records"), list) else []
    failed_records = [item for item in records if isinstance(item, dict) and item.get("result") != "passed"]
    passed_count = run_log.get("passed_count", run.passed_count or 0)
    failed_count = run_log.get("failed_count", run.failed_count or len(failed_records))
    failed_cases = []
    for record in failed_records:
        ui_log = _load_json_object(record.get("log"))
        error = ui_log.get("error") or record.get("error") or "未记录具体错误"
        failed_step, failed_step_no = _infer_failed_step(ui_log, error)
        failure, likely_reason, suggested_actions = _failure_reason_and_actions(error, failed_step)
        failed_cases.append(
            {
                "case_title": record.get("title") or ui_log.get("case_name") or "未知用例",
                "record_id": record.get("record_id"),
                "failed_step_no": failed_step_no,
                "failed_step": _step_text(failed_step) if failed_step else "未能从日志中定位到具体步骤",
                "failure": failure,
                "likely_reason": likely_reason,
                "suggested_actions": suggested_actions,
                "error_detail": error,
                "screenshot": record.get("screenshot") or ui_log.get("screenshot") or "",
            }
        )
    summary = f"本次执行共通过 {passed_count} 条，失败 {failed_count} 条。"
    if failed_cases:
        summary += f" 需要优先处理：{failed_cases[0]['case_title']}。"
    return {
        "summary": summary,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "failed_cases": failed_cases,
        "overall_suggestions": [
            "先按失败用例逐条查看截图，确认页面实际停留位置。",
            "优先检查失败步骤的定位和前置数据，不要先改业务代码。",
            "如果页面结构改过，建议重新扫描页面 DOM 后重新生成 UI 步骤。",
        ],
    }


def diagnose_failure(run: FunctionalRun, config: AiConfig | None) -> str:
    rule_payload = rule_diagnose_failure(run)
    prompt = f"""
你是一名资深软件测试工程师，请把下面的自动化失败日志整理成测试人员容易理解的诊断。
要求：
1. 明确指出哪一条用例失败；
2. 明确指出失败在第几步、该步骤做了什么；
3. 用测试视角解释失败现象、可能原因；
4. 给出可执行的下一步排查建议；
5. 只输出合法 JSON，字段保持为：summary、passed_count、failed_count、failed_cases、overall_suggestions。

规则初步诊断：
{json.dumps(rule_payload, ensure_ascii=False, indent=2)}

原始日志：
{(run.log or "")[:16000]}
"""
    try:
        payload = call_local_model_json(config, prompt)
        if isinstance(payload, dict) and payload.get("failed_cases") is not None:
            return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception as exc:
        rule_payload["model_warning"] = f"本地模型诊断失败，已使用规则诊断：{exc}"
        return json.dumps(rule_payload, ensure_ascii=False, indent=2)
    rule_payload["model_warning"] = "本地模型未返回可识别的诊断结构，已使用规则诊断。"
    return json.dumps(rule_payload, ensure_ascii=False, indent=2)
