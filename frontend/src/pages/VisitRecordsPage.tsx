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
import MarkdownView from "@/components/workspace/MarkdownView";
import { I } from "@/icons";
import type {
  EvidenceSource,
  Project,
  StakeholderCard,
  VisitRecord,
  VisitRecordInput,
} from "@/types";

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

/** 立场 → 配色（对齐 MarketingMapPage stanceColor：支持/反对/中立/观望） */
const stanceColor = (s: string): string => {
  if (s === "支持") return "var(--success)";
  if (s === "反对") return "var(--danger)";
  if (s === "中立") return "var(--warn)";
  return "var(--ink-3)"; // 观望 / 未知
};

const STRENGTHS = ["强", "中", "弱"] as const;

/** 证据类型枚举（§2.5 / §7.5） */
const EVIDENCE_TYPES = ["客户原话", "行为观察", "角色态度信号", "业务术语"] as const;

/** 拜访类型枚举（§2.5：现场访谈/电话沟通/视频会议/邮件/一句话记录） */
const VISIT_TYPES = ["现场访谈", "电话沟通", "视频会议", "邮件", "一句话记录"] as const;

/** 证据类型 → 展示标签（带图标） */
const evidenceTypeLabel: Record<string, string> = {
  客户原话: "💬 客户原话",
  行为观察: "👁️ 行为观察",
  角色态度信号: "🎯 态度信号",
  业务术语: "📖 业务术语",
};

interface Props {
  /** 全局选中项目（Topbar ProjectSelector 驱动） */
  project: Project | null;
}

// ─── 页面组件 ─────────────────────────────────────────────────

export default function VisitRecordsPage({ project }: Props) {
  const toast = useToast();
  const [visits, setVisits] = useState<VisitRecord[]>([]);
  const [evidences, setEvidences] = useState<EvidenceSource[]>([]);
  const [cards, setCards] = useState<StakeholderCard[]>([]);
  const [expandedVisitId, setExpandedVisitId] = useState<number | null>(null);
  const [filterType, setFilterType] = useState<string>("全部");
  const [filterStrength, setFilterStrength] = useState<string>("全部");
  const [filterRole, setFilterRole] = useState<string>("全部");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 拜访记录编辑弹窗（null=关闭；create=新建；edit=编辑指定拜访）
  const [visitModal, setVisitModal] = useState<
    { mode: "create" } | { mode: "edit"; visit: VisitRecord } | null
  >(null);

  const projectId = project?.id ?? null;

  // 拉取已审拜访记录 + 已确认证据（单一数据源，§2.5）
  const refresh = useCallback(async () => {
    if (projectId == null) {
      setVisits([]);
      setEvidences([]);
      setCards([]);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [v, e, c] = await Promise.all([
        api.listVisitRecords(projectId, { review_status: "reviewed" }),
        api.listEvidence(projectId, { review_status: "reviewed" }),
        // 角色卡用于把 participants_client 的角色 ID 解析为姓名（§2.5 参与人关联 StakeholderCard）
        api.listStakeholderCards(projectId, { review_status: "reviewed" }),
      ]);
      setVisits(v);
      setEvidences(e);
      setCards(c);
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

  // 删除拜访记录（其下证据由后端级联删除）
  const handleDeleteVisit = useCallback(
    async (visit: VisitRecord) => {
      if (projectId == null) return;
      if (
        !window.confirm(
          `确认删除该拜访记录（${visit.visit_date ?? "未定日期"} · ${visit.visit_type}）？其下证据将一并删除。`,
        )
      )
        return;
      try {
        await api.deleteVisitRecord(projectId, visit.id);
        toast.showToast("已删除拜访记录", "success");
        setExpandedVisitId(null);
        refresh();
      } catch (e) {
        toast.showToast(e instanceof Error ? e.message : "删除失败", "error");
      }
    },
    [projectId, toast, refresh],
  );

  // 切换项目时收起展开的拜访卡 + 重置筛选
  useEffect(() => {
    setExpandedVisitId(null);
    setFilterType("全部");
    setFilterStrength("全部");
    setFilterRole("全部");
  }, [projectId]);

  // 角色 ID → 姓名映射（解析客户方参与人）
  const cardMap = useMemo(() => {
    const m = new Map<number, string>();
    cards.forEach((c) => m.set(c.id, c.name));
    return m;
  }, [cards]);

  // 拜访 ID → 日期（证据结果列表展示来源拜访日期）
  const visitDateMap = useMemo(() => {
    const m = new Map<number, string>();
    visits.forEach((v) => {
      if (v.visit_date) m.set(v.id, v.visit_date);
    });
    return m;
  }, [visits]);

  // 证据筛选：涉及角色候选（来自已确认证据的来源角色名）
  const roleOptions = useMemo(
    () =>
      [
        ...new Set(
          evidences
            .map((e) => e.source_role_name)
            .filter((n): n is string => Boolean(n)),
        ),
      ] as string[],
    [evidences],
  );

  // 筛选后的证据（类型 / 强度 / 角色）
  const filteredEvidences = useMemo(
    () =>
      evidences
        .filter((e) => filterType === "全部" || e.evidence_type === filterType)
        .filter((e) => filterStrength === "全部" || e.strength === filterStrength)
        .filter((e) => filterRole === "全部" || e.source_role_name === filterRole),
    [evidences, filterType, filterStrength, filterRole],
  );

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
        <button
          onClick={() => setVisitModal({ mode: "create" })}
          style={primaryBtnStyle}
          title="新增拜访记录"
        >
          <I.Plus size={13} /> 新增拜访
        </button>
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
            sortedVisits.map((v) => (
              <VisitRow
                key={v.id}
                visit={v}
                cardMap={cardMap}
                visitEvidences={evidences.filter((e) => e.visit_record_id === v.id)}
                expanded={expandedVisitId === v.id}
                onToggle={() =>
                  setExpandedVisitId(expandedVisitId === v.id ? null : v.id)
                }
                onEdit={() => setVisitModal({ mode: "edit", visit: v })}
                onDelete={() => handleDeleteVisit(v)}
              />
            ))
          )}
        </div>

        {/* 右：证据筛选面板 */}
        <Card style={{ width: 320, padding: 20, flexShrink: 0, alignSelf: "flex-start", position: "sticky", top: 0, maxHeight: "calc(100vh - 140px)", overflow: "auto" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 16 }}>
            证据筛选
          </div>

          {/* 类型筛选 */}
          <div style={{ marginBottom: 12 }}>
            <div style={filterLabelStyle}>证据类型</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {(["全部", ...EVIDENCE_TYPES] as string[]).map((t) => (
                <button key={t} onClick={() => setFilterType(t)} style={filterChipStyle(filterType === t)}>
                  {t === "全部" ? "全部" : evidenceTypeLabel[t] ?? t}
                </button>
              ))}
            </div>
          </div>

          {/* 强度筛选 */}
          <div style={{ marginBottom: 12 }}>
            <div style={filterLabelStyle}>证据强度</div>
            <div style={{ display: "flex", gap: 6 }}>
              {(["全部", ...STRENGTHS] as string[]).map((s) => (
                <button
                  key={s}
                  onClick={() => setFilterStrength(s)}
                  style={{
                    ...filterChipStyle(filterStrength === s),
                    color: filterStrength === s ? "var(--accent)" : s === "强" ? "var(--success)" : s === "中" ? "var(--warn)" : "var(--ink-2)",
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* 角色筛选 */}
          <div style={{ marginBottom: 14 }}>
            <div style={filterLabelStyle}>关联角色</div>
            <select
              value={filterRole}
              onChange={(e) => setFilterRole(e.target.value)}
              style={{
                width: "100%", fontFamily: "inherit", fontSize: 12, background: "var(--surface)",
                border: "1px solid var(--line)", borderRadius: 6, padding: "6px 10px", color: "var(--ink)",
              }}
            >
              <option value="全部">全部角色</option>
              {roleOptions.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          {/* 筛选结果 */}
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-2)", marginBottom: 10 }}>
              筛选结果（{filteredEvidences.length}条）
            </div>
            {filteredEvidences.length === 0 ? (
              <div style={{ fontSize: 12, color: "var(--ink-3)", textAlign: "center", padding: 20 }}>
                {evidences.length === 0 ? "暂无已确认证据" : "无匹配证据"}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {filteredEvidences.map((e) => {
                  const vd = e.visit_record_id != null ? visitDateMap.get(e.visit_record_id) : null;
                  return (
                    <div key={e.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--line)", fontSize: 11 }}>
                      <div style={{ display: "flex", gap: 4, marginBottom: 4, flexWrap: "wrap" }}>
                        {vd && (
                          <span style={metaTagStyle({ bg: "var(--bg-3)", color: "var(--ink-3)" })}>{vd}</span>
                        )}
                        {e.source_role_name && (
                          <span style={metaTagStyle({ bg: "var(--info-soft)", color: "var(--info)" })}>{e.source_role_name}</span>
                        )}
                        <span style={metaTagStyle({ bg: strengthColor(e.strength) + "18", color: strengthColor(e.strength), weight: 500 })}>
                          {e.strength}
                        </span>
                      </div>
                      <div style={{ lineHeight: 1.5, color: "var(--ink-2)" }}>
                        {e.content.length > 80 ? e.content.slice(0, 80) + "…" : e.content}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 强度统计 */}
          <div style={{ marginTop: 16, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 8 }}>
              证据统计（共 {stats.totalEvidence} 条）
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
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

      {/* 拜访记录编辑弹窗（新增/编辑） */}
      {visitModal && projectId != null && (
        <VisitFormModal
          projectId={projectId}
          cards={cards}
          visit={"visit" in visitModal ? visitModal.visit : null}
          onClose={() => setVisitModal(null)}
          onSaved={() => {
            setVisitModal(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}

// ─── 拜访记录编辑弹窗（M4.3.6 新增/编辑，手动写入默认 reviewed §7.3）─────

function VisitFormModal({
  projectId,
  cards,
  visit,
  onClose,
  onSaved,
}: {
  projectId: number;
  cards: StakeholderCard[];
  visit: VisitRecord | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [visitDate, setVisitDate] = useState(visit?.visit_date ?? "");
  const [visitType, setVisitType] = useState<string>(visit?.visit_type ?? "现场访谈");
  const [ourParts, setOurParts] = useState((visit?.participants_our ?? []).join("、"));
  // 客户方参与人 = 关联角色卡（手动录入两者同步，简化表单）
  const [clientIds, setClientIds] = useState<number[]>(visit?.participants_client ?? []);
  const [location, setLocation] = useState(visit?.location ?? "");
  const [duration, setDuration] = useState(visit?.duration ?? "");
  const [summary, setSummary] = useState(visit?.summary ?? "");
  const [takeaways, setTakeaways] = useState((visit?.key_takeaways ?? []).join("\n"));
  const [nextSteps, setNextSteps] = useState(visit?.next_steps ?? "");
  const [saving, setSaving] = useState(false);

  const toggleClient = (id: number) =>
    setClientIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );

  const save = async () => {
    setSaving(true);
    // 我方参与按 、/，/换行 分割；关键洞察按行分割
    const ourList = ourParts.split(/[、,，\n]/).map((s) => s.trim()).filter(Boolean);
    const takeawayList = takeaways.split("\n").map((s) => s.trim()).filter(Boolean);
    const payload: VisitRecordInput = {
      visit_type: visitType,
      visit_date: visitDate || null,
      participants_our: ourList.length ? ourList : null,
      participants_client: clientIds.length ? clientIds : null,
      related_card_ids: clientIds.length ? clientIds : null,
      location: location.trim() || null,
      duration: duration.trim() || null,
      summary: summary.trim() || null,
      key_takeaways: takeawayList.length ? takeawayList : null,
      next_steps: nextSteps.trim() || null,
      review_status: "reviewed",
    };
    try {
      if (visit) {
        await api.updateVisitRecord(projectId, visit.id, payload);
        toast.showToast("已更新拜访记录", "success");
      } else {
        await api.createVisitRecord(projectId, payload);
        toast.showToast("已新增拜访记录", "success");
      }
      onSaved();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div onClick={onClose} style={modalOverlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={{ ...modalCardStyle, width: 560, maxHeight: "85vh", overflow: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <I.Calendar size={16} style={{ color: "var(--accent)" }} />
          <span style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)" }}>
            {visit ? "编辑拜访记录" : "新增拜访记录"}
          </span>
          <div style={{ flex: 1 }} />
          <button onClick={onClose} style={iconBtnStyle} title="关闭">✕</button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", gap: 12 }}>
            <label style={{ ...fieldLabelStyle, flex: 1 }}>
              <span style={miniLabelStyle}>拜访日期</span>
              <input type="date" value={visitDate} onChange={(e) => setVisitDate(e.target.value)} style={modalInputStyle} />
            </label>
            <label style={{ ...fieldLabelStyle, flex: 1 }}>
              <span style={miniLabelStyle}>拜访类型</span>
              <select value={visitType} onChange={(e) => setVisitType(e.target.value)} style={selectStyle}>
                {VISIT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
          </div>

          <label style={fieldLabelStyle}>
            <span style={miniLabelStyle}>我方参与人（顿号/逗号分隔）</span>
            <input value={ourParts} onChange={(e) => setOurParts(e.target.value)} placeholder="如：张顾问、李工" style={modalInputStyle} />
          </label>

          <label style={fieldLabelStyle}>
            <span style={miniLabelStyle}>客户方参与人 / 关联角色（多选）</span>
            <div style={clientPickStyle}>
              {cards.length === 0 ? (
                <span style={{ fontSize: 11, color: "var(--ink-4)" }}>该项目暂无已确认角色卡</span>
              ) : (
                cards.map((c) => {
                  const checked = clientIds.includes(c.id);
                  return (
                    <label key={c.id} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, cursor: "pointer", color: checked ? "var(--accent)" : "var(--ink-2)" }}>
                      <input type="checkbox" checked={checked} onChange={() => toggleClient(c.id)} />
                      {c.name}{c.position ? ` · ${c.position}` : ""}
                    </label>
                  );
                })
              )}
            </div>
          </label>

          <div style={{ display: "flex", gap: 12 }}>
            <label style={{ ...fieldLabelStyle, flex: 1 }}>
              <span style={miniLabelStyle}>地点</span>
              <input value={location} onChange={(e) => setLocation(e.target.value)} style={modalInputStyle} />
            </label>
            <label style={{ ...fieldLabelStyle, flex: 1 }}>
              <span style={miniLabelStyle}>时长</span>
              <input value={duration} onChange={(e) => setDuration(e.target.value)} placeholder="如：2小时" style={modalInputStyle} />
            </label>
          </div>

          <label style={fieldLabelStyle}>
            <span style={miniLabelStyle}>拜访摘要</span>
            <textarea value={summary} onChange={(e) => setSummary(e.target.value)} rows={3} style={textareaStyle} />
          </label>

          <label style={fieldLabelStyle}>
            <span style={miniLabelStyle}>关键洞察（每行一条）</span>
            <textarea value={takeaways} onChange={(e) => setTakeaways(e.target.value)} rows={3} placeholder={"① …\n② …"} style={textareaStyle} />
          </label>

          <label style={fieldLabelStyle}>
            <span style={miniLabelStyle}>下一步行动（支持 Markdown）</span>
            <textarea value={nextSteps} onChange={(e) => setNextSteps(e.target.value)} rows={3} style={textareaStyle} />
          </label>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <button onClick={onClose} style={ghostBtnStyle}>取消</button>
          <button onClick={save} disabled={saving} style={saveBtnStyle(saving)}>{saving ? "保存中…" : "保存"}</button>
        </div>
      </div>
    </div>
  );
}

// ─── 拜访记录卡（M4.3.2 完整折叠字段 + 可展开基本信息；M4.3.4 追加洞察/证据）─

function VisitRow({
  visit,
  cardMap,
  visitEvidences,
  expanded,
  onToggle,
  onEdit,
  onDelete,
}: {
  visit: VisitRecord;
  cardMap: Map<number, string>;
  visitEvidences: EvidenceSource[];
  expanded: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const date = visit.visit_date;
  const ourNames = visit.participants_our?.join("、") || null;
  // 客户方参与人为角色卡 ID，解析为姓名（未知则回退显示编号）
  const clientNames = (visit.participants_client ?? [])
    .map((id) => cardMap.get(id) ?? `角色#${id}`)
    .join("、");
  const relatedCardCount = visit.related_card_ids?.length ?? 0;
  const keyTakeawaysText = (visit.key_takeaways ?? []).join("\n").trim();

  return (
    <Card style={{ padding: 0, overflow: "hidden" }}>
      {/* 折叠头部（可点击展开） */}
      <div
        onClick={onToggle}
        style={{
          padding: "16px 20px", cursor: "pointer", display: "flex", alignItems: "center", gap: 14,
          transition: "background 120ms",
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-2)"; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
      >
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
        {/* 摘要 + 参与人/地点/时长 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {visit.summary ? (visit.summary.length > 50 ? visit.summary.slice(0, 50) + "…" : visit.summary) : "（无摘要）"}
          </div>
          <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {clientNames && <span>客户：{clientNames}</span>}
            {clientNames && visit.location && <span> · </span>}
            {visit.location && <span>{visit.location}</span>}
            {(clientNames || visit.location) && visit.duration && <span> · </span>}
            {visit.duration && <span>{visit.duration}</span>}
            {!clientNames && !visit.location && !visit.duration && <span style={{ color: "var(--ink-4)" }}>无补充信息</span>}
          </div>
        </div>
        {/* 统计：证据 / 已验证假设 / 关联角色卡 */}
        <div style={{ display: "flex", gap: 14, fontSize: 11, color: "var(--ink-3)", flexShrink: 0 }}>
          <span title="证据数"><I.Paperclip size={12} style={{ verticalAlign: -1, marginRight: 3 }} />{visit.evidence_count}</span>
          <span title="已验证假设" style={{ color: "var(--success)" }}><I.CircleCheck size={12} style={{ verticalAlign: -1, marginRight: 3 }} />{visit.verified_hypotheses}</span>
          <span title="关联角色卡"><I.Users size={12} style={{ verticalAlign: -1, marginRight: 3 }} />{relatedCardCount}</span>
        </div>
        <I.ChevronDown size={14} style={{
          color: "var(--ink-4)", flexShrink: 0,
          transform: expanded ? "rotate(180deg)" : "none", transition: "transform 200ms",
        }} />
      </div>

      {/* 展开体：基本信息 + 关键洞察 + 下一步行动 + 本次证据清单 */}
      {expanded && (
        <div style={{ borderTop: "1px solid var(--line)", padding: "16px 20px", background: "var(--bg)" }}>
          {/* 操作栏 */}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 6, marginBottom: 12 }}>
            <button onClick={onEdit} style={ghostBtnStyle} title="编辑拜访记录">
              <I.Edit size={12} style={{ verticalAlign: -1, marginRight: 4 }} />编辑
            </button>
            <button onClick={onDelete} style={{ ...ghostBtnStyle, color: "var(--danger)", borderColor: "var(--danger)" }} title="删除拜访记录">
              <I.Trash size={12} style={{ verticalAlign: -1, marginRight: 4 }} />删除
            </button>
          </div>

          {/* 基本信息 */}
          <div style={{ display: "flex", gap: 20, fontSize: 12, flexWrap: "wrap", marginBottom: 14 }}>
            <div><span style={{ color: "var(--ink-3)" }}>我方参与：</span><span style={{ fontWeight: 500 }}>{ourNames || "—"}</span></div>
            <div><span style={{ color: "var(--ink-3)" }}>客户参与：</span><span style={{ fontWeight: 500 }}>{clientNames || "—"}</span></div>
            <div><span style={{ color: "var(--ink-3)" }}>地点：</span>{visit.location || "—"}</div>
            <div><span style={{ color: "var(--ink-3)" }}>时长：</span>{visit.duration || "—"}</div>
          </div>

          {/* Key Takeaways */}
          {keyTakeawaysText && (
            <div style={{ padding: "12px 14px", background: "var(--accent-soft)", borderRadius: 8, marginBottom: 14, fontSize: 12, lineHeight: 1.6 }}>
              <div style={{ fontWeight: 700, color: "var(--accent)", marginBottom: 6 }}>💡 关键洞察</div>
              <MarkdownView text={keyTakeawaysText} />
            </div>
          )}

          {/* Next Steps */}
          {visit.next_steps && (
            <div style={{ padding: "12px 14px", background: "var(--info-soft)", borderRadius: 8, marginBottom: 16, fontSize: 12, lineHeight: 1.6 }}>
              <div style={{ fontWeight: 700, color: "var(--info)", marginBottom: 6 }}>📋 下一步行动</div>
              <MarkdownView text={visit.next_steps} />
            </div>
          )}

          {/* 本次拜访产出的证据清单 */}
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 10 }}>
              证据清单（{visitEvidences.length}条）
            </div>
            {visitEvidences.length === 0 ? (
              <div style={{ fontSize: 12, color: "var(--ink-4)", textAlign: "center", padding: 16 }}>本次拜访暂无已确认证据</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {visitEvidences.map((e) => (
                  <EvidenceDetail key={e.id} evidence={e} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

// ─── 证据条目（展开体内部，M4.3.5 将追加态度联动展示）──────────

function EvidenceDetail({ evidence: e }: { evidence: EvidenceSource }) {
  // §7.6：角色态度信号证据携带 implied_from_stance → implied_to_stance，确认后自动记录态度变化
  const hasStanceChange =
    e.evidence_type === "角色态度信号" && (e.implied_from_stance || e.implied_to_stance);
  return (
    <div style={{
      display: "flex", gap: 10, padding: "10px 12px",
      background: "var(--surface)", borderRadius: 8, border: "1px solid var(--line)", fontSize: 12,
    }}>
      <div style={{ width: 6, height: 6, borderRadius: 999, background: strengthColor(e.strength), flexShrink: 0, marginTop: 5 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ lineHeight: 1.6, color: "var(--ink-2)", marginBottom: 6 }}>{e.content}</div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span style={{ padding: "1px 6px", borderRadius: 4, fontSize: 10, background: "var(--bg-3)", color: "var(--ink-3)" }}>
            {evidenceTypeLabel[e.evidence_type] ?? e.evidence_type}
          </span>
          <span style={{
            padding: "1px 6px", borderRadius: 4, fontSize: 10, fontWeight: 500,
            background: strengthColor(e.strength) + "18", color: strengthColor(e.strength),
          }}>
            {e.strength}证据
          </span>
          {e.source_role_name && (
            <span style={{ padding: "1px 6px", borderRadius: 4, fontSize: 10, background: "var(--info-soft)", color: "var(--info)" }}>
              {e.source_role_name}
            </span>
          )}
          {e.related_hypothesis_name && (
            <span style={{ padding: "1px 6px", borderRadius: 4, fontSize: 10, background: "var(--accent-soft)", color: "var(--accent)", fontWeight: 500 }}>
              🔗 {e.related_hypothesis_name}
            </span>
          )}
        </div>
        {/* 态度联动（§7.6）：本次态度信号引发的态度变化 */}
        {hasStanceChange && (
          <div style={{ marginTop: 8, display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11 }}>
            <span style={{ color: "var(--ink-3)" }}>态度变化</span>
            {e.implied_from_stance ? (
              <StancePill stance={e.implied_from_stance} />
            ) : (
              <span style={{ color: "var(--ink-4)" }}>未知</span>
            )}
            <span style={{ color: "var(--ink-4)" }}>→</span>
            {e.implied_to_stance ? (
              <StancePill stance={e.implied_to_stance} />
            ) : (
              <span style={{ color: "var(--ink-4)" }}>未知</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** 立场小药丸（态度联动展示用，配色对齐 stanceColor） */
function StancePill({ stance }: { stance: string }) {
  const c = stanceColor(stance);
  return (
    <span style={{
      padding: "1px 7px", borderRadius: 999, fontSize: 11, fontWeight: 500,
      background: c + "22", color: c,
    }}>
      {stance}
    </span>
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

/** 顶部主要按钮（新增拜访） */
const primaryBtnStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 4,
  padding: "6px 14px", fontSize: 12, fontWeight: 600, fontFamily: "inherit",
  border: "none", borderRadius: 8, background: "var(--accent)", color: "var(--on-accent)",
  cursor: "pointer", whiteSpace: "nowrap",
};

/** 次要/幽灵按钮（编辑/取消/删除等） */
const ghostBtnStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center",
  padding: "5px 12px", fontSize: 12, fontWeight: 500, fontFamily: "inherit",
  border: "1px solid var(--line)", borderRadius: 8, background: "transparent", color: "var(--ink-2)",
  cursor: "pointer", whiteSpace: "nowrap",
};

/** 图标按钮（关闭等） */
const iconBtnStyle: React.CSSProperties = {
  all: "unset", cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center",
  width: 24, height: 24, borderRadius: 6, color: "var(--ink-3)", fontSize: 13,
};

/** 保存按钮（禁用态降低不透明度） */
function saveBtnStyle(disabled: boolean): React.CSSProperties {
  return {
    padding: "6px 16px", fontSize: 12, fontWeight: 600, fontFamily: "inherit",
    border: "none", borderRadius: 8, background: "var(--accent)", color: "var(--on-accent)",
    cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1,
  };
}

// ─── 弹窗 / 表单样式 ──────────────────────────────────────────

const modalOverlayStyle: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)",
  display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
};

const modalCardStyle: React.CSSProperties = {
  background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 12,
  padding: 20, boxShadow: "0 8px 32px rgba(0,0,0,0.18)",
};

const modalInputStyle: React.CSSProperties = {
  padding: "6px 9px", fontSize: 12, border: "1px solid var(--line)", borderRadius: 6,
  fontFamily: "inherit", color: "var(--ink-2)", background: "var(--surface)", width: "100%",
};

const selectStyle: React.CSSProperties = { ...modalInputStyle, cursor: "pointer" };

const textareaStyle: React.CSSProperties = {
  width: "100%", padding: "6px 9px", fontSize: 12, border: "1px solid var(--line)", borderRadius: 6,
  fontFamily: "inherit", color: "var(--ink-2)", background: "var(--surface)", resize: "vertical",
};

const fieldLabelStyle: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 3 };

const miniLabelStyle: React.CSSProperties = { fontSize: 10, fontWeight: 600, color: "var(--ink-3)" };

/** 客户角色多选区（checkbox 列表，可滚动） */
const clientPickStyle: React.CSSProperties = {
  display: "flex", flexWrap: "wrap", gap: "6px 14px",
  padding: 10, border: "1px solid var(--line)", borderRadius: 6,
  background: "var(--bg-2)", maxHeight: 120, overflow: "auto",
};

const filterLabelStyle: React.CSSProperties = {
  fontSize: 11, fontWeight: 500, color: "var(--ink-3)", marginBottom: 5,
};

/** 筛选 chip 按钮：active 高亮（accent） */
const filterChipStyle = (active: boolean): React.CSSProperties => ({
  padding: "3px 10px", borderRadius: 999, fontSize: 11, fontWeight: 500, fontFamily: "inherit",
  border: active ? "1px solid var(--accent)" : "1px solid var(--line)",
  background: active ? "var(--accent-soft)" : "transparent",
  color: active ? "var(--accent)" : "var(--ink-2)",
  cursor: "pointer", transition: "all 120ms",
});

/** 证据条目 meta 小标签 */
const metaTagStyle = ({
  bg,
  color,
  weight,
}: {
  bg: string;
  color: string;
  weight?: number;
}): React.CSSProperties => ({
  padding: "0 5px", borderRadius: 3, fontSize: 9, background: bg, color, fontWeight: weight,
});
