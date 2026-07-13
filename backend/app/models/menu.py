"""Menu ORM 模型 — 菜单自引用树，驱动侧边栏动态渲染。

与 Organization 表同模式（单表自引用邻接表）。内置菜单 is_system=True 不可删除，
仅可改排序/图标。M6.1 定义模型 + 种子数据（role_menus 依赖），M6.2 补充菜单 CRUD/可见菜单/排序 API。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Menu(Base):
    __tablename__ = "menus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 父级菜单 ID，形成自引用树（分组节点 → 叶子菜单）
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("menus.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # 菜单编码（UNIQUE）：叶子菜单对应前端 ViewName，分组节点为 group_xxx
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # Lucide icon 名称（前端按 code→icon 组件映射；分组节点可为空）
    icon: Mapped[str | None] = mapped_column(String, nullable=True)
    # 对应前端 ViewName；分组节点为空
    view_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # 同层级排序
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 是否可见（隐藏的菜单不渲染但仍可配置）
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 内置菜单不可删除（仅可改排序/图标）
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    # 关系：自引用邻接表（与 Organization 同模式）
    children: Mapped[list["Menu"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    parent: Mapped["Menu | None"] = relationship(
        back_populates="children",
        remote_side="Menu.id",
    )
