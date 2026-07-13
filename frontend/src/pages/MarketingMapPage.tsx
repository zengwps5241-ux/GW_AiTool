// 营销地图页面（M4.2 / §2.4 §5.2）
// 替换 V1.0 原型：改为消费真实后端 /api/projects/{id}/{stakeholder-cards,...}。
// 顶部项目选择器由全局 Topbar（M1.3.9/M4.4.1）驱动，本页接收 project prop。
// 本提交覆盖 M4.2.1 页面骨架（项目上下文栏 + 统计栏 + 8 视图切换 + 数据加载）
// + 角色卡视图种子（左列表 + 右只读详情，作为数据主干，M4.2.6 将升级为 5 子 Tab）。
// 组织架构/决策链/立场矩阵/采购时间线/关系网络/知识库/话术库见后续 M4.2.x 任务。
import { useCallback, useEffect, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  MarkerType,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "reactflow";
import "reactflow/dist/style.css";
import { api } from "@/api/client";
import { Card, Spinner, Tag, useToast } from "@/components/ui";
import { VisibilityControls } from "@/components/VisibilityControls";
import MarkdownView from "@/components/workspace/MarkdownView";
import { I } from "@/icons";
import type {
  BehaviorEntry,
  DisambiguationCandidate,
  KnowledgeBase,
  KnowledgeCategory,
  Project,
  ProcurementStage,
  ProcurementStageStatus,
  StakeholderCard,
  StakeholderCardInput,
  StakeholderGraph,
  StakeholderRelationType,
  StanceChangeEntry,
  StakeholderRoleType,
  StanceLevel,
  TalkScript,
  TalkScriptInput,
  VisitRecord,
} from "@/types";

// ─── 常量 ─────────────────────────────────────────────────────

/** 子视图键（8 顶 Tab，§2.4 + M4.2.8 关系网络 + M4.2.10 话术库） */
type SubView =
  | "cards"
  | "org"
  | "decision"
  | "matrix"
  | "timeline"
  | "relations"
  | "knowledge"
  | "scripts";

const SUBVIEWS: { key: SubView; label: string; icon: keyof typeof I }[] = [
  { key: "cards", label: "角色卡", icon: "UserCheck" },
  { key: "org", label: "组织架构", icon: "Building" },
  { key: "decision", label: "决策链", icon: "ClipboardList" },
  { key: "matrix", label: "立场矩阵", icon: "Target" },
  { key: "timeline", label: "采购时间线", icon: "Calendar" },
  { key: "relations", label: "关系网络", icon: "Network" },
  { key: "knowledge", label: "知识库", icon: "Book" },
  { key: "scripts", label: "话术库", icon: "MessageText" },
];

const ROLE_TYPE_LABELS: Record<StakeholderRoleType, string> = {
  economic_decision_maker: "经济决策人",
  technical_evaluator: "技术评估人",
  user: "终端用户",
  coach_supporter: "教练/支持者",
  procurement_finance: "采购/财务",
};

const ROLE_TYPE_COLOR: Record<StakeholderRoleType, string> = {
  economic_decision_maker: "var(--accent)",
  technical_evaluator: "var(--info)",
  user: "var(--warn)",
  coach_supporter: "var(--success)",
  procurement_finance: "var(--danger)",
};

const ROLE_TYPE_ORDER: StakeholderRoleType[] = [
  "economic_decision_maker",
  "technical_evaluator",
  "user",
  "coach_supporter",
  "procurement_finance",
];

interface Props {
  /** 全局选中项目（Topbar ProjectSelector 驱动） */
  project: Project | null;
  /** 跨页聚焦目标角色卡 id（M4.3.7 证据→营销地图），一次性消费 */
  focusCardId?: number | null;
  /** 聚焦应用完毕回调（清空 App.focusTarget，防重复触发） */
  onFocusConsumed?: () => void;
}

// ─── 页面组件 ─────────────────────────────────────────────────

export default function MarketingMapPage({ project, focusCardId, onFocusConsumed }: Props) {
  const toast = useToast();
  const [cards, setCards] = useState<StakeholderCard[]>([]);
  const [scripts, setScripts] = useState<TalkScript[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [subView, setSubView] = useState<SubView>("cards");
  const [selectedCardId, setSelectedCardId] = useState<number | null>(null);

  const projectId = project?.id ?? null;

  // 拉取角色卡（reviewed 正式库）+ 话术（统计/角色卡话术 Tab 复用）
  const refresh = useCallback(async () => {
    if (projectId == null) {
      setCards([]);
      setScripts([]);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [cardList, scriptList] = await Promise.all([
        api.listStakeholderCards(projectId),
        api.listTalkScripts(projectId),
      ]);
      setCards(cardList);
      setScripts(scriptList);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "加载营销地图失败";
      setError(msg);
      toast.showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // 切换项目时重置选中状态
  useEffect(() => {
    setSelectedCardId(null);
    setSubView("cards");
  }, [projectId]);

  // 跨页聚焦（M4.3.7 证据→角色卡）：选中目标卡 + 切到「角色卡」子视图
  // cards 为空时数据尚未加载，等待；加载后无论是否命中均一次性消费 focusCardId。
  useEffect(() => {
    if (focusCardId == null || cards.length === 0) return;
    setSelectedCardId(focusCardId);
    setSubView("cards");
    onFocusConsumed?.();
    // 仅依赖 focusCardId 与 cards；onFocusConsumed 为一次性内联回调，不计入依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusCardId, cards]);

  const selectedCard = useMemo(
    () => cards.find((c) => c.id === selectedCardId) ?? null,
    [cards, selectedCardId],
  );

  // ─── 派生：统计栏 ───────────────────────────────────────────
  const stats = useMemo(() => {
    const byGrade = (g: string) =>
      cards.filter((c) => c.subjective_layer?.gradeLevel === g).length;
    const byStance = (s: StanceLevel) =>
      cards.filter((c) => c.subjective_layer?.stance === s).length;
    const byRole = (rt: StakeholderRoleType) =>
      cards.filter((c) => c.role_type === rt).length;
    return {
      total: cards.length,
      champion: byGrade("Champion"),
      lean: byGrade("倾向我方"),
      neutral: byGrade("中立"),
      oppose: byGrade("反对"),
      support: byStance("支持"),
      roleCounts: ROLE_TYPE_ORDER.map((rt) => ({
        role: rt,
        count: byRole(rt),
      })),
    };
  }, [cards]);

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
            使用顶部项目选择器选择一个项目，即可查看其营销地图（角色卡 / 组织架构 / 决策链 / 立场矩阵 / 采购时间线 / 关系网络 / 知识库 / 话术库）。
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
        <span style={statStyle}>角色总数: <b style={{ color: "var(--ink)" }}>{stats.total}</b></span>
        <span style={{ ...statStyle, color: "var(--success)" }}>Champion: <b>{stats.champion}</b></span>
        <span style={{ ...statStyle, color: "var(--accent)" }}>支持: <b>{stats.support}</b></span>
        <button
          onClick={refresh}
          title="刷新"
          style={{ all: "unset", cursor: "pointer", color: "var(--ink-3)", display: "flex", alignItems: "center", padding: 4, borderRadius: 6 }}
        >
          <I.Refresh size={14} />
        </button>
      </div>

      {/* 子视图 Tab */}
      <div style={tabBarStyle}>
        {SUBVIEWS.map((sv) => {
          const Icon = I[sv.icon];
          return (
            <button
              key={sv.key}
              onClick={() => setSubView(sv.key)}
              style={{
                padding: "10px 14px",
                background: "transparent",
                border: "none",
                borderBottom: subView === sv.key ? "2px solid var(--accent)" : "2px solid transparent",
                color: subView === sv.key ? "var(--accent)" : "var(--ink-2)",
                fontSize: 13,
                fontWeight: subView === sv.key ? 600 : 400,
                cursor: "pointer",
                fontFamily: "inherit",
                transition: "color 120ms, border-color 120ms",
                display: "flex",
                alignItems: "center",
                gap: 6,
                whiteSpace: "nowrap",
              }}
            >
              <Icon size={14} />
              {sv.label}
            </button>
          );
        })}
      </div>

      {/* 主内容 */}
      <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
        {/* M5.5.1 角色去重候选确认（pending 为空时 Banner 自返回 null） */}
        <DisambiguationBanner projectId={project.id} onChanged={refresh} />

        {loading && cards.length === 0 ? (
          <Card style={{ padding: 40, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--ink-3)", fontSize: 13 }}>
              <Spinner size={16} /> 加载营销地图…
            </div>
          </Card>
        ) : error ? (
          <Card style={{ padding: 40, textAlign: "center", color: "var(--danger)", fontSize: 13 }}>
            加载失败：{error}
            <div style={{ marginTop: 12 }}>
              <button onClick={refresh} style={linkBtnStyle}>重试</button>
            </div>
          </Card>
        ) : subView === "cards" ? (
          <CardsView
            projectId={project.id}
            cards={cards}
            scripts={scripts}
            selectedCard={selectedCard}
            onSelect={setSelectedCardId}
            onChanged={refresh}
          />
        ) : subView === "org" ? (
          <OrgChartView
            cards={cards}
            onJump={(id) => {
              setSelectedCardId(id);
              setSubView("cards");
            }}
          />
        ) : subView === "decision" ? (
          <DecisionChainView
            cards={cards}
            onJump={(id) => {
              setSelectedCardId(id);
              setSubView("cards");
            }}
          />
        ) : subView === "matrix" ? (
          <StanceMatrixView
            cards={cards}
            onJump={(id) => {
              setSelectedCardId(id);
              setSubView("cards");
            }}
          />
        ) : subView === "timeline" ? (
          <ProcurementTimelineView projectId={project.id} cards={cards} />
        ) : subView === "knowledge" ? (
          <KnowledgeBaseView projectId={project.id} />
        ) : subView === "relations" ? (
          <RelationsView
            projectId={project.id}
            cards={cards}
            onJump={(id) => {
              setSelectedCardId(id);
              setSubView("cards");
            }}
          />
        ) : subView === "scripts" ? (
          <TalkScriptsView projectId={project.id} scripts={scripts} cards={cards} onChanged={refresh} />
        ) : (
          <PlaceholderView subView={subView} />
        )}
      </div>
    </div>
  );
}

// ─── 角色去重候选确认 Banner（M5.5.1 person_disambiguation，§7.1）──────────
// AI 在对话中新建角色卡草稿若与既有卡疑似同人，后端生成去重候选；
// 本 Banner 自管拉取/处置状态，pending 为空时 return null（DOM 不留痕）。
// 处置后本地移除该项并 onChanged 刷新角色卡（new→新卡 reviewed / merge→既有卡填充+草稿删除）。

function DisambiguationBanner({
  projectId,
  onChanged,
}: {
  projectId: number;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [items, setItems] = useState<DisambiguationCandidate[]>([]);
  const [expanded, setExpanded] = useState(true);
  const [acting, setActing] = useState<number | null>(null); // 正在处置的候选 id

  const refresh = useCallback(async () => {
    try {
      setItems(await api.listDisambiguationCandidates(projectId, "pending"));
    } catch {
      setItems([]); // 静默——辅助提醒不阻塞主流程
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (items.length === 0) return null;

  const resolve = async (
    candidate: DisambiguationCandidate,
    decision: "new" | "merge",
    mergeIntoId?: number,
  ) => {
    setActing(candidate.id);
    try {
      await api.resolveDisambiguationCandidate(projectId, candidate.id, {
        decision,
        merge_into_card_id: mergeIntoId ?? null,
      });
      setItems((prev) => prev.filter((c) => c.id !== candidate.id));
      onChanged(); // 刷新角色卡列表
      toast.showToast(
        decision === "new" ? "已确认为新人，草稿已发布" : "已合并到既有角色卡",
        "success",
      );
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "处置失败", "error");
    } finally {
      setActing(null);
    }
  };

  const roleName = (rt: string | null) =>
    rt && (ROLE_TYPE_LABELS as Record<string, string>)[rt]
      ? (ROLE_TYPE_LABELS as Record<string, string>)[rt]
      : rt;

  return (
    <div style={disambiguationBannerStyle}>
      {/* 标题行（可折叠） */}
      <button
        onClick={() => setExpanded((v) => !v)}
        style={{
          all: "unset",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 8,
          width: "100%",
          boxSizing: "border-box",
        }}
      >
        <I.AlertTriangle size={15} style={{ color: "var(--warn)", flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: "var(--warn)" }}>
          {items.length} 项疑似重复角色待确认
        </span>
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>
          — AI 新建草稿与既有角色疑似同人，请确认「独立建卡」或「合并到既有卡」
        </span>
        <span style={{ flex: 1 }} />
        <I.ChevronDown
          size={14}
          style={{
            color: "var(--ink-3)",
            transition: "transform 120ms",
            transform: expanded ? "rotate(180deg)" : "none",
          }}
        />
      </button>

      {/* 候选列表 */}
      {expanded && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
          {items.map((c) => {
            const draft = c.new_draft_snapshot as Record<string, unknown>;
            const draftName = (draft.name as string) ?? "(未命名)";
            return (
              <div key={c.id} style={disambiguationRowStyle}>
                {/* 新草稿信息 */}
                <div style={{ minWidth: 180, flexShrink: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>
                    {draftName}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>
                    {[
                      draft.position as string | null,
                      draft.department as string | null,
                      roleName(draft.role_type as string | null),
                    ]
                      .filter(Boolean)
                      .join(" · ") || "AI 新建草稿"}
                  </div>
                </div>

                {/* 候选既有卡（每个一个合并按钮）+ 新建按钮 */}
                <div
                  style={{
                    flex: 1,
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 6,
                    alignItems: "center",
                  }}
                >
                  <span style={{ fontSize: 11, color: "var(--ink-3)" }}>疑似同人：</span>
                  {c.candidates.map((cc) => (
                    <button
                      key={cc.id}
                      disabled={acting === c.id}
                      onClick={() => resolve(c, "merge", cc.id)}
                      style={mergeBtnStyle}
                      title={`合并到「${cc.name}」（${cc.reasons.join("、")}，相似度 ${(
                        cc.score * 100
                      ).toFixed(0)}%）`}
                    >
                      <I.Copy size={12} />
                      合并到「{cc.name}」
                      <span style={{ opacity: 0.7 }}>
                        {(cc.score * 100).toFixed(0)}%
                      </span>
                    </button>
                  ))}
                  <span
                    style={{
                      width: 1,
                      height: 18,
                      background: "var(--border)",
                      margin: "0 4px",
                    }}
                  />
                  <button
                    disabled={acting === c.id}
                    onClick={() => resolve(c, "new")}
                    style={newBtnStyle}
                    title="确认为新人，草稿独立发布为正式角色卡"
                  >
                    <I.UserCheck size={12} />
                    确认为新人
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const disambiguationBannerStyle: React.CSSProperties = {
  background: "var(--warn-soft)",
  border: "1px solid var(--warn)",
  borderRadius: 8,
  padding: "10px 14px",
  marginBottom: 12,
};
const disambiguationRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 12,
  alignItems: "center",
  background: "var(--bg-1)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "8px 12px",
};
const mergeBtnStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  padding: "4px 10px",
  fontSize: 12,
  fontFamily: "inherit",
  cursor: "pointer",
  background: "var(--accent-soft)",
  color: "var(--accent-2)",
  border: "1px solid var(--accent)",
  borderRadius: 6,
};
const newBtnStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  padding: "4px 10px",
  fontSize: 12,
  fontFamily: "inherit",
  cursor: "pointer",
  background: "var(--success-soft)",
  color: "var(--success)",
  border: "1px solid var(--success)",
  borderRadius: 6,
};

// ─── 角色卡视图（M4.2.6：左侧角色列表 + 中间 5 子 Tab 详情卡 + 右侧关联面板） ──
// 5 子 Tab：客观信息 / 主观分析 / 行为分析 / 态度历史 / 话术。
// 详情字段覆盖 §5.2 全量：客观层 7 字段（education/previousCompanies/personality/
// communicationPreference/relationships/historyWithUs/historyWithCompetitor）+
// 主观层全含 confidence + behaviors（observation/interpretation/suggestedAction）+
// stance_change_log（date/from/to/reason）+ 话术（按 stakeholder_card_id 过滤）。
// 右侧关联面板：关联拜访记录（listVisitRecords?card_id）+ 关联话术 + 关联 L3 场景。

/** 角色卡详情子 Tab */
type CardTab = "objective" | "subjective" | "behaviors" | "stance" | "scripts";

const CARD_TABS: { key: CardTab; label: string; icon: keyof typeof I }[] = [
  { key: "objective", label: "客观信息", icon: "UserCheck" },
  { key: "subjective", label: "主观分析", icon: "Target" },
  { key: "behaviors", label: "行为分析", icon: "Activity" },
  { key: "stance", label: "态度历史", icon: "Calendar" },
  { key: "scripts", label: "话术", icon: "MessageText" },
];

function CardsView({
  projectId,
  cards,
  scripts,
  selectedCard,
  onSelect,
  onChanged,
}: {
  projectId: number;
  cards: StakeholderCard[];
  scripts: TalkScript[];
  selectedCard: StakeholderCard | null;
  onSelect: (id: number) => void;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [tab, setTab] = useState<CardTab>("objective");
  const [visits, setVisits] = useState<VisitRecord[]>([]);
  const [visitsLoading, setVisitsLoading] = useState(false);
  // 角色卡编辑器：null=关闭；{card:null}=新建；{card:X}=编辑 X（M4.2.9 CRUD）
  const [cardEditor, setCardEditor] = useState<{ card: StakeholderCard | null } | null>(null);

  // 默认选中第一个（可能为 null — 空列表）
  const current = selectedCard ?? cards[0] ?? null;
  const currentId = current?.id;

  // 切换角色：重置子 Tab + 拉取关联拜访记录（card_id 过滤 related_card_ids / participants_client）
  // hooks 全部置于早期 return 之前，避免删除最后一张卡时 hooks 数量变化（M4.2.9 修复 M4.2.6 遗留）
  useEffect(() => {
    setTab("objective");
    if (currentId == null) return;
    let cancelled = false;
    setVisitsLoading(true);
    setVisits([]);
    api
      .listVisitRecords(projectId, { card_id: currentId })
      .then((list) => {
        if (!cancelled) setVisits(list);
      })
      .catch(() => {
        if (!cancelled) setVisits([]);
      })
      .finally(() => {
        if (!cancelled) setVisitsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [currentId, projectId]);

  const handleDelete = async (card: StakeholderCard) => {
    if (!window.confirm(`确认删除角色卡「${card.name}」？关联的关系/话术可能受影响。`)) return;
    try {
      await api.deleteStakeholderCard(projectId, card.id);
      toast.showToast("已删除", "success");
      onChanged();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "删除失败", "error");
    }
  };

  const editorEl = cardEditor && (
    <CardEditModal
      projectId={projectId}
      card={cardEditor.card}
      onClose={() => setCardEditor(null)}
      onSaved={() => {
        setCardEditor(null);
        onChanged();
      }}
    />
  );

  // 空项目无角色卡（提供新建入口，M4.2.9）
  if (cards.length === 0) {
    return (
      <>
        <Card style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
          <I.UserCheck size={32} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>尚未建立角色卡</div>
          <div style={{ maxWidth: 380, margin: "0 auto", lineHeight: 1.7, marginBottom: 16 }}>
            手动新增角色卡（直接进正式库），或在「对话」页用 WF12 chip 让 AI 基于拜访证据产出草稿后采纳。
          </div>
          <button onClick={() => setCardEditor({ card: null })} style={primaryBtnStyle}>
            <I.Plus size={14} /> 新增角色卡
          </button>
        </Card>
        {editorEl}
      </>
    );
  }

  // current 非空（cards.length > 0 已保证）
  const cur = current as StakeholderCard;
  const cardScripts = scripts.filter((s) => s.stakeholder_card_id === cur.id);
  // 同角色类型的通用模板话术（跨客户通用，stakeholder_card_id 为 null 且 role_type 匹配）
  const templateScripts = scripts.filter(
    (s) => s.stakeholder_card_id == null && s.role_type === cur.role_type,
  );

  const behaviors = cur.behaviors ?? [];
  const stanceLog = cur.stance_change_log ?? [];

  // 子 Tab 角标计数（仅数组类 Tab 显示数量）
  const tabBadge: Record<CardTab, number> = {
    objective: 0,
    subjective: 0,
    behaviors: behaviors.length,
    stance: stanceLog.length,
    scripts: cardScripts.length,
  };

  return (
    <div style={{ display: "flex", gap: 16, height: "100%" }}>
      {/* 左：角色列表 */}
      <Card style={{ width: 220, padding: 0, flexShrink: 0, overflow: "auto" }}>
        <div style={listHeaderStyle}>
          <span>角色列表（{cards.length}）</span>
          <button onClick={() => setCardEditor({ card: null })} style={listAddBtnStyle} title="新增角色卡">
            <I.Plus size={14} />
          </button>
        </div>
        {cards.map((c) => {
          const rt = c.role_type;
          const stance = c.subjective_layer?.stance;
          const isSel = cur.id === c.id;
          return (
            <button
              key={c.id}
              onClick={() => onSelect(c.id)}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "10px 14px",
                border: "none",
                textAlign: "left",
                borderLeft: isSel ? "3px solid var(--accent)" : "3px solid transparent",
                background: isSel ? "var(--bg-2)" : "transparent",
                cursor: "pointer",
                fontFamily: "inherit",
                fontSize: 13,
                transition: "background 120ms",
              }}
            >
              <div style={{
                width: 32, height: 32, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14, fontWeight: 700, color: "var(--on-accent)",
                background: rt ? ROLE_TYPE_COLOR[rt] : "var(--ink-3)",
                flexShrink: 0,
              }}>
                {c.name[0]}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</div>
                <div style={{ fontSize: 11, color: "var(--ink-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.position || "—"}
                </div>
              </div>
              {stance && (
                <span style={{ width: 6, height: 6, borderRadius: 999, background: stanceColor(stance), flexShrink: 0 }} />
              )}
            </button>
          );
        })}
      </Card>

      {/* 中：详情卡（头 + 5 子 Tab + 内容） */}
      <Card style={{ flex: 1, padding: 0, overflow: "auto", minWidth: 0 }}>
        <CardDetailHeader
          card={cur}
          onEdit={() => setCardEditor({ card: cur })}
          onDelete={() => handleDelete(cur)}
        />
        {/* 子 Tab 栏 */}
        <div style={cardTabBarStyle}>
          {CARD_TABS.map((t) => {
            const Icon = I[t.icon];
            const active = tab === t.key;
            const badge = tabBadge[t.key];
            return (
              <button key={t.key} onClick={() => setTab(t.key)} style={cardTabBtnStyle(active)}>
                <Icon size={13} />
                {t.label}
                {badge > 0 && <span style={cardTabBadgeStyle(active)}>{badge}</span>}
              </button>
            );
          })}
        </div>
        {/* 子 Tab 内容 */}
        <div style={{ padding: 20, fontSize: 13 }}>
          {tab === "objective" && <ObjectiveTab card={cur} />}
          {tab === "subjective" && <SubjectiveTab card={cur} />}
          {tab === "behaviors" && <BehaviorsTab behaviors={behaviors} />}
          {tab === "stance" && <StanceHistoryTab log={stanceLog} />}
          {tab === "scripts" && (
            <ScriptsTab
              cardName={cur.name}
              roleType={cur.role_type}
              cardScripts={cardScripts}
              templateScripts={templateScripts}
            />
          )}
        </div>
      </Card>

      {/* 右：关联面板（关联拜访记录 / 关联话术 / 关联 L3 场景） */}
      <Card style={{ width: 260, padding: 0, flexShrink: 0, overflow: "auto" }}>
        <RelatedPanel
          visits={visits}
          visitsLoading={visitsLoading}
          scriptCount={cardScripts.length}
          onJumpScripts={() => setTab("scripts")}
        />
      </Card>

      {editorEl}
    </div>
  );
}

// ─── 5 子 Tab 内容组件 ────────────────────────────────────────

/** 客观信息子 Tab：§5.2 objectiveLayer 7 字段 */
function ObjectiveTab({ card }: { card: StakeholderCard }) {
  const ol = card.objective_layer ?? {};
  const fields: [string, string | undefined][] = [
    ["教育背景", ol.education],
    ["过往公司与年限", ol.previousCompanies],
    ["性格特征", ol.personality],
    ["沟通偏好", ol.communicationPreference],
    ["人际关系", ol.relationships],
    ["与我方历史合作", ol.historyWithUs],
    ["与竞品历史合作", ol.historyWithCompetitor],
  ];
  const filled = fields.filter(([, v]) => v).length;
  return (
    <div>
      <div style={tabIntroStyle}>客观信息层（相对稳定，数月更新）· 已填 {filled}/7</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {fields.map(([label, value]) => (
          <Field key={label} label={label} value={value} />
        ))}
      </div>
    </div>
  );
}

/** 主观分析子 Tab：三维评分 + 综合 + 全字段（§5.2 subjectiveLayer，含 confidence） */
function SubjectiveTab({ card }: { card: StakeholderCard }) {
  const sl = card.subjective_layer ?? {};
  return (
    <div>
      <ScoreRow card={card} />
      <div style={{ ...stanceRowStyle, marginTop: 14 }}>
        {sl.stance && <StanceChip stance={sl.stance} />}
        {sl.confidence && <Tag tone="neutral">置信度：{sl.confidence}</Tag>}
        {sl.gradeLevel && <Tag tone={gradeTone(sl.gradeLevel)}>等级：{sl.gradeLevel}</Tag>}
        {sl.compositeScore != null && (
          <Tag tone="accent">综合 {sl.compositeScore}/10</Tag>
        )}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 14 }}>
        <Field label="显性 KPI" value={sl.explicitKPI} />
        <Field label="隐性个人诉求" value={sl.personalMotivation} />
        <Field label="对我方方案的态度" value={sl.attitudeToUs} />
        <Field label="对竞品的态度" value={sl.attitudeToCompetitor} />
        <Field label="核心顾虑" value={sl.coreConcerns} highlight />
        <Field label="影响杠杆" value={sl.leverage} highlight />
      </div>
    </div>
  );
}

/** 行为分析子 Tab：behaviors[]（观察 / 解读 / 建议动作，§5.2 行为分析矩阵） */
function BehaviorsTab({ behaviors }: { behaviors: BehaviorEntry[] }) {
  if (behaviors.length === 0) {
    return <EmptyTab icon="Activity" text="尚无行为分析记录。拜访后由 AI 基于证据产出（观察 → 解读 → 建议动作），M4.2.9 上线后也可手动新增。" />;
  }
  return (
    <div>
      <div style={tabIntroStyle}>行为分析矩阵（每次接触后更新）· {behaviors.length} 条</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {behaviors.map((b, i) => (
          <div key={i} style={behaviorCardStyle}>
            <BehaviorRow icon="👁" label="观察" color="var(--info)" text={b.observation} />
            <BehaviorRow icon="🧠" label="解读" color="var(--accent)" text={b.interpretation} />
            <BehaviorRow icon="➡" label="建议动作" color="var(--success)" text={b.suggestedAction} last />
          </div>
        ))}
      </div>
    </div>
  );
}

/** 行为分析单行（图标 + 标签 + 内容） */
function BehaviorRow({ icon, label, color, text, last }: { icon: string; label: string; color: string; text?: string; last?: boolean }) {
  return (
    <div style={{ display: "flex", gap: 10, paddingBottom: last ? 0 : 10, borderBottom: last ? "none" : "1px dashed var(--line)" }}>
      <span style={{ fontSize: 11, fontWeight: 700, color, flexShrink: 0, width: 78, display: "flex", alignItems: "center", gap: 4 }}>
        {icon} {label}
      </span>
      <div style={{ flex: 1, fontSize: 13, color: text ? "var(--ink-2)" : "var(--ink-4)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
        {text || "（未填写）"}
      </div>
    </div>
  );
}

/** 态度历史子 Tab：stance_change_log[]（date / from→to / reason，§5.2） */
function StanceHistoryTab({ log }: { log: StanceChangeEntry[] }) {
  if (log.length === 0) {
    return <EmptyTab icon="Calendar" text="尚无态度变化记录。新证据关联本角色且暗示态度变化时自动生成（§7.6），也可手动编辑。" />;
  }
  // 按日期降序（无日期沉底）
  const sorted = [...log].sort((a, b) => (b.date ?? "").localeCompare(a.date ?? ""));
  return (
    <div>
      <div style={tabIntroStyle}>态度变化历史 · {log.length} 条</div>
      <div style={{ position: "relative", paddingLeft: 2 }}>
        <div style={{ position: "absolute", left: 8, top: 8, bottom: 8, width: 2, background: "var(--line)" }} />
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {sorted.map((e, i) => (
            <div key={i} style={{ display: "flex", gap: 12, position: "relative" }}>
              <div style={timelineDotStyle} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-2)" }}>{e.date || "（无日期）"}</span>
                  {e.from ? <StanceChip stance={e.from} small /> : <span style={{ fontSize: 11, color: "var(--ink-4)" }}>未知</span>}
                  <I.ChevronRight size={12} style={{ color: "var(--ink-4)" }} />
                  {e.to ? <StanceChip stance={e.to} small /> : <span style={{ fontSize: 11, color: "var(--ink-4)" }}>未知</span>}
                </div>
                {e.reason && <div style={{ fontSize: 12, color: "var(--ink-3)", lineHeight: 1.6 }}>{e.reason}</div>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** 话术子 Tab：该角色定制话术 + 同角色类型通用模板（§5.2 话术库） */
function ScriptsTab({
  cardName,
  roleType,
  cardScripts,
  templateScripts,
}: {
  cardName: string;
  roleType: StakeholderRoleType | null;
  cardScripts: TalkScript[];
  templateScripts: TalkScript[];
}) {
  const hasAny = cardScripts.length > 0 || templateScripts.length > 0;
  return (
    <div>
      <div style={tabIntroStyle}>
        {cardName} 定制话术 {cardScripts.length} 条
        {roleType && <> · 同类型（{ROLE_TYPE_LABELS[roleType]}）通用模板 {templateScripts.length} 条</>}
      </div>
      {!hasAny ? (
        <EmptyTab icon="MessageText" text="尚无话术。前往顶部「话术库」Tab 新增，或在对话中让 AI 基于本角色生成。" />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {cardScripts.length > 0 && (
            <div>
              <div style={sectionLabelStyle}>定制话术（针对本角色）</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {cardScripts.map((s) => <ScriptCard key={s.id} script={s} />)}
              </div>
            </div>
          )}
          {templateScripts.length > 0 && (
            <div>
              <div style={sectionLabelStyle}>通用模板（{roleType ? ROLE_TYPE_LABELS[roleType] : ""}）</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {templateScripts.map((s) => <ScriptCard key={s.id} script={s} template />)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** 单条话术卡（场景标签 + 内容 + 展开/收起） */
function ScriptCard({ script, template }: { script: TalkScript; template?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={scriptCardStyle(template)}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, flexWrap: "wrap" }}>
        {script.scenario && <Tag tone={template ? "neutral" : "accent"}>{script.scenario}</Tag>}
        {template && <Tag tone="info">模板</Tag>}
        {script.source_customer_quote && (
          <span title="源自客户原话" style={{ fontSize: 11, color: "var(--ink-4)" }}>📎 原话</span>
        )}
      </div>
      <div style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.7, whiteSpace: "pre-wrap", maxHeight: expanded ? undefined : 72, overflow: "hidden" }}>
        {script.content}
      </div>
      <button onClick={() => setExpanded((v) => !v)} style={linkBtnStyle}>{expanded ? "收起" : "展开全部"}</button>
    </div>
  );
}

// ─── 右侧关联面板 ─────────────────────────────────────────────

/** 关联面板：关联拜访记录 + 关联话术 + 关联 L3 场景 */
function RelatedPanel({
  visits,
  visitsLoading,
  scriptCount,
  onJumpScripts,
}: {
  visits: VisitRecord[];
  visitsLoading: boolean;
  scriptCount: number;
  onJumpScripts: () => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {/* 关联拜访记录 */}
      <div style={relatedSectionStyle}>
        <div style={relatedHeaderStyle}>
          <I.Calendar size={13} />
          <span>关联拜访记录</span>
          <span style={relatedCountStyle}>{visitsLoading ? "…" : visits.length}</span>
        </div>
        {visitsLoading ? (
          <div style={relatedEmptyStyle}>加载中…</div>
        ) : visits.length === 0 ? (
          <div style={relatedEmptyStyle}>暂无关联拜访</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {visits.slice(0, 6).map((v) => (
              <div key={v.id} style={relatedItemStyle}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 6, alignItems: "center" }}>
                  <span style={{ fontSize: 11, color: "var(--ink-3)" }}>{v.visit_date || "（无日期）"}</span>
                  <Tag tone="neutral">{v.visit_type}</Tag>
                </div>
                {v.summary && (
                  <div style={clamp2Style}>{v.summary}</div>
                )}
              </div>
            ))}
            {visits.length > 6 && (
              <div style={{ fontSize: 10, color: "var(--ink-4)", textAlign: "center" }}>
                还有 {visits.length - 6} 条，前往「拜访记录」页查看
              </div>
            )}
          </div>
        )}
      </div>

      {/* 关联话术 */}
      <div style={relatedSectionStyle}>
        <div style={relatedHeaderStyle}>
          <I.MessageText size={13} />
          <span>关联话术</span>
          <span style={relatedCountStyle}>{scriptCount}</span>
        </div>
        {scriptCount === 0 ? (
          <div style={relatedEmptyStyle}>暂无定制话术</div>
        ) : (
          <button onClick={onJumpScripts} style={linkBtnStyle}>查看 {scriptCount} 条定制话术 →</button>
        )}
      </div>

      {/* 关联 L3 场景（跨模块 FK 待 M4.3 打通） */}
      <div style={relatedSectionStyle}>
        <div style={relatedHeaderStyle}>
          <I.Map size={13} />
          <span>关联 L3 场景</span>
        </div>
        <div style={{ fontSize: 11, color: "var(--ink-4)", lineHeight: 1.6 }}>
          角色卡与业务地图 L3 场景的跨模块关联，待 M4.3 拜访记录打通（证据 → 角色 → 场景）后建立。
        </div>
      </div>
    </div>
  );
}

// ─── 角色卡详情通用小组件 ─────────────────────────────────────

/** 立场徽标（带底色，可选小尺寸） */
function StanceChip({ stance, small }: { stance: StanceLevel; small?: boolean }) {
  const color = stanceColor(stance);
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: small ? "1px 7px" : "2px 9px",
      fontSize: small ? 11 : 12, fontWeight: 500,
      borderRadius: 999, background: color + "22", color,
    }}>
      {small && <span style={{ width: 5, height: 5, borderRadius: 999, background: color }} />}
      {stance}
    </span>
  );
}

/** 子 Tab 空状态 */
function EmptyTab({ icon, text }: { icon: keyof typeof I; text: string }) {
  const Icon = I[icon];
  return (
    <div style={{ padding: 30, textAlign: "center", color: "var(--ink-4)", fontSize: 13 }}>
      <Icon size={28} style={{ marginBottom: 8 }} />
      <div style={{ maxWidth: 320, margin: "0 auto", lineHeight: 1.7 }}>{text}</div>
    </div>
  );
}

/** 角色卡详情头部：头像 + 基本信息 + 标签 + 编辑/删除（M4.2.9） */
function CardDetailHeader({
  card,
  onEdit,
  onDelete,
}: {
  card: StakeholderCard;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  const rt = card.role_type;
  const grade = card.subjective_layer?.gradeLevel;
  return (
    <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 16 }}>
      <div style={{
        width: 44, height: 44, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 20, fontWeight: 700, color: "var(--on-accent)",
        background: rt ? ROLE_TYPE_COLOR[rt] : "var(--ink-3)",
        flexShrink: 0,
      }}>
        {card.name[0]}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 16, fontWeight: 600, fontFamily: "var(--serif)" }}>{card.name}</div>
        <div style={{ fontSize: 12, color: "var(--ink-2)" }}>
          {[card.position, card.department, card.reports_to ? `汇报: ${card.reports_to}` : null].filter(Boolean).join(" · ")}
        </div>
        {card.contact_info && <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>📧 {card.contact_info}</div>}
      </div>
      <div style={{ display: "flex", gap: 6, flexDirection: "column", alignItems: "flex-end" }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {rt && <Tag tone="accent">{ROLE_TYPE_LABELS[rt]}</Tag>}
          {card.decision_power && <Tag tone="info">{card.decision_power}</Tag>}
          {onEdit && (
            <button onClick={onEdit} style={iconBtnStyle} title="编辑角色卡"><I.Edit size={14} /></button>
          )}
          {onDelete && (
            <button onClick={onDelete} style={iconBtnStyle} title="删除角色卡"><I.Trash size={14} /></button>
          )}
        </div>
        {grade && (
          <Tag tone={gradeTone(grade)}>{grade}{card.subjective_layer?.confidence ? ` · 置信${card.subjective_layer.confidence}` : ""}</Tag>
        )}
      </div>
    </div>
  );
}

/** 三维评分 + 综合评分条 */
function ScoreRow({ card }: { card: StakeholderCard }) {
  const sl = card.subjective_layer ?? {};
  const dims: [string, number | undefined, string][] = [
    ["参与度", typeof sl.engagement === "number" ? sl.engagement : undefined, "var(--info)"],
    ["影响力", typeof sl.influence === "number" ? sl.influence : undefined, "var(--accent)"],
    ["支持度", typeof sl.support === "number" ? sl.support : undefined, "var(--success)"],
  ];
  return (
    <div style={{ display: "flex", gap: 12 }}>
      {dims.map(([label, value, color]) => (
        <div key={label} style={{ flex: 1, textAlign: "center", padding: "12px 8px", background: "var(--bg-2)", borderRadius: 10, border: "1px solid var(--line)" }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: value != null ? color : "var(--ink-4)" }}>
            {value != null ? value : "—"}<span style={{ fontSize: 11, color: "var(--ink-3)" }}>/10</span>
          </div>
          <div style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 2 }}>{label}</div>
        </div>
      ))}
      <div style={{ flex: 1, textAlign: "center", padding: "12px 8px", background: "var(--accent-soft)", borderRadius: 10, border: "1px solid var(--accent)" }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: "var(--accent)" }}>
          {typeof sl.compositeScore === "number" ? sl.compositeScore : "—"}<span style={{ fontSize: 11, color: "var(--ink-3)" }}>/10</span>
        </div>
        <div style={{ fontSize: 10, color: "var(--accent)", marginTop: 2, fontWeight: 600 }}>综合评分</div>
      </div>
    </div>
  );
}

// ─── 组织架构图视图（M4.2.2：树形 + 汇报关系 + 关键岗位） ──────
// 层级由每张角色卡的 reports_to 文本字段推导（name 匹配父卡）；
// 同名卡取首张为规范父卡；渲染时全局 visited 防环。
// 关系网络图（M4.2.8）用 StakeholderRelation 四类边，与此处层级视图互补。

function OrgChartView({
  cards,
  onJump,
}: {
  cards: StakeholderCard[];
  onJump: (id: number) => void;
}) {
  if (cards.length === 0) {
    return (
      <Card style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
        <I.Building size={32} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
        <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>暂无角色卡</div>
        <div>建立角色卡并填写「汇报对象」后，此处自动生成组织架构树。</div>
      </Card>
    );
  }

  // name → 规范父卡 id（同名取首张）
  const nameToCardId = new Map<string, number>();
  for (const c of cards) {
    if (c.name && !nameToCardId.has(c.name)) nameToCardId.set(c.name, c.id);
  }

  // childrenMap：父卡 id → 子卡列表；roots：无父卡的卡
  const childrenMap = new Map<number, StakeholderCard[]>();
  const roots: StakeholderCard[] = [];
  for (const c of cards) {
    const parentName = c.reports_to?.trim();
    const parentId = parentName ? nameToCardId.get(parentName) : undefined;
    if (parentId != null && parentId !== c.id) {
      const arr = childrenMap.get(parentId) ?? [];
      arr.push(c);
      childrenMap.set(parentId, arr);
    } else {
      roots.push(c);
    }
  }

  // 根按汇报对象分组（同一上级标题聚合）
  const groupKey = (c: StakeholderCard) => c.reports_to?.trim() || "（未标注汇报关系）";
  const rootGroups = new Map<string, StakeholderCard[]>();
  for (const r of roots) {
    const key = groupKey(r);
    const arr = rootGroups.get(key) ?? [];
    arr.push(r);
    rootGroups.set(key, arr);
  }

  const visited = new Set<number>();

  const renderNode = (card: StakeholderCard, depth: number): React.ReactNode => {
    if (visited.has(card.id)) return null;
    visited.add(card.id);
    const children = childrenMap.get(card.id) ?? [];
    const rt = card.role_type;
    const isKey = card.decision_power === "最终决策" || rt === "economic_decision_maker";
    return (
      <div key={card.id} style={{ marginBottom: 6 }}>
        <button
          onClick={() => onJump(card.id)}
          style={{
            display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
            width: "100%", textAlign: "left", cursor: "pointer", fontFamily: "inherit",
            background: isKey ? "var(--accent-soft)" : "var(--bg-2)",
            border: `1px solid ${isKey ? "var(--accent)" : "var(--line)"}`,
            borderRadius: depth === 0 ? 10 : 8, fontSize: 13,
          }}
        >
          <div style={{
            width: 30, height: 30, borderRadius: 7, display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 13, fontWeight: 700, color: "var(--on-accent)",
            background: rt ? ROLE_TYPE_COLOR[rt] : "var(--ink-3)", flexShrink: 0,
          }}>
            {card.name[0]}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {card.name}
              {card.position && <span style={{ fontSize: 11, fontWeight: 400, color: "var(--ink-3)", marginLeft: 6 }}>{card.position}</span>}
            </div>
            {card.department && <div style={{ fontSize: 11, color: "var(--ink-3)" }}>{card.department}</div>}
          </div>
          {rt && <Tag tone="accent">{ROLE_TYPE_LABELS[rt]}</Tag>}
          {card.decision_power && <Tag tone="info">{card.decision_power}</Tag>}
          {isKey && <span style={{ fontSize: 10, fontWeight: 700, color: "var(--accent)" }}>★ 关键</span>}
        </button>
        {children.length > 0 && (
          <div style={{ marginLeft: 18, marginTop: 4, paddingLeft: 16, borderLeft: "2px solid var(--line)" }}>
            {children.map((ch) => renderNode(ch, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <Card style={{ padding: 20, overflow: "auto", maxWidth: 720 }}>
      <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)", marginBottom: 4 }}>组织架构图</div>
      <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 16 }}>
        按角色卡「汇报对象」自动构建汇报关系树；标 ★ 为关键岗位（最终决策 / 经济决策人）。点击节点跳转角色卡详情。
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        {Array.from(rootGroups.entries()).map(([title, groupRoots]) => (
          <div key={title}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
              {title === "（未标注汇报关系）" ? title : `汇报至：${title}`}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {groupRoots.map((r) => renderNode(r, 0))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ─── 决策链角色表（M4.2.3：表格 + 影响力条 + 综合评分 + 等级，按影响力排序） ──

function DecisionChainView({
  cards,
  onJump,
}: {
  cards: StakeholderCard[];
  onJump: (id: number) => void;
}) {
  if (cards.length === 0) {
    return (
      <Card style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
        <I.ClipboardList size={32} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
        <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>暂无角色卡</div>
        <div>建立角色卡并填写主观层（影响力/参与度/支持度）后，此处按影响力排序展示决策链。</div>
      </Card>
    );
  }

  // 按影响力降序（缺失按综合评分，再缺失按 0）
  const sorted = [...cards].sort((a, b) => {
    const ia = a.subjective_layer?.influence ?? a.subjective_layer?.compositeScore ?? 0;
    const ib = b.subjective_layer?.influence ?? b.subjective_layer?.compositeScore ?? 0;
    return ib - ia;
  });

  const headers = ["角色类型", "姓名", "部门", "决策权", "影响力", "综合评分", "等级", "立场"];

  return (
    <div style={{ display: "flex", gap: 20, height: "100%" }}>
      <Card style={{ flex: 1, padding: 0, overflow: "auto" }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)" }}>
          <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)" }}>决策链角色表</div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>按影响力排序，点击行跳转角色卡详情。</div>
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "var(--bg-2)", borderBottom: "2px solid var(--line)" }}>
              {headers.map((h) => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "var(--ink-3)", whiteSpace: "nowrap" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((c) => {
              const sl = c.subjective_layer ?? {};
              const influence = typeof sl.influence === "number" ? sl.influence : 0;
              const composite = typeof sl.compositeScore === "number" ? sl.compositeScore : null;
              const grade = sl.gradeLevel;
              const stance = sl.stance;
              return (
                <tr
                  key={c.id}
                  onClick={() => onJump(c.id)}
                  style={{ borderBottom: "1px solid var(--line)", cursor: "pointer" }}
                >
                  <td style={{ padding: "10px 14px" }}>
                    {c.role_type ? <Tag tone="accent">{ROLE_TYPE_LABELS[c.role_type]}</Tag> : <span style={{ color: "var(--ink-4)" }}>—</span>}
                  </td>
                  <td style={{ padding: "10px 14px", fontWeight: 500 }}>{c.name}</td>
                  <td style={{ padding: "10px 14px", color: "var(--ink-2)" }}>{c.department || "—"}</td>
                  <td style={{ padding: "10px 14px", color: "var(--ink-2)", fontSize: 12 }}>{c.decision_power || "—"}</td>
                  <td style={{ padding: "10px 14px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div style={{ width: 60, height: 4, background: "var(--bg-3)", borderRadius: 2, overflow: "hidden" }}>
                        <div style={{ width: `${influence * 10}%`, height: "100%", background: "var(--accent)", borderRadius: 2 }} />
                      </div>
                      <span style={{ fontSize: 11, fontWeight: 600 }}>{influence}/10</span>
                    </div>
                  </td>
                  <td style={{ padding: "10px 14px" }}>
                    {composite != null ? (
                      <span style={{ fontSize: 12, fontWeight: 600, color: gradeColor(composite) }}>{composite}分</span>
                    ) : <span style={{ color: "var(--ink-4)" }}>—</span>}
                  </td>
                  <td style={{ padding: "10px 14px" }}>
                    {grade ? (
                      <span style={{ padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 500, background: gradeColor(grade) + "22", color: gradeColor(grade) }}>{grade}</span>
                    ) : <span style={{ color: "var(--ink-4)" }}>—</span>}
                  </td>
                  <td style={{ padding: "10px 14px" }}>
                    {stance ? <span style={{ fontSize: 12, fontWeight: 500, color: stanceColor(stance) }}>{stance}</span> : <span style={{ color: "var(--ink-4)" }}>—</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      {/* 右：决策链解读 */}
      <Card style={{ width: 280, padding: 20, flexShrink: 0, overflow: "auto" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 12 }}>📖 决策链解读</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 12, color: "var(--ink-2)", lineHeight: 1.6 }}>
          <div style={{ padding: 10, background: "var(--bg-2)", borderRadius: 8, borderLeft: "3px solid var(--success)" }}>
            <div style={{ fontWeight: 600, color: "var(--success)", marginBottom: 4 }}>Champion 三要素</div>
            <div style={{ fontSize: 11 }}>① 有影响力（能影响他人）；② 有意愿（主动推动）；③ 有个人利益（我方胜出与其目标相关）。三者缺一不可。</div>
          </div>
          <div>
            <b>综合评分</b> = 参与度×0.3 + 影响力×0.4 + 支持度×0.3（后端按 §5.2 公式计算）。
          </div>
          <div>
            <b>等级</b>：Champion(8-10) / 倾向我方(5-7) / 中立(3-4) / 反对(1-2)。
          </div>
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12, color: "var(--ink-3)" }}>
            决策推进策略：优先巩固 Champion 与倾向者，争取中立者，化解反对者。
          </div>
        </div>
      </Card>
    </div>
  );
}

// ─── 角色-立场矩阵（M4.2.4：横轴立场 × 纵轴影响力，气泡=参与度） ──

const STANCE_AXIS: StanceLevel[] = ["反对", "观望", "中立", "支持"];

function StanceMatrixView({
  cards,
  onJump,
}: {
  cards: StakeholderCard[];
  onJump: (id: number) => void;
}) {
  // 仅渲染有 stance + influence 的卡
  const plotable = cards.filter(
    (c) => c.subjective_layer?.stance != null && typeof c.subjective_layer?.influence === "number",
  );

  // 按 (stance, influence) 桶预计算每张卡的 {idx,total}，用于散开重叠气泡
  const scatter = useMemo(() => {
    const byKey = new Map<string, StakeholderCard[]>();
    for (const c of plotable) {
      const sl = c.subjective_layer!;
      const key = `${sl.stance}-${sl.influence}`;
      const arr = byKey.get(key) ?? [];
      arr.push(c);
      byKey.set(key, arr);
    }
    const info = new Map<number, { idx: number; total: number }>();
    for (const arr of byKey.values()) {
      arr.forEach((c, i) => info.set(c.id, { idx: i, total: arr.length }));
    }
    return info;
  }, [plotable]);

  if (cards.length === 0) {
    return (
      <Card style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
        <I.Target size={32} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
        <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>暂无角色卡</div>
        <div>建立角色卡并填写立场与影响力后，此处展示立场-影响力矩阵。</div>
      </Card>
    );
  }

  const CHART_H = 380;
  // stance → 横向中心百分比（4 等分列中心）
  const stanceX: Record<StanceLevel, number> = {
    反对: 12.5,
    观望: 37.5,
    中立: 62.5,
    支持: 87.5,
  };

  return (
    <div style={{ display: "flex", gap: 20, height: "100%" }}>
      <Card style={{ flex: 1, padding: 20, overflow: "auto" }}>
        <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)", marginBottom: 4 }}>角色-立场矩阵</div>
        <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 16 }}>
          横轴=立场，纵轴=影响力（0-10），气泡大小=参与度。点击气泡跳转角色卡。
        </div>

        {plotable.length === 0 ? (
          <div style={{ padding: 30, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
            暂无带「立场+影响力」的角色卡，无法绘制矩阵。
          </div>
        ) : (
          <div style={{ position: "relative", height: CHART_H, margin: "12px 8px 28px 36px", borderLeft: "2px solid var(--line)", borderBottom: "2px solid var(--line)" }}>
            {/* Y 轴刻度 */}
            {[0, 5, 10].map((v) => (
              <div key={v} style={{ position: "absolute", left: -30, top: v === 0 ? CHART_H - 12 : v === 10 ? -4 : CHART_H / 2 - 6, fontSize: 10, color: "var(--ink-4)" }}>{v}</div>
            ))}
            <div style={{ position: "absolute", left: -34, top: CHART_H / 2 - 30, fontSize: 11, color: "var(--ink-3)", transform: "rotate(-90deg)", transformOrigin: "left top" }}>影响力 →</div>
            {/* 中位线（influence=5） */}
            <div style={{ position: "absolute", left: 0, right: 0, top: "50%", height: 1, background: "var(--line)", border: "1px dashed transparent", borderTop: "1px dashed var(--ink-4)" }} />
            {/* X 轴标签 */}
            {STANCE_AXIS.map((s) => (
              <div key={s} style={{ position: "absolute", bottom: -22, left: `${stanceX[s]}%`, transform: "translateX(-50%)", fontSize: 11, fontWeight: 500, color: stanceColor(s) }}>{s}</div>
            ))}
            {/* 气泡 */}
            {plotable.map((c) => {
              const sl = c.subjective_layer!;
              const stance = sl.stance!;
              const influence = sl.influence as number;
              const engagement = typeof sl.engagement === "number" ? sl.engagement : 5;
              const { idx, total } = scatter.get(c.id) ?? { idx: 0, total: 1 };
              // 同桶内按索引水平抖动散开
              const spread = total > 1 ? (idx - (total - 1) / 2) * 6 : 0;
              const x = stanceX[stance] + (spread / 8); // 百分比微调
              const yPct = (10 - influence) * 10; // 0-100
              const size = Math.max(18, Math.min(48, 18 + engagement * 3));
              const color = stanceColor(stance);
              return (
                <div
                  key={c.id}
                  onClick={() => onJump(c.id)}
                  title={`${c.name}：立场${stance} 影响力${influence} 参与度${engagement ?? "—"} 综合${sl.compositeScore ?? "—"}`}
                  style={{
                    position: "absolute",
                    left: `${x}%`,
                    top: `${yPct}%`,
                    width: size,
                    height: size,
                    marginLeft: -size / 2,
                    marginTop: -size / 2,
                    borderRadius: 999,
                    background: color,
                    opacity: 0.82,
                    border: "2px solid var(--surface)",
                    boxShadow: "var(--shadow-sm)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 10,
                    fontWeight: 700,
                    color: "var(--on-accent)",
                    cursor: "pointer",
                    transition: "transform 120ms",
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.transform = "scale(1.18)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.transform = "scale(1)"; }}
                >
                  {c.name[0]}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* 右：四象限策略 */}
      <Card style={{ width: 280, padding: 20, flexShrink: 0, overflow: "auto" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 12 }}>📖 四象限策略</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 12, lineHeight: 1.5 }}>
          {[
            { area: "高影响 × 支持/观望", color: "var(--success)", act: "重点巩固，发展为 Champion；借其影响力辐射他人。" },
            { area: "高影响 × 反对/中立", color: "var(--danger)", act: "重点化解，针对性回应其核心顾虑，避免其阻挠决策。" },
            { area: "低影响 × 支持", color: "var(--accent)", act: "培养为业务示范用户，积累正面口碑，不占用主攻精力。" },
            { area: "低影响 × 中立/反对", color: "var(--ink-3)", act: "持续观察，低成本维护，优先级最低。" },
          ].map((r) => (
            <div key={r.area} style={{ padding: 10, background: "var(--bg-2)", borderRadius: 8, borderLeft: `3px solid ${r.color}` }}>
              <div style={{ fontWeight: 600, color: r.color, marginBottom: 4 }}>{r.area}</div>
              <div style={{ fontSize: 11, color: "var(--ink-2)" }}>{r.act}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ─── 采购流程时间线（M4.2.5：五阶段通用模板 + 手动填写） ────────
// 项目级单例：GET /procurement-timeline（null 用默认模板）/ PUT upsert。
// 整体替换 stages（前端管完整五阶段，含 name 默认值），后端只存不解释。

/** 五阶段默认模板（与后端 PROCUREMENT_STAGE_TEMPLATE 对齐） */
const DEFAULT_PROCUREMENT_STAGES: ProcurementStage[] = [
  { key: "need_identification", name: "需求识别", status: "not_started", startDate: null, endDate: null, note: null, ownerCardId: null },
  { key: "solution_evaluation", name: "方案评估", status: "not_started", startDate: null, endDate: null, note: null, ownerCardId: null },
  { key: "vendor_screening", name: "供应商筛选", status: "not_started", startDate: null, endDate: null, note: null, ownerCardId: null },
  { key: "commercial_negotiation", name: "商务谈判", status: "not_started", startDate: null, endDate: null, note: null, ownerCardId: null },
  { key: "contract_signing", name: "合同签署", status: "not_started", startDate: null, endDate: null, note: null, ownerCardId: null },
];

const STAGE_STATUS_META: { value: ProcurementStageStatus; label: string; color: string }[] = [
  { value: "not_started", label: "未开始", color: "var(--ink-4)" },
  { value: "in_progress", label: "进行中", color: "var(--accent)" },
  { value: "completed", label: "已完成", color: "var(--success)" },
  { value: "blocked", label: "受阻", color: "var(--danger)" },
];

function stageStatusColor(status: ProcurementStageStatus | null | undefined): string {
  return STAGE_STATUS_META.find((s) => s.value === status)?.color ?? "var(--ink-4)";
}

function ProcurementTimelineView({
  projectId,
  cards,
}: {
  projectId: number;
  cards: StakeholderCard[];
}) {
  const toast = useToast();
  const [stages, setStages] = useState<ProcurementStage[]>(DEFAULT_PROCUREMENT_STAGES);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [lastSaved, setLastSaved] = useState<string | null>(null);

  // 拉取时间线（null → 用默认模板；有数据则与默认模板合并补齐缺失字段/阶段）
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .getProcurementTimeline(projectId)
      .then((tl) => {
        if (cancelled) return;
        if (tl && Array.isArray(tl.stages) && tl.stages.length > 0) {
          const merged = DEFAULT_PROCUREMENT_STAGES.map((tpl) => {
            const s = tl.stages.find((x) => x.key === tpl.key);
            return s ? { ...tpl, ...s } : tpl;
          });
          setStages(merged);
          setLastSaved(tl.updated_at);
        } else {
          setStages(DEFAULT_PROCUREMENT_STAGES);
          setLastSaved(null);
        }
        setDirty(false);
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : "加载采购时间线失败";
        toast.showToast(msg, "error");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, toast]);

  const updateStage = (key: string, patch: Partial<ProcurementStage>) => {
    setStages((prev) => prev.map((s) => (s.key === key ? { ...s, ...patch } : s)));
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const tl = await api.upsertProcurementTimeline(projectId, { stages });
      setStages(tl.stages);
      setLastSaved(tl.updated_at);
      setDirty(false);
      toast.showToast("采购时间线已保存", "success");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "保存失败";
      toast.showToast(msg, "error");
    } finally {
      setSaving(false);
    }
  };

  const completed = stages.filter((s) => s.status === "completed").length;
  const inProgress = stages.filter((s) => s.status === "in_progress").length;
  const blocked = stages.filter((s) => s.status === "blocked").length;

  return (
    <div style={{ display: "flex", gap: 20, height: "100%" }}>
      <Card style={{ flex: 1, padding: 0, overflow: "auto", display: "flex", flexDirection: "column" }}>
        {/* 头部：标题 + 进度统计 */}
        <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)" }}>采购流程时间线</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>
              五阶段通用模板（需求识别 → 方案评估 → 供应商筛选 → 商务谈判 → 合同签署），手动填写各阶段进度。
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, fontSize: 11, color: "var(--ink-3)", whiteSpace: "nowrap" }}>
            <span>已完成 <b style={{ color: "var(--success)" }}>{completed}</b>/5</span>
            {inProgress > 0 && <span>进行中 <b style={{ color: "var(--accent)" }}>{inProgress}</b></span>}
            {blocked > 0 && <span>受阻 <b style={{ color: "var(--danger)" }}>{blocked}</b></span>}
          </div>
        </div>

        {loading ? (
          <div style={{ padding: 40, display: "flex", alignItems: "center", justifyContent: "center", gap: 10, color: "var(--ink-3)", fontSize: 13 }}>
            <Spinner size={16} /> 加载采购时间线…
          </div>
        ) : (
          <div style={{ padding: "20px 20px 8px 20px", flex: 1 }}>
            {/* 时间线主体：左侧编号圆点 + 竖向连接线 */}
            <div style={{ position: "relative" }}>
              <div style={{ position: "absolute", left: 19, top: 12, bottom: 12, width: 2, background: "var(--line)" }} />
              {stages.map((s, idx) => {
                const color = stageStatusColor(s.status);
                const owner = s.ownerCardId != null ? cards.find((c) => c.id === s.ownerCardId) ?? null : null;
                return (
                  <div key={s.key} style={{ display: "flex", gap: 16, paddingBottom: 18 }}>
                    {/* 编号圆点（颜色随状态） */}
                    <div style={{ flexShrink: 0, width: 40, display: "flex", justifyContent: "center" }}>
                      <div
                        style={{
                          width: 28, height: 28, borderRadius: 999, display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: 12, fontWeight: 700, color: "var(--on-accent)", background: color,
                          border: "3px solid var(--surface)", boxShadow: "var(--shadow-sm)", zIndex: 1,
                        }}
                      >
                        {idx + 1}
                      </div>
                    </div>
                    {/* 阶段卡 */}
                    <div style={{ flex: 1, background: "var(--bg-2)", border: "1px solid var(--line)", borderRadius: 10, padding: 14 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 14, fontWeight: 600 }}>{s.name}</span>
                        {/* 状态选择（四态切换） */}
                        <div style={{ display: "flex", gap: 4, marginLeft: "auto", flexWrap: "wrap" }}>
                          {STAGE_STATUS_META.map((m) => {
                            const active = s.status === m.value;
                            return (
                              <button key={m.value} onClick={() => updateStage(s.key, { status: m.value })} style={statusBtnStyle(active, m.color)}>
                                {m.label}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 10 }}>
                        <label style={fieldLabelStyle}>
                          <span style={miniLabelStyle}>开始日期</span>
                          <input type="date" value={s.startDate ?? ""} onChange={(e) => updateStage(s.key, { startDate: e.target.value || null })} style={dateInputStyle} />
                        </label>
                        <label style={fieldLabelStyle}>
                          <span style={miniLabelStyle}>结束日期</span>
                          <input type="date" value={s.endDate ?? ""} onChange={(e) => updateStage(s.key, { endDate: e.target.value || null })} style={dateInputStyle} />
                        </label>
                        <label style={fieldLabelStyle}>
                          <span style={miniLabelStyle}>关键角色</span>
                          <select value={s.ownerCardId ?? ""} onChange={(e) => updateStage(s.key, { ownerCardId: e.target.value ? Number(e.target.value) : null })} style={selectStyle}>
                            <option value="">（未指定）</option>
                            {cards.map((c) => (
                              <option key={c.id} value={c.id}>{c.name}{c.position ? ` · ${c.position}` : ""}</option>
                            ))}
                          </select>
                        </label>
                      </div>
                      <label style={{ display: "block" }}>
                        <span style={miniLabelStyle}>阶段说明</span>
                        <textarea value={s.note ?? ""} onChange={(e) => updateStage(s.key, { note: e.target.value || null })} placeholder="该阶段的关键事件、卡点、下一步…" rows={2} style={textareaStyle} />
                      </label>
                      {owner && (
                        <div style={{ marginTop: 8, fontSize: 11, color: "var(--ink-3)" }}>
                          关键角色：<b style={{ color: "var(--ink-2)" }}>{owner.name}</b>{owner.department ? ` · ${owner.department}` : ""}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 底部保存栏（粘底） */}
        <div style={{ padding: "12px 20px", borderTop: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 12 }}>
          {lastSaved && <span style={{ fontSize: 11, color: "var(--ink-4)" }}>最近保存：{new Date(lastSaved).toLocaleString("zh-CN")}</span>}
          {dirty && <span style={{ fontSize: 11, color: "var(--warn)" }}>● 有未保存更改</span>}
          <div style={{ flex: 1 }} />
          <button onClick={save} disabled={!dirty || saving} style={saveBtnStyle(!dirty || saving)}>
            {saving ? "保存中…" : "保存时间线"}
          </button>
        </div>
      </Card>

      {/* 右：五阶段释义 */}
      <Card style={{ width: 280, padding: 20, flexShrink: 0, overflow: "auto" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 12 }}>📖 五阶段释义</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 12, lineHeight: 1.6, color: "var(--ink-2)" }}>
          {([
            ["需求识别", "客户内部立项、明确预算与需求清单。关注经济决策人与预算来源。"],
            ["方案评估", "客户评估各方案技术与可行性。技术评估人主导，需对接方案亮点。"],
            ["供应商筛选", "客户圈定入围供应商短名单。差异化价值与教练支持关键。"],
            ["商务谈判", "价格/条款/交付周期博弈。采购财务介入，需准备让步底线。"],
            ["合同签署", "法务/合同流程收口。维持关系，为交付与续约铺垫。"],
          ] as [string, string][]).map(([name, desc]) => (
            <div key={name} style={{ padding: 10, background: "var(--bg-2)", borderRadius: 8, borderLeft: "3px solid var(--accent)" }}>
              <div style={{ fontWeight: 600, color: "var(--ink)", marginBottom: 4 }}>{name}</div>
              <div style={{ fontSize: 11, color: "var(--ink-3)" }}>{desc}</div>
            </div>
          ))}
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12, color: "var(--ink-3)", fontSize: 11 }}>
            该时间线为项目级共享，保存后团队成员均可见，可作为赢单里程碑跟踪。
          </div>
        </div>
      </Card>
    </div>
  );
}

// ─── 知识库视图（M4.2.7：三板块 + CRUD + Markdown 富文本，§2.4 §5.2） ──
// 三分类：角色识别速查 / 行为分析速查 / 新人培养流程（KnowledgeCategory）。
// 跨客户通用方法论沉淀，项目内团队共享。内容支持 Markdown 渲染（复用 MarkdownView）。
// 标准参考内容来自《营销地图设计文档V2.0》附录（.docx），由团队手动沉淀或后续后端种子导入。

/** 知识库三板块分类元数据 */
const KB_CATEGORIES: { key: KnowledgeCategory; label: string; icon: keyof typeof I; desc: string; hint: string }[] = [
  {
    key: "role_recognition",
    label: "角色识别速查",
    icon: "UserCheck",
    desc: "五类角色的典型职位、核心关注、身体语言、话语特征、典型回应、识别信号",
    hint: "建议为每类角色（经济决策人 / 技术评估人 / 终端用户 / 教练支持者 / 采购财务）各建一条，沉淀识别要点。",
  },
  {
    key: "behavior_quick_ref",
    label: "行为分析速查",
    icon: "Activity",
    desc: "常见观察行为 → 可能解读 → 建议下一步动作",
    hint: "每条记录一个观察行为及其解读与建议动作，沉淀 8 条以上形成速查库。",
  },
  {
    key: "onboarding_guide",
    label: "新人培养流程",
    icon: "Book",
    desc: "理论学习 → 模拟演练 → 跟岗实践 → 独立拜访",
    hint: "建议按四阶段各建一条：理论学习(1 周)、模拟演练(2 天)、跟岗实践(2 周)、独立拜访(持续)。",
  },
];

function KnowledgeBaseView({ projectId }: { projectId: number }) {
  const toast = useToast();
  const [entries, setEntries] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [editor, setEditor] = useState<{ category: KnowledgeCategory; entry: KnowledgeBase | null } | null>(null);
  const [open, setOpen] = useState<Record<KnowledgeCategory, boolean>>({
    role_recognition: true,
    behavior_quick_ref: true,
    onboarding_guide: true,
  });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setEntries(await api.listKnowledgeBase(projectId));
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "加载知识库失败", "error");
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleDelete = async (id: number, title: string) => {
    if (!window.confirm(`确认删除「${title}」？`)) return;
    try {
      await api.deleteKnowledgeBase(projectId, id);
      toast.showToast("已删除", "success");
      refresh();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "删除失败", "error");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 960 }}>
      {/* 顶部说明 */}
      <Card style={{ padding: "14px 18px", fontSize: 12, color: "var(--ink-3)", lineHeight: 1.6 }}>
        <b style={{ color: "var(--ink-2)" }}>📚 知识库</b> · 跨客户通用方法论沉淀（角色识别 / 行为速查 / 入职指南），
        支持 Markdown 富文本，项目内团队共享。点击「+ 新增」沉淀经验，内容实时保存到该项目。
      </Card>

      {loading ? (
        <Card style={{ padding: 40, display: "flex", alignItems: "center", justifyContent: "center", gap: 10, color: "var(--ink-3)", fontSize: 13 }}>
          <Spinner size={16} /> 加载知识库…
        </Card>
      ) : (
        KB_CATEGORIES.map((cat) => {
          const Icon = I[cat.icon];
          const list = entries.filter((e) => e.category === cat.key);
          const isOpen = open[cat.key];
          return (
            <Card key={cat.key} style={{ padding: 0, overflow: "hidden" }}>
              {/* 分类头（可折叠） */}
              <div
                onClick={() => setOpen((o) => ({ ...o, [cat.key]: !o[cat.key] }))}
                style={kbCatHeaderStyle}
              >
                <I.ChevronDown size={14} style={{ transform: isOpen ? "none" : "rotate(-90deg)", transition: "transform 120ms", flexShrink: 0 }} />
                <Icon size={15} style={{ color: "var(--accent)", flexShrink: 0 }} />
                <span style={{ fontWeight: 600, color: "var(--ink)", fontSize: 13 }}>{cat.label}</span>
                <Tag tone="neutral">{list.length}</Tag>
                <span style={kbCatDescStyle}>{cat.desc}</span>
                <div style={{ flex: 1 }} />
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditor({ category: cat.key, entry: null });
                  }}
                  style={kbAddBtnStyle}
                >
                  <I.Plus size={13} /> 新增
                </button>
              </div>
              {/* 分类内容 */}
              {isOpen && (
                <div style={{ padding: "6px 0" }}>
                  {list.length === 0 ? (
                    <div style={kbEmptyStyle}>
                      <Icon size={26} style={{ color: "var(--ink-4)", marginBottom: 6 }} />
                      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-2)", marginBottom: 4 }}>暂无内容</div>
                      <div style={{ maxWidth: 460, lineHeight: 1.7 }}>{cat.hint}</div>
                    </div>
                  ) : (
                    list.map((e) => (
                      <div key={e.id} style={kbEntryStyle}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                          <span style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)", fontFamily: "var(--serif)" }}>{e.title}</span>
                          <div style={{ flex: 1 }} />
                          <button onClick={() => setEditor({ category: cat.key, entry: e })} style={iconBtnStyle} title="编辑">
                            <I.Edit size={13} />
                          </button>
                          <button onClick={() => handleDelete(e.id, e.title)} style={iconBtnStyle} title="删除">
                            <I.Trash size={13} />
                          </button>
                        </div>
                        <MarkdownView text={e.content} />
                      </div>
                    ))
                  )}
                </div>
              )}
            </Card>
          );
        })
      )}

      {editor && (
        <KBEntryEditor
          projectId={projectId}
          category={editor.category}
          entry={editor.entry}
          onClose={() => setEditor(null)}
          onSaved={() => {
            setEditor(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}

/** 知识库条目编辑器（新建/编辑，Markdown 编辑 + 预览切换） */
function KBEntryEditor({
  projectId,
  category,
  entry,
  onClose,
  onSaved,
}: {
  projectId: number;
  category: KnowledgeCategory;
  entry: KnowledgeBase | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const cat = KB_CATEGORIES.find((c) => c.key === category)!;
  const [title, setTitle] = useState(entry?.title ?? "");
  const [content, setContent] = useState(entry?.content ?? "");
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState(false);

  const save = async () => {
    if (!title.trim() || !content.trim()) {
      toast.showToast("标题和内容不能为空", "error");
      return;
    }
    setSaving(true);
    try {
      if (entry) {
        await api.updateKnowledgeBase(projectId, entry.id, { title: title.trim(), content });
      } else {
        await api.createKnowledgeBase(projectId, { category, title: title.trim(), content });
      }
      toast.showToast(entry ? "已更新" : "已新增", "success");
      onSaved();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div onClick={onClose} style={modalOverlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={{ ...modalCardStyle, width: 640, maxHeight: "85vh", overflow: "auto" }}>
        {/* 头部 */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <span style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)" }}>
            {entry ? "编辑条目" : "新增条目"}
          </span>
          <Tag tone="accent">{cat.label}</Tag>
          <div style={{ flex: 1 }} />
          <button onClick={onClose} style={iconBtnStyle} title="关闭">✕</button>
        </div>

        {/* 标题 */}
        <label style={{ display: "block", marginBottom: 12 }}>
          <span style={miniLabelStyle}>标题</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={`如：${category === "role_recognition" ? "经济决策人 识别要点" : category === "behavior_quick_ref" ? "提前准备详细问题清单" : "理论学习阶段"}`}
            style={{ ...textareaStyle, height: "auto", padding: "7px 10px", fontWeight: 500 }}
          />
        </label>

        {/* 内容（编辑 / 预览切换） */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span style={miniLabelStyle}>内容（支持 Markdown）</span>
          <div style={{ flex: 1 }} />
          <button onClick={() => setPreview((p) => !p)} style={linkBtnStyle}>
            {preview ? "✎ 编辑" : "👁 预览"}
          </button>
        </div>
        {preview ? (
          <div style={{ ...textareaStyle, minHeight: 240, overflow: "auto" }}>
            {content.trim() ? <MarkdownView text={content} /> : <span style={{ color: "var(--ink-4)" }}>（无内容）</span>}
          </div>
        ) : (
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={"支持 Markdown：\n## 小标题\n- 要点一\n- 要点二\n\n**强调** 与 [链接](url)"}
            rows={12}
            style={{ ...textareaStyle, minHeight: 240 }}
          />
        )}

        {/* 底部操作 */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <button onClick={onClose} style={kbGhostBtnStyle}>取消</button>
          <button onClick={save} disabled={saving} style={saveBtnStyle(saving)}>
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── 角色关系网络图（M4.2.8：ReactFlow，节点=角色卡，边=4 类关系，§5.2） ──
// 数据源 GET /api/projects/{id}/stakeholder-relations/graph（nodes + edges）。
// 4 类关系（reports_to/influences/collaborates/opposes）用不同颜色 + 线型区分；
// 节点点击跳转角色卡详情（M4.2.9 加关系 CRUD 编辑）。圆形自动布局 + 用户可拖拽重排。

/** 四类关系样式（颜色 + 线型 + 中文标签） */
const RELATION_META: Record<StakeholderRelationType, { label: string; color: string; dashed: boolean }> = {
  reports_to: { label: "汇报", color: "var(--accent)", dashed: false },
  influences: { label: "影响", color: "var(--info)", dashed: false },
  collaborates: { label: "协作", color: "var(--success)", dashed: false },
  opposes: { label: "对立", color: "var(--danger)", dashed: true },
};

/** 关系图自定义节点数据 */
interface RelationNodeData {
  name: string;
  roleType: StakeholderRoleType | null;
  department: string | null;
  [key: string]: unknown;
}

/** 关系图节点（头像 + 姓名 + 部门，边框色 = 角色类型色） */
function RelationNode({ data }: NodeProps<RelationNodeData>) {
  const { name, roleType, department } = data;
  const color = roleType ? ROLE_TYPE_COLOR[roleType] : "var(--ink-3)";
  return (
    <div
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", gap: 3,
        padding: "8px 12px 6px", background: "var(--surface)",
        border: `2px solid ${color}`, borderRadius: 12,
        boxShadow: "var(--shadow-sm)", minWidth: 76,
      }}
    >
      <div style={{
        width: 34, height: 34, borderRadius: 999, background: color, color: "var(--on-accent)",
        display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, fontWeight: 700,
      }}>
        {name[0]}
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink)", fontFamily: "var(--serif)" }}>{name}</div>
      {department && (
        <div style={{ fontSize: 10, color: "var(--ink-3)", maxWidth: 110, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {department}
        </div>
      )}
    </div>
  );
}

/** nodeTypes 须稳定（模块级常量，避免 ReactFlow 重渲染循环） */
const RELATION_NODE_TYPES: NodeTypes = { relation: RelationNode };

function RelationsView({
  projectId,
  cards,
  onJump,
}: {
  projectId: number;
  cards: StakeholderCard[];
  onJump: (id: number) => void;
}) {
  const toast = useToast();
  const [graph, setGraph] = useState<StakeholderGraph | null>(null);
  const [loading, setLoading] = useState(true);
  // 关系编辑（M4.2.9）：添加弹窗 + 选中边删除
  const [showRel, setShowRel] = useState(false);
  const [selEdgeId, setSelEdgeId] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    api
      .getStakeholderGraph(projectId)
      .then(setGraph)
      .catch((e) => toast.showToast(e instanceof Error ? e.message : "加载关系网络失败", "error"))
      .finally(() => setLoading(false));
  }, [projectId, toast]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleDeleteRelation = async () => {
    if (selEdgeId == null) return;
    if (!window.confirm("确认删除该关系？")) return;
    try {
      await api.deleteStakeholderRelation(projectId, Number(selEdgeId));
      toast.showToast("已删除关系", "success");
      setSelEdgeId(null);
      refresh();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "删除失败", "error");
    }
  };

  // 圆形自动布局：N 节点均匀分布于圆周
  const rfNodes: Node<RelationNodeData>[] = useMemo(() => {
    if (!graph) return [];
    const N = graph.nodes.length;
    const R = Math.max(150, Math.min(300, N * 34));
    return graph.nodes.map((n, i) => {
      const angle = (2 * Math.PI * i) / Math.max(N, 1);
      return {
        id: String(n.id),
        type: "relation",
        position: { x: 320 + R * Math.cos(angle), y: 220 + R * Math.sin(angle) },
        data: { name: n.name, roleType: n.role_type, department: n.department },
      };
    });
  }, [graph]);

  // 边：4 类关系颜色 + 线型 + 箭头 + 中文标签；选中边加粗高亮（供 M4.2.9 删除）
  const rfEdges: Edge[] = useMemo(() => {
    if (!graph) return [];
    return graph.edges.map((e) => {
      const meta = RELATION_META[e.relation_type] ?? { label: e.relation_type, color: "var(--ink-3)", dashed: false };
      const selected = selEdgeId === String(e.id);
      return {
        id: String(e.id),
        source: String(e.source),
        target: String(e.target),
        label: meta.label,
        labelStyle: { fill: meta.color, fontWeight: 600, fontSize: 11 },
        labelBgStyle: { fill: "var(--surface)", fillOpacity: 0.9 },
        labelBgPadding: [4, 2],
        selected,
        style: { stroke: meta.color, strokeWidth: selected ? 4 : 2, strokeDasharray: meta.dashed ? "6 4" : undefined },
        markerEnd: { type: MarkerType.ArrowClosed, color: meta.color, width: 18, height: 18 },
      };
    });
  }, [graph, selEdgeId]);

  const hasCards = cards.length > 0;
  const edgeCount = graph?.edges.length ?? 0;

  // 无角色卡
  if (!loading && !hasCards) {
    return (
      <Card style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
        <I.Network size={32} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
        <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>暂无角色卡</div>
        <div>建立角色卡并为其添加关系（汇报 / 影响 / 协作 / 对立）后，此处展示交互式关系网络图。</div>
      </Card>
    );
  }

  return (
    <div style={{ display: "flex", gap: 16, height: "100%" }}>
      {/* 左：关系图 */}
      <Card style={{ flex: 1, padding: 0, overflow: "hidden", position: "relative", minWidth: 0 }}>
        <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <I.Network size={15} style={{ color: "var(--accent)" }} />
          <span style={{ fontSize: 14, fontWeight: 600, fontFamily: "var(--serif)" }}>角色关系网络图</span>
          <span style={{ fontSize: 11, color: "var(--ink-3)" }}>· {graph?.nodes.length ?? 0} 角色 / {edgeCount} 关系</span>
          {edgeCount === 0 && !loading && (
            <span style={{ fontSize: 11, color: "var(--warn)" }}>（暂无关系，点击右侧「添加关系」）</span>
          )}
          <div style={{ flex: 1 }} />
          {selEdgeId && (
            <button onClick={handleDeleteRelation} style={{ ...kbGhostBtnStyle, color: "var(--danger)", borderColor: "var(--danger)" }} title="删除选中的关系">
              <I.Trash size={13} /> 删除选中关系
            </button>
          )}
          <button onClick={() => setShowRel(true)} disabled={cards.length < 2} style={primaryBtnStyle} title={cards.length < 2 ? "至少需要 2 张角色卡" : "添加关系"}>
            <I.Plus size={13} /> 添加关系
          </button>
        </div>
        <div style={{ height: "calc(100% - 45px)", background: "var(--bg-2)" }}>
          {loading ? (
            <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 10, color: "var(--ink-3)", fontSize: 13 }}>
              <Spinner size={16} /> 加载关系网络…
            </div>
          ) : (
            <ReactFlow
              nodes={rfNodes}
              edges={rfEdges}
              nodeTypes={RELATION_NODE_TYPES}
              onNodeClick={(_, node) => onJump(Number(node.id))}
              onEdgeClick={(_, edge) => setSelEdgeId(edge.id)}
              onPaneClick={() => setSelEdgeId(null)}
              fitView
              fitViewOptions={{ padding: 0.2 }}
              proOptions={{ hideAttribution: true }}
              defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed } }}
            >
              <Background gap={16} size={1} color="var(--line)" />
              <Controls showInteractive={false} />
              <MiniMap
                nodeColor={(n) => {
                  const rt = (n.data as RelationNodeData)?.roleType;
                  return rt ? ROLE_TYPE_COLOR[rt] : "var(--ink-4)";
                }}
                maskColor="rgba(0,0,0,0.05)"
              />
            </ReactFlow>
          )}
        </div>
      </Card>

      {/* 右：关系图例 + 说明 */}
      <Card style={{ width: 240, padding: 16, flexShrink: 0, overflow: "auto" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 12 }}>
          📖 关系类型图例
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 12 }}>
          {(Object.keys(RELATION_META) as StakeholderRelationType[]).map((rt) => {
            const m = RELATION_META[rt];
            return (
              <div key={rt} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <svg width="34" height="10" style={{ flexShrink: 0 }}>
                  <line x1="0" y1="5" x2="30" y2="5" stroke={m.color} strokeWidth="2.5" strokeDasharray={m.dashed ? "5 3" : undefined} />
                  <polygon points="28,1 34,5 28,9" fill={m.color} />
                </svg>
                <span style={{ fontWeight: 600, color: m.color }}>{m.label}</span>
              </div>
            );
          })}
        </div>
        <div style={{ borderTop: "1px solid var(--line)", marginTop: 14, paddingTop: 12, fontSize: 11, color: "var(--ink-3)", lineHeight: 1.7 }}>
          <div style={{ fontWeight: 600, color: "var(--ink-2)", marginBottom: 4 }}>操作</div>
          <div>· 点击节点 → 跳转该角色卡详情</div>
          <div>· 点击边选中 → 顶部「删除选中关系」</div>
          <div>· 拖拽节点 / 滚轮缩放 / 拖动画布</div>
          <div>· 节点边框色 = 角色类型（见角色列表）</div>
        </div>
      </Card>

      {showRel && (
        <RelationEditModal
          projectId={projectId}
          cards={cards}
          relation={null}
          onClose={() => setShowRel(false)}
          onSaved={() => {
            setShowRel(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}

// ─── 角色卡编辑器（M4.2.9：手动新增/编辑角色卡，全字段，§5.2） ──
// 手动建卡直接进正式库（review_status=reviewed，后端 schema 默认亦如此，§2.4）。
// 全字段：基本信息 + 客观层 7 + 主观层（评分+全文本+confidence）+ behaviors + stance_change_log。
// compositeScore/gradeLevel 由后端按 §5.2 公式算回写，编辑器不收集。

const DECISION_POWER_OPTIONS = ["最终决策", "技术把关", "推荐建议", "影响者", "信息提供"];
const STANCE_OPTIONS: StanceLevel[] = ["支持", "中立", "反对", "观望"];
const CONFIDENCE_OPTIONS = ["高", "中", "低"];

/** 客观层 7 字段定义 */
const OBJECTIVE_FIELDS: { key: string; label: string }[] = [
  { key: "education", label: "教育背景" },
  { key: "previousCompanies", label: "过往公司与年限" },
  { key: "personality", label: "性格特征" },
  { key: "communicationPreference", label: "沟通偏好" },
  { key: "relationships", label: "人际关系" },
  { key: "historyWithUs", label: "与我方历史合作" },
  { key: "historyWithCompetitor", label: "与竞品历史合作" },
];

/** 主观层文本字段定义（评分类单独处理） */
const SUBJECTIVE_TEXT_FIELDS: { key: string; label: string }[] = [
  { key: "explicitKPI", label: "显性 KPI" },
  { key: "personalMotivation", label: "隐性个人诉求" },
  { key: "attitudeToUs", label: "对我方方案的态度" },
  { key: "attitudeToCompetitor", label: "对竞品的态度" },
  { key: "coreConcerns", label: "核心顾虑" },
  { key: "leverage", label: "影响杠杆" },
];

/** 可折叠分区 */
function EditSection({ title, open, onToggle, children }: { title: string; open: boolean; onToggle: () => void; children: React.ReactNode }) {
  return (
    <div style={{ borderBottom: "1px solid var(--line)", paddingBottom: 6, marginBottom: 6 }}>
      <button onClick={onToggle} style={sectionToggleStyle}>
        <I.ChevronDown size={13} style={{ transform: open ? "none" : "rotate(-90deg)", transition: "transform 120ms" }} />
        <span>{title}</span>
      </button>
      {open && <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 8 }}>{children}</div>}
    </div>
  );
}

/** 编辑器字段（标签 + 控件，full 跨列） */
function EditField({ label, full, children }: { label: string; full?: boolean; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 3, flex: full ? "1 1 100%" : "1 1 calc(50% - 6px)", minWidth: 0 }}>
      <span style={miniLabelStyle}>{label}</span>
      {children}
    </label>
  );
}

function CardEditModal({
  projectId,
  card,
  onClose,
  onSaved,
}: {
  projectId: number;
  card: StakeholderCard | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const isEdit = card != null;
  const ol = (card?.objective_layer ?? {}) as Record<string, string>;
  const sl = card?.subjective_layer ?? {};

  // 基本信息
  const [name, setName] = useState(card?.name ?? "");
  const [position, setPosition] = useState(card?.position ?? "");
  const [department, setDepartment] = useState(card?.department ?? "");
  const [reportsTo, setReportsTo] = useState(card?.reports_to ?? "");
  const [contactInfo, setContactInfo] = useState(card?.contact_info ?? "");
  const [roleType, setRoleType] = useState<StakeholderRoleType | "">(card?.role_type ?? "");
  const [decisionPower, setDecisionPower] = useState(card?.decision_power ?? "");

  // 客观层
  const [obj, setObj] = useState<Record<string, string>>(
    () => Object.fromEntries(OBJECTIVE_FIELDS.map((f) => [f.key, ol[f.key] ?? ""])) as Record<string, string>,
  );
  // 主观层
  const [stance, setStance] = useState<StanceLevel | "">(sl.stance ?? "");
  const [confidence, setConfidence] = useState(sl.confidence ?? "");
  const [engagement, setEngagement] = useState(sl.engagement != null ? String(sl.engagement) : "");
  const [influence, setInfluence] = useState(sl.influence != null ? String(sl.influence) : "");
  const [support, setSupport] = useState(sl.support != null ? String(sl.support) : "");
  const [subj, setSubj] = useState<Record<string, string>>(
    () => Object.fromEntries(SUBJECTIVE_TEXT_FIELDS.map((f) => [f.key, ((sl as Record<string, string>)[f.key]) ?? ""])) as Record<string, string>,
  );
  // 数组
  const [behaviors, setBehaviors] = useState<BehaviorEntry[]>(card?.behaviors ?? []);
  const [stanceLog, setStanceLog] = useState<StanceChangeEntry[]>(card?.stance_change_log ?? []);
  // 跨项目公开（M5.5.3，§5.x / §6.3）
  const [isPublic, setIsPublic] = useState<boolean>(card?.is_public ?? false);
  const [sharedWith, setSharedWith] = useState<number[]>(card?.shared_with ?? []);

  const [saving, setSaving] = useState(false);
  const [openSec, setOpenSec] = useState<Record<string, boolean>>({
    basic: true,
    objective: false,
    subjective: false,
    behaviors: false,
    stance: false,
    visibility: false,
  });
  const toggle = (k: string) => setOpenSec((s) => ({ ...s, [k]: !s[k] }));

  const numOrUndef = (s: string): number | undefined => {
    if (s.trim() === "") return undefined;
    const n = Number(s);
    if (Number.isNaN(n)) return undefined;
    return Math.max(1, Math.min(10, n));
  };

  const buildPayload = (): StakeholderCardInput => {
    const trimObj = (o: Record<string, string>): Record<string, string> => {
      const out: Record<string, string> = {};
      for (const [k, v] of Object.entries(o)) if (v.trim()) out[k] = v.trim();
      return out;
    };
    const objectiveLayer = trimObj(obj);
    const subjectiveLayer: Record<string, unknown> = { ...trimObj(subj) };
    if (stance) subjectiveLayer.stance = stance;
    if (confidence) subjectiveLayer.confidence = confidence;
    const eg = numOrUndef(engagement);
    if (eg != null) subjectiveLayer.engagement = eg;
    const inf = numOrUndef(influence);
    if (inf != null) subjectiveLayer.influence = inf;
    const sup = numOrUndef(support);
    if (sup != null) subjectiveLayer.support = sup;

    const payload: StakeholderCardInput = {
      name: name.trim(),
      position: position.trim() || null,
      department: department.trim() || null,
      reports_to: reportsTo.trim() || null,
      contact_info: contactInfo.trim() || null,
      role_type: roleType || null,
      decision_power: decisionPower || null,
      objective_layer: Object.keys(objectiveLayer).length ? objectiveLayer : undefined,
      subjective_layer: Object.keys(subjectiveLayer).length ? subjectiveLayer : undefined,
      behaviors: behaviors.length ? behaviors : null,
      stance_change_log: stanceLog.length ? stanceLog : null,
      is_public: isPublic,
      shared_with: sharedWith,
    };
    if (!isEdit) payload.review_status = "reviewed";
    return payload;
  };

  const save = async () => {
    if (!name.trim()) {
      toast.showToast("姓名不能为空", "error");
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload();
      if (isEdit && card) {
        await api.updateStakeholderCard(projectId, card.id, payload);
      } else {
        await api.createStakeholderCard(projectId, payload);
      }
      toast.showToast(isEdit ? "已更新角色卡" : "已新增角色卡", "success");
      onSaved();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  };

  const updateBeh = (i: number, key: keyof BehaviorEntry, val: string) =>
    setBehaviors((arr) => arr.map((b, j) => (j === i ? { ...b, [key]: val } : b)));
  const updateStance = (i: number, key: keyof StanceChangeEntry, val: string) =>
    setStanceLog((arr) => arr.map((e, j) => (j === i ? { ...e, [key]: val } : e)));

  return (
    <div onClick={onClose} style={modalOverlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={{ ...modalCardStyle, width: 680, maxHeight: "88vh", overflow: "auto" }}>
        {/* 头部 */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
          <span style={{ fontSize: 16, fontWeight: 600, fontFamily: "var(--serif)" }}>{isEdit ? "编辑角色卡" : "新增角色卡"}</span>
          <div style={{ flex: 1 }} />
          <button onClick={onClose} style={iconBtnStyle} title="关闭">✕</button>
        </div>

        {/* 基本信息 */}
        <EditSection title="基本信息" open={openSec.basic} onToggle={() => toggle("basic")}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <EditField label="姓名 *"><input value={name} onChange={(e) => setName(e.target.value)} style={modalInputStyle} placeholder="必填" /></EditField>
            <EditField label="职位"><input value={position} onChange={(e) => setPosition(e.target.value)} style={modalInputStyle} /></EditField>
            <EditField label="部门"><input value={department} onChange={(e) => setDepartment(e.target.value)} style={modalInputStyle} /></EditField>
            <EditField label="汇报对象"><input value={reportsTo} onChange={(e) => setReportsTo(e.target.value)} style={modalInputStyle} placeholder="姓名（驱动组织架构图）" /></EditField>
            <EditField label="联系方式"><input value={contactInfo} onChange={(e) => setContactInfo(e.target.value)} style={modalInputStyle} placeholder="邮箱 / 电话" /></EditField>
            <EditField label="角色类型">
              <select value={roleType} onChange={(e) => setRoleType(e.target.value as StakeholderRoleType | "")} style={selectStyle}>
                <option value="">（未选择）</option>
                {ROLE_TYPE_ORDER.map((rt) => <option key={rt} value={rt}>{ROLE_TYPE_LABELS[rt]}</option>)}
              </select>
            </EditField>
            <EditField label="决策权">
              <select value={decisionPower} onChange={(e) => setDecisionPower(e.target.value)} style={selectStyle}>
                <option value="">（未选择）</option>
                {DECISION_POWER_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </EditField>
          </div>
        </EditSection>

        {/* 客观层 */}
        <EditSection title="客观信息层（7 字段）" open={openSec.objective} onToggle={() => toggle("objective")}>
          {OBJECTIVE_FIELDS.map((f) => (
            <EditField key={f.key} label={f.label} full>
              <textarea value={obj[f.key]} onChange={(e) => setObj({ ...obj, [f.key]: e.target.value })} rows={2} style={textareaStyle} />
            </EditField>
          ))}
        </EditSection>

        {/* 主观层 */}
        <EditSection title="主观分析层（评分 + 全字段 + 置信度）" open={openSec.subjective} onToggle={() => toggle("subjective")}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <EditField label="立场">
              <select value={stance} onChange={(e) => setStance(e.target.value as StanceLevel | "")} style={selectStyle}>
                <option value="">（未选择）</option>
                {STANCE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </EditField>
            <EditField label="置信度">
              <select value={confidence} onChange={(e) => setConfidence(e.target.value)} style={selectStyle}>
                <option value="">（未选择）</option>
                {CONFIDENCE_OPTIONS.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </EditField>
            <EditField label="参与度 (1-10)"><input type="number" min={1} max={10} value={engagement} onChange={(e) => setEngagement(e.target.value)} style={modalInputStyle} /></EditField>
            <EditField label="影响力 (1-10)"><input type="number" min={1} max={10} value={influence} onChange={(e) => setInfluence(e.target.value)} style={modalInputStyle} /></EditField>
            <EditField label="支持度 (1-10)"><input type="number" min={1} max={10} value={support} onChange={(e) => setSupport(e.target.value)} style={modalInputStyle} /></EditField>
          </div>
          <div style={{ fontSize: 11, color: "var(--ink-4)", margin: "2px 0 8px" }}>综合评分与等级由后端按 §5.2 公式（参与度×0.3 + 影响力×0.4 + 支持度×0.3）自动计算。</div>
          {SUBJECTIVE_TEXT_FIELDS.map((f) => (
            <EditField key={f.key} label={f.label} full>
              <textarea value={subj[f.key]} onChange={(e) => setSubj({ ...subj, [f.key]: e.target.value })} rows={2} style={textareaStyle} />
            </EditField>
          ))}
        </EditSection>

        {/* 行为分析 */}
        <EditSection title={`行为分析（${behaviors.length} 条）`} open={openSec.behaviors} onToggle={() => toggle("behaviors")}>
          {behaviors.map((b, i) => (
            <div key={i} style={arrayItemStyle}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-2)" }}>#{i + 1}</span>
                <button onClick={() => setBehaviors((arr) => arr.filter((_, j) => j !== i))} style={linkBtnStyle}>删除</button>
              </div>
              <textarea value={b.observation ?? ""} onChange={(e) => updateBeh(i, "observation", e.target.value)} placeholder="观察到的行为（客观记录）" rows={2} style={textareaStyle} />
              <textarea value={b.interpretation ?? ""} onChange={(e) => updateBeh(i, "interpretation", e.target.value)} placeholder="解读（基于角色类型的推断）" rows={2} style={textareaStyle} />
              <textarea value={b.suggestedAction ?? ""} onChange={(e) => updateBeh(i, "suggestedAction", e.target.value)} placeholder="建议下一步动作" rows={2} style={textareaStyle} />
            </div>
          ))}
          <button onClick={() => setBehaviors((arr) => [...arr, {}])} style={addRowBtnStyle}>+ 添加行为</button>
        </EditSection>

        {/* 态度历史 */}
        <EditSection title={`态度变化历史（${stanceLog.length} 条）`} open={openSec.stance} onToggle={() => toggle("stance")}>
          {stanceLog.map((e, i) => (
            <div key={i} style={arrayItemStyle}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-2)" }}>#{i + 1}</span>
                <button onClick={() => setStanceLog((arr) => arr.filter((_, j) => j !== i))} style={linkBtnStyle}>删除</button>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 3, flex: "0 0 150px" }}>
                  <span style={miniLabelStyle}>日期</span>
                  <input type="date" value={e.date ?? ""} onChange={(ev) => updateStance(i, "date", ev.target.value)} style={modalInputStyle} />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 3, flex: "1 1 120px" }}>
                  <span style={miniLabelStyle}>此前立场</span>
                  <select value={e.from ?? ""} onChange={(ev) => updateStance(i, "from", ev.target.value)} style={selectStyle}>
                    <option value="">（未选择）</option>
                    {STANCE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 3, flex: "1 1 120px" }}>
                  <span style={miniLabelStyle}>当前立场</span>
                  <select value={e.to ?? ""} onChange={(ev) => updateStance(i, "to", ev.target.value)} style={selectStyle}>
                    <option value="">（未选择）</option>
                    {STANCE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </label>
              </div>
              <textarea value={e.reason ?? ""} onChange={(ev) => updateStance(i, "reason", ev.target.value)} placeholder="变化原因" rows={2} style={textareaStyle} />
            </div>
          ))}
          <button onClick={() => setStanceLog((arr) => [...arr, {}])} style={addRowBtnStyle}>+ 添加态度变化</button>
        </EditSection>

        {/* 跨项目公开（M5.5.3） */}
        <EditSection
          title={`跨项目公开${isPublic ? " · 完全公开" : sharedWith.length ? ` · 共享 ${sharedWith.length} 人` : ""}`}
          open={openSec.visibility}
          onToggle={() => toggle("visibility")}
        >
          <VisibilityControls
            isPublic={isPublic}
            sharedWith={sharedWith}
            onChange={(v) => {
              setIsPublic(v.is_public);
              setSharedWith(v.shared_with);
            }}
          />
        </EditSection>

        {/* 底部操作 */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <button onClick={onClose} style={kbGhostBtnStyle}>取消</button>
          <button onClick={save} disabled={saving} style={saveBtnStyle(saving)}>{saving ? "保存中…" : "保存"}</button>
        </div>
      </div>
    </div>
  );
}

// ─── 关系编辑（M4.2.9：增删 StakeholderRelation，M4.2.8 图视图的编辑入口） ──

function RelationEditModal({
  projectId,
  cards,
  relation,
  onClose,
  onSaved,
}: {
  projectId: number;
  cards: StakeholderCard[];
  relation: StakeholderRelationType | null;  // null 不该出现（仅新建/删除，无编辑关系）
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [fromId, setFromId] = useState<number | "">(cards[0]?.id ?? "");
  const [toId, setToId] = useState<number | "">(cards[1]?.id ?? "");
  const [relType, setRelType] = useState<StakeholderRelationType>(relation ?? "reports_to");
  const [desc, setDesc] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (fromId === "" || toId === "") {
      toast.showToast("请选择源角色和目标角色", "error");
      return;
    }
    if (fromId === toId) {
      toast.showToast("源角色与目标角色不能相同", "error");
      return;
    }
    setSaving(true);
    try {
      await api.createStakeholderRelation(projectId, {
        from_card_id: fromId,
        to_card_id: toId,
        relation_type: relType,
        description: desc.trim() || null,
      });
      toast.showToast("已添加关系", "success");
      onSaved();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "添加失败", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div onClick={onClose} style={modalOverlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={{ ...modalCardStyle, width: 460 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <I.Network size={16} style={{ color: "var(--accent)" }} />
          <span style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)" }}>添加角色关系</span>
          <div style={{ flex: 1 }} />
          <button onClick={onClose} style={iconBtnStyle} title="关闭">✕</button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <label style={fieldLabelStyle}>
            <span style={miniLabelStyle}>源角色（from）</span>
            <select value={fromId} onChange={(e) => setFromId(e.target.value ? Number(e.target.value) : "")} style={selectStyle}>
              <option value="">（选择角色）</option>
              {cards.map((c) => <option key={c.id} value={c.id}>{c.name}{c.position ? ` · ${c.position}` : ""}</option>)}
            </select>
          </label>
          <label style={fieldLabelStyle}>
            <span style={miniLabelStyle}>目标角色（to）</span>
            <select value={toId} onChange={(e) => setToId(e.target.value ? Number(e.target.value) : "")} style={selectStyle}>
              <option value="">（选择角色）</option>
              {cards.map((c) => <option key={c.id} value={c.id}>{c.name}{c.position ? ` · ${c.position}` : ""}</option>)}
            </select>
          </label>
          <label style={fieldLabelStyle}>
            <span style={miniLabelStyle}>关系类型</span>
            <select value={relType} onChange={(e) => setRelType(e.target.value as StakeholderRelationType)} style={selectStyle}>
              {(Object.keys(RELATION_META) as StakeholderRelationType[]).map((rt) => (
                <option key={rt} value={rt}>{RELATION_META[rt].label}（{rt}）</option>
              ))}
            </select>
          </label>
          <label style={fieldLabelStyle}>
            <span style={miniLabelStyle}>关系说明（可选）</span>
            <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} placeholder="如：直接汇报、技术影响…" style={textareaStyle} />
          </label>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <button onClick={onClose} style={kbGhostBtnStyle}>取消</button>
          <button onClick={save} disabled={saving} style={saveBtnStyle(saving)}>{saving ? "保存中…" : "添加"}</button>
        </div>
      </div>
    </div>
  );
}

// ─── 话术库管理（M4.2.10：按角色类型 × 场景组织 + Markdown 编辑，§5.2） ──
// TalkScript：stakeholder_card_id（关联角色，可空）+ role_type + scenario + content（Markdown）
// + source_customer_quote + is_template（跨客户通用模板）。分组：通用模板 / 5 角色类型 / 未分类。

function TalkScriptsView({
  projectId,
  scripts,
  cards,
  onChanged,
}: {
  projectId: number;
  scripts: TalkScript[];
  cards: StakeholderCard[];
  onChanged: () => void;
}) {
  const toast = useToast();
  const [editor, setEditor] = useState<{ script: TalkScript | null } | null>(null);

  const handleDelete = async (s: TalkScript) => {
    if (!window.confirm(`确认删除话术${s.scenario ? `「${s.scenario}」` : ""}？`)) return;
    try {
      await api.deleteTalkScript(projectId, s.id);
      toast.showToast("已删除", "success");
      onChanged();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "删除失败", "error");
    }
  };

  // 分组：通用模板（is_template）+ 5 角色类型 + 未分类
  const groups: { key: string; label: string; list: TalkScript[] }[] = [
    { key: "template", label: "🌐 通用模板（跨客户通用）", list: scripts.filter((s) => s.is_template) },
    ...ROLE_TYPE_ORDER.map((rt) => ({
      key: rt,
      label: ROLE_TYPE_LABELS[rt],
      list: scripts.filter((s) => !s.is_template && s.role_type === rt),
    })),
    { key: "none", label: "未分类", list: scripts.filter((s) => !s.is_template && !s.role_type) },
  ].filter((g) => g.list.length > 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 960 }}>
      {/* 顶部：标题 + 新增 */}
      <Card style={{ padding: "14px 18px", display: "flex", alignItems: "center", gap: 12 }}>
        <I.MessageText size={16} style={{ color: "var(--accent)" }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, fontFamily: "var(--serif)" }}>话术库</div>
          <div style={{ fontSize: 11, color: "var(--ink-3)" }}>
            按角色类型 × 场景组织，共 {scripts.length} 条 · 支持 Markdown 富文本 · 项目内团队共享
          </div>
        </div>
        <button onClick={() => setEditor({ script: null })} style={primaryBtnStyle}>
          <I.Plus size={14} /> 新增话术
        </button>
      </Card>

      {scripts.length === 0 ? (
        <Card style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
          <I.MessageText size={32} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>尚无话术</div>
          <div style={{ maxWidth: 380, margin: "0 auto", lineHeight: 1.7 }}>
            点击「新增话术」沉淀针对角色 / 场景（初次拜访 / 方案汇报 / 技术交流 / 预算讨论等）的话术，或在对话中让 AI 基于角色卡生成。
          </div>
        </Card>
      ) : (
        groups.map((g) => (
          <Card key={g.key} style={{ padding: 0, overflow: "hidden" }}>
            <div style={kbCatHeaderStyle}>
              <I.Folder size={14} style={{ color: "var(--ink-3)" }} />
              <span style={{ fontWeight: 600, color: "var(--ink)", fontSize: 13 }}>{g.label}</span>
              <Tag tone="neutral">{g.list.length}</Tag>
            </div>
            <div>
              {g.list.map((s) => {
                const card = s.stakeholder_card_id != null ? cards.find((c) => c.id === s.stakeholder_card_id) : null;
                return (
                  <div key={s.id} style={kbEntryStyle}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
                      {s.scenario && <Tag tone="accent">{s.scenario}</Tag>}
                      {card && <Tag tone="info">关联：{card.name}</Tag>}
                      {s.source_customer_quote && <span title="源自客户原话" style={{ fontSize: 11, color: "var(--ink-4)" }}>📎 原话</span>}
                      <div style={{ flex: 1 }} />
                      <button onClick={() => setEditor({ script: s })} style={iconBtnStyle} title="编辑"><I.Edit size={13} /></button>
                      <button onClick={() => handleDelete(s)} style={iconBtnStyle} title="删除"><I.Trash size={13} /></button>
                    </div>
                    <MarkdownView text={s.content} />
                  </div>
                );
              })}
            </div>
          </Card>
        ))
      )}

      {editor && (
        <TalkScriptEditor
          projectId={projectId}
          script={editor.script}
          cards={cards}
          onClose={() => setEditor(null)}
          onSaved={() => {
            setEditor(null);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

/** 话术编辑器（新建/编辑，Markdown 编辑 + 预览） */
function TalkScriptEditor({
  projectId,
  script,
  cards,
  onClose,
  onSaved,
}: {
  projectId: number;
  script: TalkScript | null;
  cards: StakeholderCard[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const isEdit = script != null;
  const [cardId, setCardId] = useState<number | "">(script?.stakeholder_card_id ?? "");
  const [roleType, setRoleType] = useState<StakeholderRoleType | "">(script?.role_type ?? "");
  const [scenario, setScenario] = useState(script?.scenario ?? "");
  const [content, setContent] = useState(script?.content ?? "");
  const [quote, setQuote] = useState(script?.source_customer_quote ?? "");
  const [isTemplate, setIsTemplate] = useState(script?.is_template ?? false);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState(false);

  const save = async () => {
    if (!content.trim()) {
      toast.showToast("话术内容不能为空", "error");
      return;
    }
    setSaving(true);
    const payload: TalkScriptInput = {
      stakeholder_card_id: cardId === "" ? null : cardId,
      role_type: roleType || null,
      scenario: scenario.trim() || null,
      content,
      source_customer_quote: quote.trim() || null,
      is_template: isTemplate,
    };
    try {
      if (isEdit && script) {
        await api.updateTalkScript(projectId, script.id, payload);
      } else {
        await api.createTalkScript(projectId, payload);
      }
      toast.showToast(isEdit ? "已更新话术" : "已新增话术", "success");
      onSaved();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div onClick={onClose} style={modalOverlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={{ ...modalCardStyle, width: 640, maxHeight: "85vh", overflow: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <span style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)" }}>{isEdit ? "编辑话术" : "新增话术"}</span>
          <div style={{ flex: 1 }} />
          <button onClick={onClose} style={iconBtnStyle} title="关闭">✕</button>
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
          <label style={{ ...fieldLabelStyle, flex: "1 1 200px" }}>
            <span style={miniLabelStyle}>场景（如：初次拜访 / 方案汇报）</span>
            <input value={scenario} onChange={(e) => setScenario(e.target.value)} style={modalInputStyle} placeholder="方案汇报" />
          </label>
          <label style={{ ...fieldLabelStyle, flex: "1 1 150px" }}>
            <span style={miniLabelStyle}>角色类型</span>
            <select value={roleType} onChange={(e) => setRoleType(e.target.value as StakeholderRoleType | "")} style={selectStyle}>
              <option value="">（通用）</option>
              {ROLE_TYPE_ORDER.map((rt) => <option key={rt} value={rt}>{ROLE_TYPE_LABELS[rt]}</option>)}
            </select>
          </label>
          <label style={{ ...fieldLabelStyle, flex: "1 1 180px" }}>
            <span style={miniLabelStyle}>关联角色（可选）</span>
            <select value={cardId} onChange={(e) => setCardId(e.target.value ? Number(e.target.value) : "")} style={selectStyle}>
              <option value="">（不关联具体角色）</option>
              {cards.map((c) => <option key={c.id} value={c.id}>{c.name}{c.position ? ` · ${c.position}` : ""}</option>)}
            </select>
          </label>
        </div>

        <label style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 12, fontSize: 12, color: "var(--ink-2)", cursor: "pointer" }}>
          <input type="checkbox" checked={isTemplate} onChange={(e) => setIsTemplate(e.target.checked)} />
          标记为通用模板（跨客户通用，归入「通用模板」分组）
        </label>

        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span style={miniLabelStyle}>话术内容（支持 Markdown）</span>
          <div style={{ flex: 1 }} />
          <button onClick={() => setPreview((p) => !p)} style={linkBtnStyle}>{preview ? "✎ 编辑" : "👁 预览"}</button>
        </div>
        {preview ? (
          <div style={{ ...textareaStyle, minHeight: 200, overflow: "auto" }}>
            {content.trim() ? <MarkdownView text={content} /> : <span style={{ color: "var(--ink-4)" }}>（无内容）</span>}
          </div>
        ) : (
          <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={10} placeholder="支持 Markdown：## 要点 / - 列表 / **强调**" style={{ ...textareaStyle, minHeight: 200 }} />
        )}

        <label style={{ ...fieldLabelStyle, marginTop: 12 }}>
          <span style={miniLabelStyle}>源自客户原话（可选，记录话术依据）</span>
          <textarea value={quote} onChange={(e) => setQuote(e.target.value)} rows={2} style={textareaStyle} />
        </label>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <button onClick={onClose} style={kbGhostBtnStyle}>取消</button>
          <button onClick={save} disabled={saving} style={saveBtnStyle(saving)}>{saving ? "保存中…" : "保存"}</button>
        </div>
      </div>
    </div>
  );
}

// ─── 占位视图（后续 M4.2.x 替换） ──────────────────────────────

const PLACEHOLDER_TASK: Record<SubView, { task: string; desc: string }> = {
  cards: { task: "M4.2.6", desc: "5 子 Tab 详情卡（客观/主观/行为/态度历史/话术）+ 右侧关联面板" },
  org: { task: "M4.2.2", desc: "组织架构图（树形 + 汇报关系 + 关键岗位标注）" },
  decision: { task: "M4.2.3", desc: "决策链角色表（影响力条 + 综合评分 + 等级，按影响力排序）" },
  matrix: { task: "M4.2.4", desc: "角色-立场矩阵（横轴立场 × 纵轴影响力，气泡=参与度）" },
  timeline: { task: "M4.2.5", desc: "采购流程五阶段时间线 + 手动填写" },
  relations: { task: "M4.2.8", desc: "角色关系网络图（ReactFlow，4 种关系类型不同样式）" },
  knowledge: { task: "M4.2.7", desc: "知识库（角色识别 / 行为速查 / 入职指南 三板块）" },
  scripts: { task: "M4.2.10", desc: "话术库管理（角色类型 × 场景组织 + Markdown 编辑）" },
};

function PlaceholderView({ subView }: { subView: SubView }) {
  const info = PLACEHOLDER_TASK[subView];
  return (
    <Card style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
      <I.Sparkles size={32} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
      <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>
        {info.task} · 即将实现
      </div>
      <div style={{ maxWidth: 380, margin: "0 auto", lineHeight: 1.7 }}>{info.desc}</div>
    </Card>
  );
}

// ─── 通用小组件 ───────────────────────────────────────────────

function Field({ label, value, highlight }: { label: string; value: string | null | undefined; highlight?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color: highlight ? "var(--accent)" : "var(--ink-3)", marginBottom: 3 }}>
        {label}
      </div>
      <div style={{
        fontSize: 13,
        color: value ? "var(--ink-2)" : "var(--ink-4)",
        lineHeight: 1.6,
        whiteSpace: "pre-wrap",
        ...(highlight ? { background: "var(--accent-soft)", padding: "8px 12px", borderRadius: 6 } : {}),
      }}>
        {value || "（未填写）"}
      </div>
    </div>
  );
}

// ─── 工具函数 ─────────────────────────────────────────────────

function stanceColor(s: string): string {
  if (s === "支持") return "var(--success)";
  if (s === "反对") return "var(--danger)";
  if (s === "中立") return "var(--warn)";
  return "var(--ink-3)"; // 观望 / 未知
}

function gradeTone(g: string): "success" | "accent" | "warn" | "danger" | "neutral" {
  if (g === "Champion") return "success";
  if (g === "倾向我方") return "accent";
  if (g === "中立") return "warn";
  if (g === "反对") return "danger";
  return "neutral";
}

/** 综合评分 / 等级 → 颜色（数字按 §5.2 阈值，字符串按等级名） */
function gradeColor(v: string | number): string {
  if (typeof v === "number") {
    if (v >= 8) return "var(--success)";
    if (v >= 5) return "var(--accent)";
    if (v >= 3) return "var(--warn)";
    return "var(--danger)";
  }
  if (v === "Champion") return "var(--success)";
  if (v === "倾向我方") return "var(--accent)";
  if (v === "中立") return "var(--warn)";
  if (v === "反对") return "var(--danger)";
  return "var(--ink-3)";
}

// ─── 内联样式常量 ─────────────────────────────────────────────

const topBarStyle: React.CSSProperties = {
  padding: "12px 20px",
  borderBottom: "1px solid var(--line)",
  background: "var(--bg)",
  display: "flex",
  alignItems: "center",
  gap: 16,
  flexShrink: 0,
};

const tabBarStyle: React.CSSProperties = {
  padding: "0 20px",
  borderBottom: "1px solid var(--line)",
  background: "var(--bg)",
  display: "flex",
  gap: 0,
  flexShrink: 0,
};

const statStyle: React.CSSProperties = {
  fontSize: 12,
  color: "var(--ink-3)",
  whiteSpace: "nowrap",
};

const linkBtnStyle: React.CSSProperties = {
  all: "unset",
  cursor: "pointer",
  color: "var(--accent)",
  fontSize: 12,
  fontWeight: 500,
};

// ─── 角色卡详情子 Tab 样式（M4.2.6）──────────────────────────

const cardTabBarStyle: React.CSSProperties = {
  display: "flex",
  gap: 0,
  padding: "0 16px",
  borderBottom: "1px solid var(--line)",
  flexShrink: 0,
  position: "sticky",
  top: 0,
  background: "var(--surface)",
  zIndex: 1,
};

/** 子 Tab 按钮（激活态底线 + 强调色） */
function cardTabBtnStyle(active: boolean): React.CSSProperties {
  return {
    padding: "10px 12px",
    background: "transparent",
    border: "none",
    borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
    color: active ? "var(--accent)" : "var(--ink-2)",
    fontSize: 12,
    fontWeight: active ? 600 : 400,
    cursor: "pointer",
    fontFamily: "inherit",
    display: "flex",
    alignItems: "center",
    gap: 5,
    whiteSpace: "nowrap",
    marginBottom: -1,
  };
}

/** 子 Tab 数量角标 */
function cardTabBadgeStyle(active: boolean): React.CSSProperties {
  return {
    minWidth: 16,
    height: 16,
    padding: "0 4px",
    borderRadius: 999,
    background: active ? "var(--accent)" : "var(--bg-3)",
    color: active ? "var(--on-accent)" : "var(--ink-3)",
    fontSize: 10,
    fontWeight: 700,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  };
}

const tabIntroStyle: React.CSSProperties = {
  fontSize: 11,
  color: "var(--ink-3)",
  marginBottom: 14,
};

const stanceRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 6,
  flexWrap: "wrap",
  alignItems: "center",
};

const behaviorCardStyle: React.CSSProperties = {
  padding: 12,
  background: "var(--bg-2)",
  border: "1px solid var(--line)",
  borderRadius: 10,
};

const timelineDotStyle: React.CSSProperties = {
  width: 10,
  height: 10,
  borderRadius: 999,
  background: "var(--accent)",
  border: "2px solid var(--surface)",
  boxShadow: "var(--shadow-sm)",
  flexShrink: 0,
  marginTop: 4,
  zIndex: 1,
};

const sectionLabelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: "var(--ink-3)",
  textTransform: "uppercase",
  letterSpacing: 0.5,
  marginBottom: 8,
};

/** 话术卡（模板态用虚线边区分） */
function scriptCardStyle(template?: boolean): React.CSSProperties {
  return {
    padding: 12,
    background: template ? "transparent" : "var(--bg-2)",
    border: template ? "1px dashed var(--line)" : "1px solid var(--line)",
    borderRadius: 10,
  };
}

// ─── 右侧关联面板样式 ─────────────────────────────────────────

const relatedSectionStyle: React.CSSProperties = {
  padding: "14px 16px",
  borderBottom: "1px solid var(--line)",
};

const relatedHeaderStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  fontSize: 11,
  fontWeight: 700,
  color: "var(--ink-3)",
  textTransform: "uppercase",
  letterSpacing: 0.5,
  marginBottom: 10,
};

const relatedCountStyle: React.CSSProperties = {
  marginLeft: "auto",
  fontSize: 11,
  fontWeight: 700,
  color: "var(--accent)",
  background: "var(--accent-soft)",
  borderRadius: 999,
  padding: "1px 8px",
};

const relatedEmptyStyle: React.CSSProperties = {
  fontSize: 11,
  color: "var(--ink-4)",
};

const relatedItemStyle: React.CSSProperties = {
  padding: 10,
  background: "var(--bg-2)",
  borderRadius: 8,
};

/** 两行截断（webkit line clamp） */
const clamp2Style: React.CSSProperties = {
  fontSize: 11,
  color: "var(--ink-2)",
  marginTop: 3,
  lineHeight: 1.5,
  display: "-webkit-box",
  WebkitLineClamp: 2,
  WebkitBoxOrient: "vertical",
  overflow: "hidden",
};

// ─── 知识库视图样式（M4.2.7）──────────────────────────────────

const modalOverlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.35)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const modalCardStyle: React.CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--line)",
  borderRadius: 12,
  padding: 20,
  boxShadow: "0 8px 32px rgba(0,0,0,0.18)",
};

/** 知识库分类头（可折叠 + 新增按钮） */
const kbCatHeaderStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "12px 16px",
  borderBottom: "1px solid var(--line)",
  cursor: "pointer",
  userSelect: "none",
};

const kbCatDescStyle: React.CSSProperties = {
  fontSize: 11,
  color: "var(--ink-4)",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const kbAddBtnStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 3,
  padding: "4px 10px",
  fontSize: 11,
  fontWeight: 600,
  border: "1px solid var(--accent)",
  background: "var(--accent-soft)",
  color: "var(--accent)",
  borderRadius: 999,
  cursor: "pointer",
  fontFamily: "inherit",
  flexShrink: 0,
};

const kbEmptyStyle: React.CSSProperties = {
  padding: "24px 20px",
  textAlign: "center",
  color: "var(--ink-3)",
  fontSize: 12,
};

const kbEntryStyle: React.CSSProperties = {
  padding: "14px 18px",
  borderBottom: "1px solid var(--line)",
};

/** 图标按钮（编辑/删除/关闭） */
const iconBtnStyle: React.CSSProperties = {
  all: "unset",
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: 24,
  height: 24,
  borderRadius: 6,
  color: "var(--ink-3)",
  fontSize: 13,
};

/** 次要按钮（取消） */
const kbGhostBtnStyle: React.CSSProperties = {
  padding: "7px 16px",
  fontSize: 12,
  fontWeight: 600,
  border: "1px solid var(--line)",
  background: "transparent",
  color: "var(--ink-2)",
  borderRadius: 8,
  cursor: "pointer",
  fontFamily: "inherit",
};

/** 主要按钮（新增/确认） */
const primaryBtnStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 5,
  padding: "8px 16px",
  fontSize: 13,
  fontWeight: 600,
  border: "none",
  background: "var(--accent)",
  color: "var(--on-accent)",
  borderRadius: 8,
  cursor: "pointer",
  fontFamily: "inherit",
};

/** 角色列表头（标题 + 新增按钮） */
const listHeaderStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "10px 12px",
  borderBottom: "1px solid var(--line)",
  fontSize: 11,
  fontWeight: 700,
  color: "var(--ink-3)",
  textTransform: "uppercase",
  letterSpacing: 0.6,
};

const listAddBtnStyle: React.CSSProperties = {
  all: "unset",
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: 22,
  height: 22,
  borderRadius: 6,
  color: "var(--accent)",
  border: "1px solid var(--accent)",
};

// ─── 角色卡编辑器样式（M4.2.9）────────────────────────────────

const modalInputStyle: React.CSSProperties = {
  padding: "6px 9px",
  fontSize: 12,
  border: "1px solid var(--line)",
  borderRadius: 6,
  fontFamily: "inherit",
  color: "var(--ink-2)",
  background: "var(--surface)",
  width: "100%",
};

/** 可折叠分区标题按钮 */
const sectionToggleStyle: React.CSSProperties = {
  all: "unset",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: 5,
  fontSize: 12,
  fontWeight: 700,
  color: "var(--ink-2)",
  padding: "4px 0",
};

/** 数组条目容器（行为/态度变化） */
const arrayItemStyle: React.CSSProperties = {
  padding: 10,
  background: "var(--bg-2)",
  border: "1px solid var(--line)",
  borderRadius: 8,
  display: "flex",
  flexDirection: "column",
  gap: 6,
};

/** 添加行按钮（虚线） */
const addRowBtnStyle: React.CSSProperties = {
  all: "unset",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 4,
  padding: "7px",
  fontSize: 12,
  fontWeight: 500,
  color: "var(--accent)",
  border: "1px dashed var(--accent)",
  borderRadius: 8,
  background: "var(--accent-soft)",
};

// ─── 采购时间线视图样式（M4.2.5）──────────────────────────────

/** 状态切换胶囊按钮（激活态着色） */
function statusBtnStyle(active: boolean, color: string): React.CSSProperties {
  return {
    padding: "3px 9px",
    fontSize: 11,
    fontWeight: active ? 600 : 400,
    border: `1px solid ${active ? color : "var(--line)"}`,
    background: active ? color + "22" : "transparent",
    color: active ? color : "var(--ink-3)",
    borderRadius: 999,
    cursor: "pointer",
    fontFamily: "inherit",
  };
}

const fieldLabelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 3,
};

const miniLabelStyle: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: "var(--ink-3)",
};

const dateInputStyle: React.CSSProperties = {
  padding: "5px 8px",
  fontSize: 12,
  border: "1px solid var(--line)",
  borderRadius: 6,
  fontFamily: "inherit",
  color: "var(--ink-2)",
  background: "var(--surface)",
};

const selectStyle: React.CSSProperties = {
  ...dateInputStyle,
  cursor: "pointer",
};

const textareaStyle: React.CSSProperties = {
  width: "100%",
  padding: "6px 8px",
  fontSize: 12,
  border: "1px solid var(--line)",
  borderRadius: 6,
  fontFamily: "inherit",
  color: "var(--ink-2)",
  background: "var(--surface)",
  resize: "vertical",
};

/** 保存按钮（禁用态降低不透明度） */
function saveBtnStyle(disabled: boolean): React.CSSProperties {
  return {
    padding: "7px 16px",
    fontSize: 12,
    fontWeight: 600,
    border: "none",
    borderRadius: 8,
    background: "var(--accent)",
    color: "var(--on-accent)",
    fontFamily: "inherit",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.5 : 1,
  };
}
