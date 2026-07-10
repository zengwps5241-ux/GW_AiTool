// 拜访记录页面（M4.3 / §2.5）
// 替换 V1.0 原型：改为消费真实后端 /api/projects/{id}/{visit-records,evidence-sources}。
// 顶部项目选择器由全局 Topbar（M1.3.9/M4.4.1）驱动，本页接收 project prop。
// 数据来源：该项目下所有 VisitRecord（reviewed）+ 已确认 EvidenceSource（reviewed），单一数据源。
// ── M4.3.1 骨架：项目上下文栏 + 统计栏 + 拜访列表加载 + 证据概览面板 + 加载/错误/空态。
// 拜访卡详情（M4.3.2）、证据筛选面板（M4.3.3）、展开证据清单（M4.3.4）、
// 态度联动（M4.3.5）、拜访/证据 CRUD（M4.3.6）见后续任务。
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { Card, Spinner, Tag, useToast } from "@/components/ui";
import { I } from "@/icons";
import type { EvidenceSource, Project, VisitRecord } from "@/types";

// ─── 常量 ─────────────────────────────────────────────────────

/** 拜访类型 → 配色（§2.5 五类：现场访谈/电话沟通/视频会议/邮件/一句话记录 + 兜底） */
const visitTypeColor = (t: string): string => {
  switch (t) {
    case "现场访谈":
      return "var(--accent)";
    case "电话沟通":
      return "var(--info)";
    case "视频会议":
      return "var(--success)";
    case "邮件":
    case "邮件往来":
      return "var(--ink-3)";
    case "一句话记录":
      return "var(--warn)";
    default:
      return "var(--ink-3)";
  }
};

/** 证据强度 → 配色（强/中/弱 + 兜底） */
const strengthColor = (s: string): string =>
  s === "强" ? "var(--success)" : s === "中" ? "var(--warn)" : "var(--ink-3)";

const STRENGTHS = ["强", "中", "弱"] as const;

interface Props {
  /** 全局选中项目（Topbar ProjectSelector 驱动） */
  project: Project | null;
}

// ─── 页面组件 ─────────────────────────────────────────────────

export default function VisitRecordsPage({ project }: Props) {
  const toast = useToast();
  const [visits, setVisits] = useState<VisitRecord[]>([]);
  const [evidences, setEvidences] = useState<EvidenceSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const projectId = project?.id ?? null;

  // 拉取已审拜访记录 + 已确认证据（单一数据源，§2.5）
  const refresh = useCallback(async () => {
    if (projectId == null) {
      setVisits([]);
      setEvidences([]);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [v, e] = await Promise.all([
        api.listVisitRecords(projectId, { review_status: "reviewed" }),
        api.listEvidence(projectId, { review_status: "reviewed" }),
      ]);
      setVisits(v);
      setEvidences(e);
    } catch (e2) {
      const msg = e2 instanceof Error ? e2.message : "加载拜访记录失败";
      setError(msg);
      toast.showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // 派生：统计栏 + 证据强度分布
  const stats = useMemo(() => {
    const visitCount = visits.length;
    const roleIds = new Set<number>();
    visits.forEach((v) => v.related_card_ids?.forEach((id) => roleIds.add(id)));
    const verified = visits.reduce((s, v) => s + (v.verified_hypotheses ?? 0), 0);
    const totalEvidence = evidences.length;
    const byStrength = (s: string) => evidences.filter((e) => e.strength === s).length;
    return {
      visitCount,
      roleCount: roleIds.size,
      totalEvidence,
      verified,
      strengthCounts: STRENGTHS.map((s) => ({ strength: s, count: byStrength(s) })),
    };
  }, [visits, evidences]);

  // 拜访记录按时间倒序（visit_date 降序，空值置底）
  const sortedVisits = useMemo(() => {
    return [...visits].sort((a, b) => {
      const da = a.visit_date ?? "";
      const db = b.visit_date ?? "";
      return db.localeCompare(da);
    });
  }, [visits]);

  // ─── 渲染 ───────────────────────────────────────────────────

  // 未选项目：空状态引导
  if (project == null) {
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", padding: 40 }}>
        <Card style={{ padding: 40, textAlign: "center", maxWidth: 420 }}>
          <I.Briefcase size={36} style={{ color: "var(--ink-4)", marginBottom: 12 }} />
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>
            请先选择项目
          </div>
          <div style={{ fontSize: 13, color: "var(--ink-3)", lineHeight: 1.7 }}>
            使用顶部项目选择器选择一个项目，即可查看其拜访记录时间线与证据列表。
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* 项目上下文栏 + 统计 */}
      <div style={topBarStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <I.Briefcase size={16} style={{ color: "var(--accent)", flexShrink: 0 }} />
          <span style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {project.name}
          </span>
          {project.customer_name && (
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>· {project.customer_name}</span>
          )}
          {project.my_role && (
            <Tag tone={project.my_role === "owner" ? "accent" : "neutral"}>
              {project.my_role === "owner" ? "负责人" : project.my_role === "deputy" ? "成员" : project.my_role}
            </Tag>
          )}
        </div>
        <div style={{ flex: 1 }} />
        <span style={statStyle}>拜访次数: <b style={{ color: "var(--ink)" }}>{stats.visitCount}</b></span>
        <span style={statStyle}>涉及角色: <b style={{ color: "var(--ink)" }}>{stats.roleCount}</b></span>
        <span style={statStyle}>总证据: <b style={{ color: "var(--ink)" }}>{stats.totalEvidence}</b></span>
        <span style={{ ...statStyle, color: "var(--success)" }}>
          已验证假设: <b>{stats.verified}</b>
        </span>
      </div>

      {/* 主内容：两栏（左拜访时间线 + 右证据面板） */}
      <div style={{ flex: 1, overflow: "auto", padding: 20, display: "flex", gap: 20 }}>
        {/* 左：拜访记录列表（时间倒序） */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 12 }}>
          {loading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: 60 }}>
              <Spinner size={20} />
            </div>
          ) : error ? (
            <Card style={{ padding: 24, textAlign: "center", color: "var(--danger)" }}>
              <I.CircleAlert size={24} style={{ marginBottom: 8 }} />
              <div style={{ fontSize: 13 }}>{error}</div>
              <button onClick={refresh} style={retryBtnStyle}>重试</button>
            </Card>
          ) : sortedVisits.length === 0 ? (
            <Card style={{ padding: 40, textAlign: "center" }}>
              <I.Calendar size={32} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>
                暂无拜访记录
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-3)", lineHeight: 1.7 }}>
                该项目下还没有已确认的拜访记录。在对话中产出的候选拜访/证据经审批采纳后，将在此展示。
              </div>
            </Card>
          ) : (
            sortedVisits.map((v) => <VisitRow key={v.id} visit={v} />)
          )}
        </div>

        {/* 右：证据概览面板（M4.3.3 将升级为完整筛选面板） */}
        <Card style={{ width: 320, padding: 20, flexShrink: 0, alignSelf: "flex-start", position: "sticky", top: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 16 }}>
            证据概览
          </div>

          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 16 }}>
            <span style={{ fontSize: 28, fontWeight: 700, color: "var(--ink)" }}>{stats.totalEvidence}</span>
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>条已确认证据</span>
          </div>

          {/* 强度分布 */}
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 10 }}>
              强度分布
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 12 }}>
              {stats.strengthCounts.map(({ strength, count }) => (
                <div key={strength} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ width: 6, height: 6, borderRadius: 999, background: strengthColor(strength) }} />
                    <span style={{ color: "var(--ink-2)" }}>{strength}证据</span>
                  </div>
                  <b style={{ color: "var(--ink)" }}>{count}</b>
                  <div style={{ width: 60, height: 4, background: "var(--bg-3)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{
                      width: `${stats.totalEvidence ? (count / stats.totalEvidence) * 100 : 0}%`,
                      height: "100%", background: strengthColor(strength), borderRadius: 2, transition: "width 300ms",
                    }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

// ─── 拜访记录行（M4.3.1 基础卡，M4.3.2 升级完整字段 + 展开占位）─────

function VisitRow({ visit }: { visit: VisitRecord }) {
  const date = visit.visit_date;
  const ourCount = visit.participants_our?.length ?? 0;
  const clientCount = visit.participants_client?.length ?? 0;
  return (
    <Card style={{ padding: "16px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        {/* 日期 */}
        <div style={{ textAlign: "center", flexShrink: 0, width: 56 }}>
          {date ? (
            <>
              <div style={{ fontSize: 20, fontWeight: 700, color: "var(--ink)", lineHeight: 1 }}>{date.slice(8)}</div>
              <div style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 2 }}>{date.slice(5, 7)}月</div>
            </>
          ) : (
            <div style={{ fontSize: 11, color: "var(--ink-4)" }}>未定</div>
          )}
        </div>
        {/* 类型标签 */}
        <span style={{
          padding: "3px 10px", borderRadius: 999, fontSize: 11, fontWeight: 600, flexShrink: 0,
          background: visitTypeColor(visit.visit_type) + "20", color: visitTypeColor(visit.visit_type),
        }}>
          {visit.visit_type}
        </span>
        {/* 摘要 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {visit.summary ? (visit.summary.length > 50 ? visit.summary.slice(0, 50) + "…" : visit.summary) : "（无摘要）"}
          </div>
          <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2, display: "flex", gap: 10 }}>
            <span><I.Users size={11} style={{ verticalAlign: -1, marginRight: 3 }} />我方 {ourCount} · 客户 {clientCount}</span>
            {visit.location && <span>📍 {visit.location}</span>}
          </div>
        </div>
        {/* 统计 */}
        <div style={{ display: "flex", gap: 14, fontSize: 11, color: "var(--ink-3)", flexShrink: 0 }}>
          <span title="证据数"><I.Paperclip size={12} style={{ verticalAlign: -1, marginRight: 3 }} />{visit.evidence_count}</span>
          <span title="已验证假设" style={{ color: "var(--success)" }}><I.CircleCheck size={12} style={{ verticalAlign: -1, marginRight: 3 }} />{visit.verified_hypotheses}</span>
        </div>
      </div>
    </Card>
  );
}

// ─── 样式 ─────────────────────────────────────────────────────

const topBarStyle: React.CSSProperties = {
  padding: "12px 20px",
  borderBottom: "1px solid var(--line)",
  background: "var(--bg)",
  display: "flex",
  alignItems: "center",
  gap: 16,
  flexShrink: 0,
};

const statStyle: React.CSSProperties = {
  fontSize: 12,
  color: "var(--ink-3)",
  whiteSpace: "nowrap",
};

const retryBtnStyle: React.CSSProperties = {
  marginTop: 12, padding: "6px 18px", borderRadius: 8, fontSize: 12, fontWeight: 500,
  border: "1px solid var(--line)", background: "var(--surface)", color: "var(--ink-2)",
  cursor: "pointer", fontFamily: "inherit",
};
