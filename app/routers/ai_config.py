"""AI 配置路由"""
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.utils import schema_data, latest_ai_config, serialize_ai_config
from ..database import get_db
from ..models import AiConfig, User
from ..functional_testing.model_client import call_local_model_json
from ..schemas import AiConfigConnectionTest, AiConfigUpdate
from ..security import require_admin

router = APIRouter(tags=["ai-config"])


@router.get("/api/ai-config")
def get_ai_config(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, Any]:
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
        if "api_key" in data and str(data["api_key"] or "").strip():
            config.api_key = str(data["api_key"]).strip()
        if "heal_enabled" in data:
            config.heal_enabled = int(data["heal_enabled"]) if data["heal_enabled"] is not None else 1
        if "heal_confidence_threshold" in data:
            config.heal_confidence_threshold = float(data["heal_confidence_threshold"]) if data["heal_confidence_threshold"] is not None else 0.7
    db.commit()
    db.refresh(config)
    return serialize_ai_config(config)


@router.post("/api/ai-config/test")
def test_ai_config_connection(
    payload: AiConfigConnectionTest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    current = latest_ai_config(db)
    data = schema_data(payload, exclude_unset=True)
    candidate = AiConfig(
        provider=str(data.get("provider") or getattr(current, "provider", "") or "openai_compatible").strip(),
        base_url=str(data.get("base_url") or getattr(current, "base_url", "") or "").strip(),
        model=str(data.get("model") or getattr(current, "model", "") or "").strip(),
        api_key=str(data.get("api_key") or getattr(current, "api_key", "") or "").strip(),
        create_time=datetime.now(),
        heal_enabled=int(getattr(current, "heal_enabled", 1) or 1),
        heal_confidence_threshold=float(getattr(current, "heal_confidence_threshold", 0.7) or 0.7),
    )
    if not candidate.base_url or not candidate.model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请填写API地址和模型名称")
    try:
        call_local_model_json(
            candidate,
            '只输出合法JSON：{"ok":true}',
            timeout=20,
        )
    except Exception as exc:
        text = str(exc or "")
        lowered = text.lower()
        if "401" in lowered or "403" in lowered or "unauthorized" in lowered or "api key" in lowered:
            detail = "认证失败，请检查API Key"
        elif "model" in lowered and ("not found" in lowered or "不存在" in text or "不可用" in text):
            detail = "模型不可用，请检查模型名称"
        elif "timeout" in lowered or "超时" in text:
            detail = "连接超时，请检查网络或代理配置"
        elif "proxy" in lowered or "connection" in lowered or "网络" in text:
            detail = "网络或代理连接失败"
        else:
            detail = f"连接测试失败：{text}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
    return {"ok": True, "message": "连接成功", "model": candidate.model}
