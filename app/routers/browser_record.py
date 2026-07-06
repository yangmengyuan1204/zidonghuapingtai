"""实时浏览器录制路由：启动会话 / 查询事件 / 跳转 / 关闭 / 保存为流程。"""

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import RecordedFlow, RecordedFlowStep
from ..services import browser_session, har_recorder

router = APIRouter(prefix="/api/browser-record", tags=["browser-record"])


@router.post("/sessions")
async def create_session(payload: Dict[str, Any]) -> Dict[str, Any]:
    """启动可见浏览器并打开起始页，返回 session_id。"""
    start_url = (payload.get("start_url") or "").strip()
    if not start_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_url 不能为空")
    try:
        session_id = await browser_session.start_session(start_url)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"浏览器启动失败: {exc}") from exc
    return {"session_id": session_id}


@router.get("/sessions/{session_id}/events")
def list_events(session_id: str) -> Dict[str, Any]:
    """返回当前会话已捕获的接口事件列表。"""
    items = browser_session.get_events(session_id)
    return {"count": len(items), "items": items}


@router.post("/sessions/{session_id}/navigate")
async def navigate(session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """会话内跳转到新 URL。"""
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="url 不能为空")
    try:
        await browser_session.navigate_session(session_id, url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"跳转失败: {exc}") from exc
    return {"ok": True}


@router.delete("/sessions/{session_id}")
async def close(session_id: str) -> Dict[str, Any]:
    """关闭会话并释放浏览器资源。"""
    await browser_session.close_session(session_id)
    return {"ok": True}


@router.post("/sessions/{session_id}/save")
async def save_session(
    session_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """把会话事件转成 HAR 兼容格式，复用 har_recorder 链路沉淀为 RecordedFlow。"""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="流程名称不能为空")
    description = payload.get("description") or ""
    events = browser_session.get_events(session_id)
    if not events:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="会话无捕获事件")
    har_content = _events_to_har(events)
    try:
        parsed_steps = har_recorder.parse_har(har_content)
        dynamic_schema = har_recorder.identify_dynamic_fields(parsed_steps)
        flow_definition = har_recorder.build_flow_definition(parsed_steps, dynamic_schema)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"流程构建失败: {exc}") from exc
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
    # 保存后关闭会话，释放浏览器
    await browser_session.close_session(session_id)
    return {"flow_id": flow.id, "name": flow.name}


def _events_to_har(events: list[dict]) -> dict:
    """把会话事件列表转成 har_recorder.parse_har 兼容的 HAR 结构。"""
    entries = []
    for ev in events:
        query_pairs = [{"name": k, "value": v} for k, v in (ev.get("query") or {}).items()]
        headers_pairs = [{"name": k, "value": v} for k, v in (ev.get("headers") or {}).items()]
        method = (ev.get("method") or "GET").upper()
        request: dict = {
            "method": ev.get("method", "GET"),
            "url": ev.get("url", ""),
            "queryString": query_pairs,
            "headers": headers_pairs,
        }
        if method == "POST" and ev.get("body"):
            request["postData"] = {"text": ev["body"]}
        content: dict = {}
        body = ev.get("response_body")
        if body is not None:
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False)
            content["text"] = body
        entries.append({
            "startedDateTime": ev.get("started_at", ""),
            "request": request,
            "response": {
                "status": ev.get("response_status") or 0,
                "content": content,
            },
        })
    return {"log": {"entries": entries}}
