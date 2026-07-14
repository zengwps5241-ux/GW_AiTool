"""菜单管理 API 测试（方案 A：自引用树 + 角色-菜单可见性关联）。

覆盖 M6.2 验收：
- 权限（管理端仅 admin/super，普通用户 403；GET /api/menus 任意登录用户 200）
- 内置菜单种子（4 分组 + 12 叶子，全 is_system=True）
- 菜单 CRUD（创建/查询/更新/删除；系统菜单不可删；code 唯一；parent 校验；循环/自引用检测）
- 菜单树 GET /api/admin/menus/tree（4 根分组各含子）
- 可见菜单 GET /api/menus（super 16 / admin 15 缺 loginWhitelist / user 10）
- 批量排序 PUT /api/admin/menus/sort
"""

# 分组节点 code
GROUP_CODES = {"group_zhanzuo", "group_file", "group_admin", "group_setting"}
# 全部叶子 code（12 条）
LEAF_CODES = {
    "chat", "businessMap", "marketingMap", "visitRecords",
    "personalSpace", "teamSpaces",
    "agents", "skills", "usage", "feedback", "loginWhitelist",
    "systemSettings",
}


# ─── 辅助 ────────────────────────────────────────────────────


async def _list_menus(admin_client) -> list[dict]:
    """平铺菜单列表。"""
    res = await admin_client.get("/api/admin/menus")
    assert res.status_code == 200, res.text
    return res.json()


async def _tree(admin_client) -> list[dict]:
    """管理端完整菜单树。"""
    res = await admin_client.get("/api/admin/menus/tree")
    assert res.status_code == 200, res.text
    return res.json()


async def _my_menus(client) -> list[dict]:
    """当前登录用户可见菜单树。"""
    res = await client.get("/api/menus")
    assert res.status_code == 200, res.text
    return res.json()


def _collect_codes(nodes: list[dict] | dict) -> set[str]:
    """递归收集树中所有 code。"""
    if isinstance(nodes, dict):
        nodes = [nodes]
    codes: set[str] = set()
    for n in nodes:
        codes.add(n["code"])
        codes |= _collect_codes(n.get("children", []))
    return codes


def _find(nodes: list[dict], code: str) -> dict | None:
    """在树中按 code 查节点。"""
    for n in nodes:
        if n["code"] == code:
            return n
        found = _find(n.get("children", []), code)
        if found is not None:
            return found
    return None


async def _menu_id(admin_client, code: str) -> int:
    """按 code 取菜单 id。"""
    for m in await _list_menus(admin_client):
        if m["code"] == code:
            return m["id"]
    raise AssertionError(f"菜单 {code} 不存在")


# ─── 权限：管理端 ─────────────────────────────────────────────


async def test_admin_menus_forbidden_for_user(logged_in_client):
    """普通用户不能访问菜单管理接口。"""
    res = await logged_in_client.get("/api/admin/menus")
    assert res.status_code == 403


async def test_admin_menus_allowed_for_admin(admin_client):
    res = await admin_client.get("/api/admin/menus")
    assert res.status_code == 200


async def test_admin_menus_allowed_for_super(super_client):
    res = await super_client.get("/api/admin/menus")
    assert res.status_code == 200


async def test_admin_menus_tree_forbidden_for_user(logged_in_client):
    res = await logged_in_client.get("/api/admin/menus/tree")
    assert res.status_code == 403


async def test_admin_menus_sort_forbidden_for_user(logged_in_client):
    res = await logged_in_client.put(
        "/api/admin/menus/sort", json={"items": []}
    )
    assert res.status_code == 403


# ─── 权限：用户端可见菜单 ─────────────────────────────────────


async def test_my_menus_requires_login(client):
    """未登录访问 GET /api/menus → 401。"""
    res = await client.get("/api/menus")
    assert res.status_code == 401


async def test_my_menus_allowed_for_normal_user(logged_in_client):
    """任意登录用户均可访问 GET /api/menus（无需 admin）。"""
    res = await logged_in_client.get("/api/menus")
    assert res.status_code == 200


# ─── 种子数据 ────────────────────────────────────────────────


async def test_seed_menus_count(admin_client):
    """种子：4 分组 + 12 叶子 = 16 条，全 is_system=True。"""
    menus = await _list_menus(admin_client)
    assert len(menus) == 16, f"应 16 条种子菜单，实际 {len(menus)}"
    for m in menus:
        assert m["is_system"] is True, f"{m['code']} 应为系统菜单"
    codes = {m["code"] for m in menus}
    assert codes == GROUP_CODES | LEAF_CODES


# ─── 菜单 CRUD ───────────────────────────────────────────────


async def test_create_custom_menu(admin_client):
    """创建自定义菜单（is_system 恒 False），挂在分组下。"""
    parent_id = await _menu_id(admin_client, "group_admin")
    res = await admin_client.post(
        "/api/admin/menus",
        json={
            "code": "customAdmin",
            "name": "自定义管理项",
            "parent_id": parent_id,
            "icon": "Star",
            "view_name": "customAdmin",
            "sort_order": 99,
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["code"] == "customAdmin"
    assert data["is_system"] is False
    assert data["parent_id"] == parent_id
    assert data["id"] > 0


async def test_create_menu_duplicate_code(admin_client):
    """code 唯一约束 → 400。"""
    res = await admin_client.post(
        "/api/admin/menus", json={"code": "chat", "name": "重复"}
    )
    assert res.status_code == 400


async def test_create_menu_invalid_parent(admin_client):
    """parent_id 不存在 → 400。"""
    res = await admin_client.post(
        "/api/admin/menus",
        json={"code": "orphan", "name": "孤儿", "parent_id": 99999},
    )
    assert res.status_code == 400


async def test_get_menu(admin_client):
    mid = await _menu_id(admin_client, "chat")
    res = await admin_client.get(f"/api/admin/menus/{mid}")
    assert res.status_code == 200
    assert res.json()["code"] == "chat"


async def test_get_menu_not_found(admin_client):
    res = await admin_client.get("/api/admin/menus/99999")
    assert res.status_code == 404


async def test_update_menu(admin_client):
    """更新展示字段；code 与 is_system 不可改。"""
    mid = await _menu_id(admin_client, "chat")
    res = await admin_client.put(
        f"/api/admin/menus/{mid}",
        json={"name": "对话(改名)", "icon": "MessageCircle", "sort_order": 50},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["name"] == "对话(改名)"
    assert data["icon"] == "MessageCircle"
    assert data["sort_order"] == 50
    # code / is_system 不变
    assert data["code"] == "chat"
    assert data["is_system"] is True


async def test_update_menu_not_found(admin_client):
    res = await admin_client.put("/api/admin/menus/99999", json={"name": "x"})
    assert res.status_code == 404


async def test_update_menu_self_parent_forbidden(admin_client):
    """自引用：parent_id 设为自身 → 400。"""
    mid = await _menu_id(admin_client, "chat")
    res = await admin_client.put(
        f"/api/admin/menus/{mid}", json={"parent_id": mid}
    )
    assert res.status_code == 400


async def test_update_menu_circular_forbidden(admin_client):
    """循环引用：把祖先挂到其后代下 → 400。"""
    group_id = await _menu_id(admin_client, "group_admin")
    # 建两个自定义菜单 A(parent=group) ← B(parent=A)
    a = (await admin_client.post(
        "/api/admin/menus", json={"code": "nodeA", "name": "A", "parent_id": group_id}
    )).json()["id"]
    b = (await admin_client.post(
        "/api/admin/menus", json={"code": "nodeB", "name": "B", "parent_id": a}
    )).json()["id"]
    # 把 A 的 parent 改为 B（B 是 A 的后代）→ 应拒绝
    res = await admin_client.put(
        f"/api/admin/menus/{a}", json={"parent_id": b}
    )
    assert res.status_code == 400


async def test_delete_custom_menu(admin_client):
    """自定义叶子菜单可删除。"""
    created = await admin_client.post(
        "/api/admin/menus", json={"code": "tempLeaf", "name": "临时"}
    )
    mid = created.json()["id"]
    res = await admin_client.delete(f"/api/admin/menus/{mid}")
    assert res.status_code == 204
    # 删除后查不到
    assert (await admin_client.get(f"/api/admin/menus/{mid}")).status_code == 404


async def test_delete_system_menu_forbidden(admin_client):
    """系统菜单不可删除 → 400。"""
    mid = await _menu_id(admin_client, "chat")
    res = await admin_client.delete(f"/api/admin/menus/{mid}")
    assert res.status_code == 400


async def test_delete_menu_with_children_forbidden(admin_client):
    """有子菜单的节点不可删除（需先删子）→ 400。"""
    mid = await _menu_id(admin_client, "group_admin")
    res = await admin_client.delete(f"/api/admin/menus/{mid}")
    assert res.status_code == 400


# ─── 菜单树 ──────────────────────────────────────────────────


async def test_menus_tree_structure(admin_client):
    """GET /api/admin/menus/tree：4 个根分组，各含子节点。"""
    tree = await _tree(admin_client)
    root_codes = {n["code"] for n in tree}
    assert root_codes == GROUP_CODES, f"根节点应为 4 分组，实际 {root_codes}"

    # group_admin 应包含 5 个管理叶子
    admin_group = _find(tree, "group_admin")
    assert admin_group is not None
    child_codes = {c["code"] for c in admin_group["children"]}
    assert child_codes == {"agents", "skills", "usage", "feedback", "loginWhitelist"}

    # group_zhanzuo 应包含 4 个作战台叶子
    zz = _find(tree, "group_zhanzuo")
    assert zz is not None
    assert {c["code"] for c in zz["children"]} == {
        "chat", "businessMap", "marketingMap", "visitRecords"
    }


# ─── 可见菜单 GET /api/menus（三角色）──────────────────────────


async def test_my_menus_super_all(super_client):
    """super 可见全部 16 个菜单。"""
    tree = await _my_menus(super_client)
    codes = _collect_codes(tree)
    assert codes == GROUP_CODES | LEAF_CODES
    assert len(codes) == 16


async def test_my_menus_admin_excludes_login_whitelist(admin_client):
    """admin 可见除 loginWhitelist 外的全部 15 个菜单。

    注意：admin_client 的 user.role == "admin"，用其自身 cookie 调 /api/menus。
    """
    tree = await _my_menus(admin_client)
    codes = _collect_codes(tree)
    assert "loginWhitelist" not in codes
    assert len(codes) == 15, f"admin 应见 15 个，实际 {len(codes)}"


async def test_my_menus_user_minimal(logged_in_client):
    """普通 user 可见 10 个：作战台4 + 文件2 + agents + 3 个对应分组。"""
    tree = await _my_menus(logged_in_client)
    codes = _collect_codes(tree)
    expected = {
        # 分组（管理分组因 agents 可见而纳入）
        "group_zhanzuo", "group_file", "group_admin",
        # 叶子
        "chat", "businessMap", "marketingMap", "visitRecords",
        "personalSpace", "teamSpaces",
        "agents",
    }
    assert codes == expected, f"user 可见菜单不符，实际 {codes}"
    # 不应可见
    for hidden in ("skills", "usage", "feedback", "loginWhitelist",
                    "systemSettings", "group_setting"):
        assert hidden not in codes, f"user 不应可见 {hidden}"


async def test_my_menus_user_group_structure(logged_in_client):
    """user 可见菜单树：管理分组下只有 agents 一个叶子（其余管理叶子被过滤）。"""
    tree = await _my_menus(logged_in_client)
    admin_group = _find(tree, "group_admin")
    assert admin_group is not None, "user 应见管理分组（因 agents 可见）"
    assert {c["code"] for c in admin_group["children"]} == {"agents"}
    # 设置分组不可见
    assert _find(tree, "group_setting") is None


async def test_my_menus_respects_visibility(admin_client):
    """is_visible=False 的菜单对 admin 也不可见。"""
    # 把 chat 设为不可见
    mid = await _menu_id(admin_client, "chat")
    res = await admin_client.put(
        f"/api/admin/menus/{mid}", json={"is_visible": False}
    )
    assert res.status_code == 200
    # admin 自身 cookie 查可见菜单，chat 不应出现
    tree = await _my_menus(admin_client)
    assert "chat" not in _collect_codes(tree)


# ─── 批量排序 ────────────────────────────────────────────────


async def test_sort_menus(admin_client):
    """PUT /api/admin/menus/sort 批量更新 sort_order。"""
    # 建三个自定义根菜单（默认 sort_order=0）
    ids = []
    for code in ("sortA", "sortB", "sortC"):
        r = await admin_client.post(
            "/api/admin/menus", json={"code": code, "name": code}
        )
        assert r.status_code == 201
        ids.append(r.json()["id"])

    # 设定排序：C=100, A=101, B=102 → 期望顺序 C, A, B
    res = await admin_client.put(
        "/api/admin/menus/sort",
        json={"items": [
            {"id": ids[2], "sort_order": 100},
            {"id": ids[0], "sort_order": 101},
            {"id": ids[1], "sort_order": 102},
        ]},
    )
    assert res.status_code == 200, res.text
    assert set(res.json()) == set(ids)

    # 在平铺列表中按 sort_order 过滤自定义项，验证相邻顺序
    menus = await _list_menus(admin_client)
    custom = [m for m in menus if m["code"] in ("sortA", "sortB", "sortC")]
    custom.sort(key=lambda m: m["sort_order"])
    assert [m["code"] for m in custom] == ["sortC", "sortA", "sortB"]


async def test_sort_menus_skip_unknown(admin_client):
    """不存在的 id 跳过（不报错）。"""
    mid = await _menu_id(admin_client, "chat")
    res = await admin_client.put(
        "/api/admin/menus/sort",
        json={"items": [
            {"id": mid, "sort_order": 7},
            {"id": 99999, "sort_order": 1},
        ]},
    )
    assert res.status_code == 200
    # 仅真实 id 被更新
    assert res.json() == [mid]
    menus = await _list_menus(admin_client)
    assert next(m for m in menus if m["id"] == mid)["sort_order"] == 7
