"""接口抓取路由:真跑网站抓接口 + AI 分析 + 入库。

流程:
1. POST /crawl  → 启动浏览器抓前后台接口(后台异步执行,返回 task_id)
2. GET /task/{id} → 查询抓取进度和结果
3. POST /analyze → 对抓到的接口做 AI 分析 + 入库用例库
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import get_current_user, require_admin
from ..services.api_analyzer import analyze_and_import
from ..services.api_extractor import extract_all
from ..services.site_crawler import crawl_site

router = APIRouter(tags=["api-harvester"])

# 内存任务存储(进程级,重启丢失)
_TASKS: Dict[str, Dict[str, Any]] = {}


@router.get("/api/api-harvester/extract")
def extract(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """静态扫描 data_scripts,返回接口清单预览(不入库)。保留兼容旧功能。"""
    return extract_all()


@router.post("/api/api-harvester/crawl")
async def crawl(
    payload: Dict[str, Any] = Body(default={}),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """启动浏览器抓取前后台接口。需 admin。

    Body:
    - front_url, front_account, front_password
    - back_url, back_account, back_password
    """
    required = ["front_url", "front_account", "front_password", "back_url", "back_account", "back_password"]
    for key in required:
        if not payload.get(key):
            raise HTTPException(400, f"缺少参数: {key}")

    task_id = uuid.uuid4().hex
    _TASKS[task_id] = {
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "result": None,
        "error": None,
    }

    async def _run():
        try:
            result = await crawl_site(
                front_url=payload["front_url"],
                front_account=payload["front_account"],
                front_password=payload["front_password"],
                back_url=payload["back_url"],
                back_account=payload["back_account"],
                back_password=payload["back_password"],
            )
            _TASKS[task_id].update(status="done", result=result)
        except Exception as exc:
            _TASKS[task_id].update(status="failed", error=str(exc))

    asyncio.create_task(_run())
    return {"task_id": task_id, "status": "running"}


@router.get("/api/api-harvester/task/{task_id}")
def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """查询抓取任务状态。"""
    task = _TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


@router.post("/api/api-harvester/analyze")
def analyze(
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """对抓取到的接口做 AI 分析并导入用例库。需 admin。

    Body:
    - task_id: 抓取任务 ID(从中取 endpoints)
    - endpoints: 直接传接口清单(与 task_id 二选一)
    - project_id, env_id: 落库用(可选)
    """
    endpoints = payload.get("endpoints")
    task_id = payload.get("task_id")
    if not endpoints and task_id:
        task = _TASKS.get(task_id) or {}
        result = task.get("result") or {}
        endpoints = result.get("endpoints")
    if not endpoints:
        raise HTTPException(400, "未提供 endpoints 或 task_id")

    return analyze_and_import(
        db,
        endpoints,
        project_id=payload.get("project_id"),
        env_id=payload.get("env_id"),
    )
