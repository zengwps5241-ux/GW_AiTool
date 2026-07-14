"""审计日志业务服务层。

- log_audit() 工具函数：各 service 写方法末尾主动调用（决策 #64），best-effort
  （失败只记日志不抛异常，不阻塞主业务）
- list_audit_logs()：管理端查询，支持 user_id / action / target_type / 时间范围筛选

调用约定：log_audit 在 service 写方法的业务 commit 之后调用，其内部独立 commit 审计日志。
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)


async def log_audit(
    db: AsyncSession,
    user_id: int | None,
    action: str,
    target_type: str,
    target_id: str | int | None,
    detail: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """记录一条审计日志（best-effort，失败不抛异常）。

    自动按 user_id 查 username 冗余存储。在 service 写方法业务 commit 之后调用；
    本函数内部独立 commit 审计日志（与主业务解耦，审计失败不影响主业务结果）。
    """
    try:
        username = None
        effective_user_id = user_id
        if user_id is not None:
            user = await db.get(User, user_id)
            if user is not None:
                username = user.username
            else:
                # 用户不存在（已删/非法 id）→ user_id 置 NULL，避免 FK 违反，日志仍保留
                effective_user_id = None
        log = AuditLog(
            user_id=effective_user_id,
            username=username,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            detail=detail,
            ip_address=ip_address,
        )
        db.add(log)
        await db.commit()
    except Exception:
        # 审计是 best-effort：记录失败不影响主业务
        logger.warning(
            "审计日志记录失败: action=%s target=%s/%s",
            action,
            target_type,
            target_id,
            exc_info=True,
        )
        try:
            await db.rollback()
        except Exception:
            pass


async def list_audit_logs(
    db: AsyncSession,
    *,
    user_id: int | None = None,
    action: str | None = None,
    target_type: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditLog]:
    """查询审计日志，按时间倒序，分页。各筛选条件可选。"""
    stmt = select(AuditLog)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if target_type is not None:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if start_date is not None:
        stmt = stmt.where(AuditLog.created_at >= start_date)
    if end_date is not None:
        stmt = stmt.where(AuditLog.created_at <= end_date)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()
