// 营销地图页面（M4.2 / §2.4 §5.2）
// 替换 V1.0 原型：改为消费真实后端 /api/projects/{id}/{stakeholder-cards,...}。
// 顶部项目选择器由全局 Topbar（M1.3.9/M4.4.1）驱动，本页接收 project prop。
// 本提交覆盖 M4.2.1 页面骨架（项目上下文栏 + 统计栏 + 8 视图切换 + 数据加载）
// + 角色卡视图种子（左列表 + 右只读详情，作为数据主干，M4.2.6 将升级为 5 子 Tab）。
// 组织架构/决策链/立场矩阵/采购时间线/关系网络/知识库/话术库见后续 M4.2.x 任务。
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { Card, Spinner, Tag, useToast } from "@/components/ui";
import MarkdownView from "@/components/workspace/MarkdownView";
import { I } from "@/icons";
import type {
  BehaviorEntry,
  KnowledgeBase,
  KnowledgeCategory,
  Project,
  ProcurementStage,
  ProcurementStageStatus,
  StakeholderCard,
  StanceChangeEntry,
  StakeholderRoleType,
  StanceLevel,
  TalkScript,
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
}

// ─── 页面组件 ─────────────────────────────────────────────────

export default function MarketingMapPage({ project }: Props) {
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
        ) : (
          <PlaceholderView subView={subView} />
        )}
      </div>
    </div>
  );
}

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
  onChanged: _onChanged,
}: {
  projectId: number;
  cards: StakeholderCard[];
  scripts: TalkScript[];
  selectedCard: StakeholderCard | null;
  onSelect: (id: number) => void;
  onChanged: () => void;
}) {
  const [tab, setTab] = useState<CardTab>("objective");
  const [visits, setVisits] = useState<VisitRecord[]>([]);
  const [visitsLoading, setVisitsLoading] = useState(false);

  // 空项目无角色卡
  if (cards.length === 0) {
    return (
      <Card style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
        <I.UserCheck size={32} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
        <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>尚未建立角色卡</div>
        <div style={{ maxWidth: 380, margin: "0 auto", lineHeight: 1.7 }}>
          前往「对话」页对项目 Agent 说「生成角色卡」或使用 WF12 chip，AI 会基于拜访证据产出角色卡草稿，采纳后此处可见；也可在 M4.2.9 上线后手动新增。
        </div>
      </Card>
    );
  }

  // 默认选中第一个
  const current = selectedCard ?? cards[0];
  const cardScripts = scripts.filter((s) => s.stakeholder_card_id === current.id);
  // 同角色类型的通用模板话术（跨客户通用，stakeholder_card_id 为 null 且 role_type 匹配）
  const templateScripts = scripts.filter(
    (s) => s.stakeholder_card_id == null && s.role_type === current.role_type,
  );

  // 切换角色：重置子 Tab + 拉取关联拜访记录（card_id 过滤 related_card_ids / participants_client）
  useEffect(() => {
    setTab("objective");
    let cancelled = false;
    setVisitsLoading(true);
    setVisits([]);
    api
      .listVisitRecords(projectId, { card_id: current.id })
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
  }, [current.id, projectId]);

  const behaviors = current.behaviors ?? [];
  const stanceLog = current.stance_change_log ?? [];

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
        <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--line)", fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.6 }}>
          角色列表（{cards.length}）
        </div>
        {cards.map((c) => {
          const rt = c.role_type;
          const stance = c.subjective_layer?.stance;
          const isSel = current.id === c.id;
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
        <CardDetailHeader card={current} />
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
          {tab === "objective" && <ObjectiveTab card={current} />}
          {tab === "subjective" && <SubjectiveTab card={current} />}
          {tab === "behaviors" && <BehaviorsTab behaviors={behaviors} />}
          {tab === "stance" && <StanceHistoryTab log={stanceLog} />}
          {tab === "scripts" && (
            <ScriptsTab
              cardName={current.name}
              roleType={current.role_type}
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

/** 角色卡详情头部：头像 + 基本信息 + 标签 */
function CardDetailHeader({ card }: { card: StakeholderCard }) {
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
        <div style={{ display: "flex", gap: 6 }}>
          {rt && <Tag tone="accent">{ROLE_TYPE_LABELS[rt]}</Tag>}
          {card.decision_power && <Tag tone="info">{card.decision_power}</Tag>}
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
