from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, Iterable
from urllib.parse import urlparse
from uuid import uuid4


logger = logging.getLogger(__name__)

import requests

from ..executors import SCREENSHOT_DIR, ensure_report_dirs, launch_chromium_browser
from ..models import AiConfig, FunctionalCase, FunctionalRequirementNote, FunctionalRun, FunctionalScreenshot, FunctionalTask, PageSnapshot
from .materials import (
    AXURE_DIR,
    FUNCTIONAL_DIR,
    FUNCTIONAL_SCREENSHOT_DIR,
    compact_requirement,
    ensure_functional_dirs,
    extract_axure_pages,
    read_axure_text,
    selected_axure_text,
    store_axure_file,
    store_functional_screenshot_file,
)
from .ocr import _compact_ocr_error, extract_screenshot_material
from .model_client import (
    _extract_supported_model_names,
    _format_model_http_error,
    _is_deepseek_api_base_url,
    _json_from_text,
    _openai_chat_payload,
    _raise_for_model_response,
    _retry_model_from_error,
    _unsupported_model_name,
    call_local_model_json,
    call_visual_model_json,
)
BASE_DIR = Path(__file__).resolve().parent.parent

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
    "extract_text",
    "extract_value",
    "resume_order_flow",
}


@dataclass
class GeneratedResult:
    source: str
    warning: str
    items: list[Dict[str, Any]]
    questions_for_product: list[str] | None = None


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


def fallback_screenshot_analysis(task: FunctionalTask, screenshot: FunctionalScreenshot, reason: str) -> str:
    material = extract_screenshot_material(screenshot.image_path)
    text_lines = [line.strip() for line in material.get("ocr_text", "").splitlines() if line.strip()]
    visible_controls = text_lines[:30]
    payload = {
        "analysis_source": "ocr_fallback",
        "model_error": reason,
        "page_summary": "已基于截图 OCR 提取可见文字；模型不可用或未返回合法 JSON，需人工确认关键规则。",
        "visible_controls": visible_controls,
        "inferred_rules": [
            "OCR 只能证明截图中出现过这些文字，不能单独证明字段类型、必填规则或提交成功规则。",
            "低置信度文字需要人工确认后再生成高可信自动化用例。",
        ],
        "questions_for_product": [
            "请确认 OCR 低置信度文字是否正确。",
            "请确认截图中的关键字段哪些是必填、唯一或格式校验字段。",
            "请确认提交成功后的页面、提示文案或状态变化。",
        ],
        "suggested_test_points": [
            "验证页面关键控件和文案展示。",
            "验证主流程提交后的成功提示或状态变化。",
            "验证必填、格式错误、重复数据等异常提示。",
        ],
        "ocr_material": material,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
















class FunctionalScanError(RuntimeError):
    def __init__(self, message: str, trace: list[str] | None = None):
        super().__init__(message)
        self.trace = trace or []








































# ─── 分段扫描工具函数 ──────────────────────────────────

import threading
from contextlib import contextmanager










_DOM_EXTRACT_JS = """
() => {
  try {
    const textOf = (el) => {
      try {
        return (el.innerText || el.value || el.getAttribute("aria-label") || el.getAttribute("placeholder") || "").trim().replace(/\\s+/g, " ").slice(0, 80);
      } catch(e) { return ""; }
    };
    const selectors = "a,button,input,textarea,select,[role=button],[role=link],[contenteditable=true]";
    const elements = Array.from(document.querySelectorAll(selectors)).slice(0, 150).map((el, idx) => {
      try {
        const tag = el.tagName.toLowerCase();
        const id = el.id || "";
        const name = el.getAttribute("name") || "";
        const type = el.getAttribute("type") || "";
        const placeholder = el.getAttribute("placeholder") || "";
        const ariaLabel = el.getAttribute("aria-label") || "";
        const dataTestid = el.getAttribute("data-testid") || el.getAttribute("data-test") || el.getAttribute("data-cy") || "";
        const text = textOf(el);
        // 生成推荐定位器（简化版）
        let locator = tag;
        if (dataTestid) locator = `[data-testid="${dataTestid.replace(/"/g,'\\\\"')}"]`;
        else if (id) locator = `#${CSS.escape(id)}`;
        else if (name) locator = `${tag}[name="${name.replace(/"/g,'\\\\"')}"]`;
        else if (placeholder) locator = `${tag}[placeholder="${placeholder.replace(/"/g,'\\\\"')}"]`;
        else if (ariaLabel) locator = `${tag}[aria-label="${ariaLabel.replace(/"/g,'\\\\"')}"]`;
        else if (text && ["button","a","span","label"].includes(tag)) locator = `text=${text}`;
        return { tag, id, name, type, placeholder, role: el.getAttribute("role")||"", text, locator, data_testid: dataTestid };
      } catch(e) { return null; }
    }).filter(Boolean);
    const headings = Array.from(document.querySelectorAll("h1,h2,h3,h4,label")).slice(0, 50).map(el => {
      try { return (el.innerText||"").trim().replace(/\\s+/g," ").slice(0,80); } catch(e) { return ""; }
    }).filter(Boolean);
    return { title: document.title || "", url: location.href || "", headings, elements };
  } catch(e) {
    return { title: "", url: "", headings: [], elements: [], error: e.message };
  }
}
"""
