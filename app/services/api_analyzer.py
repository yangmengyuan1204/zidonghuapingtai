"""接口 AI 分析服务。

对抓取到的接口清单,调 DeepSeek 分析:
1. 每个接口的用途(查询/创建/更新/删除/登录/导出...)
2. 哪些接口可以填到造数脚本流程里(写接口优先)
3. 给出建议的造数脚本流程清单

同时把接口补充到 ApiCase 表(状态默认 disabled)。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..core.utils import latest_ai_config
from ..functional_testing.model_client import call_local_model_json
from ..models import ApiCase, Env, Project

logger = logging.getLogger(__name__)

_GENERATED_PREFIX = "[抓取]"


def analyze_and_import(
    db: Session,
    endpoints: List[Dict[str, Any]],
    *,
    project_id: int | None = None,
    env_id: int | None = None,
) -> Dict[str, Any]:
    """分析接口清单并导入用例库。

    Returns:
    {
      "analysis": {"endpoints":[{"path","purpose","category","can_use_for_script"}], "script_suggestions":[...]},
      "imported_case_ids": [int],
      "error": "...(若有)"
    }
    """
    if not endpoints:
        return {"analysis": None, "imported_case_ids": [], "error": "接口清单为空"}

    # 1. AI 分析
    analysis = _call_ai_analyze(db, endpoints)
    if analysis is None:
        return {
            "analysis": None,
            "imported_case_ids": [],
            "error": "AI 分析失败,请检查 AI 配置或余额",
        }

    # 2. 导入 ApiCase
    project, env = _resolve_project_env(db, project_id, env_id)
    imported_case_ids: List[int] = []
    for ep in endpoints:
        case_id = _create_api_case(db, project.id, env.id, ep, analysis)
        if case_id:
            imported_case_ids.append(case_id)

    return {
        "analysis": analysis,
        "imported_case_ids": imported_case_ids,
        "imported_count": len(imported_case_ids),
    }


def _call_ai_analyze(db: Session, endpoints: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """调 DeepSeek 分析接口清单。"""
    config = latest_ai_config(db)
    if not config or not config.base_url or not config.model:
        return None

    # 精简接口清单给 AI
    brief = [
        {
            "method": ep.get("method", ""),
            "path": ep.get("path", ""),
            "source": ep.get("source", ""),
            "request_body": (ep.get("request_body") or "")[:300],
            "response_status": ep.get("response_status"),
            "response_sample": (ep.get("response_sample") or "")[:300],
        }
        for ep in endpoints
    ]

    prompt = f"""分析以下从网站抓取的接口清单,输出每个接口的用途和造数脚本建议。

## 接口清单(共 {len(brief)} 个)
{json.dumps(brief, ensure_ascii=False, indent=2)}

## 输出要求(严格 JSON,不要 markdown)
{{
  "endpoints": [
    {{
      "path": "/接口路径",
      "method": "POST",
      "purpose": "接口用途简述(如:创建出入金申请)",
      "category": "分类(login/query/create/update/delete/export/other)",
      "can_use_for_script": true/false,
      "script_role": "若可用于造数脚本,说明在流程中的角色(如:第1步登录拿token/第2步创建订单/第3步查询订单状态)"
    }}
  ],
  "script_suggestions": [
    {{
      "name": "建议的造数脚本名称(如:出入金申请全流程)",
      "description": "脚本用途描述",
      "steps": [
        {{"path": "/接口路径", "method": "POST", "purpose": "步骤说明"}}
      ],
      "key_outputs": "脚本产出的关键数据(如:order_sn, payment_id)"
    }}
  ]
}}

## 分析要点
- category 优先级:能从 path 看出用途就用 path 判断(login=登录、list/query=查询、create/add/save=创建、update/edit=更新、delete/remove=删除、export/download=导出)
- can_use_for_script:true 的条件是 create/update 类接口(能造数据),纯查询接口一般 false(除非是流程中必要的取值步骤)
- script_suggestions:把可造数的接口按业务流程串起来,每个脚本 3-8 步,覆盖订单、支付、出入金、采购、OEM 等核心业务
- response_sample 含错误信息的,category 标为 other 并在 purpose 注明
"""
    try:
        result = call_local_model_json(config, prompt, timeout=120)
        return result if isinstance(result, dict) else None
    except Exception as exc:
        logger.error("AI 分析接口失败: %s", exc)
        return None


def _resolve_project_env(
    db: Session, project_id: int | None, env_id: int | None
) -> tuple[Project, Env]:
    """解析项目和环境,未指定则取第一个。"""
    project = db.get(Project, project_id) if project_id else None
    if not project:
        project = db.query(Project).order_by(Project.id.asc()).first()
    if not project:
        raise ValueError("数据库中无项目,请先创建项目")

    env = db.get(Env, env_id) if env_id else None
    if not env or env.project_id != project.id:
        env = db.query(Env).filter(Env.project_id == project.id).order_by(Env.id.asc()).first()
    if not env:
        raise ValueError(f"项目 {project.name} 无环境,请先创建环境")

    return project, env


def _create_api_case(
    db: Session, project_id: int, env_id: int, ep: Dict[str, Any], analysis: Dict[str, Any]
) -> int | None:
    """把抓取的接口创建为 ApiCase。"""
    path = str(ep.get("path") or "").strip()
    method = str(ep.get("method") or "GET").strip().upper()
    if not path:
        return None
    # 从 AI 分析结果找用途作为 case_name
    case_name = path
    for item in (analysis.get("endpoints") or []):
        if item.get("path") == path and item.get("method", "").upper() == method:
            case_name = str(item.get("purpose") or path)
            break
    try:
        case = ApiCase(
            project_id=project_id,
            env_id=env_id,
            case_name=f"{_GENERATED_PREFIX}{case_name}",
            method=method,
            url=path,
            headers=_to_json_text(_filter_headers(ep.get("headers") or {})),
            params=_to_json_text(ep.get("query") or {}),
            body=_to_json_text(_parse_body(ep.get("request_body"))),
            assert_rule='{"status_code": 200}',
            status="disabled",
            create_time=datetime.now(),
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        return case.id
    except Exception as exc:
        logger.error("创建 ApiCase 失败: %s", exc)
        db.rollback()
        return None


def _filter_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """过滤掉动态 token,保留结构。"""
    result = {}
    for k, v in headers.items():
        if k.lower() in ("authorization", "admintoken", "usertoken", "token"):
            result[k] = "{{token}}"  # 占位,执行时用环境变量
        else:
            result[k] = v
    return result


def _parse_body(body: Any) -> Any:
    """尝试解析请求体为 dict,失败原样返回。"""
    if not body:
        return {}
    if isinstance(body, dict):
        return body
    if isinstance(body, str):
        try:
            return json.loads(body)
        except (ValueError, TypeError):
            return body
    return body


def _to_json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (ValueError, TypeError):
        return ""


__all__ = ["analyze_and_import"]
