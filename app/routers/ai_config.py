"""AI 配置路由"""
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.utils import schema_data, latest_ai_config, serialize_ai_config
from ..database import get_db
from ..models import AiConfig, User
from ..schemas import AiConfigUpdate
from ..security import get_current_user, require_admin

router = APIRouter(tags=["ai-config"])


@router.get("/api/ai-config")
def get_ai_config(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return serialize_ai_config(latest_ai_config(db))


@router.put("/api/ai-config")
def update_ai_config(
    payload: AiConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload, exclude_unset=True)
    config = latest_ai_config(db)
    if not config:
        config = AiConfig(
            provider=data.get("provider") or "openai_compatible",
            base_url=data.get("base_url") or "",
            model=data.get("model") or "",
            api_key=data.get("api_key") or "",
            create_time=datetime.now(),
            heal_enabled=int(data.get("heal_enabled")) if data.get("heal_enabled") is not None else 1,
            heal_confidence_threshold=float(data.get("heal_confidence_threshold")) if data.get("heal_confidence_threshold") is not None else 0.7,
        )
        db.add(config)
    else:
        if "provider" in data:
            config.provider = data["provider"] or "openai_compatible"
        if "base_url" in data:
            config.base_url = data["base_url"] or ""
        if "model" in data:
            config.model = data["model"] or ""
        if "api_key" in data:
            config.api_key = data["api_key"] or ""
        if "heal_enabled" in data:
            config.heal_enabled = int(data["heal_enabled"]) if data["heal_enabled"] is not None else 1
        if "heal_confidence_threshold" in data:
            config.heal_confidence_threshold = float(data["heal_confidence_threshold"]) if data["heal_confidence_threshold"] is not None else 0.7
    db.commit()
    db.refresh(config)
    return serialize_ai_config(config)
