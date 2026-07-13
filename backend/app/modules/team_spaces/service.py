"""团队空间业务逻辑。"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import BusinessMapObject, MethodologyItem, Project, StakeholderCard, TeamSpace, TeamSpaceMember, User, VisitRecord
from app.schemas.team_spaces import (
    MethodologyItemCreate,
    MethodologyItemOut,
    MethodologyItemUpdate,
    PublicAssetItem,
)


def team_workspace(space_id: int) -> Path:
    """返回团队空间目录，并确保基础 Markdown 目录存在。"""
    root = get_settings().workspaces_dir.parent / "team_workspaces" / str(space_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / ".markdown").mkdir(parents=True, exist_ok=True)
    return root


async def get_membership(db: AsyncSession, user: User, space_id: int) -> TeamSpaceMember | None:
    return (
        await db.execute(
            select(TeamSpaceMember).where(
                TeamSpaceMember.space_id == space_id,
                TeamSpaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()


async def require_member(db: AsyncSession, user: User, space_id: int) -> tuple[TeamSpace, TeamSpaceMember]:
    space = await db.get(TeamSpace, space_id)
    member = await get_membership(db, user, space_id)
    if space is None or member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="空间不存在")
    return space, member


async def require_owner(db: AsyncSession, user: User, space_id: int) -> tuple[TeamSpace, TeamSpaceMember]:
    """校验当前用户是团队空间所有者。"""
    space, member = await require_member(db, user, space_id)
    if space.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="只有空间所有者可以管理成员")
    return space, member


async def get_space_member_by_id(db: AsyncSession, space_id: int, member_id: int) -> TeamSpaceMember:
    member = await db.get(TeamSpaceMember, member_id)
    if member is None or member.space_id != space_id:
        raise HTTPException(status_code=404, detail="成员不存在")
    return member


def can_write(space: TeamSpace, member: TeamSpaceMember) -> tuple[bool, str | None]:
    if member.role != "editor":
        return False, "只读成员不能编辑团队空间"
    if space.lock_holder_user_id is None:
        return True, None
    if space.lock_holder_user_id == member.user_id:
        return True, None
    return False, "当前空间已被其他成员锁定"


async def member_count(db: AsyncSession, space_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(TeamSpaceMember).where(TeamSpaceMember.space_id == space_id)
    )
    return int(result.scalar() or 0)


async def create_space(db: AsyncSession, user: User, name: str, description: str | None) -> TeamSpace:
    space = TeamSpace(name=name, description=description, owner_user_id=user.id, created_by_user_id=user.id)
    db.add(space)
    await db.flush()
    db.add(TeamSpaceMember(space_id=space.id, user_id=user.id, role="editor", added_by_user_id=user.id))
    await db.commit()
    team_workspace(space.id)
    await db.refresh(space)
    return space


async def add_member(
    db: AsyncSession,
    owner: User,
    space_id: int,
    user_id: int,
    role: str,
) -> TeamSpaceMember:
    space, _owner_member = await require_owner(db, owner, space_id)
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    existing = (
        await db.execute(
            select(TeamSpaceMember).where(
                TeamSpaceMember.space_id == space_id,
                TeamSpaceMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.user_id == space.owner_user_id:
            raise HTTPException(status_code=400, detail="不能修改空间所有者权限")
        existing.role = role
        await db.commit()
        await db.refresh(existing)
        return existing

    member = TeamSpaceMember(
        space_id=space_id,
        user_id=user_id,
        role=role,
        added_by_user_id=owner.id,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def update_member_role(
    db: AsyncSession,
    owner: User,
    space_id: int,
    member_id: int,
    role: str,
) -> TeamSpaceMember:
    space, _owner_member = await require_owner(db, owner, space_id)
    member = await get_space_member_by_id(db, space_id, member_id)
    if member.user_id == space.owner_user_id:
        raise HTTPException(status_code=400, detail="不能修改空间所有者权限")
    member.role = role
    await db.commit()
    await db.refresh(member)
    return member


async def remove_member(db: AsyncSession, owner: User, space_id: int, member_id: int) -> None:
    space, _owner_member = await require_owner(db, owner, space_id)
    member = await get_space_member_by_id(db, space_id, member_id)
    if member.user_id == space.owner_user_id:
        raise HTTPException(status_code=400, detail="不能删除空间所有者")
    if space.lock_holder_user_id == member.user_id:
        space.lock_holder_user_id = None
        space.lock_acquired_at = None
        space.lock_note = None
    await db.delete(member)
    await db.commit()


async def transfer_owner(db: AsyncSession, owner: User, space_id: int, user_id: int) -> TeamSpace:
    space, _owner_member = await require_owner(db, owner, space_id)
    target_member = (
        await db.execute(
            select(TeamSpaceMember).where(
                TeamSpaceMember.space_id == space_id,
                TeamSpaceMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if target_member is None:
        raise HTTPException(status_code=404, detail="目标成员不存在")
    space.owner_user_id = user_id
    target_member.role = "editor"
    await db.commit()
    await db.refresh(space)
    return space


async def leave_space(db: AsyncSession, user: User, space_id: int) -> None:
    space, member = await require_member(db, user, space_id)
    if space.owner_user_id == user.id:
        raise HTTPException(status_code=400, detail="空间所有者必须先转让所有权")
    if space.lock_holder_user_id == user.id:
        space.lock_holder_user_id = None
        space.lock_acquired_at = None
        space.lock_note = None
    await db.delete(member)
    await db.commit()


async def search_member_candidates(
    db: AsyncSession,
    owner: User,
    space_id: int,
    keyword: str,
) -> list[tuple[User, bool]]:
    """空间所有者按姓名模糊搜索可添加成员。"""
    await require_owner(db, owner, space_id)

    keyword = keyword.strip()
    if not keyword:
        return []

    pattern = f"%{keyword}%"
    users = (
        await db.execute(
            select(User)
            .where(or_(User.display_name.ilike(pattern), User.username.ilike(pattern)))
            .order_by(
                User.display_name.asc().nullslast(),
                User.username.asc(),
                User.id.asc(),
            )
            .limit(20)
        )
    ).scalars().all()
    if not users:
        return []

    member_user_ids = set(
        (
            await db.execute(
                select(TeamSpaceMember.user_id).where(
                    TeamSpaceMember.space_id == space_id,
                    TeamSpaceMember.user_id.in_(
                        [candidate.id for candidate in users],
                    ),
                )
            )
        ).scalars().all()
    )
    return [(candidate, candidate.id in member_user_ids) for candidate in users]


async def lock_space(db: AsyncSession, user: User, space_id: int, note: str | None) -> TeamSpace:
    space, member = await require_member(db, user, space_id)
    if member.role != "editor":
        raise HTTPException(status_code=403, detail="只读成员不能锁定团队空间")
    if space.lock_holder_user_id not in (None, user.id):
        raise HTTPException(status_code=409, detail="当前空间已被锁定")
    space.lock_holder_user_id = user.id
    space.lock_acquired_at = datetime.now(timezone.utc)
    space.lock_note = note
    await db.commit()
    await db.refresh(space)
    return space


async def unlock_space(db: AsyncSession, user: User, space_id: int) -> TeamSpace:
    space, _member = await require_member(db, user, space_id)
    if space.lock_holder_user_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="只有持锁人可以解除锁定")
    space.lock_holder_user_id = None
    space.lock_acquired_at = None
    space.lock_note = None
    await db.commit()
    await db.refresh(space)
    return space


# ─── 对象公开机制（M5.5.3，§2.6 / §5.x / §6.3）────────────────────
#
# 字段 is_public / shared_with 已存在于 StakeholderCard / BusinessMapObject /
# VisitRecord 三模型（§3.5），create/update 早已写入。本节补「跨项目可见性聚合」：
# - list_public_assets：is_public=1 的 reviewed 对象 → 团队空间公开资产区（§6.3）
# - list_shared_with_me：shared_with ∋ 当前用户 的 reviewed 对象（§5.x 指定用户可见）
# 仅聚合最小展示信息，不放行单对象深链（项目级访问控制 require_project_member 不变）。


async def _project_name_map(db: AsyncSession, project_ids: set[int]) -> dict[int, str]:
    """批量取项目名（公开资产跨项目，需展示来源项目）。"""
    if not project_ids:
        return {}
    rows = (
        await db.execute(select(Project.id, Project.name).where(Project.id.in_(project_ids)))
    ).all()
    return {pid: name for pid, name in rows}


async def _user_name_map(db: AsyncSession, user_ids: set[int]) -> dict[int, str]:
    """批量取用户展示名（created_by 归属展示）。"""
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(User.id, User.display_name, User.username).where(User.id.in_(user_ids))
        )
    ).all()
    return {uid: (display_name or username) for uid, display_name, username in rows}


def _card_item(card: StakeholderCard, project_names: dict[int, str], user_names: dict[int, str]) -> PublicAssetItem:
    return PublicAssetItem(
        object_type="card",
        object_id=card.id,
        project_id=card.project_id,
        project_name=project_names.get(card.project_id, ""),
        title=card.name,
        subtitle=" · ".join(filter(None, [card.position, card.department])) or None,
        review_status=card.review_status,
        created_by=card.created_by,
        created_by_name=user_names.get(card.created_by, ""),
        created_at=card.created_at,
    )


def _bmo_item(obj: BusinessMapObject, project_names: dict[int, str], user_names: dict[int, str]) -> PublicAssetItem:
    return PublicAssetItem(
        object_type="business_object",
        object_id=obj.id,
        project_id=obj.project_id,
        project_name=project_names.get(obj.project_id, ""),
        title=obj.name,
        subtitle=" · ".join(filter(None, [obj.level, obj.map_type])) or None,
        review_status=obj.review_status,
        created_by=obj.created_by,
        created_by_name=user_names.get(obj.created_by, ""),
        created_at=obj.created_at,
    )


def _visit_item(visit: VisitRecord, project_names: dict[int, str], user_names: dict[int, str]) -> PublicAssetItem:
    subtitle_parts: list[str] = [visit.visit_type] if visit.visit_type else []
    if visit.visit_date:
        subtitle_parts.append(visit.visit_date.isoformat())
    return PublicAssetItem(
        object_type="visit",
        object_id=visit.id,
        project_id=visit.project_id,
        project_name=project_names.get(visit.project_id, ""),
        title=(visit.summary or "").strip()[:80] or "（无摘要）",
        subtitle=" · ".join(subtitle_parts) or None,
        review_status=visit.review_status,
        created_by=visit.created_by,
        created_by_name=user_names.get(visit.created_by, ""),
        created_at=visit.created_at,
    )


def _aggregate(
    cards: list[StakeholderCard],
    bmos: list[BusinessMapObject],
    visits: list[VisitRecord],
    project_names: dict[int, str],
    user_names: dict[int, str],
) -> dict:
    return {
        "cards": [_card_item(c, project_names, user_names) for c in cards],
        "business_objects": [_bmo_item(o, project_names, user_names) for o in bmos],
        "visits": [_visit_item(v, project_names, user_names) for v in visits],
    }


async def list_public_assets(db: AsyncSession) -> dict:
    """跨项目聚合 is_public=1 的 reviewed 对象（§6.3 公开资产归档）。

    语义：对象标记「完全公开」后，原项目内正常可见 + 团队空间公开资产区可见。
    仅含 review_status=reviewed（草稿/待审/驳回不公开，§7.3）。
    """
    cards = (
        await db.execute(
            select(StakeholderCard)
            .where(StakeholderCard.is_public == 1, StakeholderCard.review_status == "reviewed")
            .order_by(StakeholderCard.id)
        )
    ).scalars().all()
    bmos = (
        await db.execute(
            select(BusinessMapObject)
            .where(BusinessMapObject.is_public == 1, BusinessMapObject.review_status == "reviewed")
            .order_by(BusinessMapObject.id)
        )
    ).scalars().all()
    visits = (
        await db.execute(
            select(VisitRecord)
            .where(VisitRecord.is_public == 1, VisitRecord.review_status == "reviewed")
            .order_by(VisitRecord.id)
        )
    ).scalars().all()

    project_ids = {c.project_id for c in cards} | {o.project_id for o in bmos} | {v.project_id for v in visits}
    user_ids = {c.created_by for c in cards} | {o.created_by for o in bmos} | {v.created_by for v in visits}
    project_names = await _project_name_map(db, project_ids)
    user_names = await _user_name_map(db, user_ids)
    return _aggregate(cards, bmos, visits, project_names, user_names)


async def list_shared_with_me(db: AsyncSession, user_id: int) -> dict:
    """跨项目聚合 shared_with ∋ 当前用户 的 reviewed 对象（§5.x 指定用户可见）。

    用 JSONB @> 数组包含查询（cast([uid], JSONB) 避免 asyncpg 类型陷阱，
    与 visits/service.py:200 同款）；shared_with 为 NULL 不匹配。
    """
    cond = cast([user_id], JSONB)
    cards = (
        await db.execute(
            select(StakeholderCard)
            .where(
                StakeholderCard.shared_with.op("@>")(cond),
                StakeholderCard.review_status == "reviewed",
            )
            .order_by(StakeholderCard.id)
        )
    ).scalars().all()
    bmos = (
        await db.execute(
            select(BusinessMapObject)
            .where(
                BusinessMapObject.shared_with.op("@>")(cond),
                BusinessMapObject.review_status == "reviewed",
            )
            .order_by(BusinessMapObject.id)
        )
    ).scalars().all()
    visits = (
        await db.execute(
            select(VisitRecord)
            .where(
                VisitRecord.shared_with.op("@>")(cond),
                VisitRecord.review_status == "reviewed",
            )
            .order_by(VisitRecord.id)
        )
    ).scalars().all()

    project_ids = {c.project_id for c in cards} | {o.project_id for o in bmos} | {v.project_id for v in visits}
    user_ids = {c.created_by for c in cards} | {o.created_by for o in bmos} | {v.created_by for v in visits}
    project_names = await _project_name_map(db, project_ids)
    user_names = await _user_name_map(db, user_ids)
    return _aggregate(cards, bmos, visits, project_names, user_names)


async def search_users(db: AsyncSession, keyword: str, *, limit: int = 20) -> list[User]:
    """按姓名/用户名模糊搜索 active 用户（「共享给」picker 数据源）。

    与 search_member_candidates 同款 ilike，但不限团队空间成员范围；
    「共享给」是跨项目对象级共享，候选=全平台 active 用户。
    """
    keyword = keyword.strip()
    if not keyword:
        return []
    pattern = f"%{keyword}%"
    return list(
        (
            await db.execute(
                select(User)
                .where(
                    User.status == "active",
                    or_(User.display_name.ilike(pattern), User.username.ilike(pattern)),
                )
                .order_by(
                    User.display_name.asc().nullslast(),
                    User.username.asc(),
                    User.id.asc(),
                )
                .limit(limit)
            )
        ).scalars().all()
    )


# ─── 方法论库（§2.6 / §6.3，admin 维护，用户只读）─────────────────


def _methodology_to_out(
    item: MethodologyItem, user_names: dict[int, str]
) -> MethodologyItemOut:
    return MethodologyItemOut(
        id=item.id,
        category=item.category,
        title=item.title,
        content=item.content,
        sort_order=item.sort_order,
        created_by=item.created_by,
        created_by_name=user_names.get(item.created_by) if item.created_by else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def list_methodology(
    db: AsyncSession, *, category: str | None = None
) -> list[MethodologyItemOut]:
    """方法论库列表：按 类别→排序→id 有序列出；可按类别过滤。"""
    stmt = select(MethodologyItem)
    if category is not None:
        stmt = stmt.where(MethodologyItem.category == category)
    stmt = stmt.order_by(
        MethodologyItem.category, MethodologyItem.sort_order, MethodologyItem.id
    )
    rows = (await db.execute(stmt)).scalars().all()
    user_names = await _user_name_map(db, {r.created_by for r in rows if r.created_by})
    return [_methodology_to_out(r, user_names) for r in rows]


async def get_methodology(
    db: AsyncSession, item_id: int
) -> MethodologyItemOut | None:
    item = await db.get(MethodologyItem, item_id)
    if item is None:
        return None
    user_names = await _user_name_map(
        db, {item.created_by} if item.created_by else set()
    )
    return _methodology_to_out(item, user_names)


async def create_methodology(
    db: AsyncSession, payload: MethodologyItemCreate, user: User
) -> MethodologyItemOut:
    item = MethodologyItem(
        category=payload.category,
        title=payload.title,
        content=payload.content,
        sort_order=payload.sort_order,
        created_by=user.id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _methodology_to_out(item, {user.id: user.display_name or user.username})


async def update_methodology(
    db: AsyncSession, item_id: int, payload: MethodologyItemUpdate
) -> MethodologyItemOut | None:
    item = await db.get(MethodologyItem, item_id)
    if item is None:
        return None
    if payload.category is not None:
        item.category = payload.category
    if payload.title is not None:
        item.title = payload.title
    if payload.content is not None:
        item.content = payload.content
    if payload.sort_order is not None:
        item.sort_order = payload.sort_order
    await db.commit()
    await db.refresh(item)
    user_names = await _user_name_map(
        db, {item.created_by} if item.created_by else set()
    )
    return _methodology_to_out(item, user_names)


async def delete_methodology(db: AsyncSession, item_id: int) -> bool:
    item = await db.get(MethodologyItem, item_id)
    if item is None:
        return False
    await db.delete(item)
    await db.commit()
    return True


# 方法论库默认种子（三类各一条，启动时表空才播种；非破坏性，admin 可改删）
_METHODOLOGY_DEFAULTS: tuple[tuple[str, str, str, int], ...] = (
    (
        "methodology_rule",
        "道层 · 顾问方法论根本准则",
        "# 道层 · 顾问方法论根本准则\n\n"
        "面向大客户销售/交付团队的**咨询顾问智能体**根本行为准则。\n\n"
        "## 根本准则\n\n"
        "1. **客观优先、证据驱动**：先呈现可核实事实，再给推断；推断必须标注置信度（高/中/低）与依据。没有依据时**留空并标低置信度，绝不臆造数据**。\n"
        "2. **不泄露敏感信息**：不输出内部 API 密钥、系统路径、原始工具调用名；敏感内容只给结论不给载体。\n"
        "3. **结构化产出走草稿工具**：业务地图/角色卡/拜访记录等结构化数据调用草稿工具写入项目草稿区，**不直接当正式数据**，待用户采纳。\n"
        "4. **中文输出、专业克制**：分步生成用纯文本询问，不调用 AskUserQuestion。\n"
        "5. **项目隔离**：只处理当前会话绑定项目的数据，不跨项目引用。\n\n"
        "## 方法论三层（道 / 法 / 器）\n\n"
        "- **道层**：不变的根本准则（本条），永远在 System Prompt。\n"
        "- **法层**：业务地图 / 营销地图 / 拜访记录的结构化字段契约，全量读取不走 RAG。\n"
        "- **器层**：参考资料（行业报告、公开信息），Top-K 检索，可裁剪、需标注来源。",
        0,
    ),
    (
        "prompt_template",
        "角色卡（WF12）产出 Prompt 要点",
        "# 角色卡产出 Prompt 要点\n\n"
        "生成角色卡时遵循 §5.2 StakeholderCard 字段契约：\n\n"
        "1. **客观层**：姓名、岗位、部门、汇报对象、联系方式、决策权、角色类型。\n"
        "2. **主观层**：对我方立场（支持/中立/反对/观望，封闭枚举）、影响力、亲和度，"
        "每项带 confidence（高/中/低）。\n"
        "3. **三维度评分**：基于 Champion 三要素（权力/认同/行动），综合评分由服务端计算。\n"
        "4. **explicitKPI 必填**：无依据时填「待补充」，不留空。\n"
        "5. **去重**：与项目既有角色卡姓名相似（完全同名 1.0 / 包含 0.6）时进入去重候选。",
        0,
    ),
    (
        "canvas_schema",
        "业务地图 L1-L4 层级 Schema",
        "# 业务地图 L1-L4 层级 Schema\n\n"
        "业务地图按四层展开，每层节点 payload 字段严格对齐 §5.2：\n\n"
        "- **L1 公司级价值链**：核心活动、能力链、IT 系统、组织、五维健康（5 维各 1-5 分）。\n"
        "- **L2 域级**（业务域/职能域/共性技术域）：域目标(SMART)、价值流(5-7 步)、核心能力、支撑 IT 系统、关键数据实体、断点。\n"
        "- **L3 场景级**：业务目标(SMART)、业务流程(5-8 步)、关键活动、能力单元、数据流、岗位、支撑系统、痛点(可量化)、本体抽取、AI 机会、五维健康。\n"
        "- **L4 人才地图**：不计算五维健康。\n\n"
        "**五维健康键名固定**：`L5_数字意识` / `L4_数字神经` / `L3_数字器官` / `L2_数字血液` / `L1_数字骨架`，值 `{score, desc}`。",
        0,
    ),
)


async def seed_default_methodology(db: AsyncSession) -> None:
    """表空时播种方法论库默认条目（非破坏性，admin 可后续增删改）。"""
    count = (
        await db.execute(select(func.count()).select_from(MethodologyItem))
    ).scalar_one()
    if count:
        return
    for category, title, content, sort_order in _METHODOLOGY_DEFAULTS:
        db.add(
            MethodologyItem(
                category=category,
                title=title,
                content=content,
                sort_order=sort_order,
                created_by=None,
            )
        )
    await db.commit()
