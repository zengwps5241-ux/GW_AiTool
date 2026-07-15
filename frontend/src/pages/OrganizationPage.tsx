// 组织架构管理页（自建三级：公司→部门→小组）
// 功能：树形展示 + 新增/编辑/删除节点 + 成员管理 + 批量导入（JSON/CSV）
import { useCallback, useEffect, useMemo, useState } from "react";
import { I } from "@/icons";
import { Btn, Card, Input, Spinner, useToast } from "@/components/ui";
import { api } from "@/api/client";
import type {
  OrganizationInput,
  OrganizationType,
  OrganizationTreeNode,
} from "@/types";

function formatError(error: unknown): string {
  return error instanceof Error ? error.message : "未知错误";
}

/** 组织类型 → 中文标签 + 颜色 */
const TYPE_LABEL: Record<OrganizationType, string> = {
  company: "公司",
  department: "部门",
  group: "小组",
};

const TYPE_COLOR: Record<OrganizationType, string> = {
  company: "var(--accent)",
  department: "#3b82f6",
  group: "#10b981",
};

/** 简单树形节点 UI（递归） */
function OrgNode({
  node,
  depth,
  onEdit,
  onDelete,
  onAddChild,
  onRemoveMember,
}: {
  node: OrganizationTreeNode;
  depth: number;
  onEdit: (node: OrganizationTreeNode) => void;
  onDelete: (node: OrganizationTreeNode) => void;
  onAddChild: (node: OrganizationTreeNode) => void;
  onRemoveMember: (orgId: number, userId: number) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = node.children.length > 0;
  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 10px",
          paddingLeft: 10 + depth * 20,
          borderRadius: 8,
          border: "1px solid var(--line)",
          background: "var(--surface)",
          marginBottom: 4,
        }}
      >
        {hasChildren ? (
          <button
            onClick={() => setExpanded((v) => !v)}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              color: "var(--ink-3)",
              display: "flex",
              transform: expanded ? "rotate(90deg)" : "none",
              transition: "transform 120ms",
            }}
            title={expanded ? "折叠" : "展开"}
          >
            <I.ChevronRight size={14} />
          </button>
        ) : (
          <span style={{ width: 14 }} />
        )}
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: TYPE_COLOR[node.type],
            flexShrink: 0,
          }}
        />
        <span style={{ fontWeight: 500, color: "var(--ink)", fontSize: 13.5 }}>
          {node.name}
        </span>
        <span
          style={{
            fontSize: 10.5,
            color: "var(--ink-3)",
            padding: "1px 6px",
            border: "1px solid var(--line)",
            borderRadius: 4,
          }}
        >
          {TYPE_LABEL[node.type]}
        </span>
        {node.head_user_name && (
          <span style={{ fontSize: 11, color: "var(--ink-3)" }}>
            负责人：{node.head_user_name}
          </span>
        )}
        {node.members.length > 0 && (
          <span style={{ fontSize: 11, color: "var(--ink-3)" }}>
            成员 {node.members.length}
          </span>
        )}
        <div style={{ flex: 1 }} />
        <Btn variant="ghost" size="sm" onClick={() => onAddChild(node)}>
          + 子级
        </Btn>
        <Btn variant="ghost" size="sm" onClick={() => onEdit(node)}>
          编辑
        </Btn>
        <Btn variant="ghost" size="sm" onClick={() => onDelete(node)}>
          删除
        </Btn>
      </div>
      {/* 成员列表 */}
      {expanded && node.members.length > 0 && (
        <div style={{ paddingLeft: 30 + depth * 20, marginBottom: 6 }}>
          {node.members.map((m) => (
            <div
              key={`${m.user_id}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 12,
                color: "var(--ink-2)",
                padding: "3px 8px",
              }}
            >
              <I.Users size={12} />
              <span>{m.display_name || m.username}</span>
              {m.position_title && (
                <span style={{ color: "var(--ink-3)" }}>· {m.position_title}</span>
              )}
              {m.is_primary && (
                <span
                  style={{
                    fontSize: 10,
                    color: "var(--accent)",
                    border: "1px solid var(--accent-soft)",
                    borderRadius: 3,
                    padding: "0 4px",
                  }}
                >
                  主部门
                </span>
              )}
              <button
                onClick={() => onRemoveMember(node.id, m.user_id)}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--ink-3)",
                  cursor: "pointer",
                  marginLeft: "auto",
                }}
                title="移除成员"
              >
                <I.X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      {/* 子节点 */}
      {expanded &&
        hasChildren &&
        node.children.map((child) => (
          <OrgNode
            key={child.id}
            node={child}
            depth={depth + 1}
            onEdit={onEdit}
            onDelete={onDelete}
            onAddChild={onAddChild}
            onRemoveMember={onRemoveMember}
          />
        ))}
    </div>
  );
}

/** 节点编辑/新增表单 */
function OrgForm({
  initial,
  title,
  onSubmit,
  onCancel,
  submitting,
}: {
  initial: Partial<OrganizationInput> & { type?: OrganizationType };
  title: string;
  onSubmit: (data: OrganizationInput) => void;
  onCancel: () => void;
  submitting: boolean;
}) {
  const [name, setName] = useState(initial.name || "");
  const [type, setType] = useState<OrganizationType>(initial.type || "department");
  const [sortOrder, setSortOrder] = useState(String(initial.sort_order ?? 0));

  return (
    <Card style={{ padding: 16, marginBottom: 12 }}>
      <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 12, color: "var(--ink)" }}>
        {title}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <Input
          placeholder="组织名称"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <div style={{ display: "flex", gap: 8 }}>
          {(["company", "department", "group"] as OrganizationType[]).map((t) => (
            <button
              key={t}
              onClick={() => setType(t)}
              style={{
                flex: 1,
                padding: "6px 10px",
                borderRadius: 6,
                cursor: "pointer",
                fontSize: 12.5,
                border: "1px solid",
                borderColor: type === t ? TYPE_COLOR[t] : "var(--line)",
                background: type === t ? "var(--surface)" : "transparent",
                color: type === t ? TYPE_COLOR[t] : "var(--ink-2)",
                fontWeight: type === t ? 600 : 400,
              }}
            >
              {TYPE_LABEL[t]}
            </button>
          ))}
        </div>
        <Input
          placeholder="排序（数字，默认 0）"
          value={sortOrder}
          onChange={(e) => setSortOrder(e.target.value)}
        />
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Btn variant="ghost" size="sm" onClick={onCancel}>
            取消
          </Btn>
          <Btn
            variant="primary"
            size="sm"
            disabled={submitting || !name.trim()}
            onClick={() =>
              onSubmit({
                name: name.trim(),
                type,
                parent_id: initial.parent_id ?? null,
                sort_order: Number(sortOrder) || 0,
              })
            }
          >
            保存
          </Btn>
        </div>
      </div>
    </Card>
  );
}

export default function OrganizationPage() {
  const { showToast } = useToast();
  const [tree, setTree] = useState<OrganizationTreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<{
    mode: "create-root" | "create-child" | "edit" | null;
    parent?: OrganizationTreeNode;
    target?: OrganizationTreeNode;
  }>({ mode: null });
  const [submitting, setSubmitting] = useState(false);

  // 批量导入
  const [importText, setImportText] = useState("");
  const [importFormat, setImportFormat] = useState<"json" | "csv">("json");
  const [importing, setImporting] = useState(false);

  const loadTree = useCallback(async () => {
    setLoading(true);
    try {
      setTree(await api.organizationTree());
    } catch (error) {
      showToast(`加载组织架构失败：${formatError(error)}`, "error");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    void loadTree();
  }, [loadTree]);

  const nodeCount = useMemo(() => {
    let count = 0;
    const walk = (nodes: OrganizationTreeNode[]) => {
      for (const n of nodes) {
        count += 1;
        walk(n.children);
      }
    };
    walk(tree);
    return count;
  }, [tree]);

  const handleCreate = async (data: OrganizationInput) => {
    setSubmitting(true);
    try {
      await api.createOrganization(data);
      showToast("组织已创建", "success");
      setForm({ mode: null });
      await loadTree();
    } catch (error) {
      showToast(`创建失败：${formatError(error)}`, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdate = async (data: OrganizationInput) => {
    if (!form.target) return;
    setSubmitting(true);
    try {
      await api.updateOrganization(form.target.id, data);
      showToast("组织已更新", "success");
      setForm({ mode: null });
      await loadTree();
    } catch (error) {
      showToast(`更新失败：${formatError(error)}`, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (node: OrganizationTreeNode) => {
    if (!window.confirm(`确认删除「${node.name}」？存在子级或成员时将被拒绝。`)) return;
    try {
      await api.deleteOrganization(node.id);
      showToast("组织已删除", "success");
      await loadTree();
    } catch (error) {
      showToast(`删除失败：${formatError(error)}`, "error");
    }
  };

  const handleRemoveMember = async (orgId: number, userId: number) => {
    try {
      await api.removeOrganizationMember(orgId, userId);
      await loadTree();
    } catch (error) {
      showToast(`移除成员失败：${formatError(error)}`, "error");
    }
  };

  const handleImport = async () => {
    const text = importText.trim();
    if (!text) {
      showToast("请填入导入内容", "error");
      return;
    }
    setImporting(true);
    try {
      let resp;
      if (importFormat === "csv") {
        resp = await api.importOrganizationsCsv(text);
      } else {
        const rows = JSON.parse(text);
        resp = await api.importOrganizations(rows);
      }
      const r = resp.result;
      showToast(
        `导入完成：新增 ${r.created}，跳过 ${r.skipped}，错误 ${r.errors.length}`,
        r.errors.length > 0 ? "error" : "success",
      );
      if (r.errors.length > 0) {
        console.warn("导入错误明细：", r.errors);
      }
      setImportText("");
      await loadTree();
    } catch (error) {
      showToast(`导入失败：${formatError(error)}`, "error");
    } finally {
      setImporting(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 40, color: "var(--ink-3)", fontSize: 13 }}>
        加载中…
      </div>
    );
  }

  return (
    <div style={{ padding: 24, maxWidth: 900 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <div>
          <h2
            style={{
              fontSize: 18,
              fontWeight: 600,
              color: "var(--ink-1)",
              marginBottom: 4,
            }}
          >
            组织架构
          </h2>
          <div style={{ fontSize: 12, color: "var(--ink-3)" }}>
            自建三级架构（公司→部门→小组）· 共 {nodeCount} 个节点
          </div>
        </div>
        <Btn
          variant="primary"
          size="sm"
          onClick={() => setForm({ mode: "create-root" })}
        >
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <I.Plus size={14} /> 新增根组织
          </span>
        </Btn>
      </div>

      {/* 新增/编辑表单 */}
      {form.mode === "create-root" && (
        <OrgForm
          title="新增根组织"
          initial={{ type: "company", sort_order: 0 }}
          submitting={submitting}
          onSubmit={handleCreate}
          onCancel={() => setForm({ mode: null })}
        />
      )}
      {form.mode === "create-child" && form.parent && (
        <OrgForm
          title={`在「${form.parent.name}」下新增子级`}
          initial={{ type: "department", parent_id: form.parent.id, sort_order: 0 }}
          submitting={submitting}
          onSubmit={handleCreate}
          onCancel={() => setForm({ mode: null })}
        />
      )}
      {form.mode === "edit" && form.target && (
        <OrgForm
          title={`编辑「${form.target.name}」`}
          initial={{
            name: form.target.name,
            type: form.target.type,
            parent_id: form.target.parent_id,
            sort_order: form.target.sort_order,
          }}
          submitting={submitting}
          onSubmit={handleUpdate}
          onCancel={() => setForm({ mode: null })}
        />
      )}

      {/* 树形列表 */}
      {tree.length === 0 ? (
        <Card style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>
          暂无组织数据，点击右上角「新增根组织」开始
        </Card>
      ) : (
        <div>
          {tree.map((node) => (
            <OrgNode
              key={node.id}
              node={node}
              depth={0}
              onEdit={(n) => setForm({ mode: "edit", target: n })}
              onDelete={handleDelete}
              onAddChild={(n) => setForm({ mode: "create-child", parent: n })}
              onRemoveMember={handleRemoveMember}
            />
          ))}
        </div>
      )}

      {/* 批量导入 */}
      <Card style={{ padding: 16, marginTop: 24 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8, color: "var(--ink)" }}>
          批量导入
        </div>
        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          {(["json", "csv"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setImportFormat(f)}
              style={{
                padding: "4px 12px",
                borderRadius: 6,
                cursor: "pointer",
                fontSize: 12,
                border: "1px solid",
                borderColor: importFormat === f ? "var(--accent)" : "var(--line)",
                background: importFormat === f ? "var(--accent-soft)" : "transparent",
                color: importFormat === f ? "var(--accent)" : "var(--ink-2)",
                fontWeight: importFormat === f ? 600 : 400,
              }}
            >
              {f.toUpperCase()}
            </button>
          ))}
        </div>
        <textarea
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
          placeholder={
            importFormat === "csv"
              ? "name,type,parent_name,head_user_username,position_title,is_primary,sort_order\n示例集团,company,,, ,0\n研发部,department,示例集团,,,0"
              : '[\n  {"name":"示例集团","type":"company"},\n  {"name":"研发部","type":"department","parent_name":"示例集团"}\n]'
          }
          style={{
            width: "100%",
            minHeight: 120,
            padding: 10,
            borderRadius: 8,
            border: "1px solid var(--line)",
            background: "var(--bg)",
            color: "var(--ink)",
            fontSize: 12,
            fontFamily: "var(--mono, monospace)",
            resize: "vertical",
          }}
        />
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
          <Btn
            variant="primary"
            size="sm"
            disabled={importing}
            onClick={handleImport}
          >
            {importing ? <Spinner /> : "导入"}
          </Btn>
        </div>
      </Card>
    </div>
  );
}
