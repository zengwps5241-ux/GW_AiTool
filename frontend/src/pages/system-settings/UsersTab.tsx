// 用户管理 tab（M6.6.2，决策 #66）
// 左侧组织架构树（点击节点筛选）+ 右侧用户列表表格
// 顶部：搜索 + 角色筛选 + 状态筛选 + 新增按钮
// 操作列：角色分配(select) / 状态切换(启用·禁用) / 重置密码 / 审批(通过·驳回)
// 待审批用户(pending_approval)行高亮
import { useCallback, useEffect, useState } from "react";
import type { AdminUser, AdminUserFilter, OrganizationTreeNode, Role } from "@/types";
import { api } from "@/api/client";
import { I } from "@/icons";
import { Btn, Input, Spinner } from "@/components/ui";

const STATUS_META: Record<string, { label: string; color: string; bg: string }> = {
  active: { label: "启用", color: "var(--success, #2e7d32)", bg: "var(--success-soft, #e8f5e9)" },
  disabled: { label: "禁用", color: "var(--danger)", bg: "var(--danger-soft)" },
  pending_approval: { label: "待审批", color: "var(--warn, #ed6c02)", bg: "var(--warn-soft, #fff3e0)" },
};

/** 组织树递归节点（仅展示 + 选中筛选，无 CRUD） */
function OrgTreeItem({
  node,
  depth,
  selectedId,
  onSelect,
}: {
  node: OrganizationTreeNode;
  depth: number;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const active = selectedId === node.id;
  return (
    <div>
      <button
        onClick={() => onSelect(node.id)}
        style={{
          width: "100%",
          textAlign: "left",
          padding: "5px 8px",
          paddingLeft: 8 + depth * 12,
          fontSize: 12.5,
          color: active ? "var(--accent)" : "var(--ink-2)",
          background: active ? "var(--accent-soft)" : "transparent",
          border: "none",
          borderRadius: 4,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <I.Building size={12} />
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {node.name}
        </span>
      </button>
      {node.children.map((c) => (
        <OrgTreeItem
          key={c.id}
          node={c}
          depth={depth + 1}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

export default function UsersTab() {
  const [orgTree, setOrgTree] = useState<OrganizationTreeNode[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [error, setError] = useState("");

  // 筛选
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [orgFilter, setOrgFilter] = useState<number | null>(null);

  // 弹窗
  const [showCreate, setShowCreate] = useState(false);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);

  // 拉组织树 + 角色（一次）
  useEffect(() => {
    Promise.all([api.organizationTree(), api.listRoles()])
      .then(([tree, r]) => {
        setOrgTree(tree);
        setRoles(r);
      })
      .catch(() => {});
  }, []);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const filter: AdminUserFilter = {};
      if (search.trim()) filter.search = search.trim();
      if (roleFilter) filter.role = roleFilter;
      if (statusFilter) filter.status = statusFilter;
      if (orgFilter != null) filter.organization_id = orgFilter;
      setUsers(await api.listAdminUsers(filter));
    } catch {
      setError("获取用户列表失败");
    } finally {
      setLoading(false);
    }
  }, [search, roleFilter, statusFilter, orgFilter]);

  useEffect(() => {
    void fetchUsers();
  }, [fetchUsers]);

  const refresh = async () => {
    await fetchUsers();
  };

  const handleToggleStatus = async (u: AdminUser) => {
    const next = u.status === "active" ? "disabled" : "active";
    setActionLoading(u.id);
    try {
      await api.updateUserStatus(u.id, next);
      await refresh();
    } catch {
      setError("状态变更失败");
    } finally {
      setActionLoading(null);
    }
  };

  const handleRoleChange = async (u: AdminUser, roleCode: string) => {
    if (!roleCode || roleCode === u.role) return;
    setActionLoading(u.id);
    try {
      await api.assignUserRole(u.id, roleCode);
      await refresh();
    } catch {
      setError("角色变更失败");
    } finally {
      setActionLoading(null);
    }
  };

  const handleApprove = async (u: AdminUser, action: "approve" | "reject") => {
    setActionLoading(u.id);
    try {
      await api.approveUser(u.id, action);
      await refresh();
    } catch {
      setError("审批操作失败");
    } finally {
      setActionLoading(null);
    }
  };

  const selectStyle: React.CSSProperties = {
    padding: "6px 8px",
    fontSize: 12.5,
    borderRadius: 6,
    border: "1px solid var(--line)",
    background: "var(--surface)",
    color: "var(--ink-1)",
    outline: "none",
  };

  const thStyle: React.CSSProperties = {
    textAlign: "left",
    padding: "8px 10px",
    fontSize: 11.5,
    fontWeight: 600,
    color: "var(--ink-3)",
    borderBottom: "1px solid var(--line)",
    whiteSpace: "nowrap",
  };
  const tdStyle: React.CSSProperties = {
    padding: "8px 10px",
    fontSize: 12.5,
    color: "var(--ink-1)",
    borderBottom: "1px solid var(--line)",
    verticalAlign: "middle",
  };

  return (
    <div style={{ height: "100%", display: "flex", gap: 12, minHeight: 0 }}>
      {/* 左：组织树 */}
      <div
        style={{
          width: 220,
          flexShrink: 0,
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 8,
          padding: 8,
          overflow: "auto",
        }}
      >
        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", padding: "4px 8px 6px" }}>
          组织架构
        </div>
        <button
          onClick={() => setOrgFilter(null)}
          style={{
            width: "100%",
            textAlign: "left",
            padding: "5px 8px",
            fontSize: 12.5,
            color: orgFilter === null ? "var(--accent)" : "var(--ink-2)",
            background: orgFilter === null ? "var(--accent-soft)" : "transparent",
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
          }}
        >
          全部用户
        </button>
        {orgTree.map((n) => (
          <OrgTreeItem
            key={n.id}
            node={n}
            depth={0}
            selectedId={orgFilter}
            onSelect={setOrgFilter}
          />
        ))}
      </div>

      {/* 右：用户列表 */}
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 10 }}>
        {/* 工具栏 */}
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <Input
            placeholder="搜索用户名/手机号"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 200 }}
          />
          <select style={selectStyle} value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
            <option value="">全部角色</option>
            {roles.map((r) => (
              <option key={r.id} value={r.code}>
                {r.name}
              </option>
            ))}
          </select>
          <select
            style={selectStyle}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">全部状态</option>
            <option value="active">启用</option>
            <option value="disabled">禁用</option>
            <option value="pending_approval">待审批</option>
          </select>
          <div style={{ marginLeft: "auto" }}>
            <Btn variant="primary" size="sm" onClick={() => setShowCreate(true)}>
              <I.Plus size={14} /> 新增用户
            </Btn>
          </div>
        </div>

        {error && (
          <div
            style={{
              background: "var(--danger-soft)",
              color: "var(--danger)",
              padding: "8px 12px",
              borderRadius: 6,
              fontSize: 12.5,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <I.CircleAlert size={13} />
            {error}
          </div>
        )}

        {/* 表格 */}
        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflow: "auto",
            background: "var(--surface)",
            border: "1px solid var(--line)",
            borderRadius: 8,
          }}
        >
          {loading ? (
            <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
              <Spinner /> 加载中…
            </div>
          ) : users.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
              暂无用户
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={thStyle}>用户</th>
                  <th style={thStyle}>角色</th>
                  <th style={thStyle}>状态</th>
                  <th style={thStyle}>组织</th>
                  <th style={thStyle}>最后登录</th>
                  <th style={thStyle}>操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const isPending = u.status === "pending_approval";
                  const sm = STATUS_META[u.status] || {
                    label: u.status,
                    color: "var(--ink-3)",
                    bg: "var(--bg-3)",
                  };
                  return (
                    <tr
                      key={u.id}
                      style={{
                        background: isPending ? "var(--warn-soft, #fff3e0)" : "transparent",
                      }}
                    >
                      <td style={tdStyle}>
                        <div style={{ fontWeight: 500 }}>
                          {u.display_name || u.username}
                          {isPending && (
                            <span
                              style={{
                                marginLeft: 6,
                                fontSize: 10,
                                color: "var(--warn, #ed6c02)",
                                background: "transparent",
                              }}
                            >
                              · 待审批
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--ink-3)" }}>
                          {u.username}
                          {u.phone && <> · {u.phone}</>}
                        </div>
                      </td>
                      <td style={tdStyle}>
                        <select
                          style={selectStyle}
                          value={u.role}
                          disabled={actionLoading === u.id}
                          onChange={(e) => handleRoleChange(u, e.target.value)}
                        >
                          {roles.map((r) => (
                            <option key={r.id} value={r.code}>
                              {r.name}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td style={tdStyle}>
                        <span
                          style={{
                            fontSize: 11,
                            color: sm.color,
                            background: sm.bg,
                            padding: "2px 8px",
                            borderRadius: 4,
                          }}
                        >
                          {sm.label}
                        </span>
                      </td>
                      <td style={{ ...tdStyle, color: "var(--ink-2)" }}>
                        {u.organizations.map((o) => o.name).join("、") || "—"}
                      </td>
                      <td style={{ ...tdStyle, color: "var(--ink-3)", fontSize: 11.5 }}>
                        {u.last_login ? new Date(u.last_login).toLocaleString("zh-CN") : "—"}
                      </td>
                      <td style={tdStyle}>
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {isPending ? (
                            <>
                              <Btn
                                variant="primary"
                                size="sm"
                                disabled={actionLoading === u.id}
                                onClick={() => handleApprove(u, "approve")}
                              >
                                通过
                              </Btn>
                              <Btn
                                variant="ghost"
                                size="sm"
                                disabled={actionLoading === u.id}
                                onClick={() => handleApprove(u, "reject")}
                              >
                                驳回
                              </Btn>
                            </>
                          ) : (
                            <Btn
                              variant="ghost"
                              size="sm"
                              disabled={actionLoading === u.id}
                              onClick={() => handleToggleStatus(u)}
                            >
                              {u.status === "active" ? "禁用" : "启用"}
                            </Btn>
                          )}
                          <Btn
                            variant="ghost"
                            size="sm"
                            disabled={actionLoading === u.id}
                            onClick={() => setResetTarget(u)}
                          >
                            重置密码
                          </Btn>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* 新增用户弹窗 */}
      {showCreate && (
        <CreateUserModal
          roles={roles}
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            void refresh();
          }}
        />
      )}

      {/* 重置密码弹窗 */}
      {resetTarget && (
        <ResetPasswordModal
          user={resetTarget}
          onClose={() => setResetTarget(null)}
          onDone={() => {
            setResetTarget(null);
          }}
        />
      )}
    </div>
  );
}

/** 新增用户弹窗（管理员创建，跳过审批 status=active） */
function CreateUserModal({
  roles,
  onClose,
  onCreated,
}: {
  roles: Role[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [username, setUsername] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState("user");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setErr("");
    if (!username.trim()) return setErr("请输入用户名");
    if (password.length < 6) return setErr("密码至少 6 位");
    setSubmitting(true);
    try {
      await api.createAdminUser({
        username: username.trim(),
        password,
        phone: phone.trim() || undefined,
        display_name: displayName.trim() || undefined,
        role,
      });
      onCreated();
    } catch (e: any) {
      setErr(e?.message || "创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell title="新增用户" onClose={onClose}>
      <Field label="用户名 *">
        <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="登录用户名" />
      </Field>
      <Field label="手机号">
        <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="11 位手机号" maxLength={11} />
      </Field>
      <Field label="显示名称">
        <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="可选" />
      </Field>
      <Field label="密码 *">
        <Input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="至少 6 位"
        />
      </Field>
      <Field label="角色">
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          style={{ padding: "8px", borderRadius: 6, border: "1px solid var(--line)", background: "var(--surface)", color: "var(--ink-1)", width: "100%" }}
        >
          {roles.map((r) => (
            <option key={r.id} value={r.code}>
              {r.name}
            </option>
          ))}
        </select>
      </Field>
      {err && <ErrorLine text={err} />}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
        <Btn variant="ghost" size="md" onClick={onClose}>
          取消
        </Btn>
        <Btn variant="primary" size="md" disabled={submitting} onClick={submit}>
          {submitting ? "创建中…" : "创建"}
        </Btn>
      </div>
    </ModalShell>
  );
}

/** 重置密码弹窗 */
function ResetPasswordModal({
  user,
  onClose,
  onDone,
}: {
  user: AdminUser;
  onClose: () => void;
  onDone: () => void;
}) {
  const [pwd, setPwd] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setErr("");
    if (pwd.length < 6) return setErr("密码至少 6 位");
    setSubmitting(true);
    try {
      await api.resetUserPassword(user.id, pwd);
      onDone();
    } catch (e: any) {
      setErr(e?.message || "重置失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell title={`重置密码 · ${user.display_name || user.username}`} onClose={onClose}>
      <Field label="新密码 *">
        <Input
          type="password"
          value={pwd}
          onChange={(e) => setPwd(e.target.value)}
          placeholder="至少 6 位"
        />
      </Field>
      {err && <ErrorLine text={err} />}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
        <Btn variant="ghost" size="md" onClick={onClose}>
          取消
        </Btn>
        <Btn variant="primary" size="md" disabled={submitting} onClick={submit}>
          {submitting ? "重置中…" : "重置"}
        </Btn>
      </div>
    </ModalShell>
  );
}

/** 弹窗外壳（overlay + card） */
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
