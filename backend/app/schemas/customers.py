"""客户（Customer）相关 Pydantic 模型。

与 app.modules.customers.service 对齐。schemas=plain BaseModel（无 orm_mode），
路由手工逐字段构造响应。
"""

from pydantic import BaseModel, Field


class CustomerCreate(BaseModel):
    """创建客户。任何已登录用户均可创建（§3.2）。"""

    name: str = Field(..., min_length=1, max_length=200, description="客户名称")
    industry: str | None = Field(None, max_length=100, description="行业")
    scale: str | None = Field(
        None, pattern="^(大型|中型|小型)$", description="规模：大型/中型/小型"
    )
    region: str | None = Field(None, max_length=100, description="地区")
    description: str | None = Field(None, description="描述")
    visibility: str = Field("private", pattern="^(private|team)$")
    sensitivity_level: str = Field("internal", max_length=50)


class CustomerUpdate(BaseModel):
    """更新客户（所有字段可选）。"""

    name: str | None = Field(None, min_length=1, max_length=200)
    industry: str | None = Field(None, max_length=100)
    scale: str | None = Field(None, pattern="^(大型|中型|小型)$")
    region: str | None = Field(None, max_length=100)
    description: str | None = None
    visibility: str | None = Field(None, pattern="^(private|team)$")
    sensitivity_level: str | None = Field(None, max_length=50)


class CustomerOut(BaseModel):
    """客户输出。"""

    id: int
    name: str
    industry: str | None = None
    scale: str | None = None
    region: str | None = None
    description: str | None = None
    created_by: int
    created_by_name: str | None = None
    visibility: str = "private"
    sensitivity_level: str = "internal"
    project_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None
