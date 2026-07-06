"""用户管理路由"""
import threading
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.cache import invalidate
from ..core.utils import serialize, serialize_many, get_or_404, schema_data, ensure_unique_username
from ..database import get_db
from ..models import User
from ..schemas import UserCreate, UserUpdate
from ..security import get_current_user, hash_password, require_admin

router = APIRouter(tags=["users"])

# 保护「至少保留一个 admin」的序列化锁（SQLite 不支持 SELECT FOR UPDATE）
_admin_lock = threading.Lock()


@router.get("/api/users")
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[Dict[str, Any]]:
    return serialize_many(db.query(User).order_by(User.id.desc()).all())


@router.post("/api/users")
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, Any]:
    data = schema_data(payload)
    ensure_unique_username(db, data["username"])
    user = User(
        username=data["username"],
        password=hash_password(data["password"]),
        role=data["role"],
        create_time=datetime.now(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return serialize(user)


@router.put("/api/users/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    user = get_or_404(db, User, user_id)
    data = schema_data(payload, exclude_unset=True)
    old_username = user.username
    if "username" in data:
        ensure_unique_username(db, data["username"], user_id)
        user.username = data["username"]
    if "password" in data and data["password"]:
        if not data["password"].strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码不能为纯空格")
        user.password = hash_password(data["password"])
    if "role" in data and data["role"]:
        with _admin_lock:
            if user.role == "admin" and data["role"] != "admin" and db.query(User).filter(User.role == "admin", User.id != user.id).count() < 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少保留一个 admin 账号")
            user.role = data["role"]
    db.commit()
    db.refresh(user)
    invalidate(f"me:{old_username}")
    invalidate(f"me:{user.username}")
    return serialize(user)


@router.delete("/api/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    user = get_or_404(db, User, user_id)
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前登录账号")
    with _admin_lock:
        if user.role == "admin" and db.query(User).filter(User.role == "admin", User.id != user.id).count() < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少保留一个 admin 账号")
        db.delete(user)
    db.commit()
    invalidate(f"me:{user.username}")
    return {"message": "deleted"}
