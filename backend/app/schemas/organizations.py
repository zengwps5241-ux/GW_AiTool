"""组织架构相关 Pydantic 模型。

自建三级组织架构（公司→部门→小组），后台维护 + 批量导入。
与后端 app.modules.organizations.service 对齐。
"""

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    """创建/更新组织节点。"""

    name: str = Field(..., min_length=1, max_length=100, description="组织名称")
    type: str = Field(
        "department",
        pattern="^(company|department|group)$",
        description="组织类型：company/department/group",
    )
    parent_id: int | None = Field(None, description="父级组织 ID")
    head_user_id: int | None = Field(None, description="负责人用户 ID")
    sort_order: int = Field(0, description="同层级排序")


class OrganizationUpdate(BaseModel):
    """更新组织节点（所有字段可选）。"""

    name: str | None = Field(None, min_length=1, max_length=100)
    type: str | None = Field(None, pattern="^(company|department|group)$")
    parent_id: int | None = Field(None)
    head_user_id: int | None = Field(None)
    sort_order: int | None = Field(None)


class UserOrganizationOut(BaseModel):
    """用户-组织关联信息。"""

    user_id: int
    organization_id: int
    username: str
    display_name: str | None = None
    position_title: str | None = None
    is_primary: bool = False


class UserOrganizationCreate(BaseModel):
    """添加用户到组织。"""

    user_id: int
    position_title: str | None = Field(None, max_length=100)
    is_primary: bool = False


class OrganizationOut(BaseModel):
    """单个组织节点输出。"""

    id: int
    name: str
    type: str
    parent_id: int | None = None
    head_user_id: int | None = None
    head_user_name: str | None = None
    sort_order: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class OrganizationTreeNode(BaseModel):
    """树形结构节点（递归）。"""

    id: int
    name: str
    type: str
    parent_id: int | None = None
    head_user_id: int | None = None
    head_user_name: str | None = None
    sort_order: int = 0
    members: list[UserOrganizationOut] = []
    children: list["OrganizationTreeNode"] = []


class OrganizationImportRow(BaseModel):
    """批量导入单行（与 CSV/JSON 行对齐）。

    parent_name 用名称引用父级，便于导入时按名称解析；
    若 parent_name 为空且 type=company，作为根公司创建。
    """

    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field("department", pattern="^(company|department|group)$")
    parent_name: str | None = Field(None, description="父级组织名称")
    head_user_username: str | None = Field(None, description="负责人用户名")
    position_title: str | None = Field(None, description="岗位名称")
    is_primary: bool = False
    sort_order: int = 0


class OrganizationImportResult(BaseModel):
    """批量导入结果。"""

    total: int
    created: int
    skipped: int
    errors: list[str] = []


class OrganizationImportResponse(BaseModel):
    """批量导入响应。"""

    success: bool
    result: OrganizationImportResult
