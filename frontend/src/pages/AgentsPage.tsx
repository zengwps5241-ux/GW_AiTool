// 智能体管理:列表 + 居中弹窗(基础/技能/插件 三栏)
import { Children, useCallback, useEffect, useMemo, useState } from "react";
import type { Agent, Category, Plugin, Skill, UserMe } from "@/types";
import { api } from "@/api/client";
import { I } from "@/icons";
import {
  Btn,
  Card,
  Checkbox,
  ConfirmDialog,
  Field,
  Input,
  Spinner,
  Tag,
  TextArea,
} from "@/components/ui";

// 把后端 "a,b,c" 字符串解析成数组
function parseCsv(raw: string | null | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

// 用 / 分隔的 fallback metadata,展示在卡片副标题
function describeAgent(a: Agent): string {
  const parts: string[] = [];
  parts.push(a.category || "默认");
  if (a.system_prompt) parts.push("已配置系统提示词");
  const sk = parseCsv(a.skills);
  if (sk.length) parts.push(`${sk.length} 项技能`);
  const pl = parseCsv(a.plugins);
  if (pl.length) parts.push(`${pl.length} 个插件`);
  if (!parts.length) return "暂无额外配置";
  return parts.join(" · ");
}

// 弹窗左侧导航的标签
type TabKey = "basic" | "skills" | "plugins";

export default function AgentsPage({ me }: { me: UserMe }) {
  const isAdmin = me.role !== "user";
  const [agents, setAgents] = useState<Agent[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchKw, setSearchKw] = useState("");

  // 表单状态:editing = null 表示未打开;editing.id = null 表示新建
  const [editing, setEditing] = useState<{
    id: number | null;
    name: string;
    code: string;
    category_id: number | null;
    system_prompt: string;
    skills: Set<string>;
    plugins: Set<string>;
    activeTab: TabKey;
  } | null>(null);
  const [saving, setSaving] = useState(false);
  const [formErr, setFormErr] = useState<string | null>(null);

  // reinit 确认弹窗状态
  const [reinitTarget, setReinitTarget] = useState<Agent | null>(null);

  // 初次加载
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [ag, cats, sk, pl] = await Promise.all([
        api.agents(),
        api.categories(),
        api.skills(),
        api.plugins(),
      ]);
      setAgents(ag);
      setCategories(cats);
      setSkills(sk);
      setPlugins(pl);
    } catch {
      // 静默,顶部可以提示
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // 过滤
  const filtered = useMemo(() => {
    const kw = searchKw.trim().toLowerCase();
    if (!kw) return agents;
    return agents.filter(
      (a) =>
        a.name.toLowerCase().includes(kw) ||
        (a.category || "").toLowerCase().includes(kw) ||
        (a.system_prompt || "").toLowerCase().includes(kw) ||
        (a.skills || "").toLowerCase().includes(kw) ||
        (a.plugins || "").toLowerCase().includes(kw),
    );
  }, [agents, searchKw]);

  const grouped = useMemo(() => {
    const byName = new Map<string, Agent[]>();
    for (const category of categories) {
      byName.set(category.name, []);
    }
    for (const agent of filtered) {
      const key = agent.category || "默认";
      if (!byName.has(key)) byName.set(key, []);
      byName.get(key)?.push(agent);
    }
    return Array.from(byName.entries())
      .map(([name, items]) => ({ name, items }))
      .filter((group) => group.items.length > 0);
  }, [categories, filtered]);

  const defaultCategoryId = useMemo(() => {
    return categories.find((c) => c.name === "默认")?.id ?? categories[0]?.id ?? null;
  }, [categories]);

  const openCreate = () => {
    setFormErr(null);
    setEditing({
      id: null,
      name: "",
      code: "",
      category_id: defaultCategoryId,
      system_prompt: "",
      skills: new Set(),
      plugins: new Set(),
      activeTab: "basic",
    });
  };
  const openEdit = (a: Agent) => {
    setFormErr(null);
    setEditing({
      id: a.id,
      name: a.name,
      code: a.code,
      category_id: a.category_id,
      system_prompt: a.system_prompt || "",
      skills: new Set(parseCsv(a.skills)),
      plugins: new Set(parseCsv(a.plugins)),
      activeTab: "basic",
    });
  };
  const closeForm = () => {
    if (saving) return;
    setEditing(null);
    setFormErr(null);
  };

  const toggleSkill = (name: string) => {
    if (!editing) return;
    const next = new Set(editing.skills);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setEditing({ ...editing, skills: next });
  };

  const togglePlugin = (path: string) => {
    if (!editing) return;
    const next = new Set(editing.plugins);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setEditing({ ...editing, plugins: next });
  };

  const submit = async () => {
    if (!editing) return;
    const name = editing.name.trim();
    const code = editing.code.trim();
    if (!name) {
      setFormErr("请输入智能体名称");
      // 校验失败时跳到基础页,避免用户看不到错误位置
      setEditing({ ...editing, activeTab: "basic" });
      return;
    }
    if (!code) {
      setFormErr("请输入代号");
      setEditing({ ...editing, activeTab: "basic" });
      return;
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(code)) {
      setFormErr("代号只能包含字母、数字、_、-");
      setEditing({ ...editing, activeTab: "basic" });
      return;
    }
    setSaving(true);
    setFormErr(null);
    try {
      if (editing.id == null) {
        await api.createAgent({
          name,
          code,
          category_id: editing.category_id,
          system_prompt: editing.system_prompt.trim() || null,
          skills: Array.from(editing.skills).join(","),
          plugins: Array.from(editing.plugins).join(","),
        });
      } else {
        await api.updateAgent(editing.id, {
          name,
          category_id: editing.category_id,
          system_prompt: editing.system_prompt.trim() || null,
          skills: Array.from(editing.skills).join(","),
          plugins: Array.from(editing.plugins).join(","),
        });
      }
      setEditing(null);
      await reload();
    } catch (e) {
      setFormErr((e as Error).message || "保存失败,请重试");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (a: Agent) => {
    if (a.is_default) return;
    if (!confirm(`确认删除智能体 "${a.name}"?`)) return;
    try {
      await api.deleteAgent(a.id);
      await reload();
    } catch (e) {
      alert("删除失败: " + ((e as Error).message || ""));
    }
  };

  // 重新初始化工作目录:从主目录拷贝最新 plugins/skills/CLAUDE.md,保留 SDK 产物
  const reinit = async (a: Agent) => {
    setReinitTarget(a);
  };

  const doReinit = async () => {
    if (!reinitTarget) return;
    try {
      await api.reinitAgent(reinitTarget.id);
      await reload();
      setReinitTarget(null);
    } catch (e) {
      alert("刷新失败: " + ((e as Error).message || ""));
    }
  };

  return (
    <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
      {/* 主列表区 */}
      <div
        style={{
          flex: 1,
          overflow: "auto",
          padding: "24px 28px",
          minWidth: 0,
        }}
      >
        {/* 标题栏 */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            marginBottom: 18,
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <h1
              style={{
                fontFamily: "var(--serif)",
                fontSize: 24,
                fontWeight: 500,
                marginBottom: 4,
                color: "var(--ink)",
                letterSpacing: -0.01,
              }}
            >
              智能体管理{" "}
              <span
                style={{
                  fontSize: 14,
                  color: "var(--ink-3)",
                  fontWeight: 400,
                  fontFamily: "var(--sans)",
                }}
              >
                · 共 {agents.length} 个
              </span>
            </h1>
            <div style={{ fontSize: 13, color: "var(--ink-3)" }}>
              配置可调用的智能体角色、系统提示词、技能与插件
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Input
              icon={<I.Search size={14} />}
              placeholder="搜索智能体"
              value={searchKw}
              onChange={(e) => setSearchKw(e.target.value)}
              containerStyle={{ width: 220, height: 34 }}
            />
            {isAdmin && (
              <Btn variant="primary" icon={<I.Plus size={14} />} onClick={openCreate}>
                新建智能体
              </Btn>
            )}
          </div>
        </div>

        {/* 列表内容 */}
        {loading ? (
          <div
            style={{
              padding: 60,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 10,
              color: "var(--ink-3)",
              fontSize: 13,
            }}
          >
            <Spinner /> 加载中…
          </div>
        ) : filtered.length === 0 ? (
          <EmptyAgents searched={!!searchKw} onCreate={openCreate} canCreate={isAdmin} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            {grouped.map((group) => (
              <section key={group.name}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 10,
                    color: "var(--ink-2)",
                    fontSize: 13,
                    fontWeight: 700,
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: 999,
                      background: "var(--accent)",
                      boxShadow: "0 0 0 3px var(--accent-soft)",
                    }}
                  />
                  <span>{group.name}</span>
                  <span style={{ color: "var(--ink-3)", fontWeight: 500 }}>
                    · {group.items.length}
                  </span>
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
                    gap: 12,
                  }}
                >
                  {group.items.map((a) => (
                    <AgentCard
                      key={a.id}
                      agent={a}
                      isAdmin={isAdmin}
                      onEdit={() => openEdit(a)}
                      onDelete={() => remove(a)}
                      onReinit={() => reinit(a)}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>

      {/* 居中弹窗 */}
      {editing && (
        <AgentModal
          editing={editing}
          categories={categories}
          skills={skills}
          plugins={plugins}
          saving={saving}
          err={formErr}
          onChange={(patch) => setEditing({ ...editing, ...patch })}
          onSwitchTab={(t) => setEditing({ ...editing, activeTab: t })}
          onToggleSkill={toggleSkill}
          onTogglePlugin={togglePlugin}
          onSubmit={submit}
          onClose={closeForm}
        />
      )}

      {/* 刷新确认弹窗 */}
      <ConfirmDialog
        open={!!reinitTarget}
        title="同步版本"
        message="确认更新插件、技能版本？"
        confirmText="确认"
        onConfirm={doReinit}
        onCancel={() => setReinitTarget(null)}
      />
    </div>
  );
}

// ============ 智能体卡片 ============
function AgentCard({
  agent,
  isAdmin,
  onEdit,
  onDelete,
  onReinit,
}: {
  agent: Agent;
  isAdmin: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onReinit: () => void;
}) {
  const skills = parseCsv(agent.skills);
  const plugins = parseCsv(agent.plugins);
  return (
    <Card
      style={{
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        transition: "border-color 120ms, box-shadow 120ms",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = "var(--line-2)";
        e.currentTarget.style.boxShadow = "var(--shadow-sm)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "var(--line)";
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      {/* 头部 */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <span
          style={{
            width: 36,
            height: 36,
            borderRadius: 10,
            background: "var(--accent-soft)",
            color: "var(--accent)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <I.Brain size={18} />
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              marginBottom: 2,
            }}
          >
            <span
              style={{
                fontSize: 14.5,
                fontWeight: 600,
                color: "var(--ink)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {agent.name}
            </span>
            {agent.is_default && (
              <Tag tone="accent" style={{ fontSize: 10 }}>
                默认
              </Tag>
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-3)" }}>
            {describeAgent(agent)}
          </div>
        </div>
      </div>

      {/* 系统提示词预览 */}
      {agent.system_prompt && (
        <div
          style={{
            fontSize: 12.5,
            color: "var(--ink-2)",
            lineHeight: 1.55,
            padding: "8px 10px",
            background: "var(--bg-2)",
            borderRadius: 6,
            border: "1px solid var(--line)",
            maxHeight: 64,
            overflow: "hidden",
            display: "-webkit-box",
            WebkitLineClamp: 3,
            WebkitBoxOrient: "vertical",
          }}
        >
          {agent.system_prompt}
        </div>
      )}

      {/* 技能 chips */}
      {skills.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {skills.slice(0, 6).map((s) => (
            <code
              key={s}
              style={{
                fontFamily: "var(--mono)",
                fontSize: 11,
                padding: "2px 6px",
                background: "var(--bg-2)",
                border: "1px solid var(--line)",
                borderRadius: 4,
                color: "var(--ink-2)",
              }}
            >
              {s}
            </code>
          ))}
          {skills.length > 6 && (
            <span
              style={{
                fontSize: 11,
                color: "var(--ink-3)",
                padding: "2px 4px",
              }}
            >
              +{skills.length - 6}
            </span>
          )}
        </div>
      )}

      {/* 插件 chips */}
      {plugins.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {plugins.slice(0, 6).map((p) => (
            <span
              key={p}
              title={p}
              style={{
                fontFamily: "var(--mono)",
                fontSize: 11,
                padding: "2px 6px",
                background: "var(--accent-soft)",
                border: "1px solid var(--line)",
                borderRadius: 4,
                color: "var(--accent)",
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
              }}
            >
              <I.Plug size={10} />
              {p.split("/")[0]}
            </span>
          ))}
          {plugins.length > 6 && (
            <span
              style={{
                fontSize: 11,
                color: "var(--ink-3)",
                padding: "2px 4px",
              }}
            >
              +{plugins.length - 6}
            </span>
          )}
        </div>
      )}

      {/* 底部操作 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          paddingTop: 8,
          borderTop: "1px solid var(--line)",
          marginTop: "auto",
        }}
      >
        <span
          style={{
            fontSize: 11,
            color: "var(--ink-3)",
            fontFamily: "var(--mono)",
          }}
        >
          ID #{agent.id}
        </span>
        {isAdmin && (
          <div style={{ display: "flex", gap: 4 }}>
            <button
              onClick={onReinit}
              title="重新初始化工作目录"
              className="focus-ring"
              style={iconBtnStyle}
            >
              <I.Refresh size={14} />
            </button>
            <button
              onClick={onEdit}
              title="编辑"
              className="focus-ring"
              style={iconBtnStyle}
            >
              <I.Edit size={14} />
            </button>
            <button
              onClick={onDelete}
              title={agent.is_default ? "默认智能体不可删除" : "删除"}
              className="focus-ring"
              disabled={agent.is_default}
              style={{
                ...iconBtnStyle,
                color: agent.is_default ? "var(--ink-4)" : "var(--danger)",
                cursor: agent.is_default ? "not-allowed" : "pointer",
                opacity: agent.is_default ? 0.5 : 1,
              }}
            >
              <I.Trash size={14} />
            </button>
          </div>
        )}
      </div>
    </Card>
  );
}

// ============ 居中弹窗(顶部 title + 左侧导航 + 主内容) ============
function AgentModal({
  editing,
  categories,
  skills,
  plugins,
  saving,
  err,
  onChange,
  onSwitchTab,
  onToggleSkill,
  onTogglePlugin,
  onSubmit,
  onClose,
}: {
  editing: {
    id: number | null;
    name: string;
    code: string;
    category_id: number | null;
    system_prompt: string;
    skills: Set<string>;
    plugins: Set<string>;
    activeTab: TabKey;
  };
  categories: Category[];
  skills: Skill[];
  plugins: Plugin[];
  saving: boolean;
  err: string | null;
  onChange: (patch: Partial<{ name: string; code: string; category_id: number | null; system_prompt: string }>) => void;
  onSwitchTab: (t: TabKey) => void;
  onToggleSkill: (name: string) => void;
  onTogglePlugin: (path: string) => void;
  onSubmit: () => void;
  onClose: () => void;
}) {
  const isEdit = editing.id != null;
  const [skillKw, setSkillKw] = useState("");
  const [pluginKw, setPluginKw] = useState("");
  return (
    <>
      {/* 遮罩 */}
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.32)",
          zIndex: 40,
          animation: "fade 160ms ease",
        }}
      />
      {/* 居中弹窗本体 */}
      <div
        role="dialog"
        aria-modal="true"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 41,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            pointerEvents: "auto",
            width: "min(820px, 100%)",
            height: "min(640px, calc(100vh - 48px))",
            maxHeight: "min(640px, calc(100vh - 48px))",
            background: "var(--bg)",
            border: "1px solid var(--line)",
            borderRadius: 12,
            boxShadow: "var(--shadow-lg)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          {/* 顶部标题栏 */}
          <div
            style={{
              padding: "16px 20px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              borderBottom: "1px solid var(--line)",
              flexShrink: 0,
            }}
          >
            <h2
              style={{
                fontFamily: "var(--serif)",
                fontSize: 17,
                fontWeight: 500,
                color: "var(--ink)",
              }}
            >
              {isEdit ? "编辑智能体" : "新建智能体"}
            </h2>
            <button
              onClick={onClose}
              className="focus-ring"
              title="关闭"
              style={{
                background: "transparent",
                border: "none",
                color: "var(--ink-3)",
                cursor: "pointer",
                padding: 6,
                borderRadius: 6,
                display: "flex",
              }}
            >
              <I.X size={16} />
            </button>
          </div>

          {/* 左导航 + 主内容 */}
          <div
            style={{
              flex: 1,
              display: "flex",
              minHeight: 0,
            }}
          >
            {/* 左侧分类导航 */}
            <nav
              style={{
                width: 168,
                flexShrink: 0,
                borderRight: "1px solid var(--line)",
                padding: "12px 8px",
                display: "flex",
                flexDirection: "column",
                gap: 2,
                background: "var(--bg-2)",
              }}
            >
              <TabButton
                active={editing.activeTab === "basic"}
                icon={<I.Settings size={14} />}
                label="基础"
                onClick={() => onSwitchTab("basic")}
              />
              <TabButton
                active={editing.activeTab === "skills"}
                icon={<I.Sparkles size={14} />}
                label={`技能 · ${editing.skills.size}`}
                onClick={() => onSwitchTab("skills")}
              />
              <TabButton
                active={editing.activeTab === "plugins"}
                icon={<I.Plug size={14} />}
                label={`插件 · ${editing.plugins.size}`}
                onClick={() => onSwitchTab("plugins")}
              />
            </nav>

            {/* 右侧表单内容 */}
            <div
              style={{
                flex: 1,
                overflow: "auto",
                padding: 20,
                display: "flex",
                flexDirection: "column",
                gap: 16,
                minWidth: 0,
              }}
            >
              {err && (
                <div
                  style={{
                    background: "var(--danger-soft)",
                    color: "var(--danger)",
                    padding: "8px 12px",
                    borderRadius: 8,
                    fontSize: 13,
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <I.CircleAlert size={14} />
                  {err}
                </div>
              )}

              {editing.activeTab === "basic" && (
                <BasicTab
                  editing={editing}
                  categories={categories}
                  onChange={onChange}
                  isEdit={isEdit}
                />
              )}
              {editing.activeTab === "skills" && (
                <SkillsTab
                  skills={skills}
                  selected={editing.skills}
                  searchKw={skillKw}
                  onSearchChange={setSkillKw}
                  onToggle={onToggleSkill}
                />
              )}
              {editing.activeTab === "plugins" && (
                <PluginsTab
                  plugins={plugins}
                  selected={editing.plugins}
                  searchKw={pluginKw}
                  onSearchChange={setPluginKw}
                  onToggle={onTogglePlugin}
                />
              )}
            </div>
          </div>

          {/* 底部操作 */}
          <div
            style={{
              padding: 16,
              borderTop: "1px solid var(--line)",
              display: "flex",
              justifyContent: "flex-end",
              gap: 8,
              background: "var(--bg)",
              flexShrink: 0,
            }}
          >
            <Btn variant="ghost" onClick={onClose} disabled={saving}>
              取消
            </Btn>
            <Btn variant="primary" onClick={onSubmit} disabled={saving}>
              {saving ? "保存中…" : isEdit ? "保存修改" : "创建"}
            </Btn>
          </div>
        </div>
      </div>
    </>
  );
}

// ============ 左侧分类按钮 ============
function TabButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="focus-ring"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 10px",
        background: active ? "var(--bg)" : "transparent",
        border: active ? "1px solid var(--line)" : "1px solid transparent",
        borderRadius: 6,
        cursor: "pointer",
        color: active ? "var(--ink)" : "var(--ink-2)",
        fontSize: 13,
        fontWeight: active ? 500 : 400,
        textAlign: "left",
        transition: "background 120ms, color 120ms",
      }}
    >
      <span style={{ color: active ? "var(--accent)" : "var(--ink-3)" }}>
        {icon}
      </span>
      <span style={{ flex: 1 }}>{label}</span>
    </button>
  );
}

// ============ 基础 Tab ============
function BasicTab({
  editing,
  categories,
  onChange,
  isEdit,
}: {
  editing: { name: string; code: string; category_id: number | null; system_prompt: string };
  categories: Category[];
  onChange: (patch: Partial<{ name: string; code: string; category_id: number | null; system_prompt: string }>) => void;
  isEdit: boolean;
}) {
  return (
    <>
      <Field label="名称">
        <Input
          placeholder="例如:运维助手"
          value={editing.name}
          onChange={(e) => onChange({ name: e.target.value })}
          autoFocus
        />
      </Field>
      <Field label="代号">
        <Input
          placeholder="只能包含字母、数字、_、-，创建后不可修改。例如:ops-assistant"
          value={editing.code}
          onChange={(e) => onChange({ code: e.target.value })}
          disabled={isEdit}
          containerStyle={isEdit ? { background: "var(--bg-2)" } : undefined}
          style={isEdit ? { color: "var(--ink-3)" } : undefined}
        />
      </Field>
      <Field label="分类" hint="分类沿用技能管理中的分类设置">
        <select
          value={editing.category_id ?? ""}
          onChange={(e) =>
            onChange({
              category_id: e.target.value ? Number(e.target.value) : null,
            })
          }
          style={{
            width: "100%",
            height: 38,
            padding: "0 10px",
            border: "1px solid var(--line)",
            borderRadius: 8,
            background: "var(--surface)",
            color: "var(--ink)",
            fontFamily: "inherit",
            fontSize: 13,
            outline: "none",
          }}
        >
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </select>
      </Field>
      <Field
        label="系统提示词"
        hint="留空则使用默认提示词。可在此定义角色、能力边界与回复风格"
      >
        <TextArea
          placeholder="你是一位资深运维工程师……"
          value={editing.system_prompt}
          onChange={(e) => onChange({ system_prompt: e.target.value })}
          rows={6}
          style={{ minHeight: 180, resize: "vertical" }}
        />
      </Field>
    </>
  );
}

// ============ 技能 Tab ============
function SkillsTab({
  skills,
  selected,
  searchKw,
  onSearchChange,
  onToggle,
}: {
  skills: Skill[];
  selected: Set<string>;
  searchKw: string;
  onSearchChange: (kw: string) => void;
  onToggle: (name: string) => void;
}) {
  const filteredSkills = useMemo(() => {
    const kw = searchKw.trim().toLowerCase();
    if (!kw) return skills;
    // 技能搜索覆盖名称和描述,便于在长列表里快速定位能力。
    return skills.filter((s) =>
      [s.name, s.description].some((value) => (value || "").toLowerCase().includes(kw)),
    );
  }, [skills, searchKw]);

  return (
    <Field
      label={`可调用技能 · 已选 ${selected.size} / ${skills.length}`}
      hint="勾选后,智能体可在对话中调用对应的 Skills"
    >
      {skills.length === 0 ? (
        <EmptyHint text="暂无可用技能" />
      ) : (
        <SearchableCheckList
          keyword={searchKw}
          onKeywordChange={onSearchChange}
          placeholder="搜索技能名称或描述"
          emptyText="没有匹配的技能"
        >
          {filteredSkills.map((s) => (
            <CheckItem
              key={s.name}
              checked={selected.has(s.name)}
              onChange={() => onToggle(s.name)}
              title={s.name}
              description={s.description}
            />
          ))}
        </SearchableCheckList>
      )}
    </Field>
  );
}

// ============ 插件 Tab ============
function PluginsTab({
  plugins,
  selected,
  searchKw,
  onSearchChange,
  onToggle,
}: {
  plugins: Plugin[];
  selected: Set<string>;
  searchKw: string;
  onSearchChange: (kw: string) => void;
  onToggle: (path: string) => void;
}) {
  const filteredPlugins = useMemo(() => {
    const kw = searchKw.trim().toLowerCase();
    if (!kw) return plugins;
    // 插件搜索覆盖名称、描述、路径和版本,兼顾展示名与本地目录定位。
    return plugins.filter((p) =>
      [p.name, p.description, p.path, p.version].some((value) =>
        (value || "").toLowerCase().includes(kw),
      ),
    );
  }, [plugins, searchKw]);

  return (
    <Field
      label={`本地插件 · 已选 ${selected.size} / ${plugins.length}`}
      hint="读取自 claude_data_dir/plugins 目录;勾选后该插件会随智能体一同加载"
    >
      {plugins.length === 0 ? (
        <EmptyHint text="未在 claude_data_dir/plugins 目录下发现插件" />
      ) : (
        <SearchableCheckList
          keyword={searchKw}
          onKeywordChange={onSearchChange}
          placeholder="搜索插件名称、描述或路径"
          emptyText="没有匹配的插件"
        >
          {filteredPlugins.map((p) => (
            <CheckItem
              key={p.path}
              checked={selected.has(p.path)}
              onChange={() => onToggle(p.path)}
              title={
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span>{p.name}</span>
                  {p.version && (
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        padding: "1px 5px",
                        background: "var(--bg-2)",
                        border: "1px solid var(--line)",
                        borderRadius: 4,
                        color: "var(--ink-3)",
                      }}
                    >
                      v{p.version}
                    </span>
                  )}
                </span>
              }
              description={p.description || p.path}
            />
          ))}
        </SearchableCheckList>
      )}
    </Field>
  );
}

// ============ 通用勾选清单 ============
function SearchableCheckList({
  keyword,
  onKeywordChange,
  placeholder,
  emptyText,
  children,
}: {
  keyword: string;
  onKeywordChange: (kw: string) => void;
  placeholder: string;
  emptyText: string;
  children: React.ReactNode;
}) {
  const hasItems = Children.count(children) > 0;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <Input
        icon={<I.Search size={14} />}
        placeholder={placeholder}
        value={keyword}
        onChange={(e) => onKeywordChange(e.target.value)}
        containerStyle={{ height: 34 }}
      />
      {hasItems ? <CheckList>{children}</CheckList> : <EmptyHint text={emptyText} />}
    </div>
  );
}

function CheckList({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 6,
        padding: 10,
        background: "var(--bg-2)",
        border: "1px solid var(--line)",
        borderRadius: 8,
        maxHeight: 320,
        overflow: "auto",
      }}
    >
      {children}
    </div>
  );
}

function CheckItem({
  checked,
  onChange,
  title,
  description,
}: {
  checked: boolean;
  onChange: () => void;
  title: React.ReactNode;
  description?: string;
}) {
  return (
    <label
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        padding: "8px 10px",
        borderRadius: 6,
        cursor: "pointer",
        transition: "background 120ms",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "var(--surface)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
      }}
    >
      <div style={{ paddingTop: 1 }}>
        <Checkbox checked={checked} onChange={onChange} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: "block",
            fontFamily: "var(--mono)",
            fontSize: 12.5,
            fontWeight: 500,
            color: "var(--ink)",
            marginBottom: 2,
            wordBreak: "break-all",
          }}
        >
          {title}
        </div>
        {description && (
          <div
            style={{
              fontSize: 12,
              color: "var(--ink-3)",
              lineHeight: 1.5,
            }}
          >
            {description}
          </div>
        )}
      </div>
    </label>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div
      style={{
        padding: "16px 12px",
        fontSize: 13,
        color: "var(--ink-3)",
        textAlign: "center",
        border: "1px dashed var(--line-2)",
        borderRadius: 8,
        background: "var(--bg-2)",
      }}
    >
      {text}
    </div>
  );
}

// ============ 空状态 ============
function EmptyAgents({
  searched,
  onCreate,
  canCreate,
}: {
  searched: boolean;
  onCreate: () => void;
  canCreate: boolean;
}) {
  return (
    <div
      style={{
        padding: "60px 20px",
        textAlign: "center",
        color: "var(--ink-3)",
      }}
    >
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: 14,
          background: "var(--accent-soft)",
          color: "var(--accent)",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: 12,
        }}
      >
        <I.Brain size={28} />
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 17,
          color: "var(--ink)",
          marginBottom: 4,
        }}
      >
        {searched ? "没有匹配的智能体" : "还没有创建任何智能体"}
      </div>
      <div style={{ fontSize: 13, marginBottom: 16 }}>
        {searched
          ? "试试更换关键词或清空搜索"
          : "新建一个智能体,定义它的系统提示词、技能与插件"}
      </div>
      {!searched && canCreate && (
        <Btn variant="primary" icon={<I.Plus size={14} />} onClick={onCreate}>
          新建智能体
        </Btn>
      )}
    </div>
  );
}

// ============ 图标按钮样式 ============
const iconBtnStyle = {
  background: "transparent",
  border: "1px solid transparent",
  color: "var(--ink-3)",
  cursor: "pointer",
  width: 28,
  height: 28,
  borderRadius: 6,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  transition: "background 120ms, color 120ms",
} as const;
