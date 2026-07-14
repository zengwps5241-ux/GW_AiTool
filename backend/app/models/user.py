"""User ORM model。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)

    # 手机号（唯一，用于手机号+密码登录）
    phone: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)

    # 用户状态：pending_approval=待审批 / active=正常 / disabled=禁用
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active"
    )

    # 注册来源：self_register=自助注册 / admin_create=管理员创建
    registration_source: Mapped[str] = mapped_column(
        String, nullable=False, default="admin_create"
    )

    # DEPRECATED: 企微认证相关字段，保留以备未来扩展
    wechat_user_id: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True
    )
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    department: Mapped[str | None] = mapped_column(String, nullable=True)
    department_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    position: Mapped[str | None] = mapped_column(String, nullable=True)
    mobile: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    auth_source: Mapped[str] = mapped_column(
        String, nullable=False, default="local"
    )
    role: Mapped[str] = mapped_column(String, nullable=False, default="user")

    # 最后登录时间（M6.4 用户管理，登录时更新）
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )

    sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
