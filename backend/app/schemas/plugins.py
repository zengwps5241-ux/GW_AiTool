"""插件相关 Pydantic 模型。"""

from pydantic import BaseModel


class PluginOut(BaseModel):
    name: str
    version: str
    description: str
    path: str
    category: str | None = None
