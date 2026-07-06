"""模型设置接口。"""

from fastapi import APIRouter, Depends

from app.api.deps import current_user
from app.core.config import get_available_models
from app.models import User
from app.schemas.model_settings import ModelSettingsOut

router = APIRouter(prefix="/api/model-settings")


@router.get("", response_model=ModelSettingsOut)
async def get_model_settings(_: User = Depends(current_user)) -> ModelSettingsOut:
    """返回前端展示所需的模型和思考级别，不暴露供应商信息。"""
    models = get_available_models()
    return ModelSettingsOut(
        models=models,
        default_model=models[0] if models else None,
        default_thinking_level="low",
        thinking_levels=[
            {"value": "disabled", "label": "关闭"},
            {"value": "low", "label": "低"},
            {"value": "medium", "label": "中"},
            {"value": "high", "label": "高"},
        ],
    )
