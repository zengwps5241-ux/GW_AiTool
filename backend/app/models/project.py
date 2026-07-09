"""Project ORM 模型 — 客户下的咨询项目，含成员与部门授权。

关系：
- Project N:1 Customer（customer_id）
- Project 1:N ProjectMember（项目成员：owner / deputy）
- Project 1:N ProjectDepartmentAccess（按部门授权：被授权部门成员自动获得访问权）
- Project.agent_id → Agent（创建项目时自动生成，§5.2 Agent 创建规则）

权限：项目内全透明、项目外全隔离（§3.5）。成员判定见 app/api/project_deps.py。

主键 Integer 自增，FK 到 users.id/agents.id/organizations.id 均为 Integer。
"""

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 所属客户
    customer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # 自动创建的 Agent（创建项目时生成）
    agent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 项目类型：诊断 / 试点 / 落地
    project_type: Mapped[str | None] = mapped_column(String, nullable=True)
    # FDE 阶段：lead_screening / visit_preparation / onsite_validation / retrospective
    fde_stage: Mapped[str] = mapped_column(
        String, nullable=False, default="lead_screening"
    )
    # 状态：active / paused / completed / archived
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    # Owner 用户（创建者默认为 Owner；亦在 project_members 中存 role=owner 记录）
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    objectives: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # 可见性 / 敏感级别（§3.5）
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="private")
    sensitivity_level: Mapped[str] = mapped_column(
        String, nullable=False, default="internal"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


class ProjectMember(Base):
    """项目成员（Owner / Deputy）。"""

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # 角色：owner / deputy
    role: Mapped[str] = mapped_column(String, nullable=False, default="deputy")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )


class ProjectDepartmentAccess(Base):
    """项目-部门授权：被授权部门的所有成员自动获得项目访问权（§3.5 / V2.2）。"""

    __tablename__ = "project_department_access"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "organization_id", name="uq_project_department_access"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    granted_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
