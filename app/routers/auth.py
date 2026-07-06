"""认证路由：登录、当前用户信息"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..core.utils import serialize, _check_login_rate_limit, _record_login_attempt
from ..database import get_db
from ..models import User
from ..schemas import LoginRequest
from ..security import create_access_token, get_current_user, verify_password
from ..core.cache import get as cache_get, set as cache_set, invalidate

router = APIRouter(tags=["auth"])


@router.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(client_ip, payload.username)
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password):
        _record_login_attempt(client_ip, payload.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_access_token(user.username)
    return {"access_token": token, "token_type": "bearer", "user": serialize(user)}


@router.get("/api/auth/me")
def me(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    cache_key = f"me:{current_user.username}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    result = serialize(current_user)
    cache_set(cache_key, result, ttl=120)
    return result
