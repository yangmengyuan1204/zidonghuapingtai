"""AI 用例生成服务。

调 DeepSeek 分析接口清单,生成单接口用例(ApiCase)和多接口流程(RecordedFlow),
落库到数据库。生成的用例 case_name 加 [AI生成] 前缀,状态默认 disabled。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..core.utils import latest_ai_config
from ..functional_testing.model_client import call_local_model_json
from ..models import ApiCase, Env, Project, RecordedFlow, RecordedFlowStep
from .api_extractor import extract_all

logger = logging.getLogger(__name__)

_GENERATED_PREFIX = "[AI生成]"


def generate_cases(
    db: Session,
    *,
    project_id: int | None = None,
    env_id: int | None = None,
    max_api_cases: int = 50,
) -> Dict[str, Any]:
    """提取接口清单 → AI 生成用例 → 落库。

    Args:
        db: 数据库会话
        project_id: 落库用项目 ID(若为 None,自动取第一个项目)
        env_id: 落库用环境 ID(若为 None,自动取该项目第一个环境)
        max_api_cases: 最多生成的单接口用例数

    Returns:
        {"api_cases": [用例ID], "flows": [流程ID], "error": "...(若有)"}
    """
    extraction = extract_all()
    project, env = _resolve_project_env(db, project_id, env_id)

    ai_result = _call_ai_generate(db, extraction, max_api_cases)
    if ai_result is None:
        return {
            "api_cases": [],
            "flows": [],
            "error": "AI 未返回有效结果,请检查 AI 配置(base_url/model/api_key)或余额",
            "extraction_stats": extraction.get("stats"),
        }

    created_case_ids: List[int] = []
    for case_data in ai_result.get("api_cases") or []:
        case_id = _create_api_case(db, project.id, env.id, case_data)
        if case_id:
            created_case_ids.append(case_id)

    created_flow_ids: List[int] = []
    for flow_data in ai_result.get("flows") or []:
        flow_id = _create_flow(db, flow_data)
        if flow_id:
            created_flow_ids.append(flow_id)

    return {
        "api_cases": created_case_ids,
        "flows": created_flow_ids,
        "api_case_count": len(created_case_ids),
        "flow_count": len(created_flow_ids),
        "extraction_stats": extraction.get("stats"),
    }


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


def _call_ai_generate(
    db: Session, extraction: Dict[str, Any], max_api_cases: int
) -> Dict[str, Any] | None:
    """调 DeepSeek 生成用例定义。"""
    config = latest_ai_config(db)
    if not config or not config.base_url or not config.model:
        return None

    unique_endpoints = extraction.get("unique_endpoints") or []
    scripts = extraction.get("scripts") or []
    endpoints_brief = [
        {"method": ep.get("method", "POST"), "path": ep.get("path", ""), "used_in": ep.get("used_in", [])}
        for ep in unique_endpoints
    ]
    scripts_brief = [
        {"script": s.get("script_key", ""), "name": s.get("script_name", ""), "endpoints": len(s.get("endpoints") or [])}
        for s in scripts
    ]

    prompt = f"""分析以下接口清单,为每个接口生成一条单接口测试用例,并设计 3-5 条多接口业务流程。

## 接口清单(共 {len(endpoints_brief)} 个接口)
{json.dumps(endpoints_brief[:max_api_cases], ensure_ascii=False, indent=2)}

## 业务脚本(共 {len(scripts_brief)} 个)
{json.dumps(scripts_brief, ensure_ascii=False, indent=2)}

## 输出要求(严格 JSON,不要 markdown)
{{
  "api_cases": [
    {{
      "case_name": "接口用途简述",
      "method": "POST",
      "url": "/接口路径",
      "headers": {{"Content-Type": "application/x-www-form-urlencoded"}},
      "params": {{}},
      "body": {{"key": "{{变量名}}"}},
      "assert_rule": {{"status_code": 200, "contains": ["success"], "extract": {{"id": "json.data.id"}}}}
    }}
  ],
  "flows": [
    {{
      "name": "流程名称",
      "description": "流程描述",
      "steps": [
        {{"method": "POST", "path": "/接口路径", "body_template": "{{}}", "purpose": "步骤说明"}}
      ]
    }}
  ]
}}

## 断言规则
- status_code:期望 HTTP 状态码
- contains:响应体需包含的字符串列表
- extract:从响应提取变量,key 为变量名,value 为 json 路径(如 json.data.id)

## 动态字段(用 {{{{变量名}}}} 占位)
order_sn, sku, sku_list, amount, price, total, token, coupon_id, warehouse_city, inquiry_order_sn, large_order_sn, qt_code

## 注意
- api_cases 每个接口 1 条,最多 {max_api_cases} 条
- flows 设计 3-5 条核心业务流程(购物车下单支付、出入金调整、采购上架、OEM 询价等)
- body 中动态值用 {{{{变量名}}}} 占位
- url 以 / 开头(相对路径,执行时拼接 env.base_url)
"""
    try:
        result = call_local_model_json(config, prompt, timeout=120)
        return result if isinstance(result, dict) else None
    except Exception as exc:
        logger.error("AI 生成用例失败: %s", exc)
        return None


def _create_api_case(
    db: Session, project_id: int, env_id: int, case_data: Dict[str, Any]
) -> int | None:
    """创建单条 ApiCase。"""
    case_name = str(case_data.get("case_name") or "").strip()
    if not case_name:
        return None
    method = str(case_data.get("method") or "POST").strip().upper()
    url = str(case_data.get("url") or "").strip()
    if not url:
        return None
    try:
        case = ApiCase(
            project_id=project_id,
            env_id=env_id,
            case_name=f"{_GENERATED_PREFIX}{case_name}",
            method=method,
            url=url,
            headers=_to_json_text(case_data.get("headers")),
            params=_to_json_text(case_data.get("params")),
            body=_to_json_text(case_data.get("body")),
            assert_rule=_to_json_text(case_data.get("assert_rule")) or '{"status_code": 200}',
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


def _create_flow(db: Session, flow_data: Dict[str, Any]) -> int | None:
    """创建 RecordedFlow 及其步骤。"""
    name = str(flow_data.get("name") or "").strip()
    if not name:
        return None
    steps_data = flow_data.get("steps") or []
    if not steps_data:
        return None
    try:
        flow = RecordedFlow(
            name=f"{_GENERATED_PREFIX}{name}",
            description=str(flow_data.get("description") or ""),
        )
        db.add(flow)
        db.flush()
        for idx, step in enumerate(steps_data, start=1):
            db.add(RecordedFlowStep(
                flow_id=flow.id,
                step_index=idx,
                method=str(step.get("method") or "POST").upper(),
                path=str(step.get("path") or ""),
                body_template=str(step.get("body_template") or ""),
            ))
        db.commit()
        return flow.id
    except Exception as exc:
        logger.error("创建 RecordedFlow 失败: %s", exc)
        db.rollback()
        return None


def _to_json_text(value: Any) -> str:
    """dict/list 转 JSON 字符串,字符串原样返回。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (ValueError, TypeError):
        return ""


__all__ = ["generate_cases"]
