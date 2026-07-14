// 菜单管理 tab（M6.6.4，决策 #70）
// 完整菜单树（listMenusTree）展示 + 新增/编辑/删除 + 批量排序
// 系统菜单(is_system)：可编辑展示字段，但不可删除、code 不可改
// 图标选择器：Lucide 图标名列表（与 Sidebar ICON_MAP 同源）
import { useCallback, useEffect, useMemo, useState } from "react";
import type { MenuAdminTree, MenuInput, MenuUpdateInput } from "@/types";
import { api } from "@/api/client";
import { I } from "@/icons";
import { Btn, ConfirmDialog, Input, Spinner } from "@/components/ui";

/** 图标名 → I 组件映射（与 SidebarVariantA ICON_MAP 同源，自定义菜单图标回退 CircleDot） */
const ICON_MAP: Record<string, (p: { size?: number }) => JSX.Element> = {
  MessageSquare: I.MessageSquare,
  MessagesSquare: I.MessagesSquare,
  Map: I.Map,
  Target: I.Target,
  ClipboardList: I.ClipboardList,
  Folder: I.Folder,
  Folders: I.Folders,
  Brain: I.Brain,
  Puzzle: I.Puzzle,
  LayoutDashboard: I.LayoutDashboard,
  Users: I.Users,
  Settings: I.Settings,
  Server: I.Server,
  Database: I.Database,
  Bell: I.Bell,
  Book: I.Book,
  Calendar: I.Calendar,
  MessageText: I.MessageText,
  Briefcase: I.Briefcase,
  Building: I.Building,
  Network: I.Network,
  Activity: I.Activity,
  Shield: I.Shield,
  File: I.File,
  PanelLeft: I.PanelLeft,
};

/** 图标选择器可选列表 */
const ICON_OPTIONS = Object.keys(ICON_MAP);

/** 图标名 → 组件（未知回退 CircleDot） */
function iconOf(name: string | null | undefined) {
  return (name && ICON_MAP[name]) || I.CircleDot;
}

/** 扁平化菜单树为 {id, path, depth} 列表（用于父级下拉；path 形如「管理 / 系统设置」） */
interface FlatItem {
  id: number;
  path: string;
  depth: number;
}
function flattenTree(tree: MenuAdminTree[], prefix = ""): FlatItem[] {
  const out: FlatItem[] = [];
  for (const n of tree) {
    const path = prefix ? `${prefix} / ${n.name}` : n.name;
    out.push({ id: n.id, path, depth: prefix ? (prefix.split(" / ").length) : 0 });
    if (n.children.length) out.push(...flattenTree(n.children, path));
  }
  return out;
}

/** 收集节点自身 + 全部后代 id（排除作为自己的父级，防环） */
function collectSubtreeIds(node: MenuAdminTree): number[] {
  return [node.id, ...node.children.flatMap(collectSubtreeIds)];
}

/** 两个 Map 内容是否一致 */
function sortMapsEqual(a: Map<number, number>, b: Map<number, number>): boolean {
  if (a.size !== b.size) return false;
  for (const [k, v] of a) if (b.get(k) !== v) return false;
  return true;
}

/** 图标按钮通用样式 */
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

export default function MenusTab() {
  const [tree, setTree] = useState<MenuAdminTree[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // 排序：pendingSort 为当前（含本地移动）全量 sort_order；baseline 为加载时快照
  const [pendingSort, setPendingSort] = useState<Map<number, number>>(new Map());
  const [baselineSort, setBaselineSort] = useState<Map<number, number>>(new Map());
  const [savingSort, setSavingSort] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  // CRUD 弹窗
  const [createParent, setCreateParent] = useState<number | null | undefined>(undefined);
  // undefined=未开；null=根菜单；number=指定父级
  const [editTarget, setEditTarget] = useState<MenuAdminTree | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<MenuAdminTree | null>(null);

  const sortDirty = !sortMapsEqual(pendingSort, baselineSort);
  const flatList = useMemo(() => flattenTree(tree), [tree]);

  // 拉取菜单树 + 构建排序快照
  const fetchTree = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const t = await api.listMenusTree();
      setTree(t);
      const m = new Map<number, number>();
      const walk = (nodes: MenuAdminTree[]) => {
        for (const n of nodes) {
          m.set(n.id, n.sort_order);
          if (n.children.length) walk(n.children);
        }
      };
      walk(t);
      setPendingSort(new Map(m));
      setBaselineSort(new Map(m));
    } catch {
      setError("获取菜单树失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchTree();
  }, [fetchTree]);

  // 将 pendingSort 应用到树（按 sort_order 排序后渲染）
  const sortedTree = useMemo(() => {
    const apply = (nodes: MenuAdminTree[]): MenuAdminTree[] =>
      nodes
        .map((n) => ({
          ...n,
          sort_order: pendingSort.get(n.id) ?? n.sort_order,
          children: apply(n.children),
        }))
        .sort((a, b) => a.sort_order - b.sort_order);
    return apply(tree);
  }, [tree, pendingSort]);

  // 上移/下移：与相邻兄弟交换 sort_order，同步写入 pendingSort
  const handleMove = useCallback(
    (siblings: MenuAdminTree[], index: number, dir: -1 | 1) => {
      const swapWith = index + dir;
      if (swapWith < 0 || swapWith >= siblings.length) return;
      const a = siblings[index];
      const b = siblings[swapWith];
      setPendingSort((prev) => {
        const next = new Map(prev);
        const ao = prev.get(a.id) ?? a.sort_order;
        const bo = prev.get(b.id) ?? b.sort_order;
        next.set(a.id, bo);
        next.set(b.id, ao);
        return next;
      });
    },
    [],
  );

  // 收集某节点在其父级 children 中的索引（沿树查找）
  const findSiblingIndex = useCallback(
    (parentId: number | null, nodeId: number): { siblings: MenuAdminTree[]; index: number } | null => {
      const search = (nodes: MenuAdminTree[]): { siblings: MenuAdminTree[]; index: number } | null => {
        for (let i = 0; i < nodes.length; i++) {
          if (nodes[i].id === nodeId) return { siblings: nodes, index: i };
          const sub = search(nodes[i].children);
          if (sub) return sub;
        }
        return null;
      };
      if (parentId == null) return search(sortedTree);
      // 父级非根：先定位父节点再在其 children 中找
      const findParent = (nodes: MenuAdminTree[]): MenuAdminTree | null => {
        for (const n of nodes) {
          if (n.id === parentId) return n;
          const sub = findParent(n.children);
          if (sub) return sub;
        }
        return null;
      };
      const parent = findParent(sortedTree);
      if (!parent) return null;
      return search(parent.children);
    },
    [sortedTree],
  );

  const handleSaveSort = async () => {
    if (!sortDirty) return;
    setSavingSort(true);
    setError("");
    try {
      const items = [...pendingSort.entries()].map(([id, sort_order]) => ({
        id,
        sort_order,
      }));
      await api.updateMenuSort(items);
      await fetchTree();
    } catch {
      setError("保存排序失败");
    } finally {
      setSavingSort(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    try {
      await api.deleteMenu(target.id);
      await fetchTree();
    } catch (e: any) {
      const msg = e?.responseText || "";
      setError(
        e?.status === 400
          ? msg || "删除失败：请先删除子菜单"
          : e?.status === 404
            ? "菜单不存在"
            : "删除菜单失败",
      );
    } finally {
      setDeleteTarget(null);
    }
  };

  const handleToggleCollapse = useCallback((id: number) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", gap: 10, minHeight: 0 }}>
      {/* 工具栏 */}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <div style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
          共 {flatList.length} 个菜单节点
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          {sortDirty && (
            <span style={{ fontSize: 11, color: "var(--warn, #ed6c02)" }}>有未保存排序</span>
          )}
          <Btn
            variant="ghost"
            size="sm"
            disabled={!sortDirty || savingSort}
            onClick={handleSaveSort}
          >
            {savingSort ? "保存中…" : "保存排序"}
          </Btn>
          <Btn variant="primary" size="sm" onClick={() => setCreateParent(null)}>
            <I.Plus size={14} /> 新增根菜单
          </Btn>
        </div>
      </div>

      {error && <ErrorLine text={error} />}

      {/* 树体 */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: "auto",
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 8,
          padding: 8,
        }}
      >
        {loading ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
            <Spinner /> 加载中…
          </div>
        ) : sortedTree.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
            暂无菜单
          </div>
        ) : (
          sortedTree.map((n) => (
            <MenuTreeNode
              key={n.id}
              node={n}
              depth={0}
              collapsed={collapsed}
              onToggleCollapse={handleToggleCollapse}
              onMoveItem={handleMove}
              onAddChild={(parentId) => setCreateParent(parentId)}
              onEdit={(node) => setEditTarget(node)}
              onDelete={(node) => setDeleteTarget(node)}
              findSiblingIndex={findSiblingIndex}
            />
          ))
        )}
      </div>

      {/* 新增菜单弹窗 */}
      {createParent !== undefined && (
        <MenuFormModal
          editing={null}
          parentId={createParent}
          flatList={flatList}
          onClose={() => setCreateParent(undefined)}
          onSaved={() => {
            setCreateParent(undefined);
            void fetchTree();
          }}
        />
      )}

      {/* 编辑菜单弹窗 */}
      {editTarget && (
        <MenuFormModal
          editing={editTarget}
          parentId={editTarget.parent_id}
          flatList={flatList}
          onClose={() => setEditTarget(null)}
          onSaved={() => {
            setEditTarget(null);
            void fetchTree();
          }}
        />
      )}

      {/* 删除确认 */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="删除菜单"
        message={`确认删除菜单「${deleteTarget?.name ?? ""}」？`}
        confirmText="删除"
        variant="danger"
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

/** 菜单树节点（递归，含展开/收起 + 行内操作） */
function MenuTreeNode({
  node,
  depth,
  collapsed,
  onToggleCollapse,
  onMoveItem,
  onAddChild,
  onEdit,
  onDelete,
  findSiblingIndex,
}: {
  node: MenuAdminTree;
  depth: number;
  collapsed: Set<number>;
  onToggleCollapse: (id: number) => void;
  /** 上移/下移：传入本节点 id 与方向，由父级查其兄弟集合后交换 sort_order */
  onMoveItem: (siblings: MenuAdminTree[], index: number, dir: -1 | 1) => void;
  onAddChild: (parentId: number) => void;
  onEdit: (node: MenuAdminTree) => void;
  onDelete: (node: MenuAdminTree) => void;
  findSiblingIndex: (parentId: number | null, nodeId: number) =>
    { siblings: MenuAdminTree[]; index: number } | null;
}) {
  const hasChildren = node.children.length > 0;
  const isCollapsed = collapsed.has(node.id);
  const Icon = iconOf(node.icon);
  // 本节点在父级 children 中的兄弟集合与索引（用于上移/下移边界判定）
  const pos = findSiblingIndex(node.parent_id, node.id);
  const sib = pos?.siblings ?? [];
  const idx = pos?.index ?? 0;
  const isFirst = idx === 0;
  const isLast = idx === sib.length - 1;

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "6px 6px",
          paddingLeft: depth * 18 + 4,
          fontSize: 13,
          borderRadius: 6,
        }}
      >
        {/* 展开/收起 / 占位 */}
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

        {/* 图标 */}
        <span style={{ color: "var(--ink-2)", display: "inline-flex" }}>
          <Icon size={14} />
        </span>

        {/* 名称 + code */}
        <span style={{ color: "var(--ink-1)", fontWeight: 500 }}>{node.name}</span>
        <span style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{node.code}</span>

        {/* 标签 */}
        {node.is_system && (
          <TagPill color="var(--accent-2)" bg="var(--accent-soft)">系统</TagPill>
        )}
        {!node.is_visible && (
          <TagPill color="var(--warn, #ed6c02)" bg="var(--warn-soft, #fff3e0)">隐藏</TagPill>
        )}
        {node.view_name && (
          <TagPill color="var(--ink-3)" bg="var(--bg-3)">view:{node.view_name}</TagPill>
        )}

        {/* 操作 */}
        <div style={{ marginLeft: "auto", display: "flex", gap: 2 }}>
          <button onClick={() => onMoveItem(sib, idx, -1)} disabled={isFirst} title="上移"
            style={{ ...iconBtn, opacity: isFirst ? 0.3 : 1, cursor: isFirst ? "not-allowed" : "pointer" }}>
            <I.ChevronUp size={13} />
          </button>
          <button onClick={() => onMoveItem(sib, idx, 1)} disabled={isLast} title="下移"
            style={{ ...iconBtn, opacity: isLast ? 0.3 : 1, cursor: isLast ? "not-allowed" : "pointer" }}>
            <I.ChevronDown size={13} />
          </button>
          <button onClick={() => onAddChild(node.id)} title="新增子菜单" style={iconBtn}>
            <I.Plus size={13} />
          </button>
          <button onClick={() => onEdit(node)} title="编辑" style={iconBtn}>
            <I.Edit size={13} />
          </button>
          <button
            onClick={() => onDelete(node)}
            disabled={node.is_system}
            title={node.is_system ? "系统菜单不可删除" : "删除"}
            style={{
              ...iconBtn,
              opacity: node.is_system ? 0.3 : 1,
              cursor: node.is_system ? "not-allowed" : "pointer",
            }}
          >
            <I.Trash size={13} />
          </button>
        </div>
      </div>

      {/* 子节点 */}
      {!isCollapsed && hasChildren && (
        <div>
          {node.children.map((c) => (
            <MenuTreeNode
              key={c.id}
              node={c}
              depth={depth + 1}
              collapsed={collapsed}
              onToggleCollapse={onToggleCollapse}
              onMoveItem={onMoveItem}
              onAddChild={onAddChild}
              onEdit={onEdit}
              onDelete={onDelete}
              findSiblingIndex={findSiblingIndex}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** 新增/编辑菜单弹窗（编辑时 code 只读；父级下拉排除自身及后代防环） */
function MenuFormModal({
  editing,
  parentId,
  flatList,
  onClose,
  onSaved,
}: {
  editing: MenuAdminTree | null;
  parentId: number | null;
  flatList: FlatItem[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!editing;
  const [code, setCode] = useState(editing?.code ?? "");
  const [name, setName] = useState(editing?.name ?? "");
  const [parentMenuId, setParentMenuId] = useState<number | null>(parentId);
  const [icon, setIcon] = useState<string | null>(editing?.icon ?? null);
  const [viewName, setViewName] = useState(editing?.view_name ?? "");
  const [sortOrder, setSortOrder] = useState(String(editing?.sort_order ?? 0));
  const [isVisible, setIsVisible] = useState(editing?.is_visible ?? true);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");

  // 父级下拉可选项：编辑时排除自身及后代（防环）；根选项「（无，作为根菜单）」
  const parentOptions = useMemo(() => {
    if (!isEdit || !editing) return flatList;
    const exclude = new Set(collectSubtreeIds(editing));
    return flatList.filter((f) => !exclude.has(f.id));
  }, [flatList, isEdit, editing]);

  const submit = async () => {
    setErr("");
    if (!name.trim()) return setErr("请输入菜单名称");
    if (!isEdit && !code.trim()) return setErr("请输入菜单编码");
    const sort = Number(sortOrder) || 0;
    setSubmitting(true);
    try {
      if (isEdit && editing) {
        const payload: MenuUpdateInput = {
          name: name.trim(),
          parent_id: parentMenuId,
          icon,
          view_name: viewName.trim() || null,
          sort_order: sort,
          is_visible: isVisible,
        };
        await api.updateMenu(editing.id, payload);
      } else {
        const payload: MenuInput = {
          code: code.trim(),
          name: name.trim(),
          parent_id: parentMenuId,
          icon,
          view_name: viewName.trim() || null,
          sort_order: sort,
          is_visible: isVisible,
        };
        await api.createMenu(payload);
      }
      onSaved();
    } catch (e: any) {
      setErr(e?.message || (isEdit ? "更新失败" : "创建失败"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell title={isEdit ? "编辑菜单" : "新增菜单"} onClose={onClose}>
      <Field label="菜单编码 *">
        <Input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="如 consultant_workspace"
          disabled={isEdit}
        />
        {isEdit && (
          <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}>编码创建后不可修改</div>
        )}
      </Field>
      <Field label="菜单名称 *">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="如 顾问作战台" />
      </Field>
      <Field label="父级菜单">
        <select
          value={parentMenuId == null ? "" : String(parentMenuId)}
          onChange={(e) => setParentMenuId(e.target.value ? Number(e.target.value) : null)}
          style={selectStyle}
        >
          <option value="">（无，作为根菜单）</option>
          {parentOptions.map((f) => (
            <option key={f.id} value={String(f.id)}>{f.path}</option>
          ))}
        </select>
      </Field>
      <Field label="图标">
        <IconPicker value={icon} onChange={setIcon} />
      </Field>
      <Field label="视图名称（view_name）">
        <Input
          value={viewName}
          onChange={(e) => setViewName(e.target.value)}
          placeholder="叶子菜单对应前端视图，如 chat；分组留空"
        />
      </Field>
      <Field label="排序">
        <Input
          value={sortOrder}
          onChange={(e) => setSortOrder(e.target.value)}
          placeholder="数字，同层级内越小越靠前"
        />
      </Field>
      <Field label="是否可见">
        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--ink-2)", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={isVisible}
            onChange={(e) => setIsVisible(e.target.checked)}
          />
          可见（关闭后该菜单不在侧边栏显示）
        </label>
      </Field>
      {err && <ErrorLine text={err} />}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
        <Btn variant="ghost" size="md" onClick={onClose}>取消</Btn>
        <Btn variant="primary" size="md" disabled={submitting} onClick={submit}>
          {submitting ? "保存中…" : isEdit ? "保存" : "创建"}
        </Btn>
      </div>
    </ModalShell>
  );
}

/** 图标选择器：当前值预览 + 可选项网格（单选） */
function IconPicker({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (name: string | null) => void;
}) {
  const Current = iconOf(value);
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, fontSize: 12, color: "var(--ink-3)" }}>
        <span style={{ color: "var(--ink-2)", display: "inline-flex" }}><Current size={16} /></span>
        <span>{value || "未选择（回退默认图标）"}</span>
        {value && (
          <button onClick={() => onChange(null)} style={{ ...iconBtn, fontSize: 11 }}>清除</button>
        )}
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(40px, 1fr))",
          gap: 4,
          maxHeight: 160,
          overflow: "auto",
          padding: 6,
          border: "1px solid var(--line)",
          borderRadius: 6,
          background: "var(--bg)",
        }}
      >
        {ICON_OPTIONS.map((name) => {
          const Comp = ICON_MAP[name];
          const active = value === name;
          return (
            <button
              key={name}
              title={name}
              onClick={() => onChange(name)}
              style={{
                height: 34,
                border: active ? "1.5px solid var(--accent)" : "1px solid var(--line)",
                borderRadius: 6,
                background: active ? "var(--accent-soft)" : "var(--surface)",
                color: active ? "var(--accent)" : "var(--ink-2)",
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Comp size={16} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

const selectStyle: React.CSSProperties = {
  padding: "8px",
  fontSize: 13,
  borderRadius: 6,
  border: "1px solid var(--line)",
  background: "var(--surface)",
  color: "var(--ink-1)",
  outline: "none",
  width: "100%",
};

/** 小标签 pill */
function TagPill({ color, bg, children }: { color: string; bg: string; children: React.ReactNode }) {
  return (
    <span
      style={{
        fontSize: 10,
        color,
        background: bg,
        padding: "1px 6px",
        borderRadius: 4,
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

/** 弹窗外壳（overlay + card，与 UsersTab/RolesTab 同范式） */
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
          width: 420,
          maxHeight: "88vh",
          overflow: "auto",
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
