"""Organization ORM 模型 — 自建三级组织架构（公司→部门→小组）。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # 组织类型：company / department / group
    type: Mapped[str] = mapped_column(String, nullable=False, default="department")
    # 父级组织 ID，形成三级树：公司→部门→小组
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    # 负责人用户 ID
    head_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # 同层级排序
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    # 关系：自引用邻接表
    # children 为一对多（父→子），parent 为多对一（子→父，remote_side 指向主键）
    children: Mapped[list["Organization"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    parent: Mapped["Organization | None"] = relationship(
        back_populates="children",
        remote_side="Organization.id",
    )


class UserOrganization(Base):
    """用户-组织关联表。"""
    __tablename__ = "user_organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # 岗位名称
    position_title: Mapped[str | None] = mapped_column(String, nullable=True)
    # 是否主部门
    is_primary: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=0  # SQLite 兼容用 Integer 代替 Boolean
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
