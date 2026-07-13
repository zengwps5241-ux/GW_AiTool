import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "@/api/client";
import type { TeamSpace } from "@/types";
import { Btn, Input, useToast } from "@/components/ui";
import { PublicAssetsView } from "@/components/PublicAssetsView";
import { I } from "@/icons";

type SpaceTab = "spaces" | "public";

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "8px 14px",
        fontSize: 13,
        fontWeight: active ? 500 : 400,
        color: active ? "var(--accent)" : "var(--ink-2)",
        background: "transparent",
        border: "none",
        borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
        marginBottom: -1,
        cursor: "pointer",
        transition: "color 120ms, border-color 120ms",
      }}
    >
      {label}
    </button>
  );
}

interface Props {
  onOpenChat: (space: TeamSpace) => void;
  onOpenDetail: (space: TeamSpace) => void;
}

export default function TeamSpacesPage({ onOpenChat, onOpenDetail }: Props) {
  const { showToast } = useToast();
  const [tab, setTab] = useState<SpaceTab>("spaces");
  const [spaces, setSpaces] = useState<TeamSpace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);

  const loadSpaces = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSpaces(await api.teamSpaces());
    } catch (e) {
      setError((e as Error).message || "加载团队空间失败");
      setSpaces([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSpaces();
  }, [loadSpaces]);

  const submitCreate = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || creating) return;
    setCreating(true);
    try {
      const created = await api.createTeamSpace({
        name: trimmed,
        description: description.trim() || null,
      });
      setSpaces((prev) => [created, ...prev.filter((item) => item.id !== created.id)]);
      setName("");
      setDescription("");
      setDialogOpen(false);
      showToast("团队空间已创建", "success");
    } catch (e) {
      showToast((e as Error).message || "创建团队空间失败", "error");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ flex: 1, padding: 24, overflow: "auto" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              border: "1px solid var(--line)",
              background: "var(--surface)",
              color: "var(--accent)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <I.Folders size={17} />
          </span>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>团队空间</h2>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Btn
            variant="secondary"
            icon={loading ? <I.Loader size={14} /> : <I.Refresh size={14} />}
            onClick={loadSpaces}
            disabled={loading}
          >
            刷新
          </Btn>
          <Btn
            variant="primary"
            icon={<I.Plus size={14} />}
            onClick={() => setDialogOpen(true)}
            style={tab === "public" ? { display: "none" } : undefined}
          >
            创建团队空间
          </Btn>
        </div>
      </div>

      {/* 子页签：协作空间（文件工作区）/ 公开资产（M5.5.3 跨项目对象公开） */}
      <div
        style={{
          display: "flex",
          gap: 4,
          borderBottom: "1px solid var(--line)",
          marginBottom: 16,
        }}
      >
        <TabButton active={tab === "spaces"} label="协作空间" onClick={() => setTab("spaces")} />
        <TabButton active={tab === "public"} label="公开资产" onClick={() => setTab("public")} />
      </div>

      {tab === "public" ? (
        <PublicAssetsView />
      ) : (
      <>
      {error && (
        <div
          style={{
            marginBottom: 12,
            padding: "9px 12px",
            border: "1px solid var(--line)",
            borderRadius: 8,
            background: "var(--danger-soft)",
            color: "var(--danger)",
            fontSize: 13,
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <I.CircleAlert size={14} />
          {error}
        </div>
      )}

      {loading && spaces.length === 0 ? (
        <div style={{ color: "var(--ink-3)", fontSize: 13 }}>加载中…</div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: 12,
          }}
        >
          {spaces.map((space) => (
            <article
              key={space.id}
              style={{
                border: "1px solid var(--line)",
                borderRadius: 8,
                padding: 14,
                background: "var(--surface)",
                boxShadow: "var(--shadow-sm)",
                minHeight: 150,
                display: "flex",
                flexDirection: "column",
                gap: 12,
              }}
            >
              <button
                type="button"
                onClick={() => onOpenDetail(space)}
                style={{
                  all: "unset",
                  cursor: "pointer",
                  display: "block",
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    fontSize: 15,
                    fontWeight: 700,
                    color: "var(--ink)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={space.name}
                >
                  {space.name}
                </div>
                <div
                  style={{
                    color: "var(--ink-3)",
                    fontSize: 12,
                    lineHeight: 1.5,
                    marginTop: 6,
                    minHeight: 36,
                  }}
                >
                  {space.description || "暂无描述"}
                </div>
              </button>
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 6,
                  color: "var(--ink-3)",
                  fontSize: 12,
                }}
              >
                <span>{space.member_count} 人</span>
                <span>·</span>
                <span>{space.member_role === "editor" ? "可编辑" : "只读"}</span>
                {space.locked_by_user_id && (
                  <>
                    <span>·</span>
                    <span>已锁定</span>
                  </>
                )}
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: "auto" }}>
                <Btn
                  size="sm"
                  icon={<I.MessagesSquare size={14} />}
                  onClick={() => onOpenChat(space)}
                >
                  对话
                </Btn>
                <Btn
                  size="sm"
                  variant="secondary"
                  icon={<I.ExternalLink size={14} />}
                  onClick={() => onOpenDetail(space)}
                >
                  进入
                </Btn>
              </div>
            </article>
          ))}
        </div>
      )}

      {!loading && !error && spaces.length === 0 && (
        <div style={{ color: "var(--ink-3)", fontSize: 13 }}>暂无团队空间</div>
      )}
      </>
      )}

      {dialogOpen && (
        <div
          onClick={() => !creating && setDialogOpen(false)}
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
            onSubmit={submitCreate}
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(420px, 100%)",
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
            <h3 style={{ margin: 0, fontSize: 16 }}>创建团队空间</h3>
            <Input
              placeholder="空间名称"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
            <textarea
              placeholder="描述"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              style={{
                resize: "vertical",
                minHeight: 78,
                border: "1px solid var(--line)",
                borderRadius: 8,
                background: "var(--bg)",
                color: "var(--ink)",
                padding: "9px 10px",
                font: "inherit",
                outline: "none",
              }}
            />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <Btn
                type="button"
                variant="secondary"
                onClick={() => setDialogOpen(false)}
                disabled={creating}
              >
                取消
              </Btn>
              <Btn
                type="submit"
                icon={creating ? <I.Loader size={14} /> : <I.Plus size={14} />}
                disabled={creating || !name.trim()}
              >
                创建
              </Btn>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
