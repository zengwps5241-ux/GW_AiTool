"""分类相关 Pydantic 模型。"""

from pydantic import BaseModel


class CategoryOut(BaseModel):
    id: int
    name: str


class CategoryCreate(BaseModel):
    name: str


class CategoryRename(BaseModel):
    name: str
