// 角色管理 tab（M6.6.3，决策 #69）
// 左侧角色列表 + 右侧菜单权限树（带 checkbox）
// 选中角色 → 右侧显示该角色已勾选菜单（getRoleMenus）
// 勾选变更 → updateRoleMenus 全量替换；super(is_system && code==='super') 角色只读
// 角色 CRUD：新增（code 可填）/编辑（code 不可改）/删除（is_system 不可删）
import { useCallback, useEffect, useState } from "react";
import type { MenuAdminTree, Role, RoleInput, RoleUpdateInput } from "@/types";
import { api } from "@/api/client";
import { I } from "@/icons";
import { Btn, ConfirmDialog, Input, Spinner } from "@/components/ui";

/** 判定是否为只读系统角色（super 拥有全部菜单，后端 403 拒绝改菜单） */
function isSuperRole(role: Role | null): boolean {
  return !!role && role.is_system && role.code === "super";
}

/** 收集节点自身 + 全部后代 id（勾选/取消时级联到子树） */
function collectMenuIds(node: MenuAdminTree): number[] {
  return [node.id, ...node.children.flatMap(collectMenuIds)];
}

/** 两个 Set 内容是否一致（用于 dirty 判定） */
function setsEqual(a: Set<number>, b: Set<number>): boolean {
  if (a.size !== b.size) return false;
  for (const v of a) if (!b.has(v)) return false;
  return true;
}

/** 图标按钮通用样式（编辑/删除/新增） */
const iconBtn: React.CSSProperties = {
  border: "none",
  background: "transparent",
  color: "var(--ink-3)",
  cursor: "pointer",
  padding: 2,
  borderRadius: 4,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
};

export default function RolesTab() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [menuTree, setMenuTree] = useState<MenuAdminTree[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingMenus, setLoadingMenus] = useState(false);
  const [error, setError] = useState("");

  // 当前角色菜单勾选（工作区）+ 服务端基线（dirty 判定）
  const [checkedMenus, setCheckedMenus] = useState<Set<number>>(new Set());
  const [baselineMenus, setBaselineMenus] = useState<Set<number>>(new Set());
  const [collapsedMenus, setCollapsedMenus] = useState<Set<number>>(new Set());
  const [savingMenus, setSavingMenus] = useState(false);
  const [menuError, setMenuError] = useState("");

  // CRUD 弹窗
  const [showCreate, setShowCreate] = useState(false);
  const [editTarget, setEditTarget] = useState<Role | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Role | null>(null);

  // 有未保存改动时切换角色的丢弃确认
  const [pendingSelect, setPendingSelect] = useState<number | null>(null);

  const dirty = !setsEqual(checkedMenus, baselineMenus);
  const selectedRole = roles.find((r) => r.id === selectedId) ?? null;
  const readonlyMenus = isSuperRole(selectedRole);

  // 拉取角色列表（按 sort_order 排序兜底，首次自动选中第一个）
  const fetchRoles = useCallback(async () => {
    setLoadingList(true);
    setError("");
    try {
      const list = await api.listRoles();
      list.sort((a, b) => a.sort_order - b.sort_order);
      setRoles(list);
      setSelectedId((prev) => prev ?? list[0]?.id ?? null);
    } catch {
      setError("获取角色列表失败");
    } finally {
      setLoadingList(false);
    }
  }, []);

  // 初次加载：角色列表 + 完整菜单树（菜单树静态，拉一次即可）
  useEffect(() => {
    void fetchRoles();
    void api.listMenusTree().then(setMenuTree).catch(() => {});
  }, [fetchRoles]);

  // 选中角色变化 → 拉取其菜单勾选（super 返回全部 id）
  useEffect(() => {
    if (selectedId == null) {
      setCheckedMenus(new Set());
      setBaselineMenus(new Set());
      return;
    }
    let alive = true;
    setLoadingMenus(true);
    setMenuError("");
    api
      .getRoleMenus(selectedId)
      .then((ids) => {
        if (!alive) return;
        const s = new Set(ids);
        setCheckedMenus(s);
        setBaselineMenus(new Set(s));
      })
      .catch(() => {
        if (alive) setMenuError("获取角色菜单失败");
      })
      .finally(() => {
        if (alive) setLoadingMenus(false);
      });
    return () => {
      alive = false;
    };
  }, [selectedId]);

  // 勾选/取消：级联到整棵子树（勾选父→勾选全部后代；取消父→取消全部后代）
  const handleToggleCheck = useCallback(
    (node: MenuAdminTree) => {
      if (readonlyMenus) return;
      setCheckedMenus((prev) => {
        const next = new Set(prev);
        const ids = collectMenuIds(node);
        if (prev.has(node.id)) ids.forEach((id) => next.delete(id));
        else ids.forEach((id) => next.add(id));
        return next;
      });
    },
    [readonlyMenus],
  );

  const handleToggleCollapse = useCallback((id: number) => {
    setCollapsedMenus((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // 保存菜单（全量替换；用服务端返回值回填，保证前后端一致）
  const handleSaveMenus = async () => {
    if (selectedId == null || readonlyMenus || !dirty) return;
    setSavingMenus(true);
    setMenuError("");
    try {
      const result = await api.updateRoleMenus(selectedId, [...checkedMenus]);
      const serverSet = new Set(result);
      setCheckedMenus(serverSet);
      setBaselineMenus(new Set(serverSet));
    } catch (e: any) {
      setMenuError(e?.status === 403 ? "该角色菜单不可修改" : "保存菜单失败");
    } finally {
      setSavingMenus(false);
    }
  };

  // 切换角色：有未保存改动时先弹丢弃确认
  const handleSelectRole = (id: number) => {
    if (id === selectedId) return;
    if (dirty) {
      setPendingSelect(id);
      return;
    }
    setSelectedId(id);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    try {
      await api.deleteRole(target.id);
      const remaining = roles.filter((r) => r.id !== target.id);
      setRoles(remaining);
      if (selectedId === target.id) setSelectedId(remaining[0]?.id ?? null);
    } catch (e: any) {
      setError(e?.status === 403 ? "系统角色不可删除" : "删除角色失败");
    } finally {
      setDeleteTarget(null);
    }
  };

  const showTree = selectedRole != null && !loadingMenus && !menuError;

  return (
    <div style={{ height: "100%", display: "flex", gap: 12, minHeight: 0 }}>
      {/* 左：角色列表 */}
      <div
        style={{
          width: 260,
          flexShrink: 0,
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 8,
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        }}
      >
        <div
          style={{
            padding: "10px 10px 6px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)" }}>
            角色（{roles.length}）
          </div>
          <button
            onClick={() => setShowCreate(true)}
            title="新增角色"
            style={iconBtn}
          >
            <I.Plus size={14} />
          </button>
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: "0 6px 8px" }}>
          {loadingList ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--ink-3)", fontSize: 12.5 }}>
              <Spinner /> 加载中…
            </div>
          ) : roles.length === 0 ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--ink-3)", fontSize: 12.5 }}>
              暂无角色
            </div>
          ) : (
            roles.map((role) => (
              <RoleListItem
                key={role.id}
                role={role}
                active={role.id === selectedId}
                onSelect={() => handleSelectRole(role.id)}
                onEdit={() => setEditTarget(role)}
                onDelete={() => setDeleteTarget(role)}
              />
            ))
          )}
          {error && (
            <div style={{ marginTop: 8 }}>
              <ErrorLine text={error} />
            </div>
          )}
        </div>
      </div>

      {/* 右：菜单权限树 */}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 8,
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        }}
      >
        {/* 头部：标题 + 保存 */}
        <div
          style={{
            padding: "10px 14px",
            borderBottom: "1px solid var(--line)",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-1)" }}>
            菜单权限{selectedRole ? ` · ${selectedRole.name}` : ""}
          </div>
          {readonlyMenus && (
            <span
              style={{
                fontSize: 11,
                color: "var(--ink-3)",
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
              }}
            >
              <I.Lock size={12} /> 只读
            </span>
          )}
          <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
            {dirty && !readonlyMenus && (
              <span style={{ fontSize: 11, color: "var(--warn, #ed6c02)" }}>有未保存改动</span>
            )}
            <Btn
              variant="primary"
              size="sm"
              disabled={readonlyMenus || !dirty || savingMenus}
              onClick={handleSaveMenus}
            >
              {savingMenus ? "保存中…" : "保存"}
            </Btn>
          </div>
        </div>

        {/* 树体 */}
        <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
          {selectedRole == null ? (
            <Hint>请选择左侧角色查看菜单权限</Hint>
          ) : loadingMenus ? (
            <Hint>
              <Spinner /> 加载中…
            </Hint>
          ) : menuError ? (
            <ErrorLine text={menuError} />
          ) : readonlyMenus ? (
            <div
              style={{
                padding: "8px 10px",
                fontSize: 12,
                color: "var(--ink-2)",
                background: "var(--bg-3)",
                borderRadius: 6,
                marginBottom: 8,
                display: "flex",
                gap: 6,
                alignItems: "center",
              }}
            >
              <I.Shield size={13} />
              超级管理员拥有全部菜单权限，不可修改
            </div>
          ) : null}

          {showTree &&
            menuTree.map((n) => (
              <MenuTreeNode
                key={n.id}
                node={n}
                depth={0}
                checked={checkedMenus}
                readonly={readonlyMenus}
                collapsed={collapsedMenus}
                onToggleCheck={handleToggleCheck}
                onToggleCollapse={handleToggleCollapse}
              />
            ))}
        </div>
      </div>

      {/* 新增角色弹窗 */}
      {showCreate && (
        <RoleFormModal
          editing={null}
          onClose={() => setShowCreate(false)}
          onSaved={(r) => {
            setShowCreate(false);
            // 刷新列表并选中新创建的角色
            void fetchRoles().then(() => setSelectedId(r.id));
          }}
        />
      )}

      {/* 编辑角色弹窗 */}
      {editTarget && (
        <RoleFormModal
          editing={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={() => {
            setEditTarget(null);
            void fetchRoles();
          }}
        />
      )}

      {/* 删除确认 */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="删除角色"
        message={`确认删除角色「${deleteTarget?.name ?? ""}」？该操作不可撤销。`}
        confirmText="删除"
        variant="danger"
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* 切换角色丢弃改动确认 */}
      <ConfirmDialog
        open={!!pendingSelect}
        title="切换角色"
        message="当前角色有未保存的菜单改动，切换将丢弃这些改动，确认继续？"
        confirmText="丢弃并切换"
        onConfirm={() => {
          if (pendingSelect != null) setSelectedId(pendingSelect);
          setPendingSelect(null);
        }}
        onCancel={() => setPendingSelect(null)}
      />
    </div>
  );
}

/** 角色列表项（可选中、编辑、删除；is_system 删除禁用） */
function RoleListItem({
  role,
  active,
  onSelect,
  onEdit,
  onDelete,
}: {
  role: Role;
  active: boolean;
  onSelect: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      onClick={onSelect}
      style={{
        padding: "8px 8px",
        borderRadius: 6,
        cursor: "pointer",
        background: active ? "var(--accent-soft)" : "transparent",
        marginBottom: 2,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        {role.is_system && (
          <I.Shield size={13} style={{ color: active ? "var(--accent)" : "var(--ink-3)" }} />
        )}
        <span
          style={{
            flex: 1,
            fontSize: 13,
            fontWeight: 500,
            color: active ? "var(--accent)" : "var(--ink-1)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {role.name}
        </span>
        <div style={{ display: "flex", gap: 2 }}>
          <button onClick={(e) => { e.stopPropagation(); onEdit(); }} title="编辑" style={iconBtn}>
            <I.Edit size={13} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            title={role.is_system ? "系统角色不可删除" : "删除"}
            disabled={role.is_system}
            style={{
              ...iconBtn,
              opacity: role.is_system ? 0.35 : 1,
              cursor: role.is_system ? "not-allowed" : "pointer",
            }}
          >
            <I.Trash size={13} />
          </button>
        </div>
      </div>
      <div
        style={{
          fontSize: 11,
          color: active ? "var(--accent)" : "var(--ink-3)",
          marginTop: 2,
          paddingLeft: role.is_system ? 19 : 0,
        }}
      >
        {role.code}
      </div>
    </div>
  );
}

/** 菜单树节点（递归 checkbox，支持级联与折叠） */
function MenuTreeNode({
  node,
  depth,
  checked,
  readonly,
  collapsed,
  onToggleCheck,
  onToggleCollapse,
}: {
  node: MenuAdminTree;
  depth: number;
  checked: Set<number>;
  readonly: boolean;
  collapsed: Set<number>;
  onToggleCheck: (node: MenuAdminTree) => void;
  onToggleCollapse: (id: number) => void;
}) {
  const isChecked = checked.has(node.id);
  const hasChildren = node.children.length > 0;
  const isCollapsed = collapsed.has(node.id);
  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          paddingTop: 5,
          paddingBottom: 5,
          paddingRight: 6,
          paddingLeft: depth * 16 + 6,
          fontSize: 12.5,
        }}
      >
        {/* 展开/收起 */}
        {hasChildren ? (
          <button
            onClick={() => onToggleCollapse(node.id)}
            title={isCollapsed ? "展开" : "收起"}
            style={{ ...iconBtn, color: "var(--ink-3)" }}
          >
            {isCollapsed ? <I.ChevronRight size={13} /> : <I.ChevronDown size={13} />}
          </button>
        ) : (
          <span style={{ width: 13, display: "inline-block" }} />
        )}
        {/* checkbox（自绘，支持 disabled 只读态） */}
        <span
          onClick={() => onToggleCheck(node)}
          style={{
            width: 15,
            height: 15,
            borderRadius: 3,
            border: "1.5px solid " + (isChecked ? "var(--accent)" : "var(--line-2)"),
            background: isChecked ? "var(--accent)" : "transparent",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--on-accent)",
            flexShrink: 0,
            cursor: readonly ? "not-allowed" : "pointer",
            opacity: readonly ? 0.55 : 1,
          }}
        >
          {isChecked && (
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none">
              <path
                d="m5 12 5 5L20 7"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </span>
        <span
          style={{
            color: "var(--ink-1)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {node.name}
        </span>
        <span style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{node.code}</span>
        {!node.is_visible && (
          <span style={{ fontSize: 10, color: "var(--warn, #ed6c02)" }}>隐藏</span>
        )}
      </div>
      {!isCollapsed && hasChildren && (
        <div>
          {node.children.map((c) => (
            <MenuTreeNode
              key={c.id}
              node={c}
              depth={depth + 1}
              checked={checked}
              readonly={readonly}
              collapsed={collapsed}
              onToggleCheck={onToggleCheck}
              onToggleCollapse={onToggleCollapse}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** 新增/编辑角色弹窗（编辑时 code 只读，name/description/sort_order 可改） */
function RoleFormModal({
  editing,
  onClose,
  onSaved,
}: {
  editing: Role | null;
  onClose: () => void;
  onSaved: (role: Role) => void;
}) {
  const isEdit = !!editing;
  const [code, setCode] = useState(editing?.code ?? "");
  const [name, setName] = useState(editing?.name ?? "");
  const [description, setDescription] = useState(editing?.description ?? "");
  const [sortOrder, setSortOrder] = useState(String(editing?.sort_order ?? 0));
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setErr("");
    if (!name.trim()) return setErr("请输入角色名称");
    if (!isEdit && !code.trim()) return setErr("请输入角色编码");
    const sort = Number(sortOrder) || 0;
    setSubmitting(true);
    try {
      let role: Role;
      if (isEdit && editing) {
        const payload: RoleUpdateInput = {
          name: name.trim(),
          description: description.trim() || null,
          sort_order: sort,
        };
        role = await api.updateRole(editing.id, payload);
      } else {
        const payload: RoleInput = {
          code: code.trim(),
          name: name.trim(),
          description: description.trim() || null,
          sort_order: sort,
        };
        role = await api.createRole(payload);
      }
      onSaved(role);
    } catch (e: any) {
      setErr(e?.message || (isEdit ? "更新失败" : "创建失败"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell title={isEdit ? "编辑角色" : "新增角色"} onClose={onClose}>
      <Field label="角色编码 *">
        <Input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="如 analyst"
          disabled={isEdit}
        />
        {isEdit && (
          <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}>编码创建后不可修改</div>
        )}
      </Field>
      <Field label="角色名称 *">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="如 分析师" />
      </Field>
      <Field label="描述">
        <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="可选" />
      </Field>
      <Field label="排序">
        <Input
          value={sortOrder}
          onChange={(e) => setSortOrder(e.target.value)}
          placeholder="数字，越小越靠前"
        />
      </Field>
      {err && <ErrorLine text={err} />}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
        <Btn variant="ghost" size="md" onClick={onClose}>
          取消
        </Btn>
        <Btn variant="primary" size="md" disabled={submitting} onClick={submit}>
          {submitting ? "保存中…" : isEdit ? "保存" : "创建"}
        </Btn>
      </div>
    </ModalShell>
  );
}

/** 居中淡色提示（无角色 / 加载中） */
function Hint({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
      {children}
    </div>
  );
}

/** 弹窗外壳（overlay + card，与 UsersTab 同范式） */
function ModalShell({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.35)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 380,
          background: "var(--bg)",
          border: "1px solid var(--line)",
          borderRadius: 10,
          padding: 20,
          display: "flex",
          flexDirection: "column",
          gap: 12,
          boxShadow: "var(--shadow)",
        }}
      >
        <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>{title}</div>
        {children}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--ink-2)", marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}

function ErrorLine({ text }: { text: string }) {
  return (
    <div
      style={{
        background: "var(--danger-soft)",
        color: "var(--danger)",
        padding: "6px 10px",
        borderRadius: 6,
        fontSize: 12,
        display: "flex",
        alignItems: "center",
        gap: 6,
      }}
    >
      <I.CircleAlert size={12} />
      {text}
    </div>
  );
}
