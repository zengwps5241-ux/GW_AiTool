"""组织架构业务服务层。

职责：
- Organization / UserOrganization CRUD
- 树形结构查询（递归组装父子节点 + 成员）
- 批量导入解析（按名称引用父级 + 用户名引用负责人，校验+去重+批量创建）
- 防环校验（parent 链不能成环）
- 删除约束（有子节点/成员时拒绝，避免误删）

自建三级架构：公司 → 部门 → 小组。
"""

from __future__ import annotations

import csv
import io
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization, UserOrganization
from app.models.user import User
from app.schemas.organizations import (
    OrganizationImportResult,
    OrganizationImportRow,
    OrganizationOut,
    OrganizationTreeNode,
    UserOrganizationOut,
)


# ─── 工具函数 ────────────────────────────────────────────────


async def _user_display_name(db: AsyncSession, user_id: int | None) -> str | None:
    """根据 user_id 查询用户显示名（不存在则返回 None）。"""
    if user_id is None:
        return None
    user = await db.get(User, user_id)
    if user is None:
        return None
    return user.display_name or user.username


def _org_to_out(org: Organization, head_name: str | None) -> OrganizationOut:
    """ORM → 输出模型。"""
    return OrganizationOut(
        id=org.id,
        name=org.name,
        type=org.type,
        parent_id=org.parent_id,
        head_user_id=org.head_user_id,
        head_user_name=head_name,
        sort_order=org.sort_order,
        created_at=org.created_at.isoformat() if org.created_at else None,
        updated_at=org.updated_at.isoformat() if org.updated_at else None,
    )


async def _would_create_cycle(
    db: AsyncSession, org_id: int, new_parent_id: int | None
) -> bool:
    """检测把 org_id 的 parent 改为 new_parent_id 是否会形成环。

    沿 new_parent 的 parent 链向上追溯，若遇到 org_id 则成环。
    """
    if new_parent_id is None:
        return False
    if new_parent_id == org_id:
        return True
    visited: set[int] = set()
    current_id: int | None = new_parent_id
    while current_id is not None and current_id not in visited:
        if current_id == org_id:
            return True
        visited.add(current_id)
        parent = await db.get(Organization, current_id)
        if parent is None:
            break
        current_id = parent.parent_id
    return False


# ─── CRUD ────────────────────────────────────────────────────


async def list_organizations(db: AsyncSession) -> list[OrganizationOut]:
    """列出全部组织节点（扁平列表）。"""
    result = await db.execute(
        select(Organization).order_by(Organization.sort_order, Organization.id)
    )
    orgs = result.scalars().all()
    out: list[OrganizationOut] = []
    for org in orgs:
        head_name = await _user_display_name(db, org.head_user_id)
        out.append(_org_to_out(org, head_name))
    return out


async def get_organization(db: AsyncSession, org_id: int) -> OrganizationOut | None:
    """获取单个组织节点。"""
    org = await db.get(Organization, org_id)
    if org is None:
        return None
    head_name = await _user_display_name(db, org.head_user_id)
    return _org_to_out(org, head_name)


async def create_organization(
    db: AsyncSession, payload
) -> OrganizationOut:
    """创建组织节点。"""
    # 校验父级存在
    if payload.parent_id is not None:
        parent = await db.get(Organization, payload.parent_id)
        if parent is None:
            raise ValueError("父级组织不存在")
    # 校验负责人存在
    if payload.head_user_id is not None:
        user = await db.get(User, payload.head_user_id)
        if user is None:
            raise ValueError("负责人用户不存在")
    # 名称在同父级下唯一
    existing = await db.execute(
        select(Organization).where(
            Organization.name == payload.name,
            Organization.parent_id == payload.parent_id if payload.parent_id is not None else Organization.parent_id.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("同层级下已存在同名组织")

    org = Organization(
        name=payload.name,
        type=payload.type,
        parent_id=payload.parent_id,
        head_user_id=payload.head_user_id,
        sort_order=payload.sort_order,
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)
    head_name = await _user_display_name(db, org.head_user_id)
    return _org_to_out(org, head_name)


async def update_organization(
    db: AsyncSession, org_id: int, payload
) -> OrganizationOut:
    """更新组织节点。"""
    org = await db.get(Organization, org_id)
    if org is None:
        raise ValueError("组织不存在")

    # 名称变更时校验同父级唯一
    if payload.name is not None and payload.name != org.name:
        existing = await db.execute(
            select(Organization).where(
                Organization.name == payload.name,
                Organization.id != org_id,
                Organization.parent_id == org.parent_id if org.parent_id is not None else Organization.parent_id.is_(None),
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("同层级下已存在同名组织")
        org.name = payload.name

    if payload.type is not None:
        org.type = payload.type

    # parent_id 变更：校验父级存在 + 防环
    if payload.parent_id is not None and payload.parent_id != org.parent_id:
        parent = await db.get(Organization, payload.parent_id)
        if parent is None:
            raise ValueError("父级组织不存在")
        if await _would_create_cycle(db, org_id, payload.parent_id):
            raise ValueError("不能将组织挂到自身或其子节点下（会形成环）")
        org.parent_id = payload.parent_id

    if payload.head_user_id is not None:
        user = await db.get(User, payload.head_user_id)
        if user is None:
            raise ValueError("负责人用户不存在")
        org.head_user_id = payload.head_user_id

    if payload.sort_order is not None:
        org.sort_order = payload.sort_order

    await db.commit()
    await db.refresh(org)
    head_name = await _user_display_name(db, org.head_user_id)
    return _org_to_out(org, head_name)


async def delete_organization(db: AsyncSession, org_id: int) -> None:
    """删除组织节点（有子节点或成员时拒绝）。"""
    org = await db.get(Organization, org_id)
    if org is None:
        raise ValueError("组织不存在")

    # 拒绝有子节点
    children = await db.execute(
        select(Organization).where(Organization.parent_id == org_id)
    )
    if children.scalars().first() is not None:
        raise ValueError("存在子组织，不能删除（请先迁移子组织）")

    # 拒绝有成员
    members = await db.execute(
        select(UserOrganization).where(UserOrganization.organization_id == org_id)
    )
    if members.scalars().first() is not None:
        raise ValueError("组织下仍有成员，不能删除")

    await db.delete(org)
    await db.commit()


# ─── 树形查询 ────────────────────────────────────────────────


async def get_organization_tree(db: AsyncSession) -> list[OrganizationTreeNode]:
    """返回完整组织树（根节点列表，每个节点含 children + members）。"""
    # 一次性拉取所有组织 + 所有成员关联，避免 N+1
    all_orgs = (
        await db.execute(
            select(Organization).order_by(Organization.sort_order, Organization.id)
        )
    ).scalars().all()

    all_members = (
        await db.execute(select(UserOrganization))
    ).scalars().all()

    # 一次性查所有相关用户
    user_ids = {m.user_id for m in all_members} | {o.head_user_id for o in all_orgs if o.head_user_id}
    users_map: dict[int, User] = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in users_result.scalars().all():
            users_map[u.id] = u

    # 成员按 organization_id 分组
    members_by_org: dict[int, list[UserOrganizationOut]] = {}
    for m in all_members:
        u = users_map.get(m.user_id)
        members_by_org.setdefault(m.organization_id, []).append(
            UserOrganizationOut(
                user_id=m.user_id,
                organization_id=m.organization_id,
                username=u.username if u else str(m.user_id),
                display_name=(u.display_name if u else None),
                position_title=m.position_title,
                is_primary=bool(m.is_primary),
            )
        )

    # 构建 id -> node 映射
    nodes_by_id: dict[int, OrganizationTreeNode] = {}
    for o in all_orgs:
        head = users_map.get(o.head_user_id) if o.head_user_id else None
        nodes_by_id[o.id] = OrganizationTreeNode(
            id=o.id,
            name=o.name,
            type=o.type,
            parent_id=o.parent_id,
            head_user_id=o.head_user_id,
            head_user_name=(head.display_name or head.username) if head else None,
            sort_order=o.sort_order,
            members=members_by_org.get(o.id, []),
            children=[],
        )

    # 组装父子关系，收集根节点
    roots: list[OrganizationTreeNode] = []
    for o in all_orgs:
        node = nodes_by_id[o.id]
        if o.parent_id is not None and o.parent_id in nodes_by_id:
            nodes_by_id[o.parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


# ─── 成员管理 ────────────────────────────────────────────────


async def add_member(
    db: AsyncSession, org_id: int, payload
) -> UserOrganizationOut:
    """添加用户到组织。"""
    org = await db.get(Organization, org_id)
    if org is None:
        raise ValueError("组织不存在")
    user = await db.get(User, payload.user_id)
    if user is None:
        raise ValueError("用户不存在")
    # 同一用户在同一组织只能有一条记录
    existing = await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == payload.user_id,
            UserOrganization.organization_id == org_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("该用户已在此组织下")

    rel = UserOrganization(
        user_id=payload.user_id,
        organization_id=org_id,
        position_title=payload.position_title,
        is_primary=1 if payload.is_primary else 0,
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return UserOrganizationOut(
        user_id=rel.user_id,
        organization_id=rel.organization_id,
        username=user.username,
        display_name=user.display_name,
        position_title=rel.position_title,
        is_primary=bool(rel.is_primary),
    )


async def remove_member(db: AsyncSession, org_id: int, user_id: int) -> None:
    """从组织移除用户。"""
    existing = await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == user_id,
            UserOrganization.organization_id == org_id,
        )
    )
    rel = existing.scalar_one_or_none()
    if rel is None:
        raise ValueError("该用户不在此组织下")
    await db.delete(rel)
    await db.commit()


# ─── 批量导入 ────────────────────────────────────────────────


def parse_import_rows(content: str, content_type: str = "json") -> list[OrganizationImportRow]:
    """把导入内容解析成行列表。

    支持两种格式：
    - JSON: 数组对象，字段见 OrganizationImportRow
    - CSV: 首行为表头，列名 name,type,parent_name,head_user_username,position_title,is_primary,sort_order
    """
    content_type = (content_type or "json").lower()
    rows: list[OrganizationImportRow] = []

    if "csv" in content_type:
        reader = csv.DictReader(io.StringIO(content))
        for raw in reader:
            # 容错：空白行跳过
            if not raw.get("name"):
                continue
            is_primary_raw = (raw.get("is_primary") or "").strip().lower()
            sort_raw = (raw.get("sort_order") or "0").strip()
            rows.append(
                OrganizationImportRow(
                    name=raw["name"].strip(),
                    type=(raw.get("type") or "department").strip() or "department",
                    parent_name=(raw.get("parent_name") or "").strip() or None,
                    head_user_username=(raw.get("head_user_username") or "").strip() or None,
                    position_title=(raw.get("position_title") or "").strip() or None,
                    is_primary=is_primary_raw in ("1", "true", "yes"),
                    sort_order=int(sort_raw) if sort_raw else 0,
                )
            )
        return rows

    # 默认 JSON
    data = json.loads(content)
    if not isinstance(data, list):
        raise ValueError("JSON 导入内容必须是数组")
    for item in data:
        rows.append(OrganizationImportRow(**item))
    return rows


async def import_organizations(
    db: AsyncSession, rows: list[OrganizationImportRow]
) -> OrganizationImportResult:
    """批量导入组织架构。

    解析规则：
    - parent_name 引用父级：先在已存在 + 本批次已创建 中按名称查找；
      多个同名时按"最近创建"匹配；找不到且 type=company 则作根节点（parent_id=None）。
    - head_user_username 引用负责人：按 username 查 users 表，找不到则该行报错跳过。
    - 去重：同父级同名已存在则跳过（计入 skipped）。
    - 行内异常计入 errors，不中断整体导入。
    """
    total = len(rows)
    created = 0
    skipped = 0
    errors: list[str] = []

    # 名称 → 最近创建的 org_id 映射（含已存在 + 本批新增）
    name_to_id: dict[str, int] = {}
    existing_orgs = (
        await db.execute(select(Organization))
    ).scalars().all()
    # 同名多个时保留每个 id，匹配时优先精确 parent 上下文
    name_to_ids: dict[str, list[int]] = {}
    for o in existing_orgs:
        name_to_ids.setdefault(o.name, []).append(o.id)
        name_to_id[o.name] = o.id  # 兼容：最近一条

    for idx, row in enumerate(rows, start=1):
        try:
            # 解析父级
            parent_id: int | None = None
            if row.parent_name:
                candidates = name_to_ids.get(row.parent_name, [])
                if not candidates:
                    raise ValueError(f"父级组织 '{row.parent_name}' 不存在")
                parent_id = candidates[-1]
            elif row.type != "company":
                # 非公司且无父级：允许作为根部门（parent_id=None），不强制
                parent_id = None

            # 解析负责人
            head_user_id: int | None = None
            if row.head_user_username:
                u_result = await db.execute(
                    select(User).where(User.username == row.head_user_username)
                )
                u = u_result.scalar_one_or_none()
                if u is None:
                    raise ValueError(f"负责人用户 '{row.head_user_username}' 不存在")
                head_user_id = u.id

            # 去重：同父级同名
            dup_result = await db.execute(
                select(Organization).where(
                    Organization.name == row.name,
                    Organization.parent_id == parent_id if parent_id is not None else Organization.parent_id.is_(None),
                )
            )
            if dup_result.scalar_one_or_none() is not None:
                skipped += 1
                continue

            org = Organization(
                name=row.name,
                type=row.type,
                parent_id=parent_id,
                head_user_id=head_user_id,
                sort_order=row.sort_order,
            )
            db.add(org)
            await db.flush()  # 拿到 id，供后续行引用
            name_to_ids.setdefault(org.name, []).append(org.id)
            name_to_id[org.name] = org.id

            # 若行指定了成员信息（head_user_username + position_title），也建立成员关系
            if head_user_id is not None and (row.position_title or row.is_primary):
                existing_rel = await db.execute(
                    select(UserOrganization).where(
                        UserOrganization.user_id == head_user_id,
                        UserOrganization.organization_id == org.id,
                    )
                )
                if existing_rel.scalar_one_or_none() is None:
                    db.add(
                        UserOrganization(
                            user_id=head_user_id,
                            organization_id=org.id,
                            position_title=row.position_title,
                            is_primary=1 if row.is_primary else 0,
                        )
                    )

            created += 1
        except Exception as exc:  # noqa: BLE001 - 行级错误收集
            errors.append(f"第 {idx} 行「{row.name}」: {exc}")
            # 行内异常已 flush 的对象回滚由 commit 时统一处理；这里 continue 不影响其他行
            continue

    await db.commit()
    return OrganizationImportResult(
        total=total, created=created, skipped=skipped, errors=errors
    )
