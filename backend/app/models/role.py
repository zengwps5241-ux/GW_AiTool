"""Role / RoleMenu ORM 模型 — 角色与菜单可见性关联（方案 A：角色+菜单权限）。

设计要点（决策 #58 / #68）：
- 角色**只控制菜单可见性**，后端 require_admin/require_super 继续硬编码检查 User.role 字符串。
- User.role 保留字符串字段，与 Role.code 逻辑关联（不加 FK），零迁移成本。
- 内置 3 角色 code=user/admin/super，is_system=True 不可删除。
- super 角色的菜单关联不可修改（防锁死超管，决策 #63）。
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 角色编码（UNIQUE）：与 User.role 字符串逻辑关联（user/admin/super/自定义）
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # 内置角色不可删除（仅可改 name/description/sort_order）
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 排序
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


class RoleMenu(Base):
    """角色-菜单多对多关联表，控制角色可见菜单。联合主键 (role_id, menu_id)。"""

    __tablename__ = "role_menus"

    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    menu_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("menus.id", ondelete="CASCADE"), primary_key=True
    )
