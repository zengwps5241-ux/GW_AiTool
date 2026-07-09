"""Customer ORM 模型 — 客户（1:N Project）。

客户为顶层业务实体：一个客户下可有多个咨询项目。
客户基本信息跨项目共享（同一客户的不同项目看到一致的基本信息）。

主键沿用 Integer 自增（与 User/Organization/Agent 等全库一致），
FK 到 users.id 为 Integer。详见 DECISIONS.md 决策 #10。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # 行业（如：能源、金融、制造）
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    # 规模：大型 / 中型 / 小型
    scale: Mapped[str | None] = mapped_column(String, nullable=True)
    # 地区
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    # 描述
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 创建者
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # 可见性：private（私有）/ team（团队可见基本信息，§3.5 跨项目公开机制）
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="private")
    # 敏感级别：internal 等
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
