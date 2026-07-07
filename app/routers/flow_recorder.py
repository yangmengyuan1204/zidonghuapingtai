"""录制流程路由：上传 HAR / 保存流程 / 查看列表 / 详情 / 删除 / 执行回放。"""

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import RecordedFlow, RecordedFlowStep
from ..services import har_recorder
from ..services.flow_player import play_flow

router = APIRouter(prefix="/api/flow-recorder", tags=["flow-recorder"])


@router.post("/upload")
async def upload_har(file: UploadFile = File(...)) -> Dict[str, Any]:
    """上传 HAR 文件，解析后返回步骤预览、流程定义与动态字段 schema。"""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件不能为空")
    try:
        har_content = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"HAR 解析失败: {exc}") from exc
    try:
        parsed_steps = har_recorder.parse_har(har_content)
        dynamic_schema = har_recorder.identify_dynamic_fields(parsed_steps)
        flow_definition = har_recorder.build_flow_definition(parsed_steps, dynamic_schema)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"HAR 解析失败: {exc}") from exc

    preview = []
    for idx, step in enumerate(parsed_steps, start=1):
        body_raw = step.get("body") or ""
        preview.append({
            "step_index": idx,
            "method": step.get("method", "GET"),
            "path": step.get("path", ""),
            "response_status": step.get("response_status", 0),
            "body_preview": body_raw[:200],
        })
    return {
        "preview": preview,
        "flow_definition": flow_definition,
        "fields": dynamic_schema.get("fields") or [],
    }


@router.post("/save")
def save_flow(payload: Dict[str, Any], db: Session = Depends(get_db)) -> Dict[str, Any]:
    """保存录制流程及步骤。"""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="流程名称不能为空")
    description = payload.get("description") or ""
    flow_definition = payload.get("flow_definition") or {}
    steps_data = flow_definition.get("steps") or []

    flow = RecordedFlow(name=name, description=description)
    db.add(flow)
    db.flush()
    for step in steps_data:
        db.add(RecordedFlowStep(
            flow_id=flow.id,
            step_index=step.get("step_index", 0),
            method=step.get("method", "GET"),
            path=step.get("path", ""),
            headers_json=step.get("headers_json"),
            body_template=step.get("body_template"),
            field_schema_json=step.get("field_schema_json"),
            response_extraction_json=step.get("response_extraction_json"),
        ))
    db.commit()
    return {"flow_id": flow.id, "name": flow.name}


@router.get("/list")
def list_flows(db: Session = Depends(get_db)) -> list[Dict[str, Any]]:
    """返回所有录制流程列表。"""
    flows = db.query(RecordedFlow).order_by(RecordedFlow.id.desc()).all()
    return [
        {
            "id": flow.id,
            "name": flow.name,
            "description": flow.description or "",
            "step_count": len(flow.steps or []),
            "created_at": flow.created_at.strftime("%Y-%m-%d %H:%M:%S") if flow.created_at else "",
        }
        for flow in flows
    ]


@router.get("/{flow_id}")
def get_flow(flow_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """返回流程详情，含步骤与合并后的字段 schema。"""
    flow = db.query(RecordedFlow).filter(RecordedFlow.id == flow_id).first()
    if not flow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="流程不存在")
    steps = sorted(flow.steps or [], key=lambda s: s.step_index)
    merged_fields = []
    seen = set()
    for step in steps:
        try:
            schema = json.loads(step.field_schema_json or "[]")
        except (ValueError, TypeError):
            schema = []
        for field in schema if isinstance(schema, list) else []:
            name = field.get("name") if isinstance(field, dict) else None
            if name and name not in seen:
                seen.add(name)
                merged_fields.append(field)
    return {
        "id": flow.id,
        "name": flow.name,
        "description": flow.description or "",
        "steps": [
            {
                "id": step.id,
                "step_index": step.step_index,
                "method": step.method,
                "path": step.path,
                "full_url": step.full_url or "",
                "headers_json": step.headers_json,
                "body_template": step.body_template,
                "field_schema_json": step.field_schema_json,
                "response_extraction_json": step.response_extraction_json,
            }
            for step in steps
        ],
        "fields": merged_fields,
    }


@router.delete("/{flow_id}")
def delete_flow(flow_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """删除流程及步骤（级联）。"""
    flow = db.query(RecordedFlow).filter(RecordedFlow.id == flow_id).first()
    if not flow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="流程不存在")
    db.delete(flow)
    db.commit()
    return {"success": True, "flow_id": flow_id}


@router.post("/{flow_id}/execute")
def execute_flow(flow_id: int, payload: Dict[str, Any], db: Session = Depends(get_db)) -> Dict[str, Any]:
    """按步骤回放流程，失败即停止或跳过。"""
    variables = payload.get("variables") or {}
    if not isinstance(variables, dict):
        variables = {}
    skip_on_failure = bool(payload.get("skip_on_failure") or False)
    return play_flow(flow_id, variables, db, skip_on_failure=skip_on_failure)
