"""团队空间 API schema。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


TeamMemberRole = Literal["reader", "editor"]


class TeamSpaceCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None


class TeamSpaceUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None


class TeamSpaceMemberAddIn(BaseModel):
    user_id: int
    role: TeamMemberRole = "reader"


class TeamSpaceMemberUpdateIn(BaseModel):
    role: TeamMemberRole


class TeamSpaceTransferOwnerIn(BaseModel):
    user_id: int


class TeamSpaceLockIn(BaseModel):
    note: str | None = None


class TeamSpaceOut(BaseModel):
    id: int
    name: str
    description: str | None
    owner_user_id: int
    owner_name: str
    member_count: int
    locked_by_user_id: int | None
    locked_by_name: str | None
    lock_acquired_at: datetime | None
    lock_note: str | None
    member_role: TeamMemberRole
    can_write: bool
    is_owner: bool
    readonly_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeamSpaceMemberOut(BaseModel):
    id: int
    user_id: int
    username: str
    display_name: str | None
    role: TeamMemberRole
    is_owner: bool
    added_by_user_id: int
    created_at: datetime
    updated_at: datetime


class TeamSpaceMemberSearchOut(BaseModel):
    user_id: int
    username: str
    display_name: str | None
    is_member: bool


# ─── 公开资产 / 对象公开机制（M5.5.3，§2.6 / §5.x / §6.3）─────────


class PublicAssetItem(BaseModel):
    """公开资产条目：跨项目聚合三类领域对象的最小展示信息。

    角色卡 / 业务地图片段 / 拜访记录统一成此结构，
    供团队空间「公开资产区」按类型分组渲染（§6.3）。
    """

    # card / business_object / visit
    object_type: str
    object_id: int
    project_id: int
    project_name: str
    # 角色卡名 / 业务地图节点名 / 拜访摘要
    title: str
    # 副标题：职位·部门 / 层级·地图类型 / 拜访类型·日期
    subtitle: str | None = None
    review_status: str
    created_by: int
    created_by_name: str
    created_at: datetime


class PublicAssetsOut(BaseModel):
    """公开资产聚合结果（按类型分组）。"""

    cards: list[PublicAssetItem]
    business_objects: list[PublicAssetItem]
    visits: list[PublicAssetItem]


class UserSearchOut(BaseModel):
    """用户搜索条目（「共享给」picker 数据源）。"""

    user_id: int
    username: str
    display_name: str | None


# ─── 方法论库（§2.6 / §6.3，admin 维护，用户只读）─────────────────

# 三类内容：Prompt 模板 / 画布 Schema / 方法论规则
MethodologyCategory = Literal["prompt_template", "canvas_schema", "methodology_rule"]


class MethodologyItemCreate(BaseModel):
    category: MethodologyCategory
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    sort_order: int = 0


class MethodologyItemUpdate(BaseModel):
    category: MethodologyCategory | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    sort_order: int | None = None


class MethodologyItemOut(BaseModel):
    id: int
    category: MethodologyCategory
    title: str
    content: str
    sort_order: int
    created_by: int | None
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime
