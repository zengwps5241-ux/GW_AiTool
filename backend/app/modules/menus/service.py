"""菜单业务服务层。

M6.1 仅包含菜单种子数据（role_menus 依赖菜单存在）。
M6.2 将补充：菜单 CRUD、GET /api/admin/menus/tree、GET /api/menus（可见菜单）、PUT /api/admin/menus/sort。

种子数据从原 SidebarVariantA getNavItems() 硬编码迁移（决策 #59）：
4 个分组节点（作战台/文件/管理/设置）+ 12 条叶子菜单。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu import Menu

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
