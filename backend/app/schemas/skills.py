"""技能相关 Pydantic 模型。"""

from pydantic import BaseModel


class SkillOut(BaseModel):
    name: str
    description: str
    category: str | None = None
