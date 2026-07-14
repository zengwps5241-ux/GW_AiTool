"""审计日志查询 API（仅 admin/super，决策 #60）。

GET /api/admin/audit-logs 支持筛选 user_id / action / target_type / 时间范围；
默认最近 7 天，按时间倒序分页（决策 #69）。
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import User
from app.modules.audit import service as audit_service
from app.schemas.audit import AuditLogOut

router = APIRouter(prefix="/api/admin")


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    user_id: int | None = Query(None, description="按操作人筛选"),
    action: str | None = Query(None, description="操作类型 create/update/delete/..."),
    target_type: str | None = Query(None, description="目标类型 role/menu/user/..."),
    start_date: datetime | None = Query(None, description="起始时间（默认最近7天起点）"),
    end_date: datetime | None = Query(None, description="截止时间"),
    limit: int = Query(50, ge=1, le=200, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    _admin: User = Depends(require_admin),
) -> list[AuditLogOut]:
    """查询审计日志（默认最近 7 天，倒序分页）。"""
    # 未传任何时间范围 → 默认最近 7 天
    if start_date is None and end_date is None:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)

    logs = await audit_service.list_audit_logs(
        db,
        user_id=user_id,
        action=action,
        target_type=target_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return [
        AuditLogOut(
            id=log.id,
            user_id=log.user_id,
            username=log.username,
            action=log.action,
            target_type=log.target_type,
            target_id=log.target_id,
            detail=log.detail,
            ip_address=log.ip_address,
            created_at=log.created_at.isoformat() if log.created_at else None,
        )
        for log in logs
    ]
