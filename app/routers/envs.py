"""环境管理路由"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.cache import invalidate_prefix, get as cache_get, set as cache_set
from ..core.utils import (
    serialize, serialize_many, get_or_404, schema_data,
    normalize_env_payload, normalize_json_fields, ensure_project_exists,
)
from ..database import get_db
from ..models import ApiCase, Env, User
from ..schemas import EnvCreate, EnvUpdate
from ..security import get_current_user, require_admin

router = APIRouter(tags=["envs"])


@router.get("/api/envs")
def list_envs(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    cache_key = f"envs:{project_id or ''}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    query = db.query(Env)
    if project_id is not None:
        query = query.filter(Env.project_id == project_id)
    result = serialize_many(query.order_by(Env.id.asc()).all())
    cache_set(cache_key, result, ttl=30)
    return result


@router.post("/api/envs")
def create_env(payload: EnvCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, Any]:
    data = normalize_env_payload(normalize_json_fields(schema_data(payload)), require_required_fields=True)
    ensure_project_exists(db, data["project_id"])
    env = Env(**data)
    db.add(env)
    db.commit()
    db.refresh(env)
    invalidate_prefix("envs:")
    return serialize(env)


@router.put("/api/envs/{env_id}")
def update_env(
    env_id: int,
    payload: EnvUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    env = get_or_404(db, Env, env_id)
    data = normalize_env_payload(normalize_json_fields(schema_data(payload, exclude_unset=True)))
    if "project_id" in data:
        if data["project_id"] != env.project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不允许修改环境所属项目，请删除后重建")
        ensure_project_exists(db, data["project_id"])
    for field, value in data.items():
        setattr(env, field, value)
    db.commit()
    db.refresh(env)
    invalidate_prefix("envs:")
    return serialize(env)


@router.delete("/api/envs/{env_id}")
def delete_env(env_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, str]:
    env = get_or_404(db, Env, env_id)
    linked_api_count = db.query(ApiCase).filter(ApiCase.env_id == env.id).count()
    if linked_api_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"环境已被 {linked_api_count} 个接口用例引用，不能删除",
        )
    db.delete(env)
    db.commit()
    invalidate_prefix("envs:")
    return {"message": "deleted"}
