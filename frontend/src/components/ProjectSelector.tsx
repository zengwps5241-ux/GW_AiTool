// 项目选择器（M1.3.9）：客户 → 项目 级联下拉 + 新建项目
// 全局状态由父组件（App.tsx）持有 selectedProject，本组件受控。
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import type { Customer, Project } from "@/types";
import { Btn, Field, Input, Spinner, useToast } from "@/components/ui";
import { I } from "@/icons";

interface Props {
  /** 当前选中的项目 ID（null 表示未选） */
  value: number | null;
  /** 选择变化回调 */
  onChange: (project: Project | null) => void;
  /** 紧凑模式（嵌入顶栏时） */
  compact?: boolean;
}

export default function ProjectSelector({ value, onChange, compact }: Props) {
  const toast = useToast();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [selCustomerId, setSelCustomerId] = useState<number | "">("");
  const [createOpen, setCreateOpen] = useState(false);

  // 拉取客户 + 项目
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [cs, ps] = await Promise.all([api.listCustomers(), api.listProjects()]);
      setCustomers(cs);
      setProjects(ps);
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "加载客户/项目失败", "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // 当前选中项目 → 自动联动客户下拉
  const current = useMemo(
    () => projects.find((p) => p.id === value) ?? null,
    [projects, value],
  );

  useEffect(() => {
    if (current) setSelCustomerId(current.customer_id);
  }, [current]);

  // 按所选客户过滤项目
  const filteredProjects = useMemo(() => {
    if (selCustomerId === "") return projects;
    return projects.filter((p) => p.customer_id === selCustomerId);
  }, [projects, selCustomerId]);

  const handleSelectProject = (projectId: number | "") => {
    if (projectId === "") {
      onChange(null);
      return;
    }
    const p = projects.find((x) => x.id === projectId) ?? null;
    onChange(p);
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--ink-3)", fontSize: 13 }}>
        <Spinner size={13} /> 加载项目…
      </div>
    );
  }

  const selectStyle: React.CSSProperties = {
    height: 30,
    fontSize: 13,
    padding: "0 8px",
    borderRadius: 8,
    border: "1px solid var(--line)",
    background: "var(--surface)",
    color: "var(--ink)",
    cursor: "pointer",
    maxWidth: compact ? 160 : 220,
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <I.Briefcase size={14} style={{ color: "var(--ink-4)" }} />
      {/* 客户下拉 */}
      <select
        style={selectStyle}
        value={selCustomerId}
        onChange={(e) => {
          const v = e.target.value ? Number(e.target.value) : "";
          setSelCustomerId(v);
          // 切换客户时清空项目选择
          if (current && (v === "" || current.customer_id !== v)) {
            onChange(null);
          }
        }}
        title="选择客户"
      >
        <option value="">全部客户</option>
        {customers.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
      <I.ChevronDown size={12} style={{ color: "var(--ink-4)", marginLeft: -4 }} />
      {/* 项目下拉 */}
      <select
        style={selectStyle}
        value={value ?? ""}
        onChange={(e) => handleSelectProject(e.target.value ? Number(e.target.value) : "")}
        title="选择项目"
      >
        <option value="">未选项目</option>
        {filteredProjects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
            {p.my_role === "owner" ? "（我负责）" : p.my_role === "deputy" ? "（成员）" : ""}
          </option>
        ))}
      </select>
      <Btn size="sm" variant="ghost" icon={<I.Plus size={13} />} onClick={() => setCreateOpen(true)}>
        新建项目
      </Btn>

      {createOpen && (
        <CreateProjectModal
          customers={customers}
          onClose={() => setCreateOpen(false)}
          onCreated={(p) => {
            setCreateOpen(false);
            refresh().then(() => onChange(p));
            toast.showToast(`项目「${p.name}」已创建`, "success");
          }}
        />
      )}
    </div>
  );
}

// ─── 新建项目弹窗 ──────────────────────────────────────────────

function CreateProjectModal({
  customers,
  onClose,
  onCreated,
}: {
  customers: Customer[];
  onClose: () => void;
  onCreated: (p: Project) => void;
}) {
  const toast = useToast();
  const [mode, setMode] = useState<"existing" | "new">(customers.length ? "existing" : "new");
  const [customerId, setCustomerId] = useState<number | "">(customers[0]?.id ?? "");
  const [newCustomerName, setNewCustomerName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [projectType, setProjectType] = useState<"诊断" | "试点" | "落地" | "">("");
  const [submitting, setSubmitting] = useState(false);

  const canSubmit =
    projectName.trim() &&
    ((mode === "existing" && customerId !== "") || (mode === "new" && newCustomerName.trim()));

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      let cid = customerId;
      if (mode === "new") {
        const c = await api.createCustomer({ name: newCustomerName.trim() });
        cid = c.id;
      }
      const p = await api.createProject({
        customer_id: Number(cid),
        name: projectName.trim(),
        project_type: projectType || null,
      });
      onCreated(p);
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "创建项目失败", "error");
    } finally {
      setSubmitting(false);
    }
  };

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
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 420,
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 12,
          padding: 20,
          boxShadow: "0 8px 32px rgba(0,0,0,0.18)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 16,
          }}
        >
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>新建项目</div>
          <button
            onClick={onClose}
            style={{ all: "unset", cursor: "pointer", color: "var(--ink-3)" }}
            title="关闭"
          >
            <I.X size={16} />
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Field label="客户">
            <div style={{ display: "flex", gap: 8 }}>
              <select
                style={{
                  flex: 1,
                  height: 34,
                  fontSize: 13,
                  padding: "0 8px",
                  borderRadius: 8,
                  border: "1px solid var(--line)",
                  background: "var(--bg)",
                  color: "var(--ink)",
                }}
                value={mode === "existing" ? customerId : "__new__"}
                onChange={(e) => {
                  if (e.target.value === "__new__") setMode("new");
                  else {
                    setMode("existing");
                    setCustomerId(Number(e.target.value));
                  }
                }}
              >
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
                <option value="__new__">＋ 新建客户…</option>
              </select>
            </div>
            {mode === "new" && (
              <Input
                style={{ marginTop: 8 }}
                placeholder="输入新客户名称"
                value={newCustomerName}
                onChange={(e) => setNewCustomerName(e.target.value)}
              />
            )}
          </Field>

          <Field label="项目名称">
            <Input
              placeholder="如：数字化转型项目"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
            />
          </Field>

          <Field label="项目类型（可选）">
            <select
              style={{
                width: "100%",
                height: 34,
                fontSize: 13,
                padding: "0 8px",
                borderRadius: 8,
                border: "1px solid var(--line)",
                background: "var(--bg)",
                color: "var(--ink)",
              }}
              value={projectType}
              onChange={(e) => setProjectType(e.target.value as "诊断" | "试点" | "落地" | "")}
            >
              <option value="">不指定</option>
              <option value="诊断">诊断</option>
              <option value="试点">试点</option>
              <option value="落地">落地</option>
            </select>
          </Field>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
          <Btn variant="ghost" onClick={onClose}>
            取消
          </Btn>
          <Btn onClick={submit} disabled={!canSubmit || submitting}>
            {submitting ? "创建中…" : "创建项目"}
          </Btn>
        </div>
      </div>
    </div>
  );
}
