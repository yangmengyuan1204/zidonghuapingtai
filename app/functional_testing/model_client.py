from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

import requests

from ..models import AiConfig


logger = logging.getLogger(__name__)

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


def _extract_supported_model_names(text: str) -> list[str]:
    raw = str(text or "")
    match = re.search(
        r"supported API model names are\s+([^\"。；;]+?)(?:,\s*but\b|\.|$)",
        raw,
        flags=re.I,
    )
    if match:
        candidates = re.findall(r"[A-Za-z0-9_.:-]+", match.group(1))
    else:
        candidates = re.findall(r"\bdeepseek-[A-Za-z0-9_.:-]+\b", raw)
    ignored = {"or", "and", "are", "is"}
    names: list[str] = []
    for item in candidates:
        name = item.strip(" ,.;")
        if not name or name.lower() in ignored or name in names:
            continue
        names.append(name)
    return names


def _unsupported_model_name(text: str) -> str:
    match = re.search(r"but you passed\s+([A-Za-z0-9_.:-]+)", str(text or ""), flags=re.I)
    return match.group(1) if match else ""


def _retry_model_from_error(current_model: str, response_text: str) -> str:
    supported = [item for item in _extract_supported_model_names(response_text) if item != current_model]
    if not supported:
        return ""
    flash = next((item for item in supported if "flash" in item.lower()), "")
    return flash or supported[0]


def _openai_chat_payload(model: str, prompt: str) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是资深软件测试工程师，只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }


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

    supported_models = _extract_supported_model_names(response_text)
    if status_code == 400 and supported_models:
        passed_model = _unsupported_model_name(response_text)
        prefix = f"当前配置为 {passed_model}，" if passed_model else ""
        return f"模型名称不被当前接口支持，{prefix}当前接口支持：{', '.join(supported_models)}。请在 AI配置 中改成其中一个模型。"
    if status_code == 400 and "image" in response_text.lower():
        return "当前模型接口不支持图片输入；系统会先提取截图 OCR 文本，再交给文本模型生成测试点。"
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

    endpoint = base_url
    if not endpoint.endswith("/chat/completions"):
        endpoint = endpoint.rstrip("/")
        if not endpoint.endswith("/v1"):
            endpoint += "/v1"
        endpoint += "/chat/completions"
    response = requests.post(
        endpoint,
        headers=headers,
        json=_openai_chat_payload(config.model, prompt),
        timeout=timeout,
    )
    if not response.ok and response.status_code == 400:
        response_text = ""
        try:
            response_text = response.text
        except Exception:
            response_text = ""
        retry_model = _retry_model_from_error(config.model or "", response_text)
        if retry_model:
            logger.warning("AI 模型 %s 不被当前接口支持，自动重试 %s", config.model, retry_model)
            retry_response = requests.post(
                endpoint,
                headers=headers,
                json=_openai_chat_payload(retry_model, prompt),
                timeout=timeout,
            )
            response = retry_response
    _raise_for_model_response(response)
    payload = response.json()
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    return _json_from_text(content)


def call_visual_model_json(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("截图识别已改为 OCR 文本链路，不再调用视觉图片输入")
