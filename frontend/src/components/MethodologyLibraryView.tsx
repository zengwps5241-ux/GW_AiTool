import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { api } from "@/api/client";
import type {
  MethodologyCategory,
  MethodologyItem,
  MethodologyItemInput,
  UserMe,
} from "@/types";
import { Btn, Input, Spinner, Tag, TextArea, useToast } from "@/components/ui";
import MarkdownView from "@/components/workspace/MarkdownView";
import { I } from "@/icons";

/**
 * 团队空间「方法论库」（M5.5.7，§2.6 / §6.3）。
 *
 * 管理员维护的全局只读库：Prompt 模板 / 画布 Schema / 方法论规则三类。
 * 所有登录用户只读浏览；admin/super 可新增/编辑/删除（§3.2 管理种子数据）。
 * 自管 fetch + toast 反馈（同 PublicAssetsView 范式）。
 */

// 三类内容的展示元信息（顺序即分组顺序：规则打底 → 模板 → Schema）
const CATEGORY_META: {
  key: MethodologyCategory;
  label: string;
  hint: string;
}[] = [
  { key: "methodology_rule", label: "方法论规则", hint: "道层准则、根本行为规范" },
  { key: "prompt_template", label: "Prompt 模板", hint: "各 Skill 产出 Prompt 要点" },
  { key: "canvas_schema", label: "画布 Schema", hint: "结构化字段契约" },
];

const CATEGORY_LABEL: Record<MethodologyCategory, string> = {
  methodology_rule: "方法论规则",
  prompt_template: "Prompt 模板",
  canvas_schema: "画布 Schema",
};

interface EditorState {
  open: boolean;
  editing: MethodologyItem | null; // null = 新建
  category: MethodologyCategory;
  title: string;
  content: string;
  sort_order: number;
  saving: boolean;
}

const EMPTY_EDITOR: EditorState = {
  open: false,
  editing: null,
  category: "methodology_rule",
  title: "",
  content: "",
  sort_order: 0,
  saving: false,
};

function MethodologyEditor({
  state,
  setState,
  onSubmit,
  onClose,
}: {
  state: EditorState;
  setState: React.Dispatch<React.SetStateAction<EditorState>>;
  onSubmit: (e: FormEvent) => void;
  onClose: () => void;
}) {
  return (
    <div
      onClick={() => !state.saving && onClose()}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(0,0,0,0.34)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <form
        onSubmit={onSubmit}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(640px, 100%)",
          maxHeight: "88vh",
          overflow: "auto",
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 8,
          boxShadow: "var(--shadow-lg)",
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        <h3 style={{ margin: 0, fontSize: 16 }}>
          {state.editing ? "编辑方法论条目" : "新增方法论条目"}
        </h3>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, minWidth: 160 }}>
            <span style={{ fontSize: 12, color: "var(--ink-2)" }}>类别</span>
            <select
              value={state.category}
              onChange={(e) =>
                setState((s) => ({ ...s, category: e.target.value as MethodologyCategory }))
              }
              style={{
                border: "1px solid var(--line)",
                borderRadius: 8,
                background: "var(--bg)",
                color: "var(--ink)",
                padding: "9px 10px",
                font: "inherit",
                outline: "none",
              }}
            >
              {CATEGORY_META.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, width: 96 }}>
            <span style={{ fontSize: 12, color: "var(--ink-2)" }}>排序</span>
            <Input
              type="number"
              value={state.sort_order}
              onChange={(e) =>
                setState((s) => ({ ...s, sort_order: Number(e.target.value) || 0 }))
              }
            />
          </label>
        </div>
        <Input
          placeholder="标题"
          value={state.title}
          onChange={(e) => setState((s) => ({ ...s, title: e.target.value }))}
          autoFocus
        />
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "var(--ink-2)" }}>正文（Markdown）</span>
          <TextArea
            placeholder="支持 Markdown：# 标题、**加粗**、列表等"
            value={state.content}
            onChange={(e) => setState((s) => ({ ...s, content: e.target.value }))}
            rows={12}
            style={{ minHeight: 240, fontFamily: "monospace" }}
          />
        </label>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Btn type="button" variant="secondary" onClick={onClose} disabled={state.saving}>
            取消
          </Btn>
          <Btn
            type="submit"
            icon={state.saving ? <I.Loader size={14} /> : <I.Check size={14} />}
            disabled={state.saving || !state.title.trim() || !state.content.trim()}
          >
            {state.saving ? "保存中…" : "保存"}
          </Btn>
        </div>
      </form>
    </div>
  );
}

function ItemCard({
  item,
  isAdmin,
  onEdit,
  onDelete,
}: {
  item: MethodologyItem;
  isAdmin: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <article
      style={{
        border: "1px solid var(--line)",
        borderRadius: 8,
        padding: 14,
        background: "var(--surface)",
        boxShadow: "var(--shadow-sm)",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        <div
          style={{
            fontSize: 14.5,
            fontWeight: 700,
            color: "var(--ink)",
            flex: 1,
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={item.title}
        >
          {item.title}
        </div>
        <Tag tone="neutral">{CATEGORY_LABEL[item.category]}</Tag>
        {isAdmin && (
          <div style={{ display: "flex", gap: 4 }}>
            <button
              type="button"
              onClick={onEdit}
              title="编辑"
              style={{
                border: "none",
                background: "transparent",
                color: "var(--ink-3)",
                cursor: "pointer",
                padding: 4,
                display: "inline-flex",
              }}
            >
              <I.Edit size={14} />
            </button>
            <button
              type="button"
              onClick={onDelete}
              title="删除"
              style={{
                border: "none",
                background: "transparent",
                color: "var(--ink-3)",
                cursor: "pointer",
                padding: 4,
                display: "inline-flex",
              }}
            >
              <I.Trash size={14} />
            </button>
          </div>
        )}
      </div>
      <div style={{ fontSize: 13, color: "var(--ink)", lineHeight: 1.6 }}>
        <MarkdownView text={item.content} />
      </div>
      {item.created_by_name && (
        <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: "auto" }}>
          ✍ {item.created_by_name}
        </div>
      )}
    </article>
  );
}

export function MethodologyLibraryView() {
  const { showToast } = useToast();
  const [items, setItems] = useState<MethodologyItem[]>([]);
  const [me, setMe] = useState<UserMe | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorState>(EMPTY_EDITOR);

  const isAdmin = me != null && me.role !== "user";

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, meRes] = await Promise.all([api.listMethodology(), api.me()]);
      setItems(list);
      setMe(meRes);
    } catch (e) {
      setError((e as Error).message || "加载方法论库失败");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // 按类别分组（保留服务端 类别→排序→id 顺序）
  const grouped = useMemo(() => {
    const map: Record<MethodologyCategory, MethodologyItem[]> = {
      methodology_rule: [],
      prompt_template: [],
      canvas_schema: [],
    };
    for (const it of items) map[it.category].push(it);
    return map;
  }, [items]);

  const openCreate = (category: MethodologyCategory) => {
    setEditor({ ...EMPTY_EDITOR, open: true, category });
  };

  const openEdit = (item: MethodologyItem) => {
    setEditor({
      open: true,
      editing: item,
      category: item.category,
      title: item.title,
      content: item.content,
      sort_order: item.sort_order,
      saving: false,
    });
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (editor.saving) return;
    const payload: MethodologyItemInput = {
      category: editor.category,
      title: editor.title.trim(),
      content: editor.content,
      sort_order: editor.sort_order,
    };
    setEditor((s) => ({ ...s, saving: true }));
    try {
      if (editor.editing) {
        await api.updateMethodology(editor.editing.id, payload);
        showToast("已更新", "success");
      } else {
        await api.createMethodology(payload);
        showToast("已新增", "success");
      }
      setEditor(EMPTY_EDITOR);
      await load();
    } catch (err) {
      showToast((err as Error).message || "保存失败", "error");
      setEditor((s) => ({ ...s, saving: false }));
    }
  };

  const remove = async (item: MethodologyItem) => {
    if (!window.confirm(`确认删除「${item.title}」？`)) return;
    try {
      await api.deleteMethodology(item.id);
      showToast("已删除", "success");
      setItems((prev) => prev.filter((it) => it.id !== item.id));
    } catch (err) {
      showToast((err as Error).message || "删除失败", "error");
    }
  };

  if (loading && items.length === 0 && me == null) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          color: "var(--ink-3)",
          fontSize: 13,
          padding: 12,
        }}
      >
        <Spinner size={14} /> 加载中…
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div style={{ color: "var(--danger)", fontSize: 13 }}>{error}</div>
        <Btn variant="secondary" icon={<I.Refresh size={14} />} onClick={load}>
          重试
        </Btn>
      </div>
    );
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
          gap: 8,
        }}
      >
        <div style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
          管理员维护的只读方法论库，含 Prompt 模板 / 画布 Schema / 方法论规则。
          {isAdmin ? " 你以管理员身份可增删改。" : " 如需补充，请联系管理员。"}
        </div>
        <Btn
          variant="secondary"
          size="sm"
          icon={loading ? <I.Loader size={13} /> : <I.Refresh size={13} />}
          onClick={load}
          disabled={loading}
        >
          刷新
        </Btn>
      </div>

      {CATEGORY_META.map((meta) => {
        const group = grouped[meta.key];
        return (
          <section key={meta.key} style={{ marginBottom: 22 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 8,
              }}
            >
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "var(--ink)" }}>
                {meta.label}
              </h3>
              <Tag tone="neutral">{group.length}</Tag>
              <span style={{ fontSize: 12, color: "var(--ink-4)" }}>{meta.hint}</span>
              {isAdmin && (
                <Btn
                  size="sm"
                  variant="secondary"
                  icon={<I.Plus size={13} />}
                  onClick={() => openCreate(meta.key)}
                  style={{ marginLeft: "auto" }}
                >
                  新增
                </Btn>
              )}
            </div>
            {group.length === 0 ? (
              <div
                style={{
                  padding: "18px 12px",
                  textAlign: "center",
                  color: "var(--ink-3)",
                  fontSize: 13,
                  border: "1px dashed var(--line)",
                  borderRadius: 8,
                  background: "var(--bg)",
                }}
              >
                暂无{meta.label}条目。
              </div>
            ) : (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
                  gap: 12,
                }}
              >
                {group.map((item) => (
                  <ItemCard
                    key={item.id}
                    item={item}
                    isAdmin={isAdmin}
                    onEdit={() => openEdit(item)}
                    onDelete={() => remove(item)}
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}

      {editor.open && (
        <MethodologyEditor
          state={editor}
          setState={setEditor}
          onSubmit={submit}
          onClose={() => !editor.saving && setEditor(EMPTY_EDITOR)}
        />
      )}
    </div>
  );
}
