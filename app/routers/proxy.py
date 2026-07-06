"""代理请求路由"""
import logging
import time
from typing import Any, Dict

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..core.utils import guarded_proxy_request
from ..database import get_db
from ..models import User
from ..schemas import QuickRunRequest
from ..security import get_current_user

router = APIRouter(tags=["proxy"])
logger = logging.getLogger(__name__)


@router.post("/api/proxy/request")
def proxy_http_request(
    payload: QuickRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    method = payload.method.upper().strip()
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL不能为空")
    headers = dict(payload.headers or {})
    body = payload.body or ""
    client_ip = request.client.host if request.client else "unknown"
    logger.info("代理请求 [%s] %s %s (来源: %s)", method, url, current_user.username, client_ip)
    start = time.time()
    try:
        resp = guarded_proxy_request(method, url, headers, body, timeout=30)
    except HTTPException:
        raise
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="请求超时（30s）")
    except requests.exceptions.ConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"连接失败: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    elapsed = int((time.time() - start) * 1000)
    body_text = resp.text
    preview = body_text[:5000]
    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "body_preview": preview,
        "body_truncated": len(body_text) > 5000,
        "elapsed_ms": elapsed,
    }
