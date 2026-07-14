"""审计日志 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    """审计日志输出。detail 为 {before, after} 变更快照。"""

    id: int
    user_id: int | None = None
    username: str | None = None
    action: str
    target_type: str
    target_id: str | None = None
    detail: dict | None = None
    ip_address: str | None = None
    created_at: str | None = None
