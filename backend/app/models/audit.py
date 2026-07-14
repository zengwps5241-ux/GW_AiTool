"""AuditLog ORM 模型 — 关键写操作审计日志（决策 #60/#64）。

detail 用 JSONB 存变更前后快照 {before, after}。log_audit() 工具函数在各 service
写方法末尾主动调用（决策 #64：Service 层主动调用，精准可控）。

- user_id FK SET NULL：用户被删除后审计日志仍保留
- username 冗余字段：便于日志页直接展示，不依赖 join users 表
- 只记写操作（create/update/delete/login/approve/reject/adopt/rollback），数据量可控
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 操作人（用户删除后置空，日志保留）
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # 冗余用户名，便于日志页直接展示
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    # 操作类型：create/update/delete/login/approve/reject/adopt/rollback
    action: Mapped[str] = mapped_column(String, nullable=False)
    # 目标类型：user/organization/role/menu/business_map/stakeholder/visit/
    #           session/project/customer/agent/skill/plugin
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    # 目标 ID（字符串，兼容 UUID session_id 与 int PK）
    target_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # 变更前后快照 {before, after}
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
