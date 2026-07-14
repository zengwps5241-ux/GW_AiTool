"""菜单业务服务层。

职责：
- 菜单 CRUD（系统菜单 is_system=True 不可删除，可改排序/图标/可见性等展示字段）
- 菜单树查询（管理端完整树 GET /api/admin/menus/tree）
- 当前用户可见菜单树（GET /api/menus，按 User.role→Role→role_menus 计算，祖先分组自动补全）
- 菜单批量排序（PUT /api/admin/menus/sort）
- 内置菜单种子数据（role_menus 依赖菜单存在，决策 #59）

种子数据从原 SidebarVariantA getNavItems() 硬编码迁移（决策 #59）：
4 个分组节点（作战台/文件/管理/设置）+ 12 条叶子菜单。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu import Menu
from app.models.role import Role, RoleMenu

# super 角色编码 —— 始终可见全部菜单（与 roles.service 一致，此处独立定义避免循环依赖）
SUPER_ROLE_CODE = "super"

# 菜单种子：(code, name, parent_code, icon, view_name, sort_order)
# 分组节点 parent_code=None、view_name=None；叶子菜单挂在对应分组下。
_MENU_SEED: tuple[tuple[str, str, str | None, str | None, str | None, int], ...] = (
    # ── 分组节点（根）──
    ("group_zhanzuo", "作战台", None, None, None, 0),
    ("group_file", "文件", None, None, None, 10),
    ("group_admin", "管理", None, None, None, 20),
    ("group_setting", "设置", None, None, None, 30),
    # ── 作战台 ──
    ("chat", "对话", "group_zhanzuo", "MessageSquare", "chat", 1),
    ("businessMap", "业务地图", "group_zhanzuo", "Map", "businessMap", 2),
    ("marketingMap", "营销地图", "group_zhanzuo", "Target", "marketingMap", 3),
    ("visitRecords", "拜访记录", "group_zhanzuo", "ClipboardList", "visitRecords", 4),
    # ── 文件 ──
    ("personalSpace", "个人空间", "group_file", "Folder", "personalSpace", 1),
    ("teamSpaces", "团队空间", "group_file", "Folders", "teamSpaces", 2),
    # ── 管理 ──
    ("agents", "智能体管理", "group_admin", "Brain", "agents", 1),
    ("skills", "技能管理", "group_admin", "Puzzle", "skills", 2),
    ("usage", "使用统计", "group_admin", "LayoutDashboard", "usage", 3),
    ("feedback", "反馈管理", "group_admin", "MessageSquare", "feedback", 4),
    ("loginWhitelist", "用户白名单", "group_admin", "Users", "loginWhitelist", 5),
    # ── 设置 ──
    ("systemSettings", "系统设置", "group_setting", "Settings", "systemSettings", 1),
)


async def seed_default_menus(db: AsyncSession) -> dict[str, int]:
    """表空时播种内置菜单（is_system=True，非破坏性，admin 可后续增删改）。

    返回 code→id 映射，供 role_menus 种子引用。若表非空则直接返回现有映射。
    """
    count = (await db.execute(select(func.count()).select_from(Menu))).scalar_one()
    existing = (await db.execute(select(Menu))).scalars().all()
    if count:
        # 表已有数据，返回现有映射（不重复播种）
        await db.commit()
        return {m.code: m.id for m in existing}

    # 第一遍：插入分组节点（parent=None），flush 拿到 id
    for code, name, parent_code, icon, view_name, sort in _MENU_SEED:
        if parent_code is None:
            db.add(
                Menu(
                    code=code,
                    name=name,
                    parent_id=None,
                    icon=icon,
                    view_name=view_name,
                    sort_order=sort,
                    is_system=True,
                    is_visible=True,
                )
            )
    await db.flush()

    # 构建 code→id（当前仅含分组）
    groups = (
        await db.execute(select(Menu).where(Menu.parent_id.is_(None)))
    ).scalars().all()
    code_to_id: dict[str, int] = {m.code: m.id for m in groups}

    # 第二遍：插入叶子菜单，parent_id 引用分组
    for code, name, parent_code, icon, view_name, sort in _MENU_SEED:
        if parent_code is not None:
            parent_id = code_to_id.get(parent_code)
            db.add(
                Menu(
                    code=code,
                    name=name,
                    parent_id=parent_id,
                    icon=icon,
                    view_name=view_name,
                    sort_order=sort,
                    is_system=True,
                    is_visible=True,
                )
            )
    await db.commit()

    # 重新拉取全部菜单，返回完整 code→id
    all_menus = (await db.execute(select(Menu))).scalars().all()
    return {m.code: m.id for m in all_menus}


# ─── 工具：ORM → 输出 ─────────────────────────────────────────


def _menu_to_out(menu: Menu):
    """ORM → MenuOut（平铺，延迟导入避免循环依赖）。"""
    from app.schemas.menus import MenuOut

    return MenuOut(
        id=menu.id,
        parent_id=menu.parent_id,
        name=menu.name,
        code=menu.code,
        icon=menu.icon,
        view_name=menu.view_name,
        sort_order=menu.sort_order,
        is_visible=menu.is_visible,
        is_system=menu.is_system,
        created_at=menu.created_at.isoformat() if menu.created_at else None,
        updated_at=menu.updated_at.isoformat() if menu.updated_at else None,
    )


def _build_tree(menus: list[Menu]) -> list:
    """由平铺菜单列表构建树（MenuTreeOut，管理端完整字段）。

    parent_id 不在当前集合中的节点视为根（避免孤儿丢失）。
    同层级按 (sort_order, id) 排序。
    """
    from app.schemas.menus import MenuTreeOut

    nodes: dict[int, MenuTreeOut] = {
        m.id: MenuTreeOut(
            id=m.id,
            parent_id=m.parent_id,
            name=m.name,
            code=m.code,
            icon=m.icon,
            view_name=m.view_name,
            sort_order=m.sort_order,
            is_visible=m.is_visible,
            is_system=m.is_system,
            children=[],
        )
        for m in menus
    }
    roots: list[MenuTreeOut] = []
    for m in menus:
        node = nodes[m.id]
        if m.parent_id is None or m.parent_id not in nodes:
            roots.append(node)
        else:
            nodes[m.parent_id].children.append(node)

    def _sort(node_list: list[MenuTreeOut]) -> None:
        node_list.sort(key=lambda n: (n.sort_order, n.id))
        for n in node_list:
            _sort(n.children)

    _sort(roots)
    return roots


def _build_visible_tree(menus: list[Menu]) -> list:
    """由平铺菜单列表构建可见菜单树（MenuNode，渲染用精简字段）。"""
    from app.schemas.menus import MenuNode

    nodes: dict[int, MenuNode] = {
        m.id: MenuNode(
            id=m.id,
            parent_id=m.parent_id,
            name=m.name,
            code=m.code,
            icon=m.icon,
            view_name=m.view_name,
            sort_order=m.sort_order,
            children=[],
        )
        for m in menus
    }
    roots: list[MenuNode] = []
    for m in menus:
        node = nodes[m.id]
        if m.parent_id is None or m.parent_id not in nodes:
            roots.append(node)
        else:
            nodes[m.parent_id].children.append(node)

    def _sort(node_list: list[MenuNode]) -> None:
        node_list.sort(key=lambda n: (n.sort_order, n.id))
        for n in node_list:
            _sort(n.children)

    _sort(roots)
    return roots


async def _get_menu_orm(db: AsyncSession, menu_id: int) -> Menu | None:
    return await db.get(Menu, menu_id)


async def _collect_descendant_ids(db: AsyncSession, menu_id: int) -> set[int]:
    """收集某菜单的全部后代 id（广度遍历，供循环引用检测使用）。"""
    result = await db.execute(select(Menu.id, Menu.parent_id))
    children_of: dict[int | None, list[int]] = {}
    for mid, pid in result.all():
        children_of.setdefault(pid, []).append(mid)

    descendants: set[int] = set()
    queue = list(children_of.get(menu_id, []))
    while queue:
        cur = queue.pop()
        if cur in descendants:
            continue
        descendants.add(cur)
        queue.extend(children_of.get(cur, []))
    return descendants


# ─── 菜单 CRUD ───────────────────────────────────────────────


async def list_menus(db: AsyncSession) -> list:
    """列出全部菜单（按 sort_order、id 排序）。"""
    result = await db.execute(select(Menu).order_by(Menu.sort_order, Menu.id))
    return [_menu_to_out(m) for m in result.scalars().all()]


async def get_menu(db: AsyncSession, menu_id: int):
    """获取单个菜单，不存在返回 None。"""
    menu = await _get_menu_orm(db, menu_id)
    return _menu_to_out(menu) if menu else None


async def create_menu(db: AsyncSession, payload) :
    """创建自定义菜单（is_system 强制为 False）。

    - code 唯一性校验
    - parent_id 存在性校验（若提供）
    """
    # code 唯一性
    existing = await db.execute(select(Menu).where(Menu.code == payload.code))
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"菜单编码 '{payload.code}' 已存在")

    # parent_id 存在性
    if payload.parent_id is not None:
        parent = await _get_menu_orm(db, payload.parent_id)
        if parent is None:
            raise ValueError(f"父级菜单 ID {payload.parent_id} 不存在")

    menu = Menu(
        code=payload.code,
        name=payload.name,
        parent_id=payload.parent_id,
        icon=payload.icon,
        view_name=payload.view_name,
        sort_order=payload.sort_order,
        is_visible=payload.is_visible,
        is_system=False,  # 自定义菜单恒非系统菜单
    )
    db.add(menu)
    await db.commit()
    await db.refresh(menu)
    return _menu_to_out(menu)


async def update_menu(db: AsyncSession, menu_id: int, payload):
    """更新菜单（仅展示字段；code 与 is_system 不可改）。

    - parent_id 存在性校验、自引用检测、循环引用检测
    """
    menu = await _get_menu_orm(db, menu_id)
    if menu is None:
        raise ValueError("菜单不存在")

    if payload.parent_id is not None:
        # 自引用检测
        if payload.parent_id == menu_id:
            raise ValueError("不能将菜单的父级设为自身")
        # 循环引用检测：新父级不能是自己的后代
        descendant_ids = await _collect_descendant_ids(db, menu_id)
        if payload.parent_id in descendant_ids:
            raise ValueError("不能将菜单挂到其子菜单下（会形成循环）")
        parent = await _get_menu_orm(db, payload.parent_id)
        if parent is None:
            raise ValueError(f"父级菜单 ID {payload.parent_id} 不存在")
        menu.parent_id = payload.parent_id

    if payload.name is not None:
        menu.name = payload.name
    if payload.icon is not None:
        menu.icon = payload.icon
    if payload.view_name is not None:
        menu.view_name = payload.view_name
    if payload.sort_order is not None:
        menu.sort_order = payload.sort_order
    if payload.is_visible is not None:
        menu.is_visible = payload.is_visible

    await db.commit()
    await db.refresh(menu)
    return _menu_to_out(menu)


async def delete_menu(db: AsyncSession, menu_id: int) -> None:
    """删除菜单。

    - 系统菜单 is_system=True 不可删除
    - 存在子菜单时不可删除（要求先删子，避免误删整个分组）
    - role_menus 由 DB ON DELETE CASCADE 自动清理（role.py FK 定义）
    """
    menu = await _get_menu_orm(db, menu_id)
    if menu is None:
        raise ValueError("菜单不存在")
    if menu.is_system:
        raise ValueError("系统内置菜单不可删除")

    # 子菜单存在性
    child = (
        await db.execute(select(Menu.id).where(Menu.parent_id == menu_id).limit(1))
    ).first()
    if child is not None:
        raise ValueError("存在子菜单，请先删除子菜单")

    await db.delete(menu)
    await db.commit()


# ─── 菜单树 ──────────────────────────────────────────────────


async def get_menus_tree(db: AsyncSession) -> list:
    """返回完整菜单树（管理端，含 is_visible/is_system 等完整字段）。"""
    result = await db.execute(select(Menu).order_by(Menu.sort_order, Menu.id))
    return _build_tree(result.scalars().all())


async def get_visible_menus_tree(db: AsyncSession, role_code: str) -> list:
    """当前用户可见菜单树（渲染用 MenuNode，决策 #67）。

    - super → 全部 is_visible=True 菜单
    - 其他角色 → role_menus 关联的菜单，过滤 is_visible=True，
      并自动补全祖先分组（只要其下有任一子菜单可见就包含该分组）
    - 角色不存在（如自定义角色被删）→ 空树
    """
    if role_code == SUPER_ROLE_CODE:
        visible_ids: set[int] | None = None  # 标记取全部可见
    else:
        role = (
            await db.execute(select(Role).where(Role.code == role_code))
        ).scalar_one_or_none()
        if role is None:
            return []  # 角色不存在，无可见菜单
        result = await db.execute(
            select(RoleMenu.menu_id).where(RoleMenu.role_id == role.id)
        )
        visible_ids = {row[0] for row in result.all()}
        if not visible_ids:
            return []  # 角色未关联任何菜单

    # 拉取候选菜单：super 取全部，其他取关联菜单
    if visible_ids is None:
        cand = (await db.execute(select(Menu))).scalars().all()
    else:
        cand = (
            await db.execute(select(Menu).where(Menu.id.in_(visible_ids)))
        ).scalars().all()

    if not cand:
        return []

    # 过滤 is_visible=True，得到直接可见集合
    direct = [m for m in cand if m.is_visible]
    if not direct:
        return []

    # 祖先补全：把直接可见菜单的所有祖先分组也纳入（祖先仍需 is_visible=True 才显示）
    all_menus = (await db.execute(select(Menu))).scalars().all()
    by_id: dict[int, Menu] = {m.id: m for m in all_menus}
    full_ids: set[int] = set()
    for m in direct:
        cur: Menu | None = m
        guard: set[int] = set()  # 防御异常循环数据
        while cur is not None and cur.id not in guard:
            guard.add(cur.id)
            full_ids.add(cur.id)
            cur = by_id.get(cur.parent_id) if cur.parent_id is not None else None

    visible_menus = [m for m in all_menus if m.id in full_ids and m.is_visible]
    return _build_visible_tree(visible_menus)


# ─── 菜单排序 ────────────────────────────────────────────────


async def sort_menus(db: AsyncSession, items: list) -> list[int]:
    """批量更新菜单 sort_order。

    items: [{id, sort_order}, ...]，按 id 更新对应 sort_order。
    返回成功更新的菜单 id 列表。不存在的 id 跳过（不报错，便于前端传冗余项）。
    """
    target_ids = [it.id for it in items]
    if not target_ids:
        return []
    result = await db.execute(select(Menu).where(Menu.id.in_(target_ids)))
    menus = {m.id: m for m in result.scalars().all()}
    updated: list[int] = []
    for it in items:
        m = menus.get(it.id)
        if m is None:
            continue
        m.sort_order = it.sort_order
        updated.append(it.id)
    await db.commit()
    return updated
