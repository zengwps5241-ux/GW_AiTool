// 待采纳草稿徽标（M4.4.5 / §7.1 第8条 找回兜底）
// Topbar 项目级「N 待采纳」徽标：聚合本项目三类 pending 草稿（业务地图/角色卡/拜访），
// 点击展开轻量列表，可直接采纳或跳回原对话。解决用户离开生成草稿的对话后"找不到草稿"。
import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import { useToast } from "@/components/ui";
import { I } from "@/icons";
import type { Project } from "@/types";

/** 统一的待采纳条目（三类草稿归一） */
interface PendingItem {
  entityType: string;
  draftId: number;
  label: string;
  sub?: string;
  sessionId: string | null;
}

interface Props {
  project: Project | null;
  /** 跳回原对话：把 source_session_id 交给对话页打开 */
  onJumpToChat: (sessionId: string) => void;
}

export default function PendingDraftsBadge({ project, onJumpToChat }: Props) {
  const toast = useToast();
  const [items, setItems] = useState<PendingItem[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [adopting, setAdopting] = useState<string | null>(null); // `${entityType}:${draftId}`

  const projectId = project?.id ?? null;

  const refresh = useCallback(async () => {
    if (projectId == null) {
      setItems([]);
      return;
    }
    setLoading(true);
    try {
      const [bmDraft, cards, visits] = await Promise.all([
        api.getActiveBusinessMapDraft(projectId),
        api.listStakeholderCards(projectId, { review_status: "draft", include_drafts: true }),
        api.listVisitRecords(projectId, { review_status: "draft", include_drafts: true }),
      ]);
      const next: PendingItem[] = [];
      const bmReady = bmDraft?.draft_data?.ready_for_adoption !== false;
      if (bmDraft && bmReady) {
        next.push({
          entityType: "business_map_draft",
          draftId: bmDraft.id,
          label: `业务地图草稿 v${bmDraft.revision}`,
          sub: "整图草稿单元",
          sessionId: bmDraft.source_session_id,
        });
      }
      for (const c of cards) {
        next.push({
          entityType: "stakeholder_card_draft",
          draftId: c.id,
          label: c.name,
          sub: [c.position, c.department].filter(Boolean).join(" · ") || "角色卡",
          sessionId: c.source_session_id,
        });
      }
      for (const v of visits) {
        next.push({
          entityType: "visit_record_draft",
          draftId: v.id,
          label: `${v.visit_type}${v.visit_date ? ` · ${v.visit_date}` : ""}`,
          sub: v.summary ? v.summary.slice(0, 30) : "拜访记录",
          sessionId: v.source_session_id,
        });
      }
      setItems(next);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // 打开浮层时刷新（采纳可能在别处发生）
  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  const adopt = async (item: PendingItem) => {
    if (projectId == null) return;
    const key = `${item.entityType}:${item.draftId}`;
    setAdopting(key);
    try {
      const res = await api.adoptDraft(projectId, item.entityType, item.draftId);
      toast.showToast(res.message || "采纳成功", "success");
      setItems((prev) => prev.filter((it) => `${it.entityType}:${it.draftId}` !== key));
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "采纳失败", "error");
    } finally {
      setAdopting(null);
    }
  };

  if (projectId == null || items.length === 0) return null;
  const count = items.length;

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        title="待采纳草稿"
        style={{
          all: "unset", cursor: "pointer", display: "flex", alignItems: "center", gap: 5,
          padding: "4px 10px", borderRadius: 999,
          background: "var(--accent-soft)", border: "1px solid var(--accent)",
          fontSize: 12, fontWeight: 600, color: "var(--accent)",
        }}
      >
        <I.Sparkles size={13} />
        待采纳
        <span style={{
          minWidth: 16, height: 16, padding: "0 5px", borderRadius: 999,
          background: "var(--accent)", color: "#FFFCF5", fontSize: 11, fontWeight: 700,
          display: "inline-flex", alignItems: "center", justifyContent: "center",
        }}>{count}</span>
      </button>

      {open && (
        <>
          {/* 点遮罩关闭 */}
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 200 }} />
          <div style={{
            position: "absolute", right: 0, top: "calc(100% + 6px)", zIndex: 201,
            width: 320, maxHeight: 420, overflow: "auto",
            background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 10,
            boxShadow: "0 8px 32px rgba(0,0,0,0.18)", padding: 8,
          }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", padding: "6px 8px", textTransform: "uppercase", letterSpacing: 0.5 }}>
              待采纳草稿（{count}）
            </div>
            {loading && items.length === 0 ? (
              <div style={{ padding: 16, textAlign: "center", fontSize: 12, color: "var(--ink-3)" }}>加载中…</div>
            ) : (
              items.map((item) => {
                const key = `${item.entityType}:${item.draftId}`;
                const busy = adopting === key;
                return (
                  <div key={key} style={{
                    padding: 10, margin: "2px 0", borderRadius: 8,
                    background: "var(--bg-2)", border: "1px solid var(--line)",
                  }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>{item.label}</div>
                    {item.sub && <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>{item.sub}</div>}
                    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                      <button
                        onClick={() => adopt(item)}
                        disabled={busy}
                        style={{
                          padding: "4px 12px", borderRadius: 6, border: "none", cursor: busy ? "wait" : "pointer",
                          background: "var(--accent)", color: "#fff", fontSize: 12, fontWeight: 600, opacity: busy ? 0.6 : 1,
                        }}
                      >{busy ? "采纳中…" : "采纳"}</button>
                      {item.sessionId && (
                        <button
                          onClick={() => { onJumpToChat(item.sessionId!); setOpen(false); }}
                          style={{
                            padding: "4px 12px", borderRadius: 6, cursor: "pointer",
                            background: "transparent", color: "var(--ink-2)", border: "1px solid var(--line)", fontSize: 12,
                          }}
                        >跳回对话</button>
                      )}
                    </div>
                  </div>
                );
              })
            )}
            <div style={{ fontSize: 10, color: "var(--ink-4)", padding: "6px 8px", lineHeight: 1.5 }}>
              采纳即发布到正式库（Owner 直接发布 / 成员进入待审核）。角色卡/拜访草稿须带会话 ID 才能跳回。
            </div>
          </div>
        </>
      )}
    </div>
  );
}
