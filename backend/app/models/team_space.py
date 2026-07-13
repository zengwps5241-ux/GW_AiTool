"""团队空间 ORM 模型。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TeamSpace(Base):
    """团队共享工作空间。"""

    __tablename__ = "team_spaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    lock_holder_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    lock_acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    members: Mapped[list["TeamSpaceMember"]] = relationship(cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_team_spaces_owner", "owner_user_id"),
        Index("idx_team_spaces_updated", "updated_at"),
    )


class TeamSpaceMember(Base):
    """团队空间成员及权限。"""

    __tablename__ = "team_space_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("team_spaces.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="reader")
    added_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("space_id", "user_id", name="uq_team_space_members_space_user"),
        Index("idx_team_space_members_user", "user_id"),
        Index("idx_team_space_members_space", "space_id"),
    )


class MethodologyItem(Base):
    """团队空间「方法论库」条目（§2.6 / §6.3）。

    管理员维护的全局只读库，含 Prompt 模板 / 画布 Schema / 方法论规则三类。
    所有登录用户只读，admin/super 可增删改。非项目作用域（团队共享）。
    """

    __tablename__ = "methodology_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # prompt_template / canvas_schema / methodology_rule
    category: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    # Markdown 正文（Prompt 模板 / Schema 描述 / 方法论规则）
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 同类内排序（小在前）
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 创建者（admin）；种子条目为 NULL
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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

    __table_args__ = (
        Index("idx_methodology_category", "category", "sort_order", "id"),
    )
