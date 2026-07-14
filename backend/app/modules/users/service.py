"""用户管理业务服务层（管理端）。

M6.4 用户管理增强：
- list_admin_users：全量用户列表 + 筛选（role/status/organization_id/搜索）+ 所属组织聚合
- update_user_status：启用/禁用（不可禁自己）
- reset_password：管理员重置密码
- create_admin_user：管理员创建用户（跳过审批 status=active，校验 role 存在）

写操作均埋审计日志（决策 #64，actor_id 由路由层传入）。
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.models import Organization, Role, User, UserOrganization
from app.schemas.users import AdminUserOut, UserOrgBrief


def _user_to_out(user: User, orgs: list[UserOrgBrief] | None = None) -> AdminUserOut:
    """ORM → AdminUserOut。"""
    return AdminUserOut(
        id=user.id,
        username=user.username,
        phone=user.phone,
        role=user.role,
        status=user.status,
        display_name=user.display_name,
        department=user.department,
        registration_source=user.registration_source,
        organizations=orgs or [],
        created_at=user.created_at.isoformat() if user.created_at else None,
        last_login=user.last_login.isoformat() if user.last_login else None,
    )


# ─── 全量用户列表 ─────────────────────────────────────────────


async def list_admin_users(
    db: AsyncSession,
    *,
    role: str | None = None,
    status: str | None = None,
    organization_id: int | None = None,
    search: str | None = None,
) -> list[AdminUserOut]:
    """全量用户列表，支持 role/status/organization_id/搜索(username/phone 模糊)。"""
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if status:
        stmt = stmt.where(User.status == status)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(User.username.ilike(pattern), User.phone.ilike(pattern)))
    if organization_id:
        # 子查询避免多组织用户重复行
        subq = select(UserOrganization.user_id).where(
            UserOrganization.organization_id == organization_id
        )
        stmt = stmt.where(User.id.in_(subq))
    stmt = stmt.order_by(User.id)
    users = (await db.execute(stmt)).scalars().all()
    if not users:
        return []

    # 批量查所属组织
    user_ids = [u.id for u in users]
    org_rows = (
        await db.execute(
            select(UserOrganization.user_id, Organization.id, Organization.name)
            .join(Organization, Organization.id == UserOrganization.organization_id)
            .where(UserOrganization.user_id.in_(user_ids))
        )
    ).all()
    orgs_by_user: dict[int, list[UserOrgBrief]] = {}
    for uid, oid, oname in org_rows:
        orgs_by_user.setdefault(uid, []).append(UserOrgBrief(id=oid, name=oname))

    return [_user_to_out(u, orgs_by_user.get(u.id)) for u in users]


# ─── 用户状态管理 ─────────────────────────────────────────────


async def update_user_status(
    db: AsyncSession, user_id: int, status: str, actor_id: int | None = None
) -> User:
    """启用/禁用用户。不可禁用自己的账号。"""
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("用户不存在")
    if status == "disabled" and actor_id is not None and user_id == actor_id:
        raise ValueError("不能禁用自己的账号")

    before = {"status": user.status}
    user.status = status
    await db.commit()
    await db.refresh(user)
    # 审计埋点（决策 #64）
    if actor_id is not None:
        from app.modules.audit.service import log_audit

        await log_audit(
            db, actor_id, "update", "user", str(user_id),
            detail={"before": before, "after": {"status": status}},
        )
    return user


# ─── 重置密码 ────────────────────────────────────────────────


async def reset_password(
    db: AsyncSession, user_id: int, new_password: str, actor_id: int | None = None
) -> User:
    """管理员重置用户密码。"""
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("用户不存在")
    user.password_hash = security.hash_password(new_password)
    await db.commit()
    await db.refresh(user)
    # 审计埋点（决策 #64，不记密码明文）
    if actor_id is not None:
        from app.modules.audit.service import log_audit

        await log_audit(
            db, actor_id, "update", "user", str(user_id),
            detail={"after": {"password_reset": True}},
        )
    return user


# ─── 管理员创建用户 ───────────────────────────────────────────


async def create_admin_user(
    db: AsyncSession, payload, actor_id: int | None = None
) -> User:
    """管理员创建用户（跳过审批，status=active，registration_source=admin_create）。

    - username/phone 唯一校验
    - role 校验为已存在的 Role.code
    """
    # username 唯一
    if (
        await db.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none() is not None:
        raise ValueError("用户名已存在")
    # phone 唯一
    if payload.phone:
        if (
            await db.execute(select(User).where(User.phone == payload.phone))
        ).scalar_one_or_none() is not None:
            raise ValueError("手机号已注册")
    # role 须为已存在的 Role.code
    role = (
        await db.execute(select(Role).where(Role.code == payload.role))
    ).scalar_one_or_none()
    if role is None:
        raise ValueError(f"角色编码 '{payload.role}' 不存在")

    user = User(
        username=payload.username,
        password_hash=security.hash_password(payload.password),
        phone=payload.phone,
        display_name=payload.display_name or payload.username,
        status="active",
        registration_source="admin_create",
        auth_source="local",
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    # 审计埋点（决策 #64）
    if actor_id is not None:
        from app.modules.audit.service import log_audit

        await log_audit(
            db, actor_id, "create", "user", str(user.id),
            detail={"after": {"username": user.username, "role": user.role,
                              "status": user.status}},
        )
    return user
