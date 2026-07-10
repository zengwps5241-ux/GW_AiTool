// 营销地图页面（M4.2 / §2.4 §5.2）
// 替换 V1.0 原型：改为消费真实后端 /api/projects/{id}/{stakeholder-cards,...}。
// 顶部项目选择器由全局 Topbar（M1.3.9/M4.4.1）驱动，本页接收 project prop。
// 本提交覆盖 M4.2.1 页面骨架（项目上下文栏 + 统计栏 + 8 视图切换 + 数据加载）
// + 角色卡视图种子（左列表 + 右只读详情，作为数据主干，M4.2.6 将升级为 5 子 Tab）。
// 组织架构/决策链/立场矩阵/采购时间线/关系网络/知识库/话术库见后续 M4.2.x 任务。
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { Card, Spinner, Tag, useToast } from "@/components/ui";
import { I } from "@/icons";
import type {
  Project,
  StakeholderCard,
  StakeholderRoleType,
  StanceLevel,
  TalkScript,
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
        ) : (
          <PlaceholderView subView={subView} />
        )}
      </div>
    </div>
  );
}

// ─── 角色卡视图（M4.2.1 种子：左列表 + 右只读详情；M4.2.6 升级为 5 子 Tab） ──

function CardsView({
  cards,
  scripts,
  selectedCard,
  onSelect,
  onChanged: _onChanged,
}: {
  cards: StakeholderCard[];
  scripts: TalkScript[];
  selectedCard: StakeholderCard | null;
  onSelect: (id: number) => void;
  onChanged: () => void;
}) {
  // 空项目无角色卡
  if (cards.length === 0) {
    return (
      <Card style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
        <I.UserCheck size={32} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
        <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>尚未建立角色卡</div>
        <div style={{ maxWidth: 380, margin: "0 auto", lineHeight: 1.7 }}>
          前往「对话」页对项目 Agent 说「生成角色卡」或使用 WF08 chip，AI 会基于拜访证据产出角色卡草稿，采纳后此处可见；也可在 M4.2.9 上线后手动新增。
        </div>
      </Card>
    );
  }

  // 默认选中第一个
  const current = selectedCard ?? cards[0];
  const cardScripts = scripts.filter((s) => s.stakeholder_card_id === current.id);

  return (
    <div style={{ display: "flex", gap: 20, height: "100%" }}>
      {/* 左：角色列表 */}
      <Card style={{ width: 240, padding: 0, flexShrink: 0, overflow: "auto" }}>
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
                fontSize: 14, fontWeight: 700, color: "#FFFCF5",
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

      {/* 右：角色卡只读详情（种子，M4.2.6 将扩展为 5 子 Tab） */}
      <Card style={{ flex: 1, padding: 0, overflow: "auto" }}>
        <CardDetailHeader card={current} />
        <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14, fontSize: 13 }}>
          {/* 三维评分 + 综合 */}
          <ScoreRow card={current} />
          <Field label="显性 KPI" value={current.subjective_layer?.explicitKPI} />
          <Field label="隐性个人诉求" value={current.subjective_layer?.personalMotivation} />
          <Field label="对我方方案的态度" value={current.subjective_layer?.attitudeToUs} />
          <Field label="核心顾虑" value={current.subjective_layer?.coreConcerns} highlight />
          <Field label="影响杠杆" value={current.subjective_layer?.leverage} highlight />
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <Field label="与我方历史合作" value={current.objective_layer?.historyWithUs} />
            <div style={{ marginTop: 10 }}>
              <Field label="与竞品历史合作" value={current.objective_layer?.historyWithCompetitor} />
            </div>
          </div>
          {/* 行为分析条数 + 态度变化条数 + 话术条数（M4.2.6 展开） */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <Tag tone="info">行为分析 {current.behaviors?.length ?? 0}</Tag>
            <Tag tone="accent">态度变化 {current.stance_change_log?.length ?? 0}</Tag>
            <Tag tone="success">话术 {cardScripts.length}</Tag>
          </div>
        </div>
      </Card>
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
        fontSize: 20, fontWeight: 700, color: "#FFFCF5",
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
            fontSize: 13, fontWeight: 700, color: "#FFFCF5",
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
