"""项目（Project）相关 Pydantic 模型：项目 CRUD、成员管理、部门授权。

与 app.modules.projects.service 对齐。schemas=plain BaseModel（无 orm_mode）。
"""

from datetime import date, datetime

from pydantic import BaseModel, Field


# ─── 项目 CRUD ────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    """创建项目。创建者默认成为 Owner，并自动生成项目 Agent。"""

    customer_id: int = Field(..., description="所属客户 ID")
    name: str = Field(..., min_length=1, max_length=200, description="项目名称")
    project_type: str | None = Field(
        None, pattern="^(诊断|试点|落地)$", description="项目类型"
    )
    fde_stage: str = Field(
        "lead_screening",
        pattern="^(lead_screening|visit_preparation|onsite_validation|retrospective)$",
        description="FDE 阶段",
    )
    status: str = Field(
        "active", pattern="^(active|paused|completed|archived)$", description="状态"
    )
    description: str | None = None
    objectives: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    visibility: str = Field("private", pattern="^(private|team)$")
    sensitivity_level: str = Field("internal", max_length=50)


class ProjectUpdate(BaseModel):
    """更新项目（所有字段可选）。仅 Owner 可改（§3.3）。"""

    name: str | None = Field(None, min_length=1, max_length=200)
    project_type: str | None = Field(None, pattern="^(诊断|试点|落地)$")
    fde_stage: str | None = Field(
        None, pattern="^(lead_screening|visit_preparation|onsite_validation|retrospective)$"
    )
    status: str | None = Field(None, pattern="^(active|paused|completed|archived)$")
    description: str | None = None
    objectives: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    visibility: str | None = Field(None, pattern="^(private|team)$")
    sensitivity_level: str | None = Field(None, max_length=50)


class ProjectOut(BaseModel):
    """项目输出。"""

    id: int
    customer_id: int
    customer_name: str | None = None
    name: str
    agent_id: int | None = None
    project_type: str | None = None
    fde_stage: str
    status: str
    owner_id: int
    owner_name: str | None = None
    description: str | None = None
    objectives: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    created_by: int
    created_by_name: str | None = None
    visibility: str = "private"
    sensitivity_level: str = "internal"
    member_count: int = 0
    my_role: str | None = Field(
        None, description="当前用户在该项目的角色：owner/deputy/none（admin 视角为 admin）"
    )
    created_at: str | None = None
    updated_at: str | None = None


# ─── 成员管理 ──────────────────────────────────────────────────


class ProjectMemberAdd(BaseModel):
    """邀请成员（仅 Owner；role 通常为 deputy）。"""

    user_id: int
    role: str = Field("deputy", pattern="^(owner|deputy)$")


class ProjectMemberOut(BaseModel):
    """项目成员输出。"""

    id: int
    project_id: int
    user_id: int
    username: str
    display_name: str | None = None
    role: str
    joined_at: str | None = None


# ─── 部门授权 ──────────────────────────────────────────────────


class ProjectDepartmentAccessAdd(BaseModel):
    """为项目授权一个部门（仅 Owner）。"""

    organization_id: int


class ProjectDepartmentAccessOut(BaseModel):
    """项目-部门授权输出。"""

    id: int
    project_id: int
    organization_id: int
    organization_name: str | None = None
    granted_by: int
    granted_by_name: str | None = None
    granted_at: str | None = None


# ─── 内部辅助（服务层手工组装时复用） ─────────────────────────


def iso(value: datetime | None) -> str | None:
    """datetime → ISO 字符串，None 保持 None。"""
    return value.isoformat() if value else None
