"""角色业务服务层。

职责：
- Role CRUD（系统角色 is_system=True 不可删除，可改 name/description/sort_order）
- 角色-菜单关联查询/批量设置（super 角色关联不可修改，防锁死超管，决策 #63）
- 用户角色分配（更新 User.role 字符串为 Role.code，决策 #68）
- 内置角色种子 + role_menus 关联种子（super→全部 / admin→除白名单外 / user→作战台4+文件2+智能体管理）
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu import Menu
from app.models.role import Role, RoleMenu
from app.models.user import User
from app.schemas.roles import RoleCreate, RoleUpdate

# super 角色编码 —— 其菜单关联始终全部可见且不可修改
SUPER_ROLE_CODE = "super"

# 内置角色种子：(code, name, description, sort_order)
_BUILTIN_ROLES: tuple[tuple[str, str, str, int], ...] = (
    ("user", "普通用户", "默认普通用户，可见作战台、文件与智能体管理", 0),
    ("admin", "管理员", "管理员，除登录白名单外全部菜单可见", 1),
    ("super", "超级管理员", "超级管理员，全部菜单可见且关联不可修改", 2),
)

# user 角色可见叶子菜单（作战台 4 + 文件 2 + 智能体管理）
_USER_LEAF_CODES: frozenset[str] = frozenset(
    {
        "chat",
        "businessMap",
        "marketingMap",
        "visitRecords",
        "personalSpace",
        "teamSpaces",
        "agents",
    }
)


# ─── 工具函数 ────────────────────────────────────────────────


def _role_to_out(role: Role):
    """ORM → 输出模型（延迟导入避免循环依赖）。"""
    from app.schemas.roles import RoleOut

    return RoleOut(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        sort_order=role.sort_order,
        created_at=role.created_at.isoformat() if role.created_at else None,
        updated_at=role.updated_at.isoformat() if role.updated_at else None,
    )


# ─── 角色 CRUD ───────────────────────────────────────────────


async def list_roles(db: AsyncSession):
    """列出全部角色（按 sort_order、id 排序）。"""
    result = await db.execute(select(Role).order_by(Role.sort_order, Role.id))
    return [_role_to_out(r) for r in result.scalars().all()]


async def get_role(db: AsyncSession, role_id: int):
    """获取单个角色，不存在返回 None。"""
    role = await db.get(Role, role_id)
    return _role_to_out(role) if role else None


async def _get_role_orm(db: AsyncSession, role_id: int) -> Role | None:
    return await db.get(Role, role_id)


async def create_role(db: AsyncSession, payload: RoleCreate):
    """创建自定义角色（is_system 强制为 False）。"""
    # code 唯一性校验
    existing = await db.execute(select(Role).where(Role.code == payload.code))
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"角色编码 '{payload.code}' 已存在")

    role = Role(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        is_system=False,  # 自定义角色恒非系统角色
        sort_order=payload.sort_order,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return _role_to_out(role)


async def update_role(db: AsyncSession, role_id: int, payload: RoleUpdate):
    """更新角色（仅 name/description/sort_order；code 与 is_system 不可改）。"""
    role = await _get_role_orm(db, role_id)
    if role is None:
        raise ValueError("角色不存在")

    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.sort_order is not None:
        role.sort_order = payload.sort_order

    await db.commit()
    await db.refresh(role)
    return _role_to_out(role)


async def delete_role(db: AsyncSession, role_id: int) -> None:
    """删除角色（系统角色 is_system=True 不可删除）。"""
    role = await _get_role_orm(db, role_id)
    if role is None:
        raise ValueError("角色不存在")
    if role.is_system:
        raise ValueError("系统内置角色不可删除")

    # 关联的 role_menus 由 ON DELETE CASCADE 自动清理
    await db.delete(role)
    await db.commit()


# ─── 角色-菜单关联 ───────────────────────────────────────────


async def get_role_menu_ids(db: AsyncSession, role_id: int) -> list[int] | None:
    """查看角色关联的菜单 ID 列表。

    super 角色始终返回全部菜单 ID（即使关联表被清空也兜底为全部）。
    角色不存在返回 None。
    """
    role = await _get_role_orm(db, role_id)
    if role is None:
        return None

    if role.code == SUPER_ROLE_CODE:
        # super 兜底：全部菜单
        result = await db.execute(select(Menu.id).order_by(Menu.id))
        return [row[0] for row in result.all()]

    result = await db.execute(
        select(RoleMenu.menu_id).where(RoleMenu.role_id == role_id).order_by(RoleMenu.menu_id)
    )
    return [row[0] for row in result.all()]


async def set_role_menus(db: AsyncSession, role_id: int, menu_ids: list[int]) -> list[int]:
    """批量设置角色关联菜单（全量替换）。

    - super 角色：拒绝修改（始终全部可见）。
    - menu_ids 中不存在的 menu_id → 报错。
    返回替换后的菜单 ID 列表。
    """
    role = await _get_role_orm(db, role_id)
    if role is None:
        raise ValueError("角色不存在")
    if role.code == SUPER_ROLE_CODE:
        raise ValueError("super 角色的菜单关联不可修改（始终全部可见）")

    # 去重 + 校验所有 menu_id 存在
    unique_ids = list(dict.fromkeys(menu_ids))  # 保序去重
    if unique_ids:
        valid = (
            await db.execute(select(Menu.id).where(Menu.id.in_(unique_ids)))
        ).scalars().all()
        valid_set = set(valid)
        invalid = [i for i in unique_ids if i not in valid_set]
        if invalid:
            raise ValueError(f"菜单 ID 不存在：{invalid}")

    # 删除旧关联，插入新关联
    existing = await db.execute(select(RoleMenu).where(RoleMenu.role_id == role_id))
    for rm in existing.scalars().all():
        await db.delete(rm)
    for mid in unique_ids:
        db.add(RoleMenu(role_id=role_id, menu_id=mid))
    await db.commit()
    return unique_ids


# ─── 用户角色分配 ─────────────────────────────────────────────


async def assign_user_role(
    db: AsyncSession, user_id: int, role_code: str
) -> User:
    """将用户角色更新为目标 Role.code（User.role 字符串字段，决策 #68）。

    - 用户不存在 → ValueError
    - 角色 code 不存在 → ValueError
    返回更新后的 User ORM 对象。
    """
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("用户不存在")

    role = (
        await db.execute(select(Role).where(Role.code == role_code))
    ).scalar_one_or_none()
    if role is None:
        raise ValueError(f"角色编码 '{role_code}' 不存在")

    user.role = role.code  # 字符串关联，不加 FK
    await db.commit()
    await db.refresh(user)
    return user


# ─── 种子数据 ────────────────────────────────────────────────


async def seed_default_roles(db: AsyncSession) -> dict[str, int]:
    """表空时播种 3 个内置角色（is_system=True，非破坏性）。

    返回 code→id 映射，供 role_menus 种子引用。
    """
    count = (await db.execute(select(func.count()).select_from(Role))).scalar_one()
    if count:
        existing = (await db.execute(select(Role))).scalars().all()
        return {r.code: r.id for r in existing}

    for code, name, desc, sort in _BUILTIN_ROLES:
        db.add(
            Role(
                code=code,
                name=name,
                description=desc,
                is_system=True,
                sort_order=sort,
            )
        )
    await db.commit()
    existing = (await db.execute(select(Role))).scalars().all()
    return {r.code: r.id for r in existing}


def _resolve_role_menu_codes(
    all_menu_codes: set[str], role_code: str
) -> set[str]:
    """根据角色 code 计算其应关联的菜单 code 集合（含分组节点）。

    - super → 全部
    - admin → 除 loginWhitelist 外全部
    - user → 作战台4+文件2+智能体管理 + 对应分组（管理分组因 agents 可见也纳入）
    """
    group_codes = {c for c in all_menu_codes if c.startswith("group_")}
    leaf_codes = all_menu_codes - group_codes

    if role_code == SUPER_ROLE_CODE:
        return set(all_menu_codes)

    if role_code == "admin":
        # 除登录白名单外的全部菜单
        return all_menu_codes - {"loginWhitelist"}

    if role_code == "user":
        user_leaves = _USER_LEAF_CODES & leaf_codes
        # 纳入「有可见叶子」的分组节点（管理分组因 agents 可见而纳入）
        groups: set[str] = set()
        # 简单按命名前缀判断分组归属
        prefix_to_group = {
            ("chat", "businessMap", "marketingMap", "visitRecords"): "group_zhanzuo",
            ("personalSpace", "teamSpaces"): "group_file",
            ("agents", "skills", "usage", "feedback", "loginWhitelist"): "group_admin",
            ("systemSettings",): "group_setting",
        }
        for leaves, gcode in prefix_to_group.items():
            if any(l in user_leaves for l in leaves) and gcode in group_codes:
                groups.add(gcode)
        return user_leaves | groups

    # 自定义角色默认无菜单关联
    return set()


async def seed_default_role_menus(db: AsyncSession) -> None:
    """表空时播种 role_menus 关联（依赖 roles + menus 已就绪，非破坏性）。

    super→全部, admin→除白名单外全部, user→作战台4+文件2+智能体管理+对应分组。
    """
    count = (await db.execute(select(func.count()).select_from(RoleMenu))).scalar_one()
    if count:
        return

    roles = {r.code: r.id for r in (await db.execute(select(Role))).scalars().all()}
    menus = {m.code: m.id for m in (await db.execute(select(Menu))).scalars().all()}
    if not roles or not menus:
        # menus/roles 尚未就绪，跳过（一般 M6.1 已 seed，此分支不触发）
        return

    all_menu_codes = set(menus.keys())
    for role_code in (SUPER_ROLE_CODE, "admin", "user"):
        rid = roles.get(role_code)
        if rid is None:
            continue
        for code in _resolve_role_menu_codes(all_menu_codes, role_code):
            mid = menus.get(code)
            if mid is not None:
                db.add(RoleMenu(role_id=rid, menu_id=mid))
    await db.commit()
