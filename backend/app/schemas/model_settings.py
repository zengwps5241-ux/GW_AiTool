"""模型设置相关响应模型。"""

from typing import Literal

from pydantic import BaseModel


ThinkingLevelValue = Literal["disabled", "low", "medium", "high"]


class ThinkingLevelOut(BaseModel):
    value: ThinkingLevelValue
    label: str


class ModelSettingsOut(BaseModel):
    models: list[str]
    thinking_levels: list[ThinkingLevelOut]
    default_model: str | None
    default_thinking_level: ThinkingLevelValue
